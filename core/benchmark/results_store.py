"""Benchmark Results Store — SQLite-backed persistence for benchmark runs.

Tables:
  - benchmark_runs: individual run results
  - benchmark_tasks: task definitions
  - benchmark_reports: aggregated reports (snapshots)

Enables historical trend analysis across multiple benchmark sessions.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.benchmark.models import (
    BenchmarkMode,
    BenchmarkReport,
    BenchmarkRun,
    BenchmarkTask,
    RunStatus,
)
from core.storage import SYSTEM_DB

logger = logging.getLogger(__name__)

BENCHMARK_DB = SYSTEM_DB


class BenchmarkResultsStore:
    """Persistent SQLite store for benchmark results.

    Thread-safe with reentrant lock.
    """

    def __init__(self, db_path: str = BENCHMARK_DB):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS benchmark_runs (
                        run_id TEXT PRIMARY KEY,
                        model_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        status TEXT NOT NULL,
                        elapsed_seconds REAL,
                        tool_names TEXT,
                        hallucinated_tools TEXT,
                        missing_steps TEXT,
                        completed_naturally INTEGER,
                        loop_count INTEGER,
                        error_message TEXT,
                        metrics TEXT,
                        started_at TEXT,
                        finished_at TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS benchmark_tasks (
                        task_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        goal TEXT,
                        category TEXT,
                        required_tools TEXT,
                        expected_tools TEXT,
                        timeout_seconds INTEGER
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS benchmark_reports (
                        report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        generated_at TEXT NOT NULL,
                        report_json TEXT NOT NULL,
                        session_tag TEXT
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    # ── Run CRUD ───────────────────────────────────────────────────

    def save_run(self, run: BenchmarkRun) -> None:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO benchmark_runs
                       (run_id, model_id, task_id, mode, status, elapsed_seconds,
                        tool_names, hallucinated_tools, missing_steps,
                        completed_naturally, loop_count, error_message, metrics,
                        started_at, finished_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run.run_id, run.model_id, run.task_id, run.mode.value,
                        run.status.value, run.elapsed_seconds,
                        json.dumps(run.tool_names),
                        json.dumps(run.hallucinated_tools),
                        json.dumps(run.missing_steps),
                        int(run.completed_naturally), run.loop_count,
                        run.error_message, json.dumps(run.metrics),
                        run.started_at, run.finished_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_run(self, run_id: str) -> BenchmarkRun | None:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT * FROM benchmark_runs WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                return self._row_to_run(row) if row else None
            finally:
                conn.close()

    def list_runs(
        self,
        model_id: str | None = None,
        task_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> list[BenchmarkRun]:
        query = "SELECT * FROM benchmark_runs WHERE 1=1"
        params: list[Any] = []
        if model_id:
            query += " AND model_id = ?"
            params.append(model_id)
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        if mode:
            query += " AND mode = ?"
            params.append(mode)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                rows = conn.execute(query, params).fetchall()
                return [self._row_to_run(r) for r in rows if r]
            finally:
                conn.close()

    def save_task(self, task: BenchmarkTask) -> None:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO benchmark_tasks
                       (task_id, name, goal, category, required_tools, expected_tools, timeout_seconds)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task.id, task.name, task.goal, task.category.value,
                        json.dumps(task.required_tools),
                        json.dumps(task.expected_tools),
                        task.timeout_seconds,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    # ── Report Storage ─────────────────────────────────────────────

    def save_report(self, report: BenchmarkReport, session_tag: str = "") -> int:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cur = conn.execute(
                    "INSERT INTO benchmark_reports (generated_at, report_json, session_tag) VALUES (?, ?, ?)",
                    (
                        report.generated_at.isoformat() if report.generated_at else datetime.now().isoformat(),
                        json.dumps(report.to_dict()),
                        session_tag,
                    ),
                )
                conn.commit()
                return cur.lastrowid or 0
            finally:
                conn.close()

    def list_reports(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT report_id, generated_at, session_tag FROM benchmark_reports ORDER BY report_id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [
                    {"id": r[0], "generated_at": r[1], "session_tag": r[2]}
                    for r in rows
                ]
            finally:
                conn.close()

    def get_report(self, report_id: int) -> dict[str, Any] | None:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT report_json FROM benchmark_reports WHERE report_id = ?",
                    (report_id,),
                ).fetchone()
                return json.loads(row[0]) if row else None
            finally:
                conn.close()

    # ── Statistics ─────────────────────────────────────────────────

    def get_model_stats(self, model_id: str) -> dict[str, Any]:
        """Aggregate statistics for a specific model across all runs."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                raw = conn.execute(
                    """SELECT status, COUNT(*) as cnt, AVG(elapsed_seconds) as avg_elapsed
                       FROM benchmark_runs WHERE model_id = ? AND mode = 'raw'
                       GROUP BY status""",
                    (model_id,),
                ).fetchall()
                arch = conn.execute(
                    """SELECT status, COUNT(*) as cnt, AVG(elapsed_seconds) as avg_elapsed
                       FROM benchmark_runs WHERE model_id = ? AND mode = 'with_architecture'
                       GROUP BY status""",
                    (model_id,),
                ).fetchall()
                return {
                    "model_id": model_id,
                    "raw": dict(raw),
                    "with_architecture": dict(arch),
                }
            finally:
                conn.close()

    def get_overall_stats(self) -> dict[str, Any]:
        """Overall statistics across all runs."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                total = conn.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0]
                passed = conn.execute(
                    "SELECT COUNT(*) FROM benchmark_runs WHERE status = ?",
                    (RunStatus.PASSED.value,),
                ).fetchone()[0]
                models = conn.execute(
                    "SELECT COUNT(DISTINCT model_id) FROM benchmark_runs",
                ).fetchone()[0]
                tasks = conn.execute(
                    "SELECT COUNT(DISTINCT task_id) FROM benchmark_runs",
                ).fetchone()[0]
                return {
                    "total_runs": total,
                    "passed": passed,
                    "pass_rate": round(passed / total, 3) if total else 0.0,
                    "unique_models": models,
                    "unique_tasks": tasks,
                }
            finally:
                conn.close()

    # ── Helpers ────────────────────────────────────────────────────

    def _row_to_run(self, row: sqlite3.Row | tuple) -> BenchmarkRun:
        if isinstance(row, sqlite3.Row):
            return BenchmarkRun(
                run_id=row["run_id"],
                model_id=row["model_id"],
                task_id=row["task_id"],
                mode=BenchmarkMode(row["mode"]),
                status=RunStatus(row["status"]),
                elapsed_seconds=row["elapsed_seconds"] or 0.0,
                tool_names=json.loads(row["tool_names"] or "[]"),
                hallucinated_tools=json.loads(row["hallucinated_tools"] or "[]"),
                missing_steps=json.loads(row["missing_steps"] or "[]"),
                completed_naturally=bool(row["completed_naturally"]),
                loop_count=row["loop_count"] or 0,
                error_message=row["error_message"] or "",
                metrics=json.loads(row["metrics"] or "{}"),
                started_at=row["started_at"] or "",
                finished_at=row["finished_at"] or "",
            )
        # Fallback for tuple format
        return BenchmarkRun(
            run_id=row[0], model_id=row[1], task_id=row[2],
            mode=BenchmarkMode(row[3]), status=RunStatus(row[4]),
            elapsed_seconds=row[5] or 0.0,
            tool_names=json.loads(row[6] or "[]"),
            hallucinated_tools=json.loads(row[7] or "[]"),
            missing_steps=json.loads(row[8] or "[]"),
            completed_naturally=bool(row[9]), loop_count=row[10] or 0,
            error_message=row[11] or "",
            metrics=json.loads(row[12] or "{}"),
            started_at=row[13] or "", finished_at=row[14] or "",
        )
