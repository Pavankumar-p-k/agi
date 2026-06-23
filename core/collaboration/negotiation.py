"""NegotiationEngine — resolves disagreements during multi-agent collaboration.

Provides deterministic conflict resolution strategies including:
- Position-based: agents state positions, negotiation finds the middle ground
- Escalation: passes to primary agent or human when agents cannot agree
- Concession: agents concede sub-points to reach consensus

Enforces max_negotiation_rounds to prevent infinite loops.
"""

from __future__ import annotations

import logging
from typing import Any

from core.collaboration.models import (
    ArtifactReview,
    CollaborationSession,
    CollaborationStatus,
    ReviewDecision,
)

logger = logging.getLogger(__name__)


class NegotiationEngine:
    """Deterministic negotiation and conflict resolution.

    Strategies (in order):
      1. Agreement detection: all approve → no negotiation needed
      2. Escalation: rejects outweigh approves → escalate
      3. Position-based: merge suggestions from disagreeing reviewers
      4. Concession: converge toward accepted points
    """

    def __init__(self, max_negotiation_rounds: int = 3):
        self.max_negotiation_rounds = max_negotiation_rounds

    def negotiate(self, session: CollaborationSession,
                  reviews: list[ArtifactReview],
                  negotiation_round: int = 1) -> CollaborationSession:
        """Run one round of negotiation to resolve review disagreements.

        Args:
            session: The collaboration session.
            reviews: Current round's reviews.
            negotiation_round: Current negotiation round (1-indexed).

        Returns:
            Session with updated status.
        """
        if session.status.value not in (CollaborationStatus.IN_REVIEW.value,
                                         CollaborationStatus.IN_NEGOTIATION.value):
            return session

        approves = [r for r in reviews if r.decision == ReviewDecision.APPROVED]
        rejects = [r for r in reviews if r.decision == ReviewDecision.REJECTED]

        # All approve — nothing to negotiate
        if len(approves) == len(reviews):
            return session

        # Enforce max rounds
        if negotiation_round > self.max_negotiation_rounds:
            logger.info("Negotiation: max rounds (%d) exceeded — escalating",
                        self.max_negotiation_rounds)
            session.status = CollaborationStatus.ESCALATED
            return session

        # Rejects outweigh approves — not negotiable
        if len(rejects) > len(approves):
            logger.info("Negotiation: rejecting outweighs approving — escalating")
            session.status = CollaborationStatus.ESCALATED
            return session

        session.status = CollaborationStatus.IN_NEGOTIATION

        total_issues = sum(len(r.issues) for r in reviews)
        total_suggestions = sum(len(r.suggestions) for r in reviews)
        if total_issues == 0 and total_suggestions == 0:
            session.status = CollaborationStatus.IN_REVIEW
            return session

        merged_suggestions = self._merge_suggestions(reviews)
        if merged_suggestions:
            logger.info("Negotiation: %d actionable suggestions for revision",
                        len(merged_suggestions))
        elif total_issues == 0:
            logger.info("Negotiation: all disagreements resolved (no issues, no suggestions)")
            session.status = CollaborationStatus.IN_REVIEW
        else:
            logger.info("Negotiation: %d unresolved issues remain", total_issues)

        return session

    def suggest_compromise(self, session: CollaborationSession,
                           reviews: list[ArtifactReview]) -> dict[str, Any]:
        """Generate a compromise proposal from conflicting reviews.

        Returns:
            dict with keys: action (revise/escalate), priority_issues, accepted_points.
        """
        approved_points: set[str] = set()
        rejected_points: set[str] = set()

        for review in reviews:
            for issue in review.issues:
                if review.decision == ReviewDecision.APPROVED:
                    approved_points.add(issue)
                else:
                    rejected_points.add(issue)
            for suggestion in review.suggestions:
                if review.decision == ReviewDecision.APPROVED:
                    approved_points.add(suggestion)
                else:
                    rejected_points.add(suggestion)

        issue_counts: dict[str, int] = {}
        for review in reviews:
            for issue in review.issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1

        priority_issues = [k for k, v in issue_counts.items() if v >= 2]

        return {
            "action": "revise" if priority_issues else "escalate",
            "priority_issues": priority_issues,
            "agreed_points": list(approved_points - rejected_points),
            "disputed_points": list(rejected_points - approved_points),
        }

    def _merge_suggestions(self, reviews: list[ArtifactReview]) -> list[str]:
        """Deduplicate and merge suggestions across reviews."""
        seen: set[str] = set()
        merged: list[str] = []
        for review in reviews:
            for suggestion in review.suggestions:
                normalized = suggestion.strip().lower()
                if normalized not in seen:
                    seen.add(normalized)
                    merged.append(suggestion)
        return merged
