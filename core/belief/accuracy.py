"""Prediction accuracy tracking for the Belief Quality Engine."""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from core.belief.models import AccuracyRecord, DomainAccuracyMetrics

_PRIOR = 0.5
_PRIOR_WEIGHT = 2.0
_CORRECT_THRESHOLD = 0.1


class AccuracyTracker:
    """Track how well predictions match observed outcomes."""

    def __init__(self, records: Optional[List[AccuracyRecord]] = None) -> None:
        self.records: List[AccuracyRecord] = []
        if records:
            self.set_records(records)

    # ── internals ────────────────────────────────────────────────────

    @staticmethod
    def _is_correct(record: AccuracyRecord) -> bool:
        return abs(record.predicted_value - record.actual_value) <= _CORRECT_THRESHOLD

    def _filtered(
        self,
        domain: Optional[str] = None,
        category: Optional[str] = None,
        belief_id: Optional[str] = None,
    ) -> List[AccuracyRecord]:
        results = []
        for record in self.records:
            if domain is not None and record.domain != domain:
                continue
            if category is not None and record.category != category:
                continue
            if belief_id is not None and record.belief_id != belief_id:
                continue
            results.append(record)
        return results

    # ── public API ───────────────────────────────────────────────────

    def record(
        self,
        belief_id: str,
        domain: str,
        category: str,
        predicted_value: float,
        actual_value: float,
    ) -> AccuracyRecord:
        record = AccuracyRecord(
            record_id=uuid.uuid4().hex,
            belief_id=belief_id,
            domain=domain,
            category=str(getattr(category, "value", category)),
            predicted_value=float(predicted_value),
            actual_value=float(actual_value),
            error=abs(float(predicted_value) - float(actual_value)),
        )
        self.records.append(record)
        return record

    def get_accuracy(
        self,
        domain: Optional[str] = None,
        category: Optional[str] = None,
        belief_id: Optional[str] = None,
    ) -> float:
        category = getattr(category, "value", category)
        sample = self._filtered(domain=domain, category=category, belief_id=belief_id)
        if not sample:
            return _PRIOR
        correct = sum(1 for r in sample if self._is_correct(r))
        return (correct + _PRIOR * _PRIOR_WEIGHT) / (len(sample) + _PRIOR_WEIGHT)

    def get_contradiction_rate(
        self, domain: Optional[str] = None, category: Optional[str] = None
    ) -> float:
        category = getattr(category, "value", category)
        sample = self._filtered(domain=domain, category=category)
        if not sample:
            return 0.0

        groups: Dict[str, List[AccuracyRecord]] = {}
        for record in sample:
            groups.setdefault(record.belief_id, []).append(record)

        contradictory = 0
        for group in groups.values():
            values = [r.predicted_value for r in group]
            if max(values) - min(values) > _CORRECT_THRESHOLD:
                contradictory += len(group)
        return contradictory / len(sample)

    def get_domain_metrics(self, domain: str) -> DomainAccuracyMetrics:
        sample = self._filtered(domain=domain)
        total = len(sample)
        correct = sum(1 for r in sample if self._is_correct(r))
        accuracy = (correct / total) if total else 0.0
        return DomainAccuracyMetrics(
            domain=domain,
            total_records=total,
            correct_predictions=correct,
            accuracy=accuracy,
        )

    def get_all_domain_metrics(self) -> List[DomainAccuracyMetrics]:
        domains: List[str] = []
        for record in self.records:
            if record.domain not in domains:
                domains.append(record.domain)
        return [self.get_domain_metrics(domain) for domain in domains]

    def get_all_records(self) -> List[AccuracyRecord]:
        return list(self.records)

    def record_count(self) -> int:
        return len(self.records)

    def clear(self) -> None:
        self.records = []

    def set_records(self, records: List[AccuracyRecord]) -> None:
        self.records = []
        for record in records or []:
            if isinstance(record, dict):
                record = AccuracyRecord.from_dict(record)
            self.records.append(record)
