"""Phase 14.4 — Derived Property Extraction.

Bridges ActivityGraph runtime data → StructuralPropertyRegistry profiles.

For each system, scans experimental data points, computes aggregate
numeric values for DERIVED properties, and updates the system profile.

This enables the system to discover patterns from properties nobody
explicitly labeled — execution depth, artifact volume, retry frequency.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from core.generalization.models import (
    PrincipleDataPoint,
    PropertySource,
    SystemProfile,
)
from core.generalization.registry import StructuralPropertyRegistry

logger = logging.getLogger(__name__)


class DerivedPropertyExtractor:
    """Computes derived property values from data points and updates profiles.

    For each system, averages all numeric properties across its data points
    and merges the results into the system's profile. Only properties defined
    as DERIVED in the registry are computed; boolean properties are skipped.

    Usage:
        extractor = DerivedPropertyExtractor(registry)
        extractor.compute_all(data_points)
        # registry profiles now have derived property values
    """

    def __init__(self, registry: StructuralPropertyRegistry):
        self._registry = registry

    def compute_all(self, data_points: list[PrincipleDataPoint]) -> list[SystemProfile]:
        """Compute derived properties for all systems with data points.

        Args:
            data_points: Experimental data points containing numeric properties.

        Returns:
            Updated list of SystemProfiles that had derived values computed.
        """
        if not data_points:
            return []

        derived_names = self._get_derived_property_names()

        # Group data points by system
        by_system: dict[str, list[PrincipleDataPoint]] = defaultdict(list)
        for point in data_points:
            by_system[point.system_id].append(point)

        updated: list[SystemProfile] = []

        for system_id, points in by_system.items():
            derived_values = self._compute_system_derived(points, derived_names)
            if derived_values:
                profile = self._merge_into_profile(system_id, points[0].system_type,
                                                    derived_values)
                if profile:
                    updated.append(profile)

        return updated

    def compute_for_system(self, data_points: list[PrincipleDataPoint],
                            system_id: str) -> SystemProfile | None:
        """Compute derived properties for a single system."""
        if not data_points:
            return None

        derived_names = self._get_derived_property_names()
        system_points = [p for p in data_points if p.system_id == system_id]

        if not system_points:
            return None

        derived_values = self._compute_system_derived(system_points, derived_names)
        if not derived_values:
            return None

        return self._merge_into_profile(system_id, system_points[0].system_type,
                                         derived_values)

    def _get_derived_property_names(self) -> set[str]:
        """Get names of all properties defined as DERIVED in the registry."""
        props = self._registry.list_properties(source="derived")
        return {p.name for p in props}

    @staticmethod
    def _compute_system_derived(
        data_points: list[PrincipleDataPoint],
        derived_names: set[str],
    ) -> dict[str, float]:
        """Compute average of each numeric derived property for a system.

        Args:
            data_points: All data points for a single system.
            derived_names: Set of property names defined as DERIVED.

        Returns:
            Dict of property_name → average value (calculated only from
            numeric properties that exist in the data and are derived).
        """
        # Collect numeric values per property
        accum: dict[str, list[float]] = defaultdict(list)

        for point in data_points:
            for name, val in point.properties.items():
                if name not in derived_names:
                    continue
                if isinstance(val, bool):
                    continue
                if isinstance(val, (int, float)):
                    accum[name].append(float(val))

        # Compute averages
        result: dict[str, float] = {}
        for name, values in accum.items():
            if values:
                result[name] = round(sum(values) / len(values), 3)

        return result

    def _merge_into_profile(
        self, system_id: str, system_type: Any,
        derived_values: dict[str, float],
    ) -> SystemProfile | None:
        """Merge computed derived values into the system's profile.

        Gets the existing profile (or creates a default), merges the
        derived values, and persists.
        """
        profile = self._registry.get_profile(system_id)
        if profile is None:
            from core.generalization.models import SystemType
            profile = SystemProfile(
                system_id=system_id,
                system_type=system_type if isinstance(system_type, SystemType)
                              else SystemType.TOOL,
                properties={},
            )

        # Merge derived values (preserving existing static properties)
        profile.properties.update(derived_values)

        self._registry.register_profile(profile)
        logger.debug("DerivedPropertyExtractor: updated %s with %d derived values",
                      system_id, len(derived_values))
        return profile
