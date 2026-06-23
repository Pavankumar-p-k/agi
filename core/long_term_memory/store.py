"""KnowledgeStore — SQLite-backed persistent storage for knowledge items.

Lives in the same database (data/workflow.db) as activity graph, research facts,
and knowledge graph for transactional consistency.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.long_term_memory.models import (
    UNIFIED_DB,
    ExperienceSummary,
    KnowledgeItem,
    KnowledgeQuery,
)

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """Persistent storage for knowledge items and experience summaries.

    Tables:
      - knowledge_items: the condensed durable knowledge
      - experience_summaries: compressed activity views for pattern mining
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or UNIFIED_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS knowledge_items (
                    knowledge_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    claim TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    evidence_count INTEGER NOT NULL DEFAULT 1,
                    source_activity_ids_json TEXT DEFAULT '[]',
                    source_pattern_keys_json TEXT DEFAULT '[]',
                    tags_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    last_validated TEXT,
                    metadata_json TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS experience_summaries (
                    activity_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    domain TEXT NOT NULL DEFAULT 'general',
                    status TEXT NOT NULL,
                    node_count INTEGER NOT NULL DEFAULT 0,
                    agent_ids_json TEXT DEFAULT '[]',
                    tools_used_json TEXT DEFAULT '[]',
                    artifacts_produced_json TEXT DEFAULT '[]',
                    success INTEGER NOT NULL DEFAULT 1,
                    error_summary TEXT,
                    duration_seconds REAL,
                    outcome_quality REAL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_category
                    ON knowledge_items(category);
                CREATE INDEX IF NOT EXISTS idx_knowledge_confidence
                    ON knowledge_items(confidence);
                CREATE INDEX IF NOT EXISTS idx_knowledge_evidence
                    ON knowledge_items(evidence_count);
                CREATE INDEX IF NOT EXISTS idx_experience_domain
                    ON experience_summaries(domain);
                CREATE INDEX IF NOT EXISTS idx_experience_status
                    ON experience_summaries(status);
            """)

    # ── KnowledgeItem CRUD ─────────────────────────────────────────────

    def insert_knowledge(self, item: KnowledgeItem) -> KnowledgeItem:
        item.created_at = item.created_at or datetime.utcnow()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO knowledge_items
                   (knowledge_id, category, claim, confidence, evidence_count,
                    source_activity_ids_json, source_pattern_keys_json,
                    tags_json, created_at, last_validated, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.knowledge_id, item.category, item.claim, item.confidence,
                    item.evidence_count,
                    json.dumps(item.source_activity_ids),
                    json.dumps(item.source_pattern_keys),
                    json.dumps(item.tags),
                    item.created_at.isoformat(),
                    item.last_validated.isoformat() if item.last_validated else None,
                    json.dumps(item.metadata),
                ),
            )
        return item

    def get_knowledge(self, knowledge_id: str) -> KnowledgeItem | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM knowledge_items WHERE knowledge_id=?",
                (knowledge_id,),
            ).fetchone()
            if row is None:
                return None
            return _row_to_knowledge(row)

    def query_knowledge(self, query: KnowledgeQuery) -> list[KnowledgeItem]:
        clauses: list[str] = []
        params: list[Any] = []
        if query.category:
            clauses.append("category=?")
            params.append(query.category)
        if query.tag:
            clauses.append("tags_json LIKE ?")
            params.append(f'%{query.tag}%')
        if query.min_confidence > 0:
            clauses.append("confidence>=?")
            params.append(query.min_confidence)
        if query.min_evidence > 1:
            clauses.append("evidence_count>=?")
            params.append(query.min_evidence)
        where = " AND ".join(clauses) if clauses else "1=1"
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM knowledge_items WHERE {where}"
                " ORDER BY confidence DESC, evidence_count DESC LIMIT ?",
                params + [query.limit],
            ).fetchall()
            return [_row_to_knowledge(r) for r in rows]

    def search_knowledge(self, text: str, limit: int = 20) -> list[KnowledgeItem]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM knowledge_items
                   WHERE claim LIKE ?
                   ORDER BY confidence DESC, evidence_count DESC LIMIT ?""",
                (f"%{text}%", limit),
            ).fetchall()
            return [_row_to_knowledge(r) for r in rows]

    def delete_knowledge(self, knowledge_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM knowledge_items WHERE knowledge_id=?",
                (knowledge_id,),
            )

    def update_confidence(self, knowledge_id: str, new_confidence: float) -> None:
        now = datetime.utcnow()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE knowledge_items SET confidence=?, last_validated=?
                   WHERE knowledge_id=?""",
                (new_confidence, now.isoformat(), knowledge_id),
            )

    def count_knowledge(self) -> dict[str, int]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM knowledge_items GROUP BY category"
            ).fetchall()
            return {r["category"]: r["cnt"] for r in rows}

    def get_all_knowledge(self, limit: int = 100) -> list[KnowledgeItem]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM knowledge_items ORDER BY confidence DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_row_to_knowledge(r) for r in rows]

    # ── ExperienceSummary CRUD ─────────────────────────────────────────

    def insert_experience(self, exp: ExperienceSummary) -> ExperienceSummary:
        exp.created_at = exp.created_at or datetime.utcnow()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO experience_summaries
                   (activity_id, goal, domain, status, node_count,
                    agent_ids_json, tools_used_json, artifacts_produced_json,
                    success, error_summary, duration_seconds, outcome_quality,
                    created_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    exp.activity_id, exp.goal, exp.domain, exp.status,
                    exp.node_count,
                    json.dumps(exp.agent_ids),
                    json.dumps(exp.tools_used),
                    json.dumps(exp.artifacts_produced),
                    1 if exp.success else 0,
                    exp.error_summary, exp.duration_seconds,
                    exp.outcome_quality,
                    exp.created_at.isoformat(),
                    json.dumps(exp.metadata),
                ),
            )
        return exp

    def get_experience(self, activity_id: str) -> ExperienceSummary | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM experience_summaries WHERE activity_id=?",
                (activity_id,),
            ).fetchone()
            if row is None:
                return None
            return _row_to_experience(row)

    def get_experiences_by_domain(self, domain: str, limit: int = 50) -> list[ExperienceSummary]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM experience_summaries
                   WHERE domain=? ORDER BY created_at DESC LIMIT ?""",
                (domain, limit),
            ).fetchall()
            return [_row_to_experience(r) for r in rows]

    def get_all_experiences(self, limit: int = 100) -> list[ExperienceSummary]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM experience_summaries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_row_to_experience(r) for r in rows]

    def get_experience_count(self) -> int:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM experience_summaries").fetchone()
            return row[0] if row else 0

    def delete_experience(self, activity_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM experience_summaries WHERE activity_id=?",
                (activity_id,),
            )

    # ── Aggregate helpers ──────────────────────────────────────────────

    def get_statistics(self) -> dict[str, Any]:
        """Return summary statistics about stored knowledge and experiences."""
        exp_count = self.get_experience_count()
        k_counts = self.count_knowledge()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM knowledge_items").fetchone()
            total_knowledge = row[0] if row else 0
        return {
            "total_experiences": exp_count,
            "total_knowledge_items": total_knowledge,
            "knowledge_by_category": k_counts,
            "domains": self._get_domains(),
        }

    def _get_domains(self) -> list[str]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT DISTINCT domain FROM experience_summaries ORDER BY domain"
            ).fetchall()
            return [r["domain"] for r in rows]


