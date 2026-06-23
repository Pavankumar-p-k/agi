"""Phase 14.0 — Principle Store.

SQLite-backed persistence for:
  - PrincipleDataPoints (experimental evidence)
  - Accepted/Candidate Principles

Lives in the same `principles.db` as the StructuralPropertyRegistry.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.generalization.models import (
    ImprovementProposal,
    Principle,
    PrincipleCandidate,
    PrincipleDataPoint,
    PrincipleStatus,
    ProposalStatus,
    SystemType,
)

logger = logging.getLogger(__name__)


class PrincipleStore:
    """Persistent store for principles and evidence data points.

    Thread-safe, SQLite-backed, shares DB with StructuralPropertyRegistry.
    """

    def __init__(self, db_path: str = ""):
        if not db_path:
            data_dir = Path.home() / ".jarvis"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "principles.db")
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS principle_data_points (
                    point_id TEXT PRIMARY KEY,
                    system_id TEXT NOT NULL,
                    system_type TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    properties_json TEXT NOT NULL DEFAULT '{}',
                    domain TEXT DEFAULT '',
                    session_id TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS principles (
                    principle_id TEXT PRIMARY KEY,
                    property_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    support_rate REAL NOT NULL,
                    control_rate REAL NOT NULL,
                    discrimination REAL NOT NULL,
                    sample_size INTEGER NOT NULL,
                    support_count INTEGER NOT NULL,
                    control_count INTEGER NOT NULL,
                    domains_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    accepted_at TEXT,
                    evidence_point_ids_json TEXT NOT NULL DEFAULT '[]'
                );

                CREATE INDEX IF NOT EXISTS idx_points_system
                    ON principle_data_points(system_id);
                CREATE INDEX IF NOT EXISTS idx_points_domain
                    ON principle_data_points(domain);
                CREATE INDEX IF NOT EXISTS idx_principles_status
                    ON principles(status);

                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    target_system TEXT NOT NULL,
                    proposal_type TEXT NOT NULL,
                    principle_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    expected_improvement REAL NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'generated',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_proposals_status
                    ON proposals(status);
                CREATE INDEX IF NOT EXISTS idx_proposals_target
                    ON proposals(target_system);
            """)

    # ── Data Points ──────────────────────────────────────────────

    def save_data_point(self, point: PrincipleDataPoint) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO principle_data_points
                   (point_id, system_id, system_type, success,
                    properties_json, domain, session_id, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (point.point_id, point.system_id, point.system_type.value,
                 1 if point.success else 0,
                 json.dumps(point.properties),
                 point.domain, point.session_id,
                 point.timestamp.isoformat()),
            )

    def save_data_points(self, points: list[PrincipleDataPoint]) -> None:
        with self._lock, self._conn() as conn:
            for point in points:
                conn.execute(
                    """INSERT OR REPLACE INTO principle_data_points
                       (point_id, system_id, system_type, success,
                        properties_json, domain, session_id, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (point.point_id, point.system_id, point.system_type.value,
                     1 if point.success else 0,
                     json.dumps(point.properties),
                     point.domain, point.session_id,
                     point.timestamp.isoformat()),
                )

    def get_data_point(self, point_id: str) -> PrincipleDataPoint | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM principle_data_points WHERE point_id = ?",
                (point_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_point(row)

    def list_data_points(self, system_id: str | None = None,
                         domain: str | None = None,
                         limit: int = 0) -> list[PrincipleDataPoint]:
        with self._lock, self._conn() as conn:
            query = "SELECT * FROM principle_data_points WHERE 1=1"
            params: list[str] = []
            if system_id:
                query += " AND system_id = ?"
                params.append(system_id)
            if domain:
                query += " AND domain = ?"
                params.append(domain)
            query += " ORDER BY timestamp DESC"
            if limit:
                query += f" LIMIT {limit}"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_point(r) for r in rows]

    def count_data_points(self, system_id: str | None = None,
                          domain: str | None = None) -> int:
        with self._lock, self._conn() as conn:
            query = "SELECT COUNT(*) as cnt FROM principle_data_points WHERE 1=1"
            params: list[str] = []
            if system_id:
                query += " AND system_id = ?"
                params.append(system_id)
            if domain:
                query += " AND domain = ?"
                params.append(domain)
            row = conn.execute(query, params).fetchone()
            return row["cnt"] if row else 0

    # ── Principles ───────────────────────────────────────────────

    def save_principle(self, principle: Principle) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO principles
                   (principle_id, property_name, category,
                    support_rate, control_rate, discrimination,
                    sample_size, support_count, control_count,
                    domains_json, confidence, status, accepted_at,
                    evidence_point_ids_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (principle.principle_id, principle.property_name,
                 principle.category,
                 principle.support_rate, principle.control_rate,
                 principle.discrimination,
                 principle.sample_size, principle.support_count,
                 principle.control_count,
                 json.dumps(principle.domains),
                 principle.confidence, principle.status.value,
                 principle.accepted_at.isoformat(),
                 json.dumps(principle.evidence_point_ids)),
            )

    def save_candidate_as_principle(self, candidate: PrincipleCandidate,
                                    evidence_point_ids: list[str] | None = None,
                                    ) -> Principle:
        """Promote a candidate to an accepted Principle and persist it."""
        principle = Principle(
            principle_id=candidate.principle_id,
            property_name=candidate.property_name,
            category=candidate.category,
            support_rate=candidate.support_rate,
            control_rate=candidate.control_rate,
            discrimination=candidate.discrimination,
            sample_size=candidate.sample_size,
            support_count=candidate.support_count,
            control_count=candidate.control_count,
            domains=list(candidate.domains),
            confidence=candidate.confidence,
            status=PrincipleStatus.ACCEPTED,
            accepted_at=datetime.now(timezone.utc),
            evidence_point_ids=evidence_point_ids or [],
        )
        self.save_principle(principle)
        return principle

    def get_principle(self, principle_id: str) -> Principle | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM principles WHERE principle_id = ?",
                (principle_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_principle(row)

    def list_principles(self, status: str | None = None,
                        category: str | None = None,
                        limit: int = 0) -> list[Principle]:
        with self._lock, self._conn() as conn:
            query = "SELECT * FROM principles WHERE 1=1"
            params: list[str] = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if category:
                query += " AND category = ?"
                params.append(category)
            query += " ORDER BY confidence DESC, discrimination DESC"
            if limit:
                query += f" LIMIT {limit}"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_principle(r) for r in rows]

    def clear(self) -> None:
        """Clear all data. Used for testing."""
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM principle_data_points")
            conn.execute("DELETE FROM principles")
            conn.execute("DELETE FROM proposals")

    # ── Proposals (Phase 14.1) ───────────────────────────────────

    def save_proposal(self, proposal: ImprovementProposal) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO proposals
                   (proposal_id, target_system, proposal_type,
                    principle_id, title, rationale,
                    expected_improvement, confidence, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (proposal.proposal_id, proposal.target_system,
                 proposal.proposal_type, proposal.principle_id,
                 proposal.title, proposal.rationale,
                 proposal.expected_improvement, proposal.confidence,
                 proposal.status.value, proposal.created_at.isoformat()),
            )

    def save_proposals(self, proposals: list[ImprovementProposal]) -> None:
        with self._lock, self._conn() as conn:
            for p in proposals:
                conn.execute(
                    """INSERT OR REPLACE INTO proposals
                       (proposal_id, target_system, proposal_type,
                        principle_id, title, rationale,
                        expected_improvement, confidence, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (p.proposal_id, p.target_system, p.proposal_type,
                     p.principle_id, p.title, p.rationale,
                     p.expected_improvement, p.confidence,
                     p.status.value, p.created_at.isoformat()),
                )

    def get_proposal(self, proposal_id: str) -> ImprovementProposal | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_proposal(row)

    def list_proposals(self, status: str | None = None,
                       target_system: str | None = None,
                       limit: int = 0) -> list[ImprovementProposal]:
        with self._lock, self._conn() as conn:
            query = "SELECT * FROM proposals WHERE 1=1"
            params: list[str] = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if target_system:
                query += " AND target_system = ?"
                params.append(target_system)
            query += " ORDER BY created_at DESC"
            if limit:
                query += f" LIMIT {limit}"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_proposal(r) for r in rows]

    def update_proposal_status(self, proposal_id: str,
                                status: ProposalStatus) -> bool:
        with self._lock, self._conn() as conn:
            c = conn.execute(
                "UPDATE proposals SET status = ? WHERE proposal_id = ?",
                (status.value, proposal_id),
            )
            return c.rowcount > 0

    def count_proposals(self, status: str | None = None) -> int:
        with self._lock, self._conn() as conn:
            query = "SELECT COUNT(*) as cnt FROM proposals WHERE 1=1"
            params: list[str] = []
            if status:
                query += " AND status = ?"
                params.append(status)
            row = conn.execute(query, params).fetchone()
            return row["cnt"] if row else 0

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _row_to_proposal(row: sqlite3.Row) -> ImprovementProposal:
        return ImprovementProposal(
            proposal_id=row["proposal_id"],
            target_system=row["target_system"],
            proposal_type=row["proposal_type"],
            principle_id=row["principle_id"],
            title=row["title"],
            rationale=row["rationale"],
            expected_improvement=row["expected_improvement"],
            confidence=row["confidence"],
            status=ProposalStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_point(row: sqlite3.Row) -> PrincipleDataPoint:
        return PrincipleDataPoint(
            point_id=row["point_id"],
            system_id=row["system_id"],
            system_type=SystemType(row["system_type"]),
            success=bool(row["success"]),
            properties=json.loads(row["properties_json"]),
            domain=row["domain"],
            session_id=row["session_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )

    @staticmethod
    def _row_to_principle(row: sqlite3.Row) -> Principle:
        return Principle(
            principle_id=row["principle_id"],
            property_name=row["property_name"],
            category=row["category"],
            support_rate=row["support_rate"],
            control_rate=row["control_rate"],
            discrimination=row["discrimination"],
            sample_size=row["sample_size"],
            support_count=row["support_count"],
            control_count=row["control_count"],
            domains=json.loads(row["domains_json"]),
            confidence=row["confidence"],
            status=PrincipleStatus(row["status"]),
            accepted_at=datetime.fromisoformat(row["accepted_at"])
                if row["accepted_at"] else datetime.now(timezone.utc),
            evidence_point_ids=json.loads(row["evidence_point_ids_json"]),
        )
