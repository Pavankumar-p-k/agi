"""Phase 11 — Multi-Agent Collaboration data models.

CollaborationSession: a session where multiple agents work together
ReviewRound: one round of review/feedback cycle
ArtifactReview: structured feedback from one agent on another's work
ConsensusVote: a vote during consensus resolution
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class CollaborationStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    IN_NEGOTIATION = "IN_NEGOTIATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


class ReviewDecision(str, enum.Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECTED = "REJECTED"


class VoteValue(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"


@dataclass
class ArtifactVersion:
    """A versioned artifact produced by an agent during collaboration."""
    version_id: str
    agent_id: str
    content: str
    description: str = ""
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactReview:
    """Structured review feedback from one agent on another's artifact."""
    review_id: str
    reviewer_id: str
    artifact_version_id: str
    decision: ReviewDecision
    comments: str = ""                               # summary feedback
    issues: list[str] = field(default_factory=list)  # specific issues
    suggestions: list[str] = field(default_factory=list)  # improvement ideas
    score: float = 0.5                               # 0.0-1.0 quality score
    timestamp: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "reviewer_id": self.reviewer_id,
            "decision": self.decision.value,
            "comments": self.comments,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "score": self.score,
        }


@dataclass
class ConsensusVote:
    """A single vote during consensus resolution."""
    voter_id: str
    vote: VoteValue
    rationale: str = ""


@dataclass
class ReviewRound:
    """One review cycle: producer creates version, reviewer provides feedback."""
    round_number: int
    artifact_version: ArtifactVersion
    review: ArtifactReview | None = None
    resolved: bool = False
    created_at: datetime | None = None


@dataclass
class CollaborationSession:
    """A multi-agent collaboration session.

    Lifecycle:
      PENDING → IN_PROGRESS → IN_REVIEW → (IN_NEGOTIATION → IN_REVIEW)* → COMPLETED
    """
    session_id: str
    goal: str                                          # what the session aims to produce
    primary_agent_id: str                              # lead agent
    reviewer_agent_ids: list[str] = field(default_factory=list)  # assigned reviewers
    status: CollaborationStatus = CollaborationStatus.PENDING
    review_rounds: list[ReviewRound] = field(default_factory=list)
    final_artifact: str | None = None                  # accepted final content
    votes: list[ConsensusVote] = field(default_factory=list)
    max_review_rounds: int = 3                         # escalation after this
    created_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def current_round(self) -> int:
        return len(self.review_rounds)

    @property
    def latest_version(self) -> ArtifactVersion | None:
        if not self.review_rounds:
            return None
        return self.review_rounds[-1].artifact_version

    @property
    def latest_review(self) -> ArtifactReview | None:
        if not self.review_rounds:
            return None
        return self.review_rounds[-1].review

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "primary_agent_id": self.primary_agent_id,
            "reviewer_agent_ids": self.reviewer_agent_ids,
            "status": self.status.value,
            "current_round": self.current_round,
            "max_review_rounds": self.max_review_rounds,
            "votes": [{"voter": v.voter_id, "vote": v.vote.value} for v in self.votes],
        }
