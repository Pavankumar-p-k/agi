"""Principle extraction from data points (Phase 14.0)."""
from __future__ import annotations

import statistics
import uuid
from typing import Dict, List, Optional

from core.generalization.models import PrincipleCandidate


def _is_numeric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _rate(points, prop: str, target) -> Optional[float]:
    group = [p for p in points if p.properties.get(prop) is target]
    if not group:
        return None
    return sum(1 for p in group if p.success) / len(group)


class PrincipleExtractor:
    """Derive principle candidates from observed data points."""

    def extract_all(self, points: List) -> List[PrincipleCandidate]:
        if not points:
            return []

        names = set()
        for point in points:
            for key, value in point.properties.items():
                if isinstance(value, bool):
                    names.add(key)

        candidates: List[PrincipleCandidate] = []
        for name in sorted(names):
            support = [p for p in points if p.properties.get(name) is True]
            control = [p for p in points if p.properties.get(name) is False]
            if not support or not control:
                continue
            support_rate = sum(1 for p in support if p.success) / len(support)
            control_rate = sum(1 for p in control if p.success) / len(control)
            discrimination = support_rate - control_rate
            if abs(discrimination) < 1e-9:
                continue
            domains = sorted({
                p.domain for p in (support + control) if getattr(p, "domain", "")
            })
            candidates.append(PrincipleCandidate(
                principle_id=f"pc_{uuid.uuid4().hex[:12]}",
                property_name=name,
                category="",
                support_rate=support_rate,
                control_rate=control_rate,
                discrimination=discrimination,
                sample_size=len(support) + len(control),
                support_count=len(support),
                control_count=len(control),
                domains=domains,
            ))
        return candidates

    def extract_all_numeric(
        self, points: List, property_name: Optional[str] = None
    ) -> List[PrincipleCandidate]:
        if not points:
            return []

        names = set()
        for point in points:
            for key, value in point.properties.items():
                if _is_numeric(value) and (property_name is None or key == property_name):
                    names.add(key)

        candidates: List[PrincipleCandidate] = []
        for name in sorted(names):
            values = [
                p.properties[name] for p in points
                if _is_numeric(p.properties.get(name))
            ]
            if len(values) < 2:
                continue
            threshold = statistics.median(values)
            high = [p for p in points if _is_numeric(p.properties.get(name))
                    and p.properties[name] > threshold]
            low = [p for p in points if _is_numeric(p.properties.get(name))
                   and p.properties[name] <= threshold]
            if not high or not low:
                continue
            support_rate = sum(1 for p in high if p.success) / len(high)
            control_rate = sum(1 for p in low if p.success) / len(low)
            discrimination = support_rate - control_rate
            if abs(discrimination) < 1e-9:
                continue
            domains = sorted({
                p.domain for p in (high + low) if getattr(p, "domain", "")
            })
            candidates.append(PrincipleCandidate(
                principle_id=f"pc_{uuid.uuid4().hex[:12]}",
                property_name=name,
                category="",
                support_rate=support_rate,
                control_rate=control_rate,
                discrimination=discrimination,
                sample_size=len(high) + len(low),
                support_count=len(high),
                control_count=len(low),
                domains=domains,
            ))
        return candidates
