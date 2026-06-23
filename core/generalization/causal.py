"""Phase 14.3 — Causal Filter.

Controls for hidden confounders when evaluating principle candidates.

The core question is not "does property X correlate with success?"
but "is the observed discrimination causal, or driven by a confounder?"

For a candidate property P, checks each other boolean property C:
  - Compute P(success | P=True, C=True) - P(success | P=False, C=True)
  - Compute P(success | P=True, C=False) - P(success | P=False, C=False)
  - If both are near zero, C is a likely confounder.
"""

from __future__ import annotations

import logging
from typing import Any

from core.generalization.models import (
    CausalAnalysis,
    CausalStatus,
    PrincipleCandidate,
    PrincipleDataPoint,
)

logger = logging.getLogger(__name__)

# Minimum adjusted discrimination to avoid being flagged as confounded
_MIN_ADJUSTED_DISCRIMINATION = 0.05

# Minimum data points in a confounder-controlled subset to compute discrimination
_MIN_SUBSET_SIZE = 4


class CausalFilter:
    """Analyzes whether a candidate principle's discrimination is causal.

    For each candidate, checks every other boolean property as a potential
    confounder. If controlling for a confounder collapses the discrimination,
    the candidate is marked LIKELY_CONFOUNDED.
    """

    def __init__(self, min_adjusted_discrimination: float = _MIN_ADJUSTED_DISCRIMINATION,
                 min_subset_size: int = _MIN_SUBSET_SIZE):
        self.min_adjusted_discrimination = min_adjusted_discrimination
        self.min_subset_size = min_subset_size

    def analyze(self, candidate: PrincipleCandidate,
                data_points: list[PrincipleDataPoint]) -> CausalAnalysis:
        """Run confounder-controlled analysis on a candidate principle.

        Args:
            candidate: The principle candidate to analyze.
            data_points: All experimental data points.

        Returns:
            CausalAnalysis with adjusted discrimination and confounder list.
        """
        prop = candidate.property_name
        raw_discrimination = candidate.discrimination

        # Collect all boolean properties (excluding the candidate's own)
        boolean_props = self._collect_boolean_properties(data_points, prop)

        if not boolean_props:
            return CausalAnalysis(
                property_name=prop,
                raw_discrimination=raw_discrimination,
                adjusted_discrimination=raw_discrimination,
                confounders_checked=[],
                confounded_by=[],
                status=CausalStatus.LIKELY_CAUSAL,
                confidence=candidate.confidence,
            )

        confounders_checked: list[str] = []
        confounded_by: list[str] = []
        controlled_discriminations: list[float] = []

        for confounder in boolean_props:
            confounders_checked.append(confounder)
            d = self._compute_controlled_discrimination(
                data_points, prop, confounder,
            )
            if d is not None:
                controlled_discriminations.append(d)
                if abs(d) < self.min_adjusted_discrimination:
                    confounded_by.append(confounder)

        adjusted = self._compute_adjusted_discrimination(
            raw_discrimination, controlled_discriminations,
        )

        likely_causal = len(confounded_by) == 0
        status = CausalStatus.LIKELY_CAUSAL if likely_causal else CausalStatus.LIKELY_CONFOUNDED
        confidence = self._compute_confidence(raw_discrimination, adjusted,
                                               candidate.confidence,
                                               len(confounded_by),
                                               len(confounders_checked))

        return CausalAnalysis(
            property_name=prop,
            raw_discrimination=raw_discrimination,
            adjusted_discrimination=adjusted,
            confounders_checked=confounders_checked,
            confounded_by=confounded_by,
            status=status,
            confidence=confidence,
        )

    def _compute_controlled_discrimination(
        self,
        data_points: list[PrincipleDataPoint],
        prop: str,
        confounder: str,
    ) -> float | None:
        """Compute discrimination while controlling for a confounder.

        Returns the minimum absolute discrimination across both
        confounder=True and confounder=False subsets.
        Returns None if either subset is too small.
        """
        discriminations: list[float] = []

        for confounder_value in [True, False]:
            subset = [
                p for p in data_points
                if isinstance(p.properties.get(confounder), bool)
                and p.properties[confounder] == confounder_value
            ]

            if len(subset) < self.min_subset_size:
                continue

            d = self._compute_subset_discrimination(subset, prop)
            if d is not None:
                discriminations.append(d)

        if not discriminations:
            return None

        return min(abs(d) for d in discriminations)

    @staticmethod
    def _compute_subset_discrimination(
        data_points: list[PrincipleDataPoint],
        prop: str,
    ) -> float | None:
        """Compute P(success | prop=True) - P(success | prop=False) in subset."""
        true_success = 0
        true_total = 0
        false_success = 0
        false_total = 0

        for point in data_points:
            val = point.properties.get(prop)
            if not isinstance(val, bool):
                continue
            if val:
                true_total += 1
                if point.success:
                    true_success += 1
            else:
                false_total += 1
                if point.success:
                    false_success += 1

        if true_total == 0 or false_total == 0:
            return None

        support = true_success / true_total
        control = false_success / false_total
        return support - control

    @staticmethod
    def _collect_boolean_properties(
        data_points: list[PrincipleDataPoint],
        exclude: str,
    ) -> list[str]:
        """Collect unique boolean property names, excluding the candidate's own."""
        props: set[str] = set()
        for point in data_points:
            for name, val in point.properties.items():
                if name == exclude:
                    continue
                if isinstance(val, bool):
                    props.add(name)
        return sorted(props)

    @staticmethod
    def _compute_adjusted_discrimination(
        raw: float,
        controlled: list[float],
    ) -> float:
        """Compute adjusted discrimination as the minimum controlled value."""
        if not controlled:
            return raw
        # Use minimum absolute controlled discrimination
        min_controlled = min(abs(d) for d in controlled)
        return min_controlled if raw >= 0 else -min_controlled

    @staticmethod
    def _compute_confidence(
        raw_discrimination: float,
        adjusted_discrimination: float,
        base_confidence: float,
        confounded_count: int,
        checked_count: int,
    ) -> float:
        """Reduce confidence proportionally to discrimination collapse."""
        if raw_discrimination == 0:
            return 0.0

        ratio = abs(adjusted_discrimination) / abs(raw_discrimination)
        penalty = 1.0 - ratio
        return max(round(base_confidence * (1.0 - penalty * 0.5), 3), 0.0)
