"""Module: core.planner.evidence
Evidence recording for planner replanning decisions.
Every replan records: what failed, why, what alternatives existed,
why this alternative was selected, what changed, and whether the revised
execution succeeded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class EvidenceSource(str, Enum):
    AGENT_EXECUTION = "agent_execution"
    STATE_MACHINE = "state_machine"
    STRATEGY_COMPARISON = "strategy_comparison"
    REPLAN_DECISION = "replan_decision"
    VERIFICATION = "verification"


@dataclass
class FailureEvidence:
    """Record of why a step/subgoal failed."""

    source: EvidenceSource
    step_id: str
    error: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: int = 0  # index/proxy for execution order


@dataclass
class ReplanEvidence:
    """Record of a replanning decision."""

    source: EvidenceSource
    failed_step_id: str
    failure_evidence: FailureEvidence
    available_strategies: List[str] = field(default_factory=list)
    selected_strategy: str | None = None
    selection_reason: str | None = None
    original_plan_hash: str = ""
    revised_plan_hash: str = ""
    timestamp: int = 0


@dataclass
class StrategyComparisonEvidence:
    """Record of strategy comparison reasoning."""

    source: EvidenceSource
    failed_step_id: str
    compared_strategies: List[str] = field(default_factory=list)
    comparison_criteria: Dict[str, Any] = field(default_factory=dict)
    ranking: List[tuple[str, float]] = field(default_factory=list)  # (strategy_id, score)
    selected_strategy_id: str | None = None
    explanation: str = ""
    timestamp: int = 0


@dataclass
class VerificationEvidence:
    """Record of execution verification."""

    source: EvidenceSource
    step_id: str
    execution_result: dict[str, Any]
    verification_status: str  # "verified", "unverified", "failed_verification"
    verification_details: dict[str, Any] = field(default_factory=dict)
    timestamp: int = 0


@dataclass
class PlannerEvidence:
    """Aggregate evidence for a complete planner lifecycle."""

    failure_evidence: FailureEvidence | None = None
    replan_evidence: ReplanEvidence | None = None
    comparison_evidence: StrategyComparisonEvidence | None = None
    verification_evidence: VerificationEvidence | None = None
    success: bool | None = None
    terminal_state: str | None = None

    def mark_failure(
        self, step_id: str, error: str, context: dict[str, Any] | None = None
    ) -> FailureEvidence:
        """Record a failure and return the evidence."""
        fe = FailureEvidence(
            source=EvidenceSource.AGENT_EXECUTION,
            step_id=step_id,
            error=error,
            context=context or {},
            timestamp=len(self._failure_evidence) if hasattr(self, "_failure_evidence") else 0,
        )
        self.failure_evidence = fe
        return fe

    def mark_replan(
        self,
        failed_step_id: str,
        failure_evidence: FailureEvidence,
        available_strategies: List[str],
        selected_strategy: str | None = None,
        selection_reason: str | None = None,
        original_plan_hash: str = "",
        revised_plan_hash: str = "",
    ) -> ReplanEvidence:
        """Record a replanning decision and return the evidence."""
        re = ReplanEvidence(
            source=EvidenceSource.REPLAN_DECISION,
            failed_step_id=failed_step_id,
            failure_evidence=failure_evidence,
            available_strategies=available_strategies,
            selected_strategy=selected_strategy,
            selection_reason=selection_reason,
            original_plan_hash=original_plan_hash,
            revised_plan_hash=revised_plan_hash,
            timestamp=len(self._replan_evidence) if hasattr(self, "_replan_evidence") else 0,
        )
        self.replan_evidence = re
        return re

    def mark_comparison(
        self,
        failed_step_id: str,
        compared_strategies: List[str],
        comparison_criteria: Dict[str, Any],
        ranking: List[tuple[str, float]],
        selected_strategy_id: str | None = None,
        explanation: str = "",
    ) -> StrategyComparisonEvidence:
        """Record strategy comparison and return the evidence."""
        ce = StrategyComparisonEvidence(
            source=EvidenceSource.STRATEGY_COMPARISON,
            failed_step_id=failed_step_id,
            compared_strategies=compared_strategies,
            comparison_criteria=comparison_criteria,
            ranking=ranking,
            selected_strategy_id=selected_strategy_id,
            explanation=explanation,
            timestamp=len(self._comparison_evidence) if hasattr(self, "_comparison_evidence") else 0,
        )
        self.comparison_evidence = ce
        return ce

    def mark_verification(
        self, step_id: str, execution_result: dict[str, Any], verification_status: str,
        verification_details: dict[str, Any] | None = None,
    ) -> VerificationEvidence:
        """Record verification evidence and return it."""
        ve = VerificationEvidence(
            source=EvidenceSource.VERIFICATION,
            step_id=step_id,
            execution_result=execution_result,
            verification_status=verification_status,
            verification_details=verification_details or {},
            timestamp=len(self._verification_evidence) if hasattr(self, "_verification_evidence") else 0,
        )
        self.verification_evidence = ve
        return ve