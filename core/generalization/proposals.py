"""Improvement proposal generation (Phase 14.1)."""
from __future__ import annotations

import uuid
from typing import List

from core.generalization.models import (
    ImprovementProposal,
    Principle,
    PrincipleStatus,
)


def _is_numeric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_accepted(principle) -> bool:
    return getattr(principle.status, "value", principle.status) == "accepted"


class ProposalEngine:
    """Turn accepted principles into concrete improvement proposals."""

    def generate_proposals(
        self, principles: List[Principle], profiles: List
    ) -> List[ImprovementProposal]:
        proposals: List[ImprovementProposal] = []
        for principle in principles or []:
            proposals.extend(self.generate_for_principle(principle, profiles))
        return proposals

    def generate_for_principle(
        self, principle: Principle, profiles: List
    ) -> List[ImprovementProposal]:
        if not _is_accepted(principle):
            return []
        proposals = []
        for profile in profiles or []:
            proposal = self._proposal_for(principle, profile)
            if proposal is not None:
                proposals.append(proposal)
        return proposals

    def generate_for_system(
        self, principles: List[Principle], profile
    ) -> List[ImprovementProposal]:
        proposals = []
        for principle in principles or []:
            proposal = self._proposal_for(principle, profile)
            if proposal is not None:
                proposals.append(proposal)
        return proposals

    # ── internals ────────────────────────────────────────────────────

    def _proposal_for(self, principle, profile):
        if not _is_accepted(principle):
            return None
        name = principle.property_name
        value = profile.properties.get(name)

        if value is True:
            return None
        if _is_numeric(value) and value > 0:
            # Capability already present at a positive level.
            return None

        domains = list(principle.domains or [])
        rationale = (
            f"{name} improves success by {principle.discrimination:.0%} "
            f"(confidence {principle.confidence:.0%}, "
            f"{principle.sample_size} samples, {len(domains)} domains)"
        )
        return ImprovementProposal(
            proposal_id=f"prp_{uuid.uuid4().hex[:12]}",
            target_system=profile.system_id,
            proposal_type="add_capability",
            principle_id=principle.principle_id,
            title=f"Add {name} to {profile.system_id}",
            rationale=rationale,
            expected_improvement=principle.discrimination * principle.confidence,
            confidence=principle.confidence,
        )
