from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BENCHMARK_DB_DIR = Path.home() / ".jarvis"
_BENCHMARK_DB_FILE = _BENCHMARK_DB_DIR / "benchmark.db"


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
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    crash_rate: float = 0.0
    avg_cost: float = 0.0


class BenchmarkStore:
    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or str(_BENCHMARK_DB_FILE)
        self._init_db()

    def _init_db(self) -> None:
        _BENCHMARK_DB_DIR.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    language TEXT DEFAULT '',
                    framework TEXT DEFAULT '',
                    success INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    quality_score REAL DEFAULT 0.0,
                    retries INTEGER DEFAULT 0,
                    crash INTEGER DEFAULT 0,
                    cost REAL DEFAULT 0.0,
                    tokens_used INTEGER DEFAULT 0,
                    exit_code INTEGER DEFAULT 0,
                    output_snippet TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bench_provider
                ON benchmark_results(provider_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bench_category
                ON benchmark_results(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bench_language
                ON benchmark_results(language)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bench_provider_category
                ON benchmark_results(provider_id, category)
            """)
            conn.commit()

    def save_result(self, result) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO benchmark_results
                   (task_id, provider_id, category, language, framework,
                    success, duration_ms, quality_score, retries, crash,
                    cost, tokens_used, exit_code, output_snippet, error, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (result.task_id, result.provider_id, result.category,
                 result.language, result.framework,
                 1 if result.success else 0, result.duration_ms,
                 result.quality_score, result.retries, 1 if result.crash else 0,
                 result.cost, result.tokens_used, result.exit_code,
                 result.output_snippet[:500], result.error[:200], result.timestamp),
            )
            conn.commit()

    def save_results(self, results: list) -> None:
        with sqlite3.connect(self._db_path) as conn:
            rows = [
                (r.task_id, r.provider_id, r.category, r.language, r.framework,
                 1 if r.success else 0, r.duration_ms, r.quality_score,
                 r.retries, 1 if r.crash else 0, r.cost, r.tokens_used,
                 r.exit_code, r.output_snippet[:500], r.error[:200], r.timestamp)
                for r in results
            ]
            conn.executemany(
                """INSERT INTO benchmark_results
                   (task_id, provider_id, category, language, framework,
                    success, duration_ms, quality_score, retries, crash,
                    cost, tokens_used, exit_code, output_snippet, error, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.commit()

    def get_results(self, provider_id: str | None = None,
                    category: str | None = None,
                    language: str | None = None,
                    limit: int = 100) -> list[dict]:
        query = "SELECT * FROM benchmark_results WHERE 1=1"
        params: list[Any] = []
        if provider_id:
            query += " AND provider_id = ?"
            params.append(provider_id)
        if category:
            query += " AND category = ?"
            params.append(category)
        if language:
            query += " AND language = ?"
            params.append(language)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_summary(self, provider_id: str | None = None,
                    category: str | None = None) -> list[BenchmarkSummary]:
        where = "WHERE 1=1"
        params: list[Any] = []
        if provider_id:
            where += " AND provider_id = ?"
            params.append(provider_id)
        if category:
            where += " AND category = ?"
            params.append(category)

        query = f"""
            SELECT
                provider_id,
                COALESCE(category, '') as category,
                COALESCE(language, '') as language,
                COUNT(*) as total_runs,
                SUM(success) as success_count,
                AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END) as success_rate,
                AVG(duration_ms) as avg_duration_ms,
                AVG(quality_score) as avg_quality,
                AVG(crash) as crash_rate,
                AVG(COALESCE(cost, 0.0)) as avg_cost
            FROM benchmark_results
            {where}
            GROUP BY provider_id, category, language
            ORDER BY provider_id, category
        """

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [
                BenchmarkSummary(
                    provider_id=r["provider_id"],
                    category=r["category"],
                    language=r["language"],
                    total_runs=r["total_runs"],
                    success_count=r["success_count"],
                    success_rate=round(r["success_rate"] or 0.0, 3),
                    avg_duration_ms=round(r["avg_duration_ms"] or 0.0, 1),
                    avg_quality=round(r["avg_quality"] or 0.0, 3),
                    crash_rate=round(r["crash_rate"] or 0.0, 3),
                    avg_cost=round(r["avg_cost"] or 0.0, 4),
                )
                for r in rows
            ]

    def get_best_provider(self, category: str, language: str = "",
                          metric: str = "quality") -> dict[str, Any] | None:
        where = "category = ?"
        params: list[Any] = [category]
        if language:
            where += " AND language = ?"
            params.append(language)

        order = "avg_quality DESC" if metric == "quality" else "success_rate DESC, avg_duration_ms ASC"

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(f"""
                SELECT
                    provider_id,
                    COUNT(*) as runs,
                    AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END) as success_rate,
                    AVG(duration_ms) as avg_duration_ms,
                    AVG(quality_score) as avg_quality
                FROM benchmark_results
                WHERE {where}
                GROUP BY provider_id
                HAVING runs >= 2
                ORDER BY {order}
                LIMIT 1
            """, params).fetchone()
            if row:
                return dict(row)
            return None

    def get_leaderboard(self, category: str | None = None,
                        language: str | None = None) -> list[dict]:
        where = "1=1"
        params: list[Any] = []
        if category:
            where += " AND category = ?"
            params.append(category)
        if language:
            where += " AND language = ?"
            params.append(language)

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"""
                SELECT
                    provider_id,
                    COALESCE(category, '') as category,
                    COALESCE(language, '') as language,
                    COUNT(*) as runs,
                    SUM(success) as successes,
                    ROUND(AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END), 3) as success_rate,
                    ROUND(AVG(duration_ms), 1) as avg_duration_ms,
                    ROUND(AVG(quality_score), 3) as avg_quality,
                    ROUND(AVG(crash), 3) as crash_rate
                FROM benchmark_results
                WHERE {where}
                GROUP BY provider_id, category, language
                HAVING runs >= 2
                ORDER BY avg_quality DESC, success_rate DESC, avg_duration_ms ASC
            """, params).fetchall()
            return [dict(r) for r in rows]

    def clear(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM benchmark_results")
            conn.commit()

    def get_stats(self) -> dict[str, Any]:
        with sqlite3.connect(self._db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM benchmark_results").fetchone()[0]
            providers = conn.execute("SELECT COUNT(DISTINCT provider_id) FROM benchmark_results").fetchone()[0]
            categories = conn.execute("SELECT COUNT(DISTINCT category) FROM benchmark_results").fetchone()[0]
            last = conn.execute("SELECT MAX(timestamp) FROM benchmark_results").fetchone()[0]
            return {
                "total_runs": total,
                "providers": providers,
                "categories": categories,
                "last_run": last,
            }


benchmark_store = BenchmarkStore()
