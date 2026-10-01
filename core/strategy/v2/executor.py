"""Strategy decision execution for v2 (Phase 15.0)."""
from __future__ import annotations

from typing import Dict, List, Optional

from core.generalization.executor import ProposalExecutor
from core.strategy.v2.models import StrategyStatus


def _status(obj) -> str:
    return getattr(obj.status, "value", obj.status)


class StrategyExecutor:
    """Execute selected strategies by driving their proposals through experiments."""

    def __init__(self, store, proposal_executor=None) -> None:
        self.store = store
        self.proposal_executor = proposal_executor or ProposalExecutor()

    def _resolve_chosen(self, decision, candidates) -> object:
        for candidate in candidates or []:
            if candidate.strategy_id == decision.chosen_strategy_id:
                return candidate
        raise ValueError(
            f"Chosen strategy {decision.chosen_strategy_id} not found in candidates"
        )

    def execute_decision(self, decision, candidates) -> Dict[str, str]:
        chosen = self._resolve_chosen(decision, candidates)
        results: Dict[str, str] = {}
        for proposal_id in chosen.proposal_ids:
            proposal = self.store.get_proposal(proposal_id)
            if proposal is None or _status(proposal) != "approved":
                continue
            experiment_id = self.proposal_executor.execute(proposal, self.store)
            results[proposal_id] = experiment_id
        decision.status = StrategyStatus.EXECUTING
        return results

    def complete_decision(
        self,
        decision,
        candidates,
        overall_success: bool = True,
        per_proposal_results: Optional[Dict] = None,
    ) -> Dict[str, bool]:
        chosen = self._resolve_chosen(decision, candidates)
        results: Dict[str, bool] = {}
        for proposal_id in chosen.proposal_ids:
            proposal = self.store.get_proposal(proposal_id)
            if proposal is None or _status(proposal) != "experimenting":
                continue
            info = (per_proposal_results or {}).get(proposal_id, {}) or {}
            success = bool(info.get("success", overall_success))
            self.proposal_executor.complete(
                proposal,
                self.store,
                success,
                control_metrics=info.get("control_metrics"),
                candidate_metrics=info.get("candidate_metrics"),
            )
            results[proposal_id] = success
        decision.status = (
            StrategyStatus.COMPLETED if overall_success
            else StrategyStatus.SUPERSEDED
        )
        return results
