"""CollaborationCoordinator — manages the lifecycle of multi-agent collaboration sessions.

Architecture:
  produce → review → negotiate → consensus → revise/complete

Uses ConsensusEngine for deterministic voting (supermajority, tiebreaker)
and NegotiationEngine for resolving disagreements before consensus.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Callable

from core.collaboration.models import (
    ArtifactReview,
    ArtifactVersion,
    CollaborationSession,
    CollaborationStatus,
    ReviewDecision,
    ReviewRound,
)
from core.collaboration.consensus import ConsensusEngine
from core.collaboration.negotiation import NegotiationEngine

logger = logging.getLogger(__name__)

AgentExecuteFn = Callable[[str, str], str]
AgentReviewFn = Callable[[str, str, str], ArtifactReview]


class CollaborationCoordinator:
    """Orchestrates multi-agent collaboration sessions with negotiation and consensus.

    Flow per review round:
      1. Collect reviews from all reviewers
      2. Negotiate to resolve disagreements (may escalate)
      3. ConsensusEngine produces final decision (supermajority, tiebreaker)
      4. APPROVED → complete
      5. Not approved + max rounds reached → escalate
      6. Not approved + rounds remaining → revise and repeat
    """

    def __init__(self,
                 consensus_engine: ConsensusEngine | None = None,
                 negotiation_engine: NegotiationEngine | None = None):
        self._sessions: dict[str, CollaborationSession] = {}
        self.consensus = consensus_engine or ConsensusEngine()
        self.negotiation = negotiation_engine or NegotiationEngine()

    def create_session(self, goal: str, primary_agent: str,
                       reviewers: list[str] | None = None,
                       max_rounds: int = 3) -> CollaborationSession:
        session_id = f"col_{uuid.uuid4().hex[:12]}"
        session = CollaborationSession(
            session_id=session_id,
            goal=goal,
            primary_agent_id=primary_agent,
            reviewer_agent_ids=reviewers or [],
            max_review_rounds=max_rounds,
            status=CollaborationStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        self._sessions[session_id] = session
        logger.info("Coordinator: created session %s (primary=%s, reviewers=%s)",
                     session_id, primary_agent, reviewers)
        return session

    def get_session(self, session_id: str) -> CollaborationSession | None:
        return self._sessions.get(session_id)

    def run_full_session(self, session_id: str,
                         execute_fn: AgentExecuteFn,
                         review_fn: AgentReviewFn) -> CollaborationSession:
        """Run a complete collaboration session.

        Flow per round:
          produce → review → negotiate → consensus → revise/complete
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Unknown session: {session_id}")

        if session.status != CollaborationStatus.PENDING:
            raise ValueError(f"Session {session_id} already started")

        session.status = CollaborationStatus.IN_PROGRESS

        # Phase 1: Primary agent produces initial artifact
        initial_content = execute_fn(session.primary_agent_id, session.goal)
        initial_version = ArtifactVersion(
            version_id=f"v_{uuid.uuid4().hex[:8]}",
            agent_id=session.primary_agent_id,
            content=initial_content,
            description="Initial draft",
            timestamp=datetime.utcnow(),
        )

        first_round = ReviewRound(
            round_number=1,
            artifact_version=initial_version,
            created_at=datetime.utcnow(),
        )
        session.review_rounds.append(first_round)
        session.status = CollaborationStatus.IN_REVIEW

        # Phase 2: Review → negotiate → consensus → revise cycle
        for round_num in range(1, session.max_review_rounds + 1):
            current_round = session.review_rounds[-1]
            artifact = current_round.artifact_version

            # Collect reviews from all reviewers
            reviews: list[ArtifactReview] = []
            for reviewer_id in session.reviewer_agent_ids:
                review = review_fn(reviewer_id, artifact.content, session.goal)
                reviews.append(review)

            # Step 1: Negotiation — resolve disagreements
            session = self.negotiation.negotiate(
                session, reviews, negotiation_round=round_num,
            )
            if session.status == CollaborationStatus.ESCALATED:
                session.final_artifact = artifact.content
                session.completed_at = datetime.utcnow()
                logger.info("Coordinator: session %s escalated during negotiation (round %d)",
                            session_id, round_num)
                return session

            # Step 2: Consensus — final decision
            overall_decision = self.consensus.resolve(reviews)
            current_round.review = reviews[0] if reviews else None
            current_round.resolved = (overall_decision == ReviewDecision.APPROVED)

            if current_round.resolved:
                session.final_artifact = artifact.content
                session.status = CollaborationStatus.COMPLETED
                session.completed_at = datetime.utcnow()
                logger.info("Coordinator: session %s completed (round %d)", session_id, round_num)
                return session

            if round_num >= session.max_review_rounds:
                session.status = CollaborationStatus.ESCALATED
                session.final_artifact = artifact.content
                session.completed_at = datetime.utcnow()
                logger.info("Coordinator: session %s escalated (round %d)", session_id, round_num)
                return session

            # Step 3: Producer revises based on feedback
            feedback_text = self._format_reviews(reviews)
            revision_prompt = (
                f"{session.goal}\n\n"
                f"Previous version:\n{artifact.content}\n\n"
                f"Feedback:\n{feedback_text}\n\n"
                f"Revise."
            )
            revised_content = execute_fn(session.primary_agent_id, revision_prompt)

            next_version = ArtifactVersion(
                version_id=f"v_{uuid.uuid4().hex[:8]}",
                agent_id=session.primary_agent_id,
                content=revised_content,
                description=f"Revision {round_num + 1}",
                timestamp=datetime.utcnow(),
            )

            next_round = ReviewRound(
                round_number=round_num + 1,
                artifact_version=next_version,
                created_at=datetime.utcnow(),
            )
            session.review_rounds.append(next_round)
            session.status = CollaborationStatus.IN_REVIEW

        session.status = CollaborationStatus.FAILED
        session.completed_at = datetime.utcnow()
        return session

    @staticmethod
    def _format_reviews(reviews: list[ArtifactReview]) -> str:
        parts: list[str] = []
        for review in reviews:
            parts.append(f"Reviewer {review.reviewer_id} ({review.decision.value}):")
            if review.comments:
                parts.append(f"  {review.comments}")
            for issue in review.issues:
                parts.append(f"  - Issue: {issue}")
            for suggestion in review.suggestions:
                parts.append(f"  - Suggestion: {suggestion}")
        return "\n".join(parts)
