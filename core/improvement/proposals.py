"""ProposalEngine — converts ImprovementProposals into concrete knob changes.

Each proposal is evaluated against the KnobStore to determine what
knobs to change, to what values, and with what rationale.
"""

from __future__ import annotations

import logging
from typing import Any

from core.improvement.detector import ImprovementDetector
from core.improvement.knob_store import KnobStore
from core.improvement.models import ImprovementProposal, KnobChange, KnobCategory

logger = logging.getLogger(__name__)


class ProposalEngine:
    """Converts detected improvement opportunities into concrete knob changes.

    Usage:
        engine = ProposalEngine(knob_store)
        changes = engine.evaluate(proposal)
    """

    # Maps proposal patterns to (knob_name, value_calculator)
    _RESOLUTION_MAP: dict[str, list[tuple[str, callable]]] = {
        "planner": [
            ("planner.inject_domain_patterns", lambda p: True),
            ("planner.inject_failure_warnings", lambda p: True),
        ],
        "coding": [
            ("coding.simulation_required", lambda p: True),
            ("coding.safety_threshold", lambda p: max(0.5, min(0.9, p.confidence))),
        ],
        "research": [
            ("research.min_sources", lambda p: max(2, min(5, int(p.confidence * 5)))),
        ],
    }

    def __init__(self, knob_store: KnobStore | None = None):
        self._knob_store = knob_store or KnobStore()

    def evaluate(self, proposal: ImprovementProposal) -> list[KnobChange]:
        """Convert a proposal into concrete knob changes.

        Returns empty list if no changes are warranted.
        """
        changes: list[KnobChange] = []
        cat = proposal.category.value

        resolvers = self._RESOLUTION_MAP.get(cat, [])
        for knob_name, calc in resolvers:
            current = self._knob_store.get(knob_name)
            if current is None:
                continue
            new_value = calc(proposal)
            if new_value != current and new_value is not None:
                changes.append(KnobChange(
                    knob_name=knob_name,
                    new_value=new_value,
                    reason=proposal.reason[:100],
                ))
        return changes

    def evaluate_all(self, proposals: list[ImprovementProposal]) -> list[KnobChange]:
        """Evaluate multiple proposals and return all resulting knob changes."""
        all_changes: dict[str, KnobChange] = {}
        for proposal in proposals:
            for change in self.evaluate(proposal):
                # Higher-confidence proposals override
                if change.knob_name not in all_changes:
                    all_changes[change.knob_name] = change
        return list(all_changes.values())

    def detect_and_evaluate(self) -> list[KnobChange]:
        """Run full pipeline: detect → evaluate. Returns proposed changes."""
        detector = ImprovementDetector()
        proposals = detector.detect_all()
        return self.evaluate_all(proposals)