def _row_to_knowledge(row: sqlite3.Row) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=row["knowledge_id"],
        category=row["category"],
        claim=row["claim"],
        confidence=row["confidence"],
        evidence_count=row["evidence_count"],
        source_activity_ids=json.loads(row["source_activity_ids_json"]),
        source_pattern_keys=json.loads(row["source_pattern_keys_json"]),
        tags=json.loads(row["tags_json"]),
        created_at=_parse_dt(row["created_at"]),
        last_validated=_parse_dt(row["last_validated"]),
        metadata=json.loads(row["metadata_json"]),
    )


def _row_to_experience(row: sqlite3.Row) -> ExperienceSummary:
    return ExperienceSummary(
        activity_id=row["activity_id"],
        goal=row["goal"],
        domain=row["domain"],
        status=row["status"],
        node_count=row["node_count"],
        agent_ids=json.loads(row["agent_ids_json"]),
        tools_used=json.loads(row["tools_used_json"]),
        artifacts_produced=json.loads(row["artifacts_produced_json"]),
        success=bool(row["success"]),
        error_summary=row["error_summary"],
        duration_seconds=row["duration_seconds"],
        outcome_quality=row["outcome_quality"],
        created_at=_parse_dt(row["created_at"]),
        metadata=json.loads(row["metadata_json"]),
    )


def _parse_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None
