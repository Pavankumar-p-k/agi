"""Causal filtering of principle candidates (Phase 14.3)."""
from __future__ import annotations

from typing import List, Optional

from core.generalization.models import CausalAnalysis, CausalStatus

_COLLAPSE_THRESHOLD = 0.05


def _discrimination(points: List, prop: str) -> Optional[float]:
    support = [p for p in points if p.properties.get(prop) is True]
    control = [p for p in points if p.properties.get(prop) is False]
    if not support or not control:
        return None
    support_rate = sum(1 for p in support if p.success) / len(support)
    control_rate = sum(1 for p in control if p.success) / len(control)
    return support_rate - control_rate


class CausalFilter:
    """Check whether a candidate's discrimination survives controlling for
    other boolean system properties."""

    def __init__(self, min_subset_size: int = 4) -> None:
        self.min_subset_size = min_subset_size

    def _other_boolean_properties(self, points: List, prop: str) -> List[str]:
        names = set()
        for point in points:
            for key, value in point.properties.items():
                if key == prop or not isinstance(value, bool):
                    continue
                names.add(key)
        usable = []
        for name in sorted(names):
            values = [p.properties.get(name) for p in points]
            if True in values and False in values:
                usable.append(name)
        return usable

    def analyze(self, candidate, points: List) -> CausalAnalysis:
        prop = candidate.property_name
        others = self._other_boolean_properties(points, prop)

        controlled: List[float] = []
        confounded_by: List[str] = []
        for conf in others:
            sub_discs: List[float] = []
            for value in (True, False):
                subset = [p for p in points if p.properties.get(conf) is value]
                if len(subset) < self.min_subset_size:
                    continue
                disc = _discrimination(subset, prop)
                if disc is not None:
                    sub_discs.append(disc)
            if sub_discs:
                minimum = min(sub_discs)
                controlled.append(minimum)
                if minimum < _COLLAPSE_THRESHOLD:
                    confounded_by.append(conf)

        adjusted = min(controlled) if controlled else candidate.discrimination

        if confounded_by:
            status = CausalStatus.LIKELY_CONFOUNDED
            confidence = candidate.confidence * 0.5
        elif not points:
            status = CausalStatus.INSUFFICIENT_DATA
            confidence = candidate.confidence * 0.5
        else:
            status = CausalStatus.LIKELY_CAUSAL
            confidence = candidate.confidence

        return CausalAnalysis(
            property_name=prop,
            raw_discrimination=candidate.discrimination,
            adjusted_discrimination=adjusted,
            confounders_checked=others,
            confounded_by=confounded_by,
            status=status,
            confidence=confidence,
        )
