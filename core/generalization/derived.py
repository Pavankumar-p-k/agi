"""Derived property extraction (Phase 14.4)."""
from __future__ import annotations

import statistics
from typing import List, Optional

from core.generalization.models import SystemProfile, SystemType


def _is_numeric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class DerivedPropertyExtractor:
    """Average numeric properties across a system's executions."""

    def __init__(self, registry) -> None:
        self.registry = registry

    def compute_all(self, points: List) -> List[SystemProfile]:
        if not points:
            return []
        system_ids: List[str] = []
        for point in points:
            if point.system_id not in system_ids:
                system_ids.append(point.system_id)
        updated: List[SystemProfile] = []
        for system_id in system_ids:
            profile = self.compute_for_system(points, system_id)
            if profile is not None:
                updated.append(profile)
        return updated

    def compute_for_system(
        self, points: List, system_id: str
    ) -> Optional[SystemProfile]:
        subset = [p for p in points if p.system_id == system_id]
        if not subset:
            return None

        derived_names = self.registry.derived_property_names()
        values = {}
        for name in derived_names:
            numbers = [
                p.properties[name] for p in subset
                if _is_numeric(p.properties.get(name))
            ]
            if numbers:
                values[name] = round(statistics.mean(numbers), 3)

        if not values:
            return None

        profile = self.registry.get_profile(system_id)
        if profile is None:
            profile = SystemProfile(system_id, SystemType.TOOL, {})
        profile.properties.update(values)
        self.registry.register_profile(profile)
        return profile
