"""Phase 15.0 — Proposal Executor.

The bridge between ImprovementProposals and measurable Experiments.

Before Phase 15:
    Proposal (suggestion, no action)

After Phase 15:
    Proposal → Experiment → Outcome → Knowledge

The executor manages the full lifecycle:
    APPROVED → EXPERIMENTING → PROMOTED | REJECTED

Each executed proposal produces a PrincipleDataPoint recording the outcome,
closing the learning loop back into principle extraction.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from core.generalization.models import (
    ImprovementProposal,
    PrincipleDataPoint,
    ProposalStatus,
    SystemType,
)
from core.generalization.store import PrincipleStore
from core.improvement.experiment import ExperimentRunner
from core.improvement.models import KnobChange

logger = logging.getLogger(__name__)


class ProposalExecutor:
    """Manages the lifecycle of a proposal from approval to outcome.

    Flow:
        execute(proposal)        → proposal status: EXPERIMENTING
                                   experiment created (PLANNED)

        complete(proposal, data) → proposal status: PROMOTED or REJECTED
                                   outcome recorded as PrincipleDataPoint
                                   experiment completed
    """

    def __init__(self, experiment_runner: ExperimentRunner | None = None):
        self._experiment_runner = experiment_runner or ExperimentRunner()

    def execute(self, proposal: ImprovementProposal,
                store: PrincipleStore) -> str:
        """Execute an approved proposal by creating an experiment.

        Args:
            proposal: Must have status == APPROVED.
            store: PrincipleStore for persisting status changes.

        Returns:
            experiment_id for tracking.

        Raises:
            ValueError if proposal is not APPROVED.
        """
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError(
                f"Cannot execute proposal {proposal.proposal_id} "
                f"with status {proposal.status.value} — must be APPROVED"
            )

        changes = self._proposal_to_knob_changes(proposal)
        experiment = self._experiment_runner.create_experiment(
            proposal.proposal_id, changes,
        )

        store.update_proposal_status(proposal.proposal_id,
                                      ProposalStatus.EXPERIMENTING)
        proposal.status = ProposalStatus.EXPERIMENTING

        logger.info(
            "ProposalExecutor: executed %s → experiment %s",
            proposal.proposal_id, experiment.experiment_id,
        )
        return experiment.experiment_id

    def complete(self, proposal: ImprovementProposal,
                 store: PrincipleStore,
                 success: bool,
                 control_metrics: dict[str, float] | None = None,
                 candidate_metrics: dict[str, float] | None = None,
                 ) -> bool:
        """Complete a proposal experiment and record the outcome.

        Args:
            proposal: The proposal being experimented on. Must have
                      status == EXPERIMENTING.
            store: PrincipleStore for persisting changes.
            success: Whether the experiment outcome was positive.
            control_metrics: Optional baseline metrics.
            candidate_metrics: Optional candidate metrics.

        Returns:
            True if promoted, False if rejected.

        Raises:
            ValueError if proposal is not EXPERIMENTING.
        """
        if proposal.status != ProposalStatus.EXPERIMENTING:
            raise ValueError(
                f"Cannot complete proposal {proposal.proposal_id} "
                f"with status {proposal.status.value} — must be EXPERIMENTING"
            )

        if success:
            store.update_proposal_status(proposal.proposal_id,
                                          ProposalStatus.PROMOTED)
            proposal.status = ProposalStatus.PROMOTED
            logger.info("ProposalExecutor: promoted %s", proposal.proposal_id)
        else:
            store.update_proposal_status(proposal.proposal_id,
                                          ProposalStatus.REJECTED)
            proposal.status = ProposalStatus.REJECTED
            logger.info("ProposalExecutor: rejected %s", proposal.proposal_id)

        # Record the outcome as a PrincipleDataPoint for future learning
        data_point = self._build_outcome_point(proposal, success,
                                                control_metrics,
                                                candidate_metrics)
        store.save_data_point(data_point)

        return success

    def execute_and_complete(self, proposal: ImprovementProposal,
                              store: PrincipleStore,
                              success: bool,
                              control_metrics: dict[str, float] | None = None,
                              candidate_metrics: dict[str, float] | None = None,
                              ) -> tuple[str, bool]:
        """Run execute + complete in one call (for simple flows).

        Returns (experiment_id, promoted).
        """
        experiment_id = self.execute(proposal, store)
        promoted = self.complete(proposal, store, success,
                                  control_metrics, candidate_metrics)
        return experiment_id, promoted

    def _proposal_to_knob_changes(self, proposal: ImprovementProposal
                                   ) -> list[KnobChange]:
        """Convert a proposal to KnobChanges for experiment tracking.

        Architectural proposals don't map to named knobs directly.
        The knob change records the proposal metadata so the experiment
        table tracks what was proposed.
        """
        return [
            KnobChange(
                knob_name=f"proposal:{proposal.proposal_id}",
                new_value=f"{proposal.target_system}:{proposal.proposal_type}",
                reason=proposal.rationale,
            ),
        ]

    def _build_outcome_point(
        self,
        proposal: ImprovementProposal,
        success: bool,
        control_metrics: dict[str, float] | None = None,
        candidate_metrics: dict[str, float] | None = None,
    ) -> PrincipleDataPoint:
        """Build a data point recording the experiment outcome.

        This closes the learning loop — the outcome feeds back into
        the principle extraction pipeline.
        """
        properties = {
            "proposal_type": proposal.proposal_type,
            "expected_improvement": proposal.expected_improvement,
            "confidence": proposal.confidence,
        }
        if control_metrics:
            properties["control_success_rate"] = control_metrics.get("success_rate", 0.0)
        if candidate_metrics:
            properties["candidate_success_rate"] = candidate_metrics.get("success_rate", 0.0)

        return PrincipleDataPoint(
            point_id=f"out_{uuid.uuid4().hex[:12]}",
            system_id=proposal.target_system,
            system_type=SystemType.TOOL,
            success=success,
            properties=properties,
            domain="self_improvement",
            session_id=proposal.proposal_id,
            timestamp=datetime.now(timezone.utc),
        )
