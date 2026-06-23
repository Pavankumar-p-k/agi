"""AccuracyTracker — tracks prediction accuracy across domains and categories.

Answers:
  - Which beliefs in which domains tend to be correct?
  - What is the historical accuracy for this category of knowledge?
  - How noisy is a particular domain (contradiction rate)?

Accuracy is tracked at three granularities:
  1. Per-domain: "how accurate are predictions in the android domain?"
  2. Per-category: "how accurate are principles vs heuristics?"
  3. Per-source: "how accurate is this specific source?"

Combined accuracy for a belief blends these based on available data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from core.belief.models import AccuracyRecord, DomainAccuracyMetrics

# Minimum records before accuracy is trusted over the prior
MIN_RECORDS_FOR_ACCURACY = 3
# Prior accuracy (before any data, assume 50%)
PRIOR_ACCURACY = 0.5
# Smoothing weight for the prior
PRIOR_WEIGHT = 5.0

# Error threshold for considering a prediction "correct"
CORRECT_THRESHOLD = 0.15


class AccuracyTracker:
    """Tracks prediction accuracy across domains, categories, and sources.

    Thread-safe if the caller holds the store's lock externally.
    """

    def __init__(self):
        self._records: list[AccuracyRecord] = []

    def record(
        self,
        belief_id: str,
        domain: str,
        category: str,
        predicted_value: float,
        actual_value: float,
        source_id: str | None = None,
    ) -> AccuracyRecord:
        """Record whether a belief/prediction was correct."""
        error = abs(predicted_value - actual_value)
        record = AccuracyRecord(
            record_id=str(uuid.uuid4()),
            belief_id=belief_id,
            domain=domain,
            category=category,
            predicted_value=predicted_value,
            actual_value=actual_value,
            error=error,
            timestamp=datetime.now(timezone.utc),
            source_id=source_id,
        )
        self._records.append(record)
        return record

    def get_accuracy(
        self,
        domain: str | None = None,
        category: str | None = None,
        source_id: str | None = None,
    ) -> float:
        """Compute smoothed accuracy for the given filters.

        Returns PRIOR_ACCURACY if insufficient data.
        Uses Bayesian smoothing with a prior.
        """
        filtered = self._filter(domain=domain, category=category, source_id=source_id)
        if not filtered:
            return PRIOR_ACCURACY

        correct = sum(
            1 for r in filtered if r.error <= CORRECT_THRESHOLD
        )
        total = len(filtered)

        smoothed = (correct + PRIOR_WEIGHT * PRIOR_ACCURACY) / (
            total + PRIOR_WEIGHT
        )
        return max(0.0, min(1.0, smoothed))

    def get_contradiction_rate(
        self, domain: str | None = None
    ) -> float:
        """Estimate contradiction rate in a domain.

        Looks at records where the same belief_id has multiple entries
        with diverging predicted values within the domain.
        """
        filtered = self._filter(domain=domain)
        if len(filtered) < 2:
            return 0.0

        belief_values: dict[str, list[float]] = {}
        for r in filtered:
            if r.belief_id not in belief_values:
                belief_values[r.belief_id] = []
            belief_values[r.belief_id].append(r.predicted_value)

        contradictory = sum(
            1 for values in belief_values.values()
            if len(values) >= 2 and max(values) - min(values) > CORRECT_THRESHOLD
        )
        total = len(belief_values)
        return contradictory / total if total > 0 else 0.0

    def get_domain_metrics(self, domain: str) -> DomainAccuracyMetrics:
        """Get aggregated accuracy metrics for a specific domain."""
        domain_records = self._filter(domain=domain)
        if not domain_records:
            return DomainAccuracyMetrics(domain=domain)

        correct = sum(
            1 for r in domain_records if r.error <= CORRECT_THRESHOLD
        )
        mean_error = sum(r.error for r in domain_records) / len(domain_records)
        contradiction_rate = self.get_contradiction_rate(domain=domain)

        return DomainAccuracyMetrics(
            domain=domain,
            total_records=len(domain_records),
            correct_predictions=correct,
            accuracy=correct / len(domain_records) if domain_records else 0.0,
            mean_error=mean_error,
            contradiction_rate=contradiction_rate,
            last_updated=datetime.now(timezone.utc),
        )

    def get_all_domain_metrics(self) -> list[DomainAccuracyMetrics]:
        domains = set(r.domain for r in self._records)
        return [self.get_domain_metrics(d) for d in sorted(domains)]

    def get_all_records(self) -> list[AccuracyRecord]:
        return list(self._records)

    def record_count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()

    def set_records(self, records: list[AccuracyRecord]) -> None:
        self._records = list(records)

    def _filter(
        self,
        domain: str | None = None,
        category: str | None = None,
        source_id: str | None = None,
    ) -> list[AccuracyRecord]:
        result = self._records
        if domain:
            result = [r for r in result if r.domain == domain]
        if category:
            result = [r for r in result if r.category == category]
        if source_id:
            result = [r for r in result if r.source_id == source_id]
        return result
