# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""core/self_healing.py
Self-healing framework + continuous learning loop for JARVIS.
3-layer: detection -> diagnosis -> recovery.
Continuous learning: accept/reject feedback -> auto-improve prompts.

Primary storage: ``health_state`` and ``learning_state`` tables in ``system.db``,
with JSON fallback for backward compatibility.

Deprecated JSON paths: ``data/health.json``, ``data/learnings.json``
"""

import json
import logging
import os
import sqlite3
import time
from datetime import UTC, datetime
from threading import Lock

from core.storage.registry import SYSTEM_DB, ensure_db_dir

logger = logging.getLogger("self_healing")

_HEALTH_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "health.json")
_LEARNINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "learnings.json")
_FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "feedback.json")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS health_state (
    key  TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_state (
    key  TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
"""


# â”€â”€ Self-Healing Framework â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class HealthRecord:
    def __init__(self):
        self.checks: dict[str, dict] = {}
        self.failures: list[dict] = []
        self.recoveries: list[dict] = []
        self.last_check_time: float = 0

    def to_dict(self) -> dict:
        return {
            "checks": self.checks,
            "failures": self.failures[-20:],
            "recoveries": self.recoveries[-20:],
            "last_check_time": self.last_check_time,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HealthRecord":
        r = cls()
        r.checks = data.get("checks", {})
        r.failures = data.get("failures", [])
        r.recoveries = data.get("recoveries", [])
        r.last_check_time = data.get("last_check_time", 0)
        return r


class SelfHealing:
    """3-layer self-healing: detection -> diagnosis -> recovery.

    Primary storage: ``health_state`` table in ``system.db``.
    Fallback: ``data/health.json`` (auto-migrated on init).
    """

    def __init__(self):
        self.record = HealthRecord()
        self._lock = Lock()
        ensure_db_dir(SYSTEM_DB)
        self._init_schema()
        self._load()
        self._recovery_handlers: dict[str, callable] = {}

    def _init_schema(self) -> None:
        try:
            with sqlite3.connect(SYSTEM_DB) as conn:
                conn.executescript(_SCHEMA)
                conn.commit()
        except Exception as e:
            logger.debug("[SELF-HEAL] Schema init error: %s", e)

    def register_recovery(self, component: str, handler: callable):
        self._recovery_handlers[component] = handler

    # Layer 1: Detection
    async def check(self, component: str, healthy: bool, detail: str = "") -> bool:
        now = time.time()
        self.record.last_check_time = now
        prev = self.record.checks.get(component, {})
        prev_healthy = prev.get("healthy", True)

        self.record.checks[component] = {
            "healthy": healthy,
            "detail": detail,
            "checked_at": now,
            "checked_at_iso": datetime.now(UTC).isoformat(),
        }

        if not healthy and prev_healthy:
            failure = {
                "component": component,
                "detail": detail,
                "detected_at": now,
                "detected_at_iso": datetime.now(UTC).isoformat(),
            }
            self.record.failures.append(failure)
            logger.warning(f"[SELF-HEAL] Detection: {component} failed â€” {detail}")
            # Layer 2 + 3: Diagnose + Recover
            await self._heal(component, detail)
            return False

        if healthy and not prev_healthy:
            self.record.recoveries.append({
                "component": component,
                "detail": "auto-recovered",
                "recovered_at": now,
                "recovered_at_iso": datetime.now(UTC).isoformat(),
            })
            logger.info(f"[SELF-HEAL] {component} recovered")
        return healthy

    # Layer 2 + 3: Diagnosis + Recovery
    async def _heal(self, component: str, detail: str):
        diagnosis = self._diagnose(component, detail)
        logger.info(f"[SELF-HEAL] Diagnosis: {component} â€” {diagnosis}")
        if component in self._recovery_handlers:
            try:
                result = await self._recovery_handlers[component](diagnosis)
                if result:
                    self.record.checks[component] = {
                        "healthy": True,
                        "detail": f"recovered: {result}",
                        "checked_at": time.time(),
                        "checked_at_iso": datetime.now(UTC).isoformat(),
                    }
                    self.record.recoveries.append({
                        "component": component,
                        "detail": result,
                        "recovered_at": time.time(),
                        "recovered_at_iso": datetime.now(UTC).isoformat(),
                    })
                    logger.info(f"[SELF-HEAL] Recovery: {component} â€” {result}")
            except Exception as e:
                logger.error(f"[SELF-HEAL] Recovery failed for {component}: {e}")

    def _diagnose(self, component: str, detail: str) -> str:
        detail_lower = detail.lower()
        if "timeout" in detail_lower or "timed out" in detail_lower:
            return "timeout_error"
        if "connection" in detail_lower or "refused" in detail_lower or "eof" in detail_lower:
            return "connection_error"
        if "memory" in detail_lower or "vram" in detail_lower:
            return "memory_error"
        if "model" in detail_lower and "not found" in detail_lower:
            return "model_not_found"
        if "import" in detail_lower or "module" in detail_lower:
            return "missing_dependency"
        return "unknown_error"

    def get_status(self) -> dict:
        return {
            "healthy": all(c.get("healthy", True) for c in self.record.checks.values()),
            "checks": self.record.checks,
            "recent_failures": self.record.failures[-5:],
            "recent_recoveries": self.record.recoveries[-5:],
        }

    def _load(self):
        """Load health record from SQLite, fall back to JSON."""
        with self._lock:
            try:
                with sqlite3.connect(SYSTEM_DB) as conn:
                    row = conn.execute(
                        "SELECT data FROM health_state WHERE key = 'default'"
                    ).fetchone()
                    if row:
                        self.record = HealthRecord.from_dict(json.loads(row[0]))
                        return
            except Exception as e:
                logger.debug("[SELF-HEAL] SQLite load error: %s", e)

            # Fallback: JSON file
            try:
                if os.path.isfile(_HEALTH_FILE):
                    with open(_HEALTH_FILE) as f:
                        self.record = HealthRecord.from_dict(json.load(f))
                    self.save()  # Migrate to SQLite
            except Exception as e:
                logger.debug("[SELF-HEAL] JSON load error: %s", e)

    def save(self):
        """Persist health record to SQLite (+ JSON fallback)."""
        with self._lock:
            data = json.dumps(self.record.to_dict(), default=str)
            try:
                with sqlite3.connect(SYSTEM_DB) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO health_state (key, data) VALUES ('default', ?)",
                        (data,),
                    )
                    conn.commit()
            except Exception as e:
                logger.debug("[SELF-HEAL] SQLite save error, falling back to JSON: %s", e)
                try:
                    os.makedirs(os.path.dirname(_HEALTH_FILE), exist_ok=True)
                    with open(_HEALTH_FILE, "w") as f:
                        json.dump(self.record.to_dict(), f, indent=2)
                except Exception as e2:
                    logger.debug("[SELF-HEAL] JSON save error: %s", e2)

    async def heal_ollama(self, detail: str = ""):
        await self._heal("ollama", detail)

    async def heal_search(self, detail: str = ""):
        await self._heal("search", detail)


