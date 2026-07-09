"""Frozen contract for the Reasoning stage output.

``ReasoningResult`` is the single canonical artifact produced by the
Reasoning stage and consumed by all downstream stages (Planner,
Execution, Reflection, Explainability).  It replaces the ad-hoc
``reasoning_assessment`` dict with a typed, frozen, deterministic,
and replayable contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.research.reasoner import Contradiction
from core.research.reasoning import Belief, CounterHypothesis, EvidenceItem


@dataclass(frozen=True)
class ReasoningResult:
    """Canonical output of the Reasoning stage.

    Every downstream stage reads from this artifact.  No other stage
    may construct a ``ReasoningResult`` (enforced by architecture Rule 48).
    """

    reasoning_id: str
    """Unique identifier for this reasoning pass."""

    activity_id: str
    """Activity graph node id this reasoning is attached to."""

    complexity: str
    """One of ``"simple"``, ``"multi_step"``, ``"agentic"`` (legacy classifier)."""

    beliefs: tuple[Belief, ...] = ()
    """Beliefs constructed by the ReasoningEngine."""

    evidence: tuple[EvidenceItem, ...] = ()
    """Evidence items collected and linked to beliefs."""

    contradictions: tuple[Contradiction, ...] = ()
    """Cross-source contradictions detected by FactReasoner."""

    counter_hypotheses: tuple[CounterHypothesis, ...] = ()
    """Counter-hypotheses generated to challenge uncertain beliefs."""

    confidence: float = 0.5
    """Overall reasoning confidence derived from belief revision."""

    reasoning_trace: tuple[str, ...] = ()
    """Ordered trace of reasoning steps for replay and explainability."""

    metadata: Mapping[str, Any] = field(default_factory=dict)
    """Extensible bag for stage-specific metadata."""

    def to_assessment_dict(self) -> dict[str, Any]:
        """Backward-compatible representation for ``context.reasoning_assessment``.

        Produces the same shape that the existing PlannerStage expects,
        allowing incremental migration away from the legacy dict format.
        """
        return {
            "complexity": self.complexity,
            "requirements": self.metadata.get("requirements", []),
            "constraints": self.metadata.get("constraints", []),
            "confidence": self.confidence,
            "estimated_steps": self.metadata.get("estimated_steps", 1),
            "routing_hints": {
                "prefer_local": False,
            },
            "metadata": {
                "reasoning_id": self.reasoning_id,
                "belief_count": len(self.beliefs),
                "evidence_count": len(self.evidence),
                "contradiction_count": len(self.contradictions),
                "counter_hypothesis_count": len(self.counter_hypotheses),
            },
        }
