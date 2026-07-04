"""Phase 15.1a — Strategy Executor.

Bridges StrategicDecision to ProposalExecutor.

Before this bridge:
  StrategicDecision → STOP (recommendation only)

After this bridge:
  StrategicDecision → Experiment → Outcome → Learning

The executor takes a decision from the Strategic Selector,
executes all proposals in the chosen strategy via ProposalExecutor,
and records outcomes as PrincipleDataPoints — closing the
strategy→action→learning loop.
"""

from __future__ import annotations

import logging
from typing import Any

from core.generalization.executor import ProposalExecutor
from core.generalization.models import ProposalStatus
from core.generalization.store import PrincipleStore
from core.strategy.v2.models import (
    StrategicDecision,
    StrategyCandidate,
    StrategyStatus,
)

logger = logging.getLogger(__name__)


class StrategyExecutor:
    """Manages the lifecycle of a StrategicDecision from selection to outcome.

    Full flow:
        execute_decision(decision, candidates)
            → chosen strategy identified
            → each APPROVED proposal → ProposalExecutor.execute() → EXPERIMENTING
            → decision marked EXECUTING

        complete_decision(decision, candidates, success, ...)
            → each EXPERIMENTING proposal → ProposalExecutor.complete() → PROMOTED/REJECTED
            → outcome data points recorded (closes learning loop)
            → decision marked COMPLETED or SUPERSEDED
    """

    def __init__(self, principle_store: PrincipleStore,
                 proposal_executor: ProposalExecutor | None = None):
        self._store = principle_store
        self._executor = proposal_executor or ProposalExecutor()

    def execute_decision(self, decision: StrategicDecision,
                         candidates: list[StrategyCandidate],
                         ) -> dict[str, str]:
        """Execute all proposals in the chosen strategy.

        Each APPROVED proposal is transitioned to EXPERIMENTING via
        ProposalExecutor. Already-experimenting proposals are skipped.

        Args:
            decision: StrategicDecision with chosen_strategy_id set.
            candidates: All strategy candidates (to find the chosen one).

        Returns:
            dict[proposal_id → experiment_id] for successfully started experiments.

        Raises:
            ValueError if the chosen strategy is not found in candidates.
        """
        chosen = self._find_chosen(decision, candidates)
        if chosen is None:
            raise ValueError(
                f"Chosen strategy {decision.chosen_strategy_id} "
                f"not found in {len(candidates)} candidates"
            )

        results: dict[str, str] = {}
        for pid in chosen.proposal_ids:
            proposal = self._store.get_proposal(pid)
            if proposal is None:
                logger.warning("StrategyExecutor: proposal %s not found, skipping", pid)
                continue
            if proposal.status == ProposalStatus.APPROVED:
                exp_id = self._executor.execute(proposal, self._store)
                results[pid] = exp_id
                logger.info(
                    "StrategyExecutor: executed proposal %s → experiment %s",
                    pid, exp_id,
                )
            elif proposal.status == ProposalStatus.EXPERIMENTING:
                logger.info(
                    "StrategyExecutor: proposal %s already experimenting, skipping", pid,
                )
            else:
                logger.warning(
                    "StrategyExecutor: proposal %s has status %s, skipping",
                    pid, proposal.status.value,
                )

        decision.status = StrategyStatus.EXECUTING
        logger.info(
            "StrategyExecutor: decision %s now EXECUTING (%d proposals executed)",
            decision.decision_id, len(results),
        )
        return results

    def complete_decision(self, decision: StrategicDecision,
                          candidates: list[StrategyCandidate],
                          overall_success: bool,
                          per_proposal_results: dict[str, dict[str, Any]]
                          | None = None,
                          ) -> dict[str, bool]:
        """Complete all executed proposals and record outcomes.

        Each EXPERIMENTING proposal is transitioned to PROMOTED or REJECTED
        via ProposalExecutor.complete(). Outcome data points are recorded
        automatically (closing the learning loop).

        Args:
            decision: StrategicDecision (must be EXECUTING).
            candidates: All strategy candidates.
            overall_success: If True, decision → COMPLETED, else SUPERSEDED.
            per_proposal_results: Optional dict of proposal_id → {
                "success": bool,
                "control_metrics": dict | None,
                "candidate_metrics": dict | None,
            }. Falls back to overall_success for each proposal.

        Returns:
            dict[proposal_id → promoted (bool)].
        """
        chosen = self._find_chosen(decision, candidates)
        if chosen is None:
            raise ValueError(
                f"Chosen strategy {decision.chosen_strategy_id} "
                f"not found in {len(candidates)} candidates"
            )

        per_proposal = per_proposal_results or {}

        results: dict[str, bool] = {}
        for pid in chosen.proposal_ids:
            proposal = self._store.get_proposal(pid)
            if proposal is None:
                logger.warning("StrategyExecutor: proposal %s not found, skipping", pid)
                continue
            if proposal.status != ProposalStatus.EXPERIMENTING:
                logger.warning(
                    "StrategyExecutor: proposal %s has status %s (expected EXPERIMENTING), skipping",
                    pid, proposal.status.value,
                )
                continue

            ppr = per_proposal.get(pid, {})
            promoted = self._executor.complete(
                proposal,
                self._store,
                success=ppr.get("success", overall_success),
                control_metrics=ppr.get("control_metrics"),
                candidate_metrics=ppr.get("candidate_metrics"),
            )
            results[pid] = promoted

        decision.status = (
            StrategyStatus.COMPLETED if overall_success
            else StrategyStatus.SUPERSEDED
        )
        logger.info(
            "StrategyExecutor: decision %s now %s (%d proposals completed)",
            decision.decision_id, decision.status.value, len(results),
        )
        return results

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _find_chosen(decision: StrategicDecision,
                     candidates: list[StrategyCandidate],
                     ) -> StrategyCandidate | None:
        """Find the candidate matching the decision's chosen strategy."""
        for c in candidates:
            if c.strategy_id == decision.chosen_strategy_id:
                return c
        return None
