"""Phase 14.0 — Principle Extractor.

Consumes experimental data points (properties + outcomes) and produces
candidate principles using discrimination-based correlation.

The extractor does not validate — it only proposes.
Validation is the PrincipleValidator's job.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import Any

from core.generalization.models import (
    PrincipleCandidate,
    PrincipleDataPoint,
    PrincipleStatus,
)

logger = logging.getLogger(__name__)

_DISCRIMINATION_MIN_VARIANCE = 0.01  # minimum discrimination to produce a candidate


class PrincipleExtractor:
    """Stateless extractor that finds property-outcome correlations.

    For each property present across data points, computes:
      support_rate  = P(success | property=True)
      control_rate  = P(success | property=False)
      discrimination = support_rate - control_rate

    Only produces candidates for properties that actually vary across the
    dataset (both True and False values exist).
    """

    def extract_all(self, data_points: list[PrincipleDataPoint],
                    ) -> list[PrincipleCandidate]:
        """Extract candidate principles from experimental data.

        Args:
            data_points: Collection of experimental outcomes with properties.

        Returns:
            List of candidate principles, one per varying property.
            Empty list if no meaningful correlations found.
        """
        if not data_points:
            return []

        # Group data points by binary property values
        # For each property, collect (success, domain) tuples for True and False groups
        by_property: dict[str, dict[str, Any]] = {}

        for point in data_points:
            for prop_name, prop_value in point.properties.items():
                # Only analyze boolean or numeric-threshold properties
                if not isinstance(prop_value, bool):
                    continue

                if prop_name not in by_property:
                    by_property[prop_name] = {
                        "true_success": 0,
                        "true_total": 0,
                        "false_success": 0,
                        "false_total": 0,
                        "domains_true": set(),
                        "domains_false": set(),
                        "point_ids": [],
                    }

                bucket = by_property[prop_name]
                bucket["point_ids"].append(point.point_id)

                if prop_value:
                    bucket["true_total"] += 1
                    if point.success:
                        bucket["true_success"] += 1
                    if point.domain:
                        bucket["domains_true"].add(point.domain)
                else:
                    bucket["false_total"] += 1
                    if point.success:
                        bucket["false_success"] += 1
                    if point.domain:
                        bucket["domains_false"].add(point.domain)

        candidates: list[PrincipleCandidate] = []

        for prop_name, bucket in by_property.items():
            true_total = bucket["true_total"]
            false_total = bucket["false_total"]

            # Skip properties that don't vary
            if true_total == 0 or false_total == 0:
                continue

            support_rate = bucket["true_success"] / true_total if true_total > 0 else 0.0
            control_rate = bucket["false_success"] / false_total if false_total > 0 else 0.0
            discrimination = support_rate - control_rate

            # Skip noise-level signals
            if abs(discrimination) < _DISCRIMINATION_MIN_VARIANCE:
                continue

            all_domains = bucket["domains_true"] | bucket["domains_false"]

            candidates.append(PrincipleCandidate(
                principle_id=f"pc_{uuid.uuid4().hex[:12]}",
                property_name=prop_name,
                category=self._infer_category(prop_name),
                support_rate=support_rate,
                control_rate=control_rate,
                discrimination=discrimination,
                sample_size=true_total + false_total,
                support_count=true_total,
                control_count=false_total,
                domains=sorted(all_domains) if all_domains else [],
                status=PrincipleStatus.CANDIDATE,
            ))

        return candidates

    def extract_all_numeric(self, data_points: list[PrincipleDataPoint],
                            threshold_fn=None,
                            ) -> list[PrincipleCandidate]:
        """Extract candidates from numeric properties using a threshold.

        Args:
            data_points: Experimental data points.
            threshold_fn: Optional callable (prop_name, values) -> threshold.
                          If None, uses median split.

        Returns:
            List of candidate principles.
        """
        if not data_points:
            return []

        # Collect all numeric values per property
        numeric_values: dict[str, list[tuple[float, bool, str]]] = defaultdict(list)

        for point in data_points:
            for prop_name, prop_value in point.properties.items():
                if not isinstance(prop_value, (int, float)):
                    continue
                if isinstance(prop_value, bool):
                    continue
                numeric_values[prop_name].append(
                    (prop_value, point.success, point.point_id, point.domain),
                )

        candidates: list[PrincipleCandidate] = []

        for prop_name, values in numeric_values.items():
            if len(values) < 4:
                continue

            # Determine threshold
            if threshold_fn:
                threshold = threshold_fn(prop_name, [v[0] for v in values])
            else:
                # Median split
                sorted_vals = sorted(v[0] for v in values)
                threshold = sorted_vals[len(sorted_vals) // 2]

            high_success = sum(1 for v in values if v[0] > threshold and v[1])
            high_total = sum(1 for v in values if v[0] > threshold)
            low_success = sum(1 for v in values if v[0] <= threshold and v[1])
            low_total = sum(1 for v in values if v[0] <= threshold)

            if high_total == 0 or low_total == 0:
                continue

            support_rate = high_success / high_total if high_total > 0 else 0.0
            control_rate = low_success / low_total if low_total > 0 else 0.0
            discrimination = support_rate - control_rate

            if abs(discrimination) < _DISCRIMINATION_MIN_VARIANCE:
                continue

            domains = list({v[3] for v in values if v[3]})

            candidates.append(PrincipleCandidate(
                principle_id=f"pc_{uuid.uuid4().hex[:12]}",
                property_name=prop_name,
                category=self._infer_category(prop_name),
                support_rate=support_rate,
                control_rate=control_rate,
                discrimination=discrimination,
                sample_size=high_total + low_total,
                support_count=high_total,
                control_count=low_total,
                domains=domains,
                status=PrincipleStatus.CANDIDATE,
            ))

        return candidates

    @staticmethod
    def _infer_category(prop_name: str) -> str:
        """Infer property category from name conventions."""
        cat_map = {
            "retry": "execution_model",
            "repair": "execution_model",
            "stateful": "execution_model",
            "verification": "verification",
            "artifact": "verification",
            "memory": "memory",
            "collaboration": "collaboration",
            "multi": "collaboration",
            "strategy": "reasoning",
            "calibration": "reasoning",
        }
        for key, category in cat_map.items():
            if key in prop_name.lower():
                return category
        return "execution_model"
