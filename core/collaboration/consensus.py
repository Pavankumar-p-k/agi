"""ConsensusEngine — deterministic voting and agreement detection for multi-agent collaboration.

Canonical flow:
  ArtifactReview → ConsensusVote → ReviewDecision

Rules:
- APPROVED: majority approves, no rejections → immediate pass
- CHANGES_REQUESTED: majority requests changes → revise
- TIE: escalate to tiebreaker (primary agent casts deciding vote)
- REJECTED: any rejection → fail unless supermajority (>=2/3) overrides
"""

from __future__ import annotations

import logging
from typing import Any

from core.collaboration.models import ArtifactReview, ConsensusVote, ReviewDecision, VoteValue

logger = logging.getLogger(__name__)


class ConsensusEngine:
    """Deterministic consensus resolution for multi-agent collaboration.

    Canonical flow:
      resolve(reviews, tiebreaker_vote) → ReviewDecision

    Internally converts ArtifactReview → ConsensusVote → Decision.
    """

    def __init__(self, supermajority_threshold: float = 2.0 / 3.0):
        self.supermajority_threshold = supermajority_threshold

    def resolve(self, reviews: list[ArtifactReview],
                tiebreaker_vote: VoteValue | None = None) -> ReviewDecision:
        """Canonical entry point. ArtifactReview → ReviewDecision.

        Args:
            reviews: List of ArtifactReview from reviewer agents.
            tiebreaker_vote: Optional tiebreaker from primary agent.

        Returns:
            Resolved ReviewDecision.
        """
        votes = self.reviews_to_votes(reviews)
        return self._resolve_votes(votes, tiebreaker_vote)

    def reviews_to_votes(self, reviews: list[ArtifactReview]) -> list[ConsensusVote]:
        """Convert ArtifactReview list to ConsensusVote list."""
        return [
            ConsensusVote(
                voter_id=r.reviewer_id,
                vote=self._review_to_vote_value(r.decision),
                rationale=r.comments,
            )
            for r in reviews
        ]

    def _resolve_votes(self, votes: list[ConsensusVote],
                        tiebreaker_vote: VoteValue | None = None) -> ReviewDecision:
        """Core voting logic operating on ConsensusVote objects."""
        if not votes:
            return ReviewDecision.APPROVED

        approves = sum(1 for v in votes if v.vote == VoteValue.APPROVE)
        changes = sum(1 for v in votes if v.vote == VoteValue.ABSTAIN)
        rejects = sum(1 for v in votes if v.vote == VoteValue.REJECT)
        total = len(votes)

        # Rule 1: Any rejection without supermajority override → REJECTED
        if rejects > 0:
            override_ratio = approves / total if total > 0 else 0
            if override_ratio <= self.supermajority_threshold:
                return ReviewDecision.REJECTED
            return ReviewDecision.CHANGES_REQUESTED

        # Rule 2: All approve → APPROVED
        if approves == total:
            return ReviewDecision.APPROVED

        # Rule 3: Majority approve
        if approves > changes and approves > 0:
            return ReviewDecision.APPROVED

        # Rule 4: Majority changes requested
        if changes > approves:
            return ReviewDecision.CHANGES_REQUESTED

        # Rule 5: Tie — use tiebreaker
        if tiebreaker_vote == VoteValue.APPROVE:
            return ReviewDecision.APPROVED
        elif tiebreaker_vote == VoteValue.REJECT:
            return ReviewDecision.REJECTED
        else:
            return ReviewDecision.CHANGES_REQUESTED

    def count_votes(self, votes: list[ConsensusVote]) -> dict[str, int]:
        """Tally votes for each value."""
        counts = {v.value: 0 for v in VoteValue}
        for vote in votes:
            if vote.vote.value in counts:
                counts[vote.vote.value] += 1
        return counts

    def needs_tiebreaker(self, votes: list[ConsensusVote]) -> bool:
        """Check if a tiebreaker vote is needed (approve == reject)."""
        counts = self.count_votes(votes)
        return counts["APPROVE"] == counts["REJECT"] and counts["APPROVE"] > 0

    @staticmethod
    def _review_to_vote_value(decision: ReviewDecision) -> VoteValue:
        mapping = {
            ReviewDecision.APPROVED: VoteValue.APPROVE,
            ReviewDecision.CHANGES_REQUESTED: VoteValue.ABSTAIN,
            ReviewDecision.REJECTED: VoteValue.REJECT,
        }
        return mapping.get(decision, VoteValue.ABSTAIN)
