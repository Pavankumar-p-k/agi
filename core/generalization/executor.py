"""Proposal execution lifecycle (Phase 15.0)."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict, Optional

from core.generalization.models import (
    PrincipleDataPoint,
    ProposalStatus,
    SystemType,
)


class _DefaultExperimentRunner:
    """Minimal runner used when none is injected."""

    def create_experiment(self, *args, **kwargs):
        return SimpleNamespace(experiment_id=f"exp_{uuid.uuid4().hex[:12]}")


class ProposalExecutor:
    """Drive proposals APPROVED → EXPERIMENTING → PROMOTED/REJECTED."""

    def __init__(self, experiment_runner=None) -> None:
        self.experiment_runner = experiment_runner or _DefaultExperimentRunner()

    def execute(self, proposal, store) -> str:
        if getattr(proposal.status, "value", proposal.status) != "approved":
            raise ValueError(
                f"Proposal {proposal.proposal_id} is not approved"
            )
        experiment = self.experiment_runner.create_experiment(proposal)
        experiment_id = getattr(experiment, "experiment_id", None) or (
            f"exp_{uuid.uuid4().hex[:12]}"
        )
        proposal.status = ProposalStatus.EXPERIMENTING
        proposal.experiment_id = experiment_id
        store.save_proposal(proposal)
        return experiment_id

    def complete(
        self,
        proposal,
        store,
        success: bool,
        control_metrics: Optional[Dict[str, Any]] = None,
        candidate_metrics: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if getattr(proposal.status, "value", proposal.status) != "experimenting":
            raise ValueError(
                f"Proposal {proposal.proposal_id} is not experimenting"
            )
        proposal.status = (
            ProposalStatus.PROMOTED if success else ProposalStatus.REJECTED
        )
        store.save_proposal(proposal)
        self._record_outcome(
            proposal, store, success, control_metrics, candidate_metrics
        )
        return success

    def execute_and_complete(
        self,
        proposal,
        store,
        success: bool,
        control_metrics: Optional[Dict[str, Any]] = None,
        candidate_metrics: Optional[Dict[str, Any]] = None,
    ):
        experiment_id = self.execute(proposal, store)
        promoted = self.complete(
            proposal, store, success,
            control_metrics=control_metrics,
            candidate_metrics=candidate_metrics,
        )
        return experiment_id, promoted

    # ── internals ────────────────────────────────────────────────────

    def _record_outcome(
        self, proposal, store, success, control_metrics, candidate_metrics
    ) -> None:
        properties: Dict[str, Any] = {
            "proposal_type": proposal.proposal_type,
            "expected_improvement": proposal.expected_improvement,
        }
        if control_metrics:
            properties["control_success_rate"] = control_metrics.get("success_rate")
        if candidate_metrics:
            properties["candidate_success_rate"] = candidate_metrics.get(
                "success_rate"
            )
        point = PrincipleDataPoint(
            point_id=f"pt_{uuid.uuid4().hex[:12]}",
            system_id=proposal.target_system,
            system_type=SystemType.TOOL,
            success=bool(success),
            properties=properties,
            domain="self_improvement",
            session_id=proposal.proposal_id,
        )
        store.save_data_point(point)
