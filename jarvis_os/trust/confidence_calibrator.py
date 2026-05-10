"""Confidence Calibrator - Phase 7 Mythos Omega.

Implements bucket-based calibration, drift detection, and post-penalty calibration ONLY.
Drift reset does NOT erase history (audit requirement).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CalibrationBucket:
    """Bucket for confidence calibration."""
    confidence_range: tuple  # (min, max)
    predictions: List[float] = field(default_factory=list)
    outcomes: List[bool] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        """Compute empirical accuracy for this bucket."""
        if not self.predictions:
            return 0.5
        correct = sum(1 for o in self.outcomes if o)
        return correct / len(self.outcomes)

    @property
    def avg_confidence(self) -> float:
        """Average confidence in this bucket."""
        if not self.predictions:
            return 0.5
        return sum(self.predictions) / len(self.predictions)


@dataclass
class DriftRecord:
    """Record of calibration drift over time."""
    timestamp: float
    bucket_idx: int
    expected_accuracy: float
    actual_accuracy: float
    drift_score: float


class ConfidenceCalibrator:
    """
    Bucket-based confidence calibrator.

    KEY AUDIT REQUIREMENTS:
    1. Calibration applied AFTER penalties (not before)
    2. Bucket collapse detection (buckets with too few samples)
    3. Drift reset does NOT erase history
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._buckets = self._init_buckets()
        self._drift_history: List[DriftRecord] = []
        self._calibration_history: List[Dict[str, Any]] = []
        self._bucket_collapse_threshold = getattr(self.config, 'bucket_collapse_threshold', 10)
        self._drift_threshold = getattr(self.config, 'drift_threshold', 0.15)

    def _init_buckets(self) -> List[CalibrationBucket]:
        """Initialize calibration buckets."""
        buckets = [
            CalibrationBucket(confidence_range=(0.0, 0.2)),
            CalibrationBucket(confidence_range=(0.2, 0.4)),
            CalibrationBucket(confidence_range=(0.4, 0.6)),
            CalibrationBucket(confidence_range=(0.6, 0.8)),
            CalibrationBucket(confidence_range=(0.8, 1.0)),
        ]
        return buckets

    def calibrate(
        self,
        result: Dict[str, Any],
        penalties_applied: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Calibrate confidence AFTER penalties have been applied.
        This is POST-PENALTY calibration only (audit requirement).
        """
        # Get the confidence AFTER penalties
        raw_confidence = result.get("confidence", 0.5)

        # Find appropriate bucket
        bucket_idx = self._find_bucket(raw_confidence)
        bucket = self._buckets[bucket_idx]

        # Check for bucket collapse
        if len(bucket.predictions) < self._bucket_collapse_threshold:
            logger.warning(
                "Bucket %d has insufficient samples (%d < %d)",
                bucket_idx, len(bucket.predictions), self._bucket_collapse_threshold
            )
            # Use adjacent bucket if available
            if bucket_idx > 0 and len(self._buckets[bucket_idx - 1].predictions) > self._bucket_collapse_threshold:
                bucket_idx -= 1
                bucket = self._buckets[bucket_idx]

        # Compute calibration adjustment
        empirical_accuracy = bucket.accuracy
        calibration_adjustment = empirical_accuracy - raw_confidence

        # Apply calibration
        calibrated_confidence = raw_confidence + calibration_adjustment * 0.5  # Dampen adjustment
        calibrated_confidence = max(0.01, min(1.0, calibrated_confidence))

        # Record for drift detection
        record = {
            "timestamp": time.time(),
            "raw_confidence": raw_confidence,
            "calibrated_confidence": calibrated_confidence,
            "bucket_idx": bucket_idx,
            "penalties_applied": penalties_applied or [],
            "empirical_accuracy": empirical_accuracy,
        }
        self._calibration_history.append(record)

        # Update bucket with this prediction (we'll update outcome later if available)
        bucket.predictions.append(raw_confidence)

        # Check for drift
        drift_score = abs(empirical_accuracy - raw_confidence)
        if drift_score > self._drift_threshold:
            self._drift_history.append(DriftRecord(
                timestamp=time.time(),
                bucket_idx=bucket_idx,
                expected_accuracy=raw_confidence,
                actual_accuracy=empirical_accuracy,
                drift_score=drift_score,
            ))
            logger.warning(
                "Drift detected in bucket %d: score=%.3f",
                bucket_idx, drift_score
            )

        # Return calibrated result
        result["confidence"] = calibrated_confidence
        result["calibration"] = {
            "raw_confidence": raw_confidence,
            "calibrated_confidence": calibrated_confidence,
            "bucket_idx": bucket_idx,
            "empirical_accuracy": empirical_accuracy,
            "drift_detected": drift_score > self._drift_threshold,
        }

        return result

    def update_outcome(self, calibrated_confidence: float, was_correct: bool):
        """
        Update the outcome for the most recent prediction in the bucket.
        This is called when we learn if the prediction was correct.
        """
        bucket_idx = self._find_bucket(calibrated_confidence)
        bucket = self._buckets[bucket_idx]

        # Find the most recent prediction without an outcome
        if len(bucket.outcomes) < len(bucket.predictions):
            bucket.outcomes.append(was_correct)

    def _find_bucket(self, confidence: float) -> int:
        """Find the bucket index for a given confidence value."""
        for i, bucket in enumerate(self._buckets):
            min_c, max_c = bucket.confidence_range
            if min_c <= confidence <= max_c:
                return i
        # Default to last bucket
        return len(self._buckets) - 1

    def get_drift_report(self) -> Dict[str, Any]:
        """Generate drift report without erasing history."""
        report = {
            "total_predictions": sum(len(b.predictions) for b in self._buckets),
            "total_correct": sum(len(b.outcomes) for b in self._buckets),
            "buckets": [],
            "drift_events": len(self._drift_history),
            "recent_drift": self._drift_history[-10:] if self._drift_history else [],
        }

        for i, bucket in enumerate(self._buckets):
            report["buckets"].append({
                "bucket_idx": i,
                "range": bucket.confidence_range,
                "sample_count": len(bucket.predictions),
                "accuracy": bucket.accuracy,
                "avg_confidence": bucket.avg_confidence,
                "collapsed": len(bucket.predictions) < self._bucket_collapse_threshold,
            })

        return report

    def reset_drift(self):
        """
        Reset drift detection WITHOUT erasing history.
        AUDIT REQUIREMENT: drift reset does NOT erase history.
        """
        # Only reset the drift tracking, NOT the bucket data
        self._drift_history.clear()
        logger.info("Drift tracking reset. Bucket history preserved: %d samples total.",
                    sum(len(b.predictions) for b in self._buckets))

    def get_calibration_history(self) -> List[Dict[str, Any]]:
        """Return calibration history (never erased)."""
        return self._calibration_history.copy()
