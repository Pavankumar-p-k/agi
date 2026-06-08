from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from croniter import croniter
    _HAS_CRONITER = True
except ImportError:
    _HAS_CRONITER = False

logger = logging.getLogger("jarvis.cron")

DB_PATH = Path.home() / ".jarvis" / "cron.db"


class Scheduler:
    """Persistent job scheduler with interval and cron support."""

    def __init__(self):
        self._init_db()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def _init_db(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    schedule TEXT,
                    action TEXT,
                    params TEXT,
                    enabled INTEGER DEFAULT 1,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    created_at TIMESTAMP
                )
            """)
            conn.commit()

    def add(self, job_id: str, schedule: str, action: str,
            params: Optional[Dict] = None, enabled: bool = True) -> Dict:
        now = datetime.now()
        next_run = self._next_run(schedule, now)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO jobs (id, schedule, action, params, enabled, next_run, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    schedule=excluded.schedule, action=excluded.action,
                    params=excluded.params, enabled=excluded.enabled,
                    next_run=excluded.next_run
            """, (job_id, schedule, action, json.dumps(params or {}),
                  1 if enabled else 0, next_run.isoformat() if next_run else None,
                  now.isoformat()))
            conn.commit()
        logger.info("Scheduled job '%s': %s", job_id, schedule)
        return {"id": job_id, "next_run": next_run.isoformat() if next_run else None}

    def _next_run(self, schedule: str, after: datetime) -> Optional[datetime]:
        s = schedule.strip().lower()
        try:
            if s.endswith("s"):
                return after + timedelta(seconds=int(s[:-1]))
            if s.endswith("m"):
                return after + timedelta(minutes=int(s[:-1]))
            if s.endswith("h"):
                return after + timedelta(hours=int(s[:-1]))
            if s.endswith("d"):
                return after + timedelta(days=int(s[:-1]))
        except (ValueError, AttributeError):
            pass
        if _HAS_CRONITER:
            try:
                return croniter(schedule, after).get_next(datetime)
            except Exception as _e:
                logger.debug("cron parse schedule failed: %s", _e)
        logger.warning("Cannot parse schedule: %s", schedule)
        return None

    async def _execute(self, job_id: str, action: str, params: Dict):
        logger.info("Executing job '%s': %s", job_id, action)
        try:
            if action == "backup":
                from core.backup import backup_manager
                await backup_manager.create_backup()
            elif action == "remind":
                from core.commitments import commitment_store
                upcoming = commitment_store.upcoming(hours=1)
                if upcoming:
                    logger.info("Upcoming commitments: %d", len(upcoming))
            now = datetime.now()
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute("SELECT schedule FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if row:
                    next_run = self._next_run(row[0], now)
                    conn.execute(
                        "UPDATE jobs SET last_run = ?, next_run = ? WHERE id = ?",
                        (now.isoformat(), next_run.isoformat() if next_run else None, job_id),
                    )
                    conn.commit()
        except Exception as e:
            logger.exception("Job '%s' failed: %s", job_id, e)

    async def _loop(self):
        while self._running:
            try:
                now = datetime.now().isoformat()
                with sqlite3.connect(DB_PATH) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT * FROM jobs WHERE enabled = 1 AND next_run IS NOT NULL AND next_run <= ?",
                        (now,),
                    ).fetchall()
                for row in rows:
                    params = json.loads(row["params"])
                    asyncio.create_task(self._execute(row["id"], row["action"], params))
            except Exception as e:
                logger.error("Scheduler loop error: %s", e)
            await asyncio.sleep(60)

    def list_jobs(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def remove_job(self, job_id: str) -> bool:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            conn.commit()
            return cur.rowcount > 0

    async def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("Scheduler started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Scheduler stopped")


scheduler = Scheduler()

__all__ = ["scheduler", "Scheduler"]
