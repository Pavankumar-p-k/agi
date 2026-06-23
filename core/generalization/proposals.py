"""Phase 14.1 — Principle Application Engine (ProposalEngine).

Deterministically generates architectural improvement proposals from
accepted principles. No LLM — purely set operations over system profiles.

Pipeline:
    Accepted Principle + System Profile → Proposal
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from core.generalization.models import (
    ImprovementProposal,
    Principle,
    PrincipleStatus,
    ProposalStatus,
    SystemProfile,
)

logger = logging.getLogger(__name__)


class ProposalEngine:
    """Generates architectural improvement proposals from accepted principles.

    For each accepted principle, checks every registered system profile.
    If a system is missing the property (or has it set to False for booleans),
    generates a proposal to add it.

    Pure deterministic logic — no prompts, no LLM, no external state.
    """

    def generate_proposals(
        self,
        principles: list[Principle],
        profiles: list[SystemProfile],
    ) -> list[ImprovementProposal]:
        """Generate proposals for applying accepted principles to systems.

        Args:
            principles: List of principles (only ACCEPTED ones are considered).
            profiles: System profiles to evaluate against.

        Returns:
            List of ImprovementProposal objects (status=GENERATED).
        """
        proposals: list[ImprovementProposal] = []

        accepted = [p for p in principles if p.status == PrincipleStatus.ACCEPTED]
        if not accepted:
            return []

        for principle in accepted:
            for profile in profiles:
                if self._should_generate(principle, profile):
                    proposal = self._build_proposal(principle, profile)
                    proposals.append(proposal)

        return proposals

    def generate_for_system(
        self,
        principles: list[Principle],
        profile: SystemProfile,
    ) -> list[ImprovementProposal]:
        """Generate proposals for a single target system."""
        return self.generate_proposals(principles, [profile])

    def generate_for_principle(
        self,
        principle: Principle,
        profiles: list[SystemProfile],
    ) -> list[ImprovementProposal]:
        """Generate proposals from a single principle across systems."""
        return self.generate_proposals([principle], profiles)

    def _should_generate(
        self, principle: Principle, profile: SystemProfile,
    ) -> bool:
        """Check if a proposal should be generated for this system.

        Generates a proposal when:
        - The property is absent from the profile (not defined)
        - The property is a boolean set to False
        - The property is a numeric value below a minimum threshold

        Does NOT generate when:
        - The property is already present and True (bool)
        - The property is already present with a numeric value >= threshold
        """
        if profile.system_id == principle.property_name:
            return False

        value = profile.properties.get(principle.property_name)

        if value is None:
            return True

        if isinstance(value, bool):
            return not value

        if isinstance(value, (int, float)):
            return value < 0.5

        return False

    def _build_proposal(
        self, principle: Principle, profile: SystemProfile,
    ) -> ImprovementProposal:
        """Construct a proposal from a principle and a target system."""
        prop_name = principle.property_name
        system_id = profile.system_id

        discrimination_pct = f"{principle.discrimination * 100:.0f}"
        confidence_pct = f"{principle.confidence * 100:.0f}"

        title = f"Add {prop_name} to {system_id}"
        rationale = (
            f"{prop_name} improves success by {discrimination_pct}% "
            f"(confidence: {confidence_pct}%, "
            f"evidence: {principle.sample_size} data points "
            f"across {len(principle.domains)} domains)"
        )

        return ImprovementProposal(
            proposal_id=f"prp_{uuid.uuid4().hex[:12]}",
            target_system=system_id,
            proposal_type="add_capability",
            principle_id=principle.principle_id,
            title=title,
            rationale=rationale,
            expected_improvement=principle.discrimination,
            confidence=principle.confidence,
            status=ProposalStatus.GENERATED,
            created_at=datetime.now(timezone.utc),
        )
