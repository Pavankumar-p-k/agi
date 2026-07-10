"""NegotiationEngine — collects multi-agent opinions, finds consensus,
identifies dissent, and resolves sessions.

Consensus algorithm:
  1. Group opinions by position (the strategy/approach they recommend)
  2. Score each position by weighted confidence sum (higher confidence = more weight)
  3. Pick the position with the highest weighted score
  4. Any agent whose top choice differs from consensus is marked as dissent
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from core.negotiation.agents import (
    ExecutionAgent,
    PlannerAgent,
    ResearchAgent,
    ReviewerAgent,
    RiskAgent,
)
from core.negotiation.models import AgentOpinion, ConsensusResult
from core.storage import SYSTEM_DB

logger = logging.getLogger(__name__)

_DEFAULT_DB = SYSTEM_DB

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS negotiations (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    opinions TEXT NOT NULL DEFAULT '[]',
    consensus TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
"""


class NegotiationEngine:
    """Multi-agent negotiation coordinator."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(_TABLE_SQL)

    # ── Agent collection ──────────────────────────────────────────────────

    def _collect_opinions(self, goal: str) -> list[AgentOpinion]:
        """Collect opinions from all 5 agents."""
        agents = [
            PlannerAgent(),
            ResearchAgent(),
            RiskAgent(),
            ReviewerAgent(),
            ExecutionAgent(),
        ]
        opinions = []
        for agent in agents:
            try:
                opinion = agent.produce_opinion(goal)
                opinions.append(opinion)
            except Exception as e:
                logger.warning("Agent %s failed: %s", agent.__class__.__name__, e)
                opinions.append(AgentOpinion(
                    agent_name=agent.__class__.__name__.replace("Agent", "").lower(),
                    position="error",
                    confidence=0.0,
                    reasoning=f"Agent error: {e}",
                ))
        return opinions

    # ── Consensus ─────────────────────────────────────────────────────────

    def _find_consensus(self, opinions: list[AgentOpinion]) -> ConsensusResult:
        """Find consensus by weighting opinions by confidence and grouping by position."""
        if not opinions:
            return ConsensusResult(
                decision="no_opinions",
                confidence=0.0,
                reasoning="No agent opinions collected",
            )

        # Group by position, sum weighted confidence
        position_scores: dict[str, float] = {}
        agent_scores: dict[str, float] = {}
        for op in opinions:
            pos = op.position
            weighted = op.confidence * (1.0 / max(len(opinions), 1))
            position_scores[pos] = position_scores.get(pos, 0) + weighted
            agent_scores[op.agent_name] = op.confidence

        # Pick highest-scored position
        if not position_scores:
            return ConsensusResult(
                decision="no_agreement",
                confidence=0.0,
                reasoning="No positions to evaluate",
            )

        decision, max_score = max(position_scores.items(), key=lambda x: x[1])
        confidence = min(1.0, max_score * len(opinions))

        # Find dissenters: agents whose position differs from consensus
        dissent = []
        for op in opinions:
            if op.position != decision and op.confidence > 0.3:
                dissent.append(op.agent_name)

        # Build reasoning
        agent_summaries = [f"{op.agent_name}: {op.position} ({op.confidence:.0%})" for op in opinions]
        reasoning = f"Consensus: {decision}. " + "; ".join(agent_summaries)
        if dissent:
            reasoning += f". Dissent: {', '.join(dissent)}"

        return ConsensusResult(
            decision=decision,
            confidence=round(confidence, 2),
            reasoning=reasoning[:300],
            dissent=dissent,
            individual_scores=agent_scores,
        )

    # ── Session lifecycle ────────────────────────────────────────────────

    def create_session(self, goal: str) -> dict[str, Any]:
        """Create a negotiation session for a goal."""
        session_id = f"neg_{uuid.uuid4().hex[:12]}"
        opinions = self._collect_opinions(goal)
        consensus = self._find_consensus(opinions)
        now = datetime.utcnow().isoformat()

        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO negotiations
                   (id, goal, status, opinions, consensus, created_at)
                   VALUES (?, ?, 'open', ?, ?, ?)""",
                (session_id, goal, json.dumps([o.to_dict() for o in opinions]),
                 json.dumps(consensus.to_dict()), now),
            )

        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM negotiations WHERE id = ?", (session_id,)
            ).fetchone()
        if not row:
            return None
        return self._decode(dict(row))

    def list_sessions(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM negotiations WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM negotiations ORDER BY created_at DESC"
                ).fetchall()
        return [self._decode(dict(r)) for r in rows]

    def resolve_session(self, session_id: str, accepted: bool = True) -> dict[str, Any] | None:
        """Mark a session as resolved (accepted) or rejected."""
        status = "accepted" if accepted else "rejected"
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE negotiations SET status = ?, resolved_at = ? WHERE id = ?",
                (status, now, session_id),
            )
        return self.get_session(session_id)

    def renegotiate(self, session_id: str) -> dict[str, Any] | None:
        """Re-collect opinions and re-compute consensus for an existing session."""
        session = self.get_session(session_id)
        if not session:
            return None
        return self.create_session(session["goal"])

    @staticmethod
    def _decode(row: dict) -> dict:
        for key in ("opinions", "consensus"):
            if isinstance(row.get(key), str):
                try:
                    row[key] = json.loads(row[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return row