# â”€â”€ Continuous Learning Loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class LearningLoop:
    """Records accepts/rejects from user feedback to auto-improve prompts and examples.

    Primary storage: ``learning_state`` table in ``system.db``.
    Fallback: ``data/learnings.json`` (auto-migrated on init).
    """

    def __init__(self):
        self.learnings: list[dict] = []
        self.rules: list[str] = []
        self.examples: list[dict] = []
        self._lock = Lock()
        ensure_db_dir(SYSTEM_DB)
        self._init_schema()
        self._load()

    def _init_schema(self) -> None:
        try:
            with sqlite3.connect(SYSTEM_DB) as conn:
                conn.executescript(_SCHEMA)
                conn.commit()
        except Exception as e:
            logger.debug("[LEARN] Schema init error: %s", e)

    def record_feedback(self, message: str, response: str, accepted: bool, reason: str = ""):
        entry = {
            "message": message,
            "response": response,
            "accepted": accepted,
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.learnings.append(entry)
        self._extract_rule(entry)
        self._update_examples(entry)
        self.save()
        logger.info(f"[LEARN] Feedback recorded: {'accepted' if accepted else 'rejected'} â€” {reason[:50]}")

    def _extract_rule(self, entry: dict):
        if not entry["accepted"] and entry["reason"]:
            reason = entry["reason"].lower()
            if "too formal" in reason or "wrong tone" in reason:
                rule = "Use casual conversational tone. Avoid corporate jargon."
                if rule not in self.rules:
                    self.rules.append(rule)
            elif "wrong" in reason or "incorrect" in reason:
                rule = f"Verify facts before responding. Avoid speculating on {entry['message'][:30]}."
                if rule not in self.rules:
                    self.rules.append(rule)
            elif "too long" in reason or "too verbose" in reason:
                rule = "Keep responses concise. Use 1-3 paragraphs maximum."
                if rule not in self.rules:
                    self.rules.append(rule)
            elif "not helpful" in reason or "useless" in reason:
                rule = "Provide actionable answers. If the user asks to DO something, do it rather than explain."
                if rule not in self.rules:
                    self.rules.append(rule)

    def _update_examples(self, entry: dict):
        if entry["accepted"]:
            self.examples.append({
                "input": entry["message"],
                "output": entry["response"],
                "source": "user_accepted",
            })
            if len(self.examples) > 20:
                self.examples = self.examples[-20:]
        elif entry["reason"] and len(entry["reason"]) > 10:
            self.examples.append({
                "input": entry["message"],
                "error": entry["response"],
                "correction": entry["reason"],
                "source": "user_rejected",
            })
            if len(self.examples) > 10:
                self.examples = self.examples[-10:]

    def get_system_prompt_suffix(self) -> str:
        parts = []
        if self.rules:
            parts.append("## Learning-Derived Rules\n" + "\n".join(f"- {r}" for r in self.rules[-5:]))
        if self.examples:
            good = [e for e in self.examples if e.get("source") == "user_accepted"]
            if good:
                ex = good[-1]
                parts.append(f"## Example of Good Response\nUser: {ex['input']}\nAssistant: {ex['output']}")
        return "\n\n".join(parts)

    def _load(self):
        """Load learning state from SQLite, fall back to JSON."""
        with self._lock:
            try:
                with sqlite3.connect(SYSTEM_DB) as conn:
                    row = conn.execute(
                        "SELECT data FROM learning_state WHERE key = 'default'"
                    ).fetchone()
                    if row:
                        data = json.loads(row[0])
                        self.learnings = data.get("learnings", [])
                        self.rules = data.get("rules", [])
                        self.examples = data.get("examples", [])
                        return
            except Exception as e:
                logger.debug("[LEARN] SQLite load error: %s", e)

            # Fallback: JSON file
            try:
                if os.path.isfile(_LEARNINGS_FILE):
                    with open(_LEARNINGS_FILE) as f:
                        data = json.load(f)
                        self.learnings = data.get("learnings", [])
                        self.rules = data.get("rules", [])
                        self.examples = data.get("examples", [])
                    self.save()  # Migrate to SQLite
            except Exception as e:
                logger.debug("[LEARN] JSON load error: %s", e)

    def save(self):
        """Persist learning state to SQLite (+ JSON fallback)."""
        with self._lock:
            data = json.dumps({
                "learnings": self.learnings[-100:],
                "rules": self.rules,
                "examples": self.examples,
            }, default=str)
            try:
                with sqlite3.connect(SYSTEM_DB) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO learning_state (key, data) VALUES ('default', ?)",
                        (data,),
                    )
                    conn.commit()
            except Exception as e:
                logger.debug("[LEARN] SQLite save error, falling back to JSON: %s", e)
                try:
                    os.makedirs(os.path.dirname(_LEARNINGS_FILE), exist_ok=True)
                    with open(_LEARNINGS_FILE, "w") as f:
                        json.dump({
                            "learnings": self.learnings[-100:],
                            "rules": self.rules,
                            "examples": self.examples,
                        }, f, indent=2)
                except Exception as e2:
                    logger.debug("[LEARN] JSON save error: %s", e2)


# â”€â”€ Auto-Healing Recovery Handlers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def heal_ollama(diagnosis: str) -> str:
    """Recovery handler for Ollama failures."""
    import httpx
    from core.config_registry import config as _c
    _ollama = _c.get("ollama.base_url")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_ollama}/api/tags")
            if r.status_code == 200:
                return "ollama_is_running"
    except Exception as e:
        logger.warning("[SelfHeal] ollama health check failed: %s", e)

    import subprocess
    try:
        subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
        return "restarted_ollama_serve"
    except Exception as e:
        return f"ollama_restart_failed: {e}"


async def heal_search(diagnosis: str) -> str:
    """Recovery handler for SearXNG search failures."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("http://localhost:8888/search?q=test&format=json")
            if r.status_code == 200:
                return "searxng_is_running"
    except Exception as e:
        logger.warning("[SelfHeal] search health check failed: %s", e)
    return "searxng_not_available"


# â”€â”€ Singleton instances â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

self_healing = SelfHealing()
learning_loop = LearningLoop()

# Register default recovery handlers
self_healing.register_recovery("ollama", heal_ollama)
self_healing.register_recovery("search", heal_search)
