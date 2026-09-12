"""Execution-graph memory for orchestration (SQLite).

Completed from the committed contract in tests/unit/test_orchestration.py
(TestOrchestrationStore).  One table per concern; all queries are defensive
(never raise on empty/missing data).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from core.providers.orchestration.models import OrchestrationResult


class OrchestrationStore:
    """Durable record of plans, steps, and outcomes for later learning."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if not db_path:
            from core.constants import DATA_DIR
            db_path = str(Path(DATA_DIR) / "orchestration_store.db")
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._init_db()

    @property
    def _db_path_read(self) -> str:  # pragma: no cover - compat alias
        return self._db_path

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS plans (
                        plan_id TEXT PRIMARY KEY,
                        goal TEXT NOT NULL DEFAULT '',
                        overall_success INTEGER NOT NULL DEFAULT 0,
                        start_time REAL NOT NULL DEFAULT 0,
                        end_time REAL NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS steps (
                        step_id TEXT NOT NULL,
                        plan_id TEXT NOT NULL,
                        provider_id TEXT NOT NULL DEFAULT '',
                        chain_type TEXT NOT NULL DEFAULT '',
                        success INTEGER NOT NULL DEFAULT 0,
                        output TEXT NOT NULL DEFAULT '',
                        error TEXT NOT NULL DEFAULT '',
                        duration_ms REAL NOT NULL DEFAULT 0,
                        confidence REAL NOT NULL DEFAULT 0,
                        quality_score REAL NOT NULL DEFAULT 0,
                        cost REAL NOT NULL DEFAULT 0,
                        risk REAL NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS idx_steps_plan ON steps(plan_id);
                    CREATE INDEX IF NOT EXISTS idx_steps_provider ON steps(provider_id);
                    CREATE INDEX IF NOT EXISTS idx_plans_goal ON plans(goal);
                    """
                )
                conn.commit()
            finally:
                conn.close()

    # ── Write path ──────────────────────────────────────────────────────────

    def save_result(self, result: OrchestrationResult) -> bool:
        try:
            now = __import__("time").time()
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO plans (plan_id, goal, overall_success,"
                        " start_time, end_time, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            result.plan.plan_id,
                            result.plan.goal,
                            1 if result.overall_success else 0,
                            float(result.start_time or 0.0),
                            float(result.end_time or 0.0),
                            now,
                        ),
                    )
                    for step_result in result.step_results:
                        conn.execute(
                            "INSERT INTO steps (step_id, plan_id, provider_id, chain_type,"
                            " success, output, error, duration_ms, confidence,"
                            " quality_score, cost, risk, created_at)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                step_result.step_id,
                                result.plan.plan_id,
                                step_result.provider_id,
                                getattr(step_result.chain_type, "value", str(step_result.chain_type)),
                                1 if step_result.success else 0,
                                step_result.output,
                                step_result.error,
                                float(step_result.duration_ms or 0.0),
                                float(step_result.confidence.confidence or 0.0),
                                float(step_result.confidence.quality_score or 0.0),
                                float(step_result.confidence.cost or 0.0),
                                float(step_result.confidence.risk or 0.0),
                                now,
                            ),
                        )
                    conn.commit()
                finally:
                    conn.close()
            return True
        except Exception as exc:
            import logging

            logging.getLogger(__name__).debug("[orchestration_store] save failed: %s", exc)
            return False

    # ── Read path ───────────────────────────────────────────────────────────

    def get_plan(self, plan_id: str) -> Optional[dict[str, Any]]:
        try:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT plan_id, goal, overall_success, start_time, end_time, created_at"
                    " FROM plans WHERE plan_id = ?",
                    (plan_id,),
                ).fetchone()
            finally:
                conn.close()
            if row is None:
                return None
            return {
                "plan_id": row[0],
                "goal": row[1],
                "overall_success": bool(row[2]),
                "start_time": row[3],
                "end_time": row[4],
                "created_at": row[5],
            }
        except Exception:
            return None

    def get_steps_for_plan(self, plan_id: str) -> list[dict[str, Any]]:
        try:
            conn = sqlite3.connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT step_id, provider_id, chain_type, success, output, error,"
                    " duration_ms, confidence FROM steps WHERE plan_id = ?",
                    (plan_id,),
                ).fetchall()
            finally:
                conn.close()
            return [
                {
                    "step_id": r[0],
                    "provider_id": r[1],
                    "chain_type": r[2],
                    "success": bool(r[3]),
                    "output": r[4],
                    "error": r[5],
                    "duration_ms": r[6],
                    "confidence": r[7],
                }
                for r in rows
            ]
        except Exception:
            return []

    def query_by_goal(self, substring: str, limit: int = 20) -> list[dict[str, Any]]:
        try:
            conn = sqlite3.connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT plan_id, goal, overall_success, created_at FROM plans"
                    " WHERE goal LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (f"%{substring}%", int(limit)),
                ).fetchall()
            finally:
                conn.close()
            return [
                {
                    "plan_id": r[0],
                    "goal": r[1],
                    "overall_success": bool(r[2]),
                    "created_at": r[3],
                }
                for r in rows
            ]
        except Exception:
            return []

    def get_success_rate(self, goal_substring: str = "") -> float:
        try:
            conn = sqlite3.connect(self._db_path)
            try:
                if goal_substring:
                    row = conn.execute(
                        "SELECT COUNT(*), SUM(overall_success) FROM plans WHERE goal LIKE ?",
                        (f"%{goal_substring}%",),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT COUNT(*), SUM(overall_success) FROM plans"
                    ).fetchone()
            finally:
                conn.close()
            total = int(row[0] or 0)
            if total == 0:
                return 0.0
            return float(row[1] or 0) / total
        except Exception:
            return 0.0

    def get_avg_duration(self) -> float:
        try:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT AVG(end_time - start_time) FROM plans"
                    " WHERE end_time > start_time"
                ).fetchone()
            finally:
                conn.close()
            # Stored plan times are already in milliseconds (see
            # test_avg_duration: start=0, end=1000 -> avg 2000 across two plans).
            return float(row[0] or 0.0) if row and row[0] else 0.0
        except Exception:
            return 0.0

    def get_most_used_providers(self, limit: int = 5) -> list[dict[str, Any]]:
        try:
            conn = sqlite3.connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT provider_id, COUNT(*) AS uses FROM steps"
                    " GROUP BY provider_id ORDER BY uses DESC, provider_id LIMIT ?",
                    (int(limit),),
                ).fetchall()
            finally:
                conn.close()
            return [{"provider_id": r[0], "uses": r[1]} for r in rows]
        except Exception:
            return []

    def get_provider_success_rate(self, provider_id: str) -> dict[str, Any]:
        try:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT COUNT(*), SUM(success) FROM steps WHERE provider_id = ?",
                    (provider_id,),
                ).fetchone()
            finally:
                conn.close()
            total = int(row[0] or 0)
            return {
                "total": total,
                "success_rate": (float(row[1] or 0) / total) if total else 0.0,
            }
        except Exception:
            return {"total": 0, "success_rate": 0.0}

    def get_failure_analysis(self, limit: int = 5) -> list[dict[str, Any]]:
        try:
            conn = sqlite3.connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT error, provider_id, COUNT(*) AS failure_count FROM steps"
                    " WHERE success = 0 AND error != ''"
                    " GROUP BY error, provider_id"
                    " ORDER BY failure_count DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            finally:
                conn.close()
            return [
                {"error": r[0], "provider_id": r[1], "failure_count": r[2]}
                for r in rows
            ]
        except Exception:
            return []

    def get_summary_stats(self) -> dict[str, Any]:
        try:
            conn = sqlite3.connect(self._db_path)
            try:
                plans_row = conn.execute(
                    "SELECT COUNT(*), SUM(overall_success) FROM plans"
                ).fetchone()
                steps_row = conn.execute("SELECT COUNT(*) FROM steps").fetchone()
            finally:
                conn.close()
            total_plans = int(plans_row[0] or 0)
            return {
                "total_plans": total_plans,
                "total_steps": int(steps_row[0] or 0),
                "overall_success_rate":
                    (float(plans_row[1] or 0) / total_plans) if total_plans else 0.0,
            }
        except Exception:
            return {"total_plans": 0, "total_steps": 0, "overall_success_rate": 0.0}

    def get_recent_plans(self, limit: int = 10) -> list[dict[str, Any]]:
        try:
            conn = sqlite3.connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT plan_id, goal, overall_success, created_at FROM plans"
                    " ORDER BY created_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            finally:
                conn.close()
            return [
                {
                    "plan_id": r[0],
                    "goal": r[1],
                    "overall_success": bool(r[2]),
                    "created_at": r[3],
                }
                for r in rows
            ]
        except Exception:
            return []

    def clear(self) -> None:
        try:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute("DELETE FROM steps")
                    conn.execute("DELETE FROM plans")
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            pass


orchestration_store: Optional[OrchestrationStore] = None


def get_orchestration_store() -> OrchestrationStore:
    """Lazily create the module-level store singleton (keeps imports cheap)."""
    global orchestration_store
    if orchestration_store is None:
        orchestration_store = OrchestrationStore()
    return orchestration_store
