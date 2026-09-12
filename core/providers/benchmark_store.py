"""Durable SQLite store for benchmark results.

Completed from the committed contract in tests/unit/test_provider_benchmark.py:
save/batch save, filtered listing, per-(provider, category) summaries, best
provider and leaderboard rankings, stats, clear, and durability across
instances at the same db path.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")


@dataclass
class BenchmarkSummary:
    provider_id: str = ""
    category: str = ""
    language: str = ""
    total_runs: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    avg_duration_ms: float = 0.0
    avg_quality: float = 0.0
    avg_cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "category": self.category,
            "language": self.language,
            "total_runs": self.total_runs,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "avg_duration_ms": self.avg_duration_ms,
            "avg_quality": self.avg_quality,
            "avg_cost": self.avg_cost,
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS benchmark_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    framework TEXT NOT NULL DEFAULT '',
    success INTEGER NOT NULL DEFAULT 0,
    duration_ms REAL NOT NULL DEFAULT 0.0,
    quality_score REAL NOT NULL DEFAULT 0.0,
    retries INTEGER NOT NULL DEFAULT 0,
    crash INTEGER NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0.0,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    exit_code INTEGER NOT NULL DEFAULT 0,
    output_snippet TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    timestamp REAL NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_bench_provider ON benchmark_results(provider_id);
CREATE INDEX IF NOT EXISTS idx_bench_category ON benchmark_results(category);
CREATE INDEX IF NOT EXISTS idx_bench_language ON benchmark_results(language);
"""


class BenchmarkStore:
    """SQLite-backed result store.  All failures degrade to empty results."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or os.path.join(_DEFAULT_DB_DIR, "benchmark_results.db")
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._lock:
                conn = self._connect()
                conn.executescript(_SCHEMA)
                conn.commit()
                conn.close()
        except Exception as exc:
            logger.warning("[benchmark_store] init failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Writes                                                             #
    # ------------------------------------------------------------------ #

    def save_result(self, result: Any) -> bool:
        data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        try:
            with self._lock:
                conn = self._connect()
                conn.execute(
                    """INSERT INTO benchmark_results
                       (task_id, provider_id, category, language, framework, success,
                        duration_ms, quality_score, retries, crash, cost, tokens_used,
                        exit_code, output_snippet, error, timestamp)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        data.get("task_id", ""),
                        data.get("provider_id", ""),
                        data.get("category", ""),
                        data.get("language", ""),
                        data.get("framework", ""),
                        int(data.get("success", 0)),
                        float(data.get("duration_ms", 0.0)),
                        float(data.get("quality_score", 0.0)),
                        int(data.get("retries", 0)),
                        int(data.get("crash", 0)),
                        float(data.get("cost", 0.0)),
                        int(data.get("tokens_used", 0)),
                        int(data.get("exit_code", 0)),
                        data.get("output_snippet", ""),
                        data.get("error", ""),
                        float(data.get("timestamp", time.time())),
                    ),
                )
                conn.commit()
                conn.close()
                return True
        except Exception as exc:
            logger.warning("[benchmark_store] save_result failed: %s", exc)
            return False

    def save_results(self, results: list[Any]) -> int:
        saved = 0
        for result in results:
            if self.save_result(result):
                saved += 1
        return saved

    # ------------------------------------------------------------------ #
    # Reads                                                              #
    # ------------------------------------------------------------------ #

    def get_results(
        self,
        provider_id: Optional[str] = None,
        category: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM benchmark_results WHERE 1=1"
        params: list[Any] = []
        if provider_id is not None:
            query += " AND provider_id = ?"
            params.append(provider_id)
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        if language is not None:
            query += " AND language = ?"
            params.append(language)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        try:
            with self._lock:
                conn = self._connect()
                rows = conn.execute(query, params).fetchall()
                conn.close()
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("[benchmark_store] get_results failed: %s", exc)
            return []

    def get_summary(
        self,
        provider_id: Optional[str] = None,
        category: Optional[str] = None,
        language: Optional[str] = None,
    ) -> list[BenchmarkSummary]:
        rows = self.get_results(provider_id=provider_id, category=category, language=language, limit=100000)
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = (row.get("provider_id", ""), row.get("category", ""), row.get("language", ""))
            grouped.setdefault(key, []).append(row)
        summaries = []
        for (pid, cat, lang), items in sorted(grouped.items()):
            total = len(items)
            successes = sum(1 for i in items if i.get("success"))
            summaries.append(BenchmarkSummary(
                provider_id=pid,
                category=cat,
                language=lang,
                total_runs=total,
                success_count=successes,
                success_rate=round(successes / total, 4) if total else 0.0,
                avg_duration_ms=round(sum(float(i.get("duration_ms", 0.0)) for i in items) / total, 2) if total else 0.0,
                avg_quality=round(sum(float(i.get("quality_score", 0.0)) for i in items) / total, 4) if total else 0.0,
                avg_cost=round(sum(float(i.get("cost", 0.0)) for i in items) / total, 6) if total else 0.0,
            ))
        return summaries

    def get_best_provider(self, category: str) -> Optional[dict[str, Any]]:
        summaries = [s for s in self.get_summary(category=category) if s.total_runs > 0]
        if not summaries:
            return None
        best = max(summaries, key=lambda s: (s.success_rate, s.avg_quality))
        return best.to_dict()

    def get_leaderboard(self, category: Optional[str] = None) -> list[dict[str, Any]]:
        summaries = [s for s in self.get_summary(category=category) if s.total_runs > 0]
        summaries.sort(key=lambda s: (s.success_rate, s.avg_quality), reverse=True)
        return [s.to_dict() for s in summaries]

    def get_stats(self) -> dict[str, int]:
        try:
            with self._lock:
                conn = self._connect()
                row = conn.execute(
                    """SELECT COUNT(*) AS total_runs,
                              COUNT(DISTINCT provider_id) AS providers,
                              COUNT(DISTINCT category) AS categories
                       FROM benchmark_results"""
                ).fetchone()
                conn.close()
                return {
                    "total_runs": int(row["total_runs"]),
                    "providers": int(row["providers"]),
                    "categories": int(row["categories"]),
                }
        except Exception as exc:
            logger.warning("[benchmark_store] get_stats failed: %s", exc)
            return {"total_runs": 0, "providers": 0, "categories": 0}

    def clear(self) -> bool:
        try:
            with self._lock:
                conn = self._connect()
                conn.execute("DELETE FROM benchmark_results")
                conn.commit()
                conn.close()
                return True
        except Exception as exc:
            logger.warning("[benchmark_store] clear failed: %s", exc)
            return False


benchmark_store = BenchmarkStore()
