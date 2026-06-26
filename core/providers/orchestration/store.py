from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from core.providers.orchestration.models import (
    OrchestrationPlan, OrchestrationResult, StepResult,
)

logger = logging.getLogger(__name__)

_ORCH_DB_DIR = Path.home() / ".jarvis"
_ORCH_DB_FILE = _ORCH_DB_DIR / "orchestration.db"


class OrchestrationStore:
    """SQLite-backed execution graph memory for orchestration history.

    Stores every orchestration execution with plan metadata, per-step results,
    confidence scores, typed artifacts, and failure analysis. Enables queries
    like "what's the success rate for Python API projects?".
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or str(_ORCH_DB_FILE)
        self._init_db()

    def _init_db(self) -> None:
        _ORCH_DB_DIR.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orchestration_plans (
                    plan_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    total_steps INTEGER NOT NULL,
                    provider_count INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    overall_success INTEGER,
                    avg_confidence REAL,
                    avg_quality REAL,
                    total_cost REAL,
                    overall_risk REAL,
                    duration_ms REAL,
                    error TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orchestration_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    chain_type TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    output_preview TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    confidence REAL DEFAULT 0.0,
                    quality_score REAL DEFAULT 0.0,
                    cost REAL DEFAULT 0.0,
                    risk REAL DEFAULT 0.0,
                    retries INTEGER DEFAULT 0,
                    artifacts_json TEXT DEFAULT '{}',
                    typed_artifacts_json TEXT DEFAULT '[]',
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_plan_goal
                ON orchestration_plans(goal)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_plan_success
                ON orchestration_plans(overall_success)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_step_plan
                ON orchestration_steps(plan_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_step_provider
                ON orchestration_steps(provider_id)
            """)
            conn.commit()

    # ── Save ───────────────────────────────────────────────────────────

    def save_result(self, result: OrchestrationResult) -> None:
        plan = result.plan
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO orchestration_plans
                (plan_id, goal, total_steps, provider_count, created_at,
                 started_at, completed_at, overall_success, avg_confidence,
                 avg_quality, total_cost, overall_risk, duration_ms, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                plan.plan_id, plan.goal, plan.total_steps,
                plan.provider_count(), plan.created_at,
                result.start_time if result.start_time else None,
                result.end_time if result.end_time else None,
                1 if result.overall_success else 0,
                result.avg_confidence, result.avg_quality,
                result.total_cost, result.overall_risk,
                result.duration_ms, result.error[:500] if result.error else None,
            ))

            for s_result in result.step_results:
                arts_json = json.dumps(s_result.artifacts)
                typed_arts_json = json.dumps([
                    {"type": ta.type.value, "path": ta.path,
                     "summary": ta.summary, "metadata": ta.metadata}
                    for ta in s_result.typed_artifacts
                ])
                conn.execute("""
                    INSERT INTO orchestration_steps
                    (plan_id, step_id, provider_id, chain_type, success,
                     duration_ms, output_preview, error, confidence,
                     quality_score, cost, risk, retries,
                     artifacts_json, typed_artifacts_json, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    plan.plan_id, s_result.step_id, s_result.provider_id,
                    s_result.chain_type.value, 1 if s_result.success else 0,
                    s_result.duration_ms, s_result.output[:200],
                    s_result.error[:200] if s_result.error else None,
                    s_result.confidence.confidence,
                    s_result.confidence.quality_score,
                    s_result.confidence.cost,
                    s_result.confidence.risk,
                    s_result.retries,
                    arts_json, typed_arts_json,
                    time.time(),
                ))
            conn.commit()

    # ── Query Plans ────────────────────────────────────────────────────

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM orchestration_plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_recent_plans(self, limit: int = 10) -> list[dict[str, Any]]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM orchestration_plans ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def query_by_goal(self, goal_pattern: str, limit: int = 20) -> list[dict[str, Any]]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM orchestration_plans WHERE goal LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{goal_pattern}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_steps_for_plan(self, plan_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM orchestration_steps WHERE plan_id = ? ORDER BY id",
                (plan_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Analytics ──────────────────────────────────────────────────────

    def get_success_rate(self, goal_pattern: str = "") -> float:
        with sqlite3.connect(self._db_path) as conn:
            if goal_pattern:
                row = conn.execute(
                    """SELECT
                        COUNT(*) as total,
                        SUM(overall_success) as successes
                       FROM orchestration_plans
                       WHERE goal LIKE ?""",
                    (f"%{goal_pattern}%",),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as total, SUM(overall_success) as successes FROM orchestration_plans",
                ).fetchone()
            total = row[0] or 0
            successes = row[1] or 0
            return successes / total if total > 0 else 0.0

    def get_avg_duration(self, goal_pattern: str = "") -> float:
        with sqlite3.connect(self._db_path) as conn:
            if goal_pattern:
                row = conn.execute(
                    "SELECT AVG(duration_ms) FROM orchestration_plans WHERE goal LIKE ? AND duration_ms IS NOT NULL",
                    (f"%{goal_pattern}%",),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT AVG(duration_ms) FROM orchestration_plans WHERE duration_ms IS NOT NULL",
                ).fetchone()
            return row[0] or 0.0

    def get_most_used_providers(self, limit: int = 5) -> list[dict[str, Any]]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT
                    provider_id,
                    COUNT(*) as executions,
                    SUM(success) as successes,
                    AVG(confidence) as avg_confidence,
                    AVG(quality_score) as avg_quality
                FROM orchestration_steps
                GROUP BY provider_id
                ORDER BY executions DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_provider_success_rate(self, provider_id: str) -> dict[str, Any]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(success) as successes,
                    AVG(duration_ms) as avg_duration,
                    AVG(confidence) as avg_confidence,
                    AVG(quality_score) as avg_quality
                FROM orchestration_steps
                WHERE provider_id = ?
            """, (provider_id,)).fetchone()
            total = row[0] or 0
            successes = row[1] or 0
            return {
                "provider_id": provider_id,
                "total": total,
                "success_rate": successes / total if total > 0 else 0.0,
                "avg_duration_ms": row[2] or 0.0,
                "avg_confidence": row[3] or 0.0,
                "avg_quality": row[4] or 0.0,
            }

    def get_failure_analysis(self, limit: int = 10) -> list[dict[str, Any]]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT
                    s.provider_id,
                    s.chain_type,
                    s.error,
                    COUNT(*) as failure_count
                FROM orchestration_steps s
                WHERE s.success = 0 AND s.error IS NOT NULL AND s.error != ''
                GROUP BY s.provider_id, s.chain_type, s.error
                ORDER BY failure_count DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_summary_stats(self) -> dict[str, Any]:
        with sqlite3.connect(self._db_path) as conn:
            total_plans = conn.execute("SELECT COUNT(*) FROM orchestration_plans").fetchone()[0]
            total_steps = conn.execute("SELECT COUNT(*) FROM orchestration_steps").fetchone()[0]
            success_rate = self.get_success_rate()
            avg_dur = self.get_avg_duration()
            providers_row = conn.execute(
                "SELECT COUNT(DISTINCT provider_id) FROM orchestration_steps"
            ).fetchone()
            last_row = conn.execute(
                "SELECT MAX(completed_at) FROM orchestration_plans"
            ).fetchone()
            return {
                "total_plans": total_plans,
                "total_steps": total_steps,
                "overall_success_rate": success_rate,
                "avg_duration_ms": avg_dur,
                "distinct_providers": providers_row[0] or 0,
                "last_execution": last_row[0],
            }

    def clear(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM orchestration_steps")
            conn.execute("DELETE FROM orchestration_plans")
            conn.commit()


orchestration_store = OrchestrationStore()
