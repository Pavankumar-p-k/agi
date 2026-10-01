"""Persistence for principles, data points and proposals."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from typing import Any, List, Optional

from core.generalization.models import (
    ImprovementProposal,
    Principle,
    PrincipleCandidate,
    PrincipleDataPoint,
    PrincipleStatus,
    ProposalStatus,
)


class PrincipleStore:
    """SQLite-backed store for the generalization subsystem."""

    def __init__(self, db_path: str = "data/principles.db") -> None:
        self.db_path = db_path
        if db_path and db_path != ":memory:":
            directory = os.path.dirname(os.path.abspath(db_path))
            if directory:
                os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS gen_data_points ("
                "point_id TEXT PRIMARY KEY, system_id TEXT, domain TEXT, data TEXT NOT NULL)"
            )
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS gen_principles ("
                "principle_id TEXT PRIMARY KEY, status TEXT, data TEXT NOT NULL)"
            )
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS gen_proposals ("
                "proposal_id TEXT PRIMARY KEY, status TEXT, target_system TEXT, data TEXT NOT NULL)"
            )
            self._conn.commit()

    # ── data points ──────────────────────────────────────────────────

    def save_data_point(self, point: PrincipleDataPoint) -> None:
        self._write(
            "INSERT OR REPLACE INTO gen_data_points "
            "(point_id, system_id, domain, data) VALUES (?, ?, ?, ?)",
            (point.point_id, point.system_id, point.domain,
             json.dumps(point.to_dict())),
        )

    def save_data_points(self, points: List[PrincipleDataPoint]) -> None:
        for point in points or []:
            self.save_data_point(point)

    def get_data_point(self, point_id: str) -> Optional[PrincipleDataPoint]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM gen_data_points WHERE point_id = ?", (point_id,)
            ).fetchone()
        return PrincipleDataPoint.from_dict(json.loads(row["data"])) if row else None

    def list_data_points(
        self, domain: Optional[str] = None, system_id: Optional[str] = None
    ) -> List[PrincipleDataPoint]:
        query = "SELECT data FROM gen_data_points"
        clauses, params = [], []
        if domain is not None:
            clauses.append("domain = ?")
            params.append(domain)
        if system_id is not None:
            clauses.append("system_id = ?")
            params.append(system_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._lock:
            rows = self._conn.execute(query, tuple(params)).fetchall()
        return [PrincipleDataPoint.from_dict(json.loads(r["data"])) for r in rows]

    def count_data_points(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM gen_data_points"
            ).fetchone()
        return int(row["n"])

    # ── principles ───────────────────────────────────────────────────

    def save_principle(self, principle: Principle) -> None:
        self._write(
            "INSERT OR REPLACE INTO gen_principles "
            "(principle_id, status, data) VALUES (?, ?, ?)",
            (principle.principle_id, getattr(principle.status, "value",
                                             principle.status),
             json.dumps(principle.to_dict())),
        )

    def save_candidate_as_principle(
        self, candidate: PrincipleCandidate,
        evidence_point_ids: Optional[List[str]] = None,
    ) -> Principle:
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
            evidence_point_ids=list(evidence_point_ids or []),
        )
        self.save_principle(principle)
        return principle

    def get_principle(self, principle_id: str) -> Optional[Principle]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM gen_principles WHERE principle_id = ?",
                (principle_id,),
            ).fetchone()
        return Principle.from_dict(json.loads(row["data"])) if row else None

    def list_principles(self, status: Optional[str] = None) -> List[Principle]:
        query = "SELECT data FROM gen_principles"
        params: tuple = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (getattr(status, "value", status),)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [Principle.from_dict(json.loads(r["data"])) for r in rows]

    # ── proposals ────────────────────────────────────────────────────

    def save_proposal(self, proposal: ImprovementProposal) -> None:
        self._write(
            "INSERT OR REPLACE INTO gen_proposals "
            "(proposal_id, status, target_system, data) VALUES (?, ?, ?, ?)",
            (proposal.proposal_id,
             getattr(proposal.status, "value", proposal.status),
             proposal.target_system, json.dumps(proposal.to_dict())),
        )

    def save_proposals(self, proposals: List[ImprovementProposal]) -> None:
        for proposal in proposals or []:
            self.save_proposal(proposal)

    def get_proposal(self, proposal_id: str) -> Optional[ImprovementProposal]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM gen_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        return ImprovementProposal.from_dict(json.loads(row["data"])) if row else None

    def list_proposals(
        self, status: Optional[str] = None,
        target_system: Optional[str] = None,
    ) -> List[ImprovementProposal]:
        query = "SELECT data FROM gen_proposals"
        clauses, params = [], []
        if status is not None:
            clauses.append("status = ?")
            params.append(getattr(status, "value", status))
        if target_system is not None:
            clauses.append("target_system = ?")
            params.append(target_system)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._lock:
            rows = self._conn.execute(query, tuple(params)).fetchall()
        return [ImprovementProposal.from_dict(json.loads(r["data"])) for r in rows]

    def count_proposals(self, status: Optional[str] = None) -> int:
        query = "SELECT COUNT(*) AS n FROM gen_proposals"
        params: tuple = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (getattr(status, "value", status),)
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        return int(row["n"])

    def update_proposal_status(self, proposal_id: str, status) -> bool:
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            return False
        proposal.status = ProposalStatus(getattr(status, "value", status))
        self.save_proposal(proposal)
        return True

    # ── misc ─────────────────────────────────────────────────────────

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM gen_data_points")
            self._conn.execute("DELETE FROM gen_principles")
            self._conn.execute("DELETE FROM gen_proposals")
            self._conn.commit()

    def _write(self, query: str, params: tuple) -> None:
        with self._lock:
            self._conn.execute(query, params)
            self._conn.commit()


def make_point_id() -> str:
    return f"pt_{uuid.uuid4().hex[:12]}"
