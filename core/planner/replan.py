"""Module: core.planner.replan
Genuine replanning logic for when a subgoal fails.

When a subgoal fails:
    1. identify failed subgoal
    2. preserve the original plan
    3. record failure reason/evidence
    4. determine whether retry is appropriate
    5. determine whether an alternate strategy exists
    6. compare available strategies
    7. choose the best permitted alternate
    8. create/update the revised plan
    9. execute the revised path
    10. verify the final result

The revised plan must be distinguishable from the original plan.
Do not simply retry the exact same operation and call that replanning.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

from core.planner.comparison import (
    ComparisonCriterion,
    ComparisonResult,
    StrategyProfile,
    StrategyComparator,
)
from core.planner.evidence import (
    FailureEvidence,
    PlannerEvidence,
    ReplanEvidence,
    StrategyComparisonEvidence,
    VerificationEvidence,
    EvidenceSource,
)
from core.planner.outcomes import determine_outcome, PlannerOutcome
from core.planner.state_machine import PlannerStateName, PlannerStateMachine
from core.planner.strategies import Strategy, StrategyRegistry


class ReplanDecision(Enum):
    """Possible replanning decisions."""

    RETRY_SAME = "retry_same"
    SWITCH_STRATEGY = "switch_strategy"
    ABORT = "abort"
    CONTINUE_ANYWAY = "continue_anyway"


@dataclass
class RevisedPlan:
    """A plan that differs from the original (has a different hash)."""

    original_plan_hash: str
    revised_plan_hash: str
    changes: List[str]  # human-readable description of changes
    strategy_id: str  # the strategy that was selected
    state_transition: PlannerStateName  # state machine transition


def _plan_hash(plan_description: str) -> str:
    """Compute a deterministic hash for a plan description."""
    return hashlib.sha256(plan_description.encode()).hexdigest()[:16]


def _revised_plan_description(
    original: str, strategy_id: str, changes: List[str],
) -> str:
    """Create a revised plan description that's distinguishable from the original."""
    changes_str = "; ".join(changes) if changes else "strategy switch"
    return f"{original} [via {strategy_id}: {changes_str}]"


