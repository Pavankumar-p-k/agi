"""Browser procedural memory (uses the existing memory/ infrastructure).

Websites change, so procedures are stored with verification/expiry metadata
instead of being treated as permanent truth:

    site ("github.com"), task ("create_repository"),
    steps (ordered procedure with selectors),
    required_conditions, failure_modes, last_verified, confidence.

Storage: a `browser_procedures` table inside the SAME sqlite database the rest
of memory/ uses (data/memory.db, WAL, thread-locked).  Each successful run is
also mirrored into the memory facade's episodic store so cross-specialist
recall (memory.memory_facade) can find browser experience.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

DEFAULT_TTL_DAYS = 14.0
BASE_CONFIDENCE = 0.5
SUCCESS_BOOST = 0.1
FAILURE_PENALTY = 0.15
MAX_CONFIDENCE = 0.95
MIN_CONFIDENCE = 0.1


def _get_db_path() -> str:
    os.makedirs(_DB_DIR, exist_ok=True)
    return os.path.join(_DB_DIR, "memory.db")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BrowserProceduralMemory:
    def __init__(self, db_path: str | None = None, ttl_days: float = DEFAULT_TTL_DAYS) -> None:
        self._db_path = db_path or _get_db_path()
        self.ttl_days = float(ttl_days)
        self._lock = threading.Lock()
        from pathlib import Path
        parent = Path(self._db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------ #
    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS browser_procedures (
                    id TEXT PRIMARY KEY,
                    site TEXT NOT NULL,
                    task TEXT NOT NULL,
                    steps TEXT NOT NULL DEFAULT '[]',
                    selectors TEXT NOT NULL DEFAULT '{}',
                    required_conditions TEXT NOT NULL DEFAULT '[]',
                    failure_modes TEXT NOT NULL DEFAULT '[]',
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    last_verified TEXT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(site, task, user_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_browser_proc_site ON browser_procedures(site)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_browser_proc_task ON browser_procedures(task)")
            conn.commit()
            conn.close()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_site(url_or_site: str) -> str:
        from urllib.parse import urlparse
        value = str(url_or_site or "").strip().lower()
        if not value:
            return ""
        if "://" not in value:
            value = "https://" + value
        host = urlparse(value).netloc.lower().removeprefix("www.")
        return host or value

    @staticmethod
    def _normalize_task(task: str) -> str:
        return re_sub_task(str(task or "").strip().lower())

    def record(
        self,
        site: str,
        task: str,
        steps: list[dict[str, Any]],
        *,
        success: bool = True,
        selectors: dict[str, str] | None = None,
        required_conditions: list[str] | None = None,
        failure_mode: str | None = None,
        user_id: str = "default",
    ) -> str:
        """Record a procedure run.  Successful runs update steps/selectors and
        refresh last_verified + confidence; failures only adjust confidence and
        append the failure mode."""
        site = self._normalize_site(site)
        task = self._normalize_task(task)
        if not site or not task:
            return ""
        now = _now().isoformat()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM browser_procedures WHERE site = ? AND task = ? AND user_id = ?",
                (site, task, user_id),
            ).fetchone()
            if row is None:
                proc_id = str(uuid.uuid4())
                confidence = BASE_CONFIDENCE if success else max(MIN_CONFIDENCE, BASE_CONFIDENCE - FAILURE_PENALTY)
                conn.execute(
                    """INSERT INTO browser_procedures
                       (id, site, task, steps, selectors, required_conditions, failure_modes,
                        success_count, failure_count, confidence, last_verified, user_id,
                        updated_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        proc_id, site, task,
                        json.dumps(steps if success else [], default=str),
                        json.dumps(selectors or {}, default=str),
                        json.dumps(required_conditions or []),
                        json.dumps([failure_mode] if failure_mode else []),
                        1 if success else 0,
                        0 if success else 1,
                        round(confidence, 3),
                        now if success else None,
                        user_id, now, now,
                    ),
                )
                conn.commit()
                conn.close()
                self._mirror_episode(site, task, steps, success, failure_mode)
                return proc_id

            data = dict(row)
            success_count = int(data["success_count"]) + (1 if success else 0)
            failure_count = int(data["failure_count"]) + (0 if success else 1)
            confidence = float(data["confidence"])
            confidence = min(MAX_CONFIDENCE, confidence + SUCCESS_BOOST) if success else max(MIN_CONFIDENCE, confidence - FAILURE_PENALTY)
            failure_modes = json.loads(data.get("failure_modes") or "[]")
            if failure_mode:
                failure_modes = (failure_modes + [failure_mode])[-10:]
            conn.execute(
                """UPDATE browser_procedures
                   SET steps = ?, selectors = ?, required_conditions = ?, failure_modes = ?,
                       success_count = ?, failure_count = ?, confidence = ?, last_verified = ?,
                       updated_at = ?
                   WHERE id = ?""",
                (
                    json.dumps(steps if success else json.loads(data.get("steps") or "[]"), default=str),
                    json.dumps(selectors or json.loads(data.get("selectors") or "{}"), default=str),
                    json.dumps(required_conditions or json.loads(data.get("required_conditions") or "[]")),
                    json.dumps(failure_modes),
                    success_count, failure_count, round(confidence, 3),
                    now if success else data["last_verified"],
                    now, data["id"],
                ),
            )
            conn.commit()
            conn.close()
            self._mirror_episode(site, task, steps, success, failure_mode)
            return str(data["id"])

    def _mirror_episode(self, site: str, task: str, steps: list[dict[str, Any]], success: bool, failure_mode: str | None) -> None:
        try:
            from memory.memory_facade import memory
            memory.store_episode(
                goal=f"browser procedure [{site}] {task}",
                actions=steps,
                context={"site": site, "task": task},
                result={"success": success, "failure_mode": failure_mode or ""},
                episode_type="browser_procedure",
                tags=["browser", site, task],
            )
        except Exception as exc:  # memory facade is optional
            logger.debug("procedural memory mirror failed: %s", exc)

    # ------------------------------------------------------------------ #
    def get(self, site: str, task: str, user_id: str = "default") -> dict[str, Any] | None:
        site = self._normalize_site(site)
        task = self._normalize_task(task)
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM browser_procedures WHERE site = ? AND task = ? AND user_id = ?",
                (site, task, user_id),
            ).fetchone()
            conn.close()
        return self._with_freshness(dict(row)) if row else None

    def find(self, query: str, user_id: str = "default", limit: int = 5) -> list[dict[str, Any]]:
        """Lookup procedures by substring match on site/task (used to seed new runs)."""
        needle = str(query or "").strip().lower()
        if not needle:
            return []
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM browser_procedures
                   WHERE user_id = ? AND (site LIKE ? OR task LIKE ?)
                   ORDER BY confidence DESC, last_verified DESC LIMIT ?""",
                (user_id, f"%{needle}%", f"%{needle}%", limit),
            ).fetchall()
            conn.close()
        return [self._with_freshness(dict(r)) for r in rows]

    def all(self, user_id: str = "default") -> list[dict[str, Any]]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM browser_procedures WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
            conn.close()
        return [self._with_freshness(dict(r)) for r in rows]

    # ------------------------------------------------------------------ #
    def _with_freshness(self, data: dict[str, Any]) -> dict[str, Any]:
        for key in ("steps", "selectors", "required_conditions", "failure_modes"):
            try:
                data[key] = json.loads(data.get(key) or ("{}" if key == "selectors" else "[]"))
            except (json.JSONDecodeError, TypeError):
                data[key] = {} if key == "selectors" else []
        last_verified = data.get("last_verified")
        stale = True
        age_days: float | None = None
        if last_verified:
            try:
                verified_at = datetime.fromisoformat(str(last_verified))
                age_days = (_now() - verified_at).total_seconds() / 86400.0
                stale = age_days > self.ttl_days
            except (ValueError, TypeError):
                stale = True
        total = int(data.get("success_count", 0)) + int(data.get("failure_count", 0))
        data["stale"] = stale
        data["age_days"] = round(age_days, 2) if age_days is not None else None
        data["expires_after_days"] = self.ttl_days
        data["success_rate"] = round(int(data.get("success_count", 0)) / total, 3) if total else None
        data["usable"] = bool(data.get("steps")) and not stale and float(data.get("confidence", 0)) >= 0.5
        return data

    def summary(self, user_id: str = "default") -> dict[str, Any]:
        procs = self.all(user_id)
        return {
            "procedures": len(procs),
            "fresh": sum(1 for p in procs if not p["stale"]),
            "stale": sum(1 for p in procs if p["stale"]),
            "usable": sum(1 for p in procs if p["usable"]),
        }


def re_sub_task(task: str) -> str:
    """Normalize a task label: collapse whitespace, keep underscores."""
    import re
    return re.sub(r"\s+", "_", task.strip().lower()).strip("_")


singleton_lock = threading.Lock()
_singleton: BrowserProceduralMemory | None = None


def browser_procedural_memory() -> BrowserProceduralMemory:
    global _singleton
    with singleton_lock:
        if _singleton is None:
            _singleton = BrowserProceduralMemory()
        return _singleton