class Replanner:
    """Handle replanning when a subgoal fails.

    Responsibilities:
    - Detect failure via mark_failed integration
    - Preserve original plan state
    - Record failure evidence
    - Compare available alternate strategies
    - Select the best permitted alternate
    - Create a revised plan distinguishable from the original
    - Transition the state machine appropriately
    """

    def __init__(
        self,
        state_machine: PlannerStateMachine,
        evidence: PlannerEvidence,
        strategy_registry: StrategyRegistry,
        comparator: StrategyComparator | None = None,
        max_retries: int = 3,
    ):
        self.state_machine = state_machine
        self.evidence = evidence
        self.strategy_registry = strategy_registry
        self.comparator = comparator or StrategyComparator()
        self.max_retries = max_retries
        self._retry_count: dict[str, int] = {}

    def handle_failure(
        self,
        step_id: str,
        error: str,
        context: dict[str, Any] | None = None,
        current_plan_desc: str | None = None,
    ) -> dict[str, Any]:
        """Handle a subgoal failure and initiate replanning.

        Returns a dict with:
        - decision: ReplanDecision
        - outcome: PlannerOutcome
        - evidence records updated
        - revised_plan info if a new path was chosen
        """
        # 1. Record failure evidence
        failure_evidence = self.evidence.mark_failure(
            step_id=step_id,
            error=error,
            context=context or {},
        )

        # 2. Record in state machine
        self.state_machine.transition(
            PlannerStateName.FAILED,
            reason=f"step {step_id} failed: {error}",
        )

        # 3. Check retry count
        retry_count = self._retry_count.get(step_id, 0)
        if retry_count < self.max_retries:
            # Try retrying the same strategy first
            self._retry_count[step_id] = retry_count + 1
            retry_decision = self._should_retry(step_id, error)
            if retry_decision:
                self.state_machine.transition(
                    PlannerStateName.RETRYING,
                    reason=f"retry #{retry_count + 1} for {step_id}",
                )
                return {
                    "decision": ReplanDecision.RETRY_SAME,
                    "outcome": PlannerOutcome.UNCONFIRMED,
                    "failure_evidence": failure_evidence,
                    "retry_count": retry_count + 1,
                }

        # 4. No more retries — move to replanning
        self.state_machine.transition(
            PlannerStateName.REPLANNING,
            reason=f"replanning after failure of {step_id}",
        )

        # 5. Identify available alternate strategies
        available = self.strategy_registry.get_viable()

        if not available:
            # No valid alternate strategies exist
            self.evidence.replan_evidence = (
                self.evidence.mark_replan(
                    failed_step_id=step_id,
                    failure_evidence=failure_evidence,
                    available_strategies=[],
                    selected_strategy=None,
                    selection_reason="no viable alternate strategies",
                    original_plan_hash=_plan_hash(current_plan_desc or ""),
                    revised_plan_hash="",
                )
                if self.evidence.replan_evidence is None
                else self.evidence.replan_evidence
            )
            self.state_machine.transition(
                PlannerStateName.ABORTED,
                reason="no viable alternate strategies — aborting",
            )
            return {
                "decision": ReplanDecision.ABORT,
                "outcome": PlannerOutcome.FAILURE,
                "failure_evidence": failure_evidence,
                "available_strategies": [],
                "selected_strategy": None,
            }

        # 6. Compare strategies using explicit criteria
        profiles = [StrategyProfile(
            strategy_id=s.strategy_id,
            description=s.description,
            preconditions=s.preconditions,
            required_capabilities=s.required_capabilities,
            risk=s.risk,
            cost=s.cost,
            expected_success=s.expected_success,
            verification_available=s.verification_available,
            fallback_relationship=s.fallback_relationship,
            previous_failure_count=retry_count,
        ) for s in available]

        comparison_result = self.comparator.compare(profiles=profiles)

        # 7. Record comparison evidence
        self.evidence.mark_comparison(
            failed_step_id=step_id,
            compared_strategies=[s.strategy_id for s in available],
            comparison_criteria={
                c.value: getattr(self.comparator, f"_{c.value}_score")  # simplified
                for c in ComparisonCriterion
                if c in comparison_result.criteria_used
            } if comparison_result.criteria_used else {},
            ranking=comparison_result.ranked_strategies,
            selected_strategy_id=comparison_result.selected_strategy_id,
            explanation=comparison_result.explanation,
        )

        selected_id = comparison_result.selected_strategy_id
        if selected_id is None:
            # Fallback: pick the first available
            selected_id = available[0].strategy_id

        selected_strategy = self.strategy_registry.get(selected_id)

        # 8. Record replan evidence
        changes: List[str] = []
        if selected_strategy and selected_strategy.preconditions:
            changes.append("new preconditions")
        if selected_strategy and selected_strategy.required_capabilities:
            changes.append(f"capabilities: {selected_strategy.required_capabilities}")

        revised_desc = _revised_plan_description(
            current_plan_desc or "unknown plan",
            selected_id,
            changes,
        )

        original_hash = _plan_hash(current_plan_desc or "unknown plan")
        revised_hash = _plan_hash(revised_desc)

        self.evidence.replan_evidence = self.evidence.mark_replan(
            failed_step_id=step_id,
            failure_evidence=failure_evidence,
            available_strategies=[s.strategy_id for s in available],
            selected_strategy=selected_id,
            selection_reason=comparison_result.explanation,
            original_plan_hash=original_hash,
            revised_plan_hash=revised_hash,
        )

        # 9. Transition state machine to REPLANNING → then RUNNING
        self.state_machine.transition(
            PlannerStateName.REPLANNING,
            reason=f"replan selected strategy {selected_id}",
        )

        return {
            "decision": ReplanDecision.SWITCH_STRATEGY,
            "outcome": PlannerOutcome.UNCONFIRMED,
            "failure_evidence": failure_evidence,
            "selected_strategy": selected_id,
            "selection_reason": comparison_result.explanation,
            "available_strategies": [s.strategy_id for s in available],
            "revised_plan_description": revised_desc,
            "original_plan_hash": original_hash,
            "revised_plan_hash": revised_hash,
            "comparison_explanation": comparison_result.explanation,
        }

    def _should_retry(self, step_id: str, error: str) -> bool:
        """Determine whether retrying the same strategy is appropriate.

        In a deterministic implementation, retry is appropriate only when
        the error is transient/intermittent. For deterministic errors,
        retry is not appropriate and we proceed to full replanning.
        """
        # If the error message contains known transient indicators, retry
        transient_keywords = ["timeout", "interrupted", "temporarily", "contention"]
        error_lower = error.lower()
        return any(keyword in error_lower for keyword in transient_keywords)

    def record_verification(
        self, step_id: str, execution_result: dict[str, Any],
        verified: bool,
    ) -> VerificationEvidence:
        """Record verification evidence for a revised execution step."""
        return self.evidence.mark_verification(
            step_id=step_id,
            execution_result=execution_result,
            verification_status="verified" if verified else "unverified",
        )

    def determine_final_outcome(
        self, success: bool, verified: bool, replanned: bool = False,
    ) -> PlannerOutcome:
        """Determine the final outcome using the outcomes module rules."""
        return determine_outcome(
            success=success,
            verified=verified,
            replanned=replanned,
        )