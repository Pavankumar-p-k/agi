"""
Mythos v13 — Health Predictor
================================
Upgrades MetaGovernor from reactive → anticipatory.

Uses the bounded snapshot history already stored in HealthTelemetry
to compute health trends and forecast failures BEFORE they occur.

DESIGN:
  - No model calls — pure arithmetic (slope, weighted avg, exponential smoothing)
  - O(window) per prediction — bounded and fast
  - Returns PredictionResult with confidence interval
  - Integrated into MetaGovernor._analyze() as first step
  - Signals are cross-validated: slope must agree with raw values before acting

PREDICTION METHODS:
  1. Linear slope (least-squares over last N snapshots)
  2. Exponential weighted moving average (EWMA) — recent data weighted more
  3. Composite: slope × magnitude × volatility → normalized risk score

THRESHOLDS are adaptive (updated by MetaGovernor._adapt_thresholds):
  - preemptive_throttle: predicted score drops below this → PREEMPTIVE_THROTTLE
  - predicted_critical: forecast hits this within N steps → PREEMPTIVE_SAFE_MODE
"""

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

from utils.logger import SystemLogger

logger = SystemLogger(__name__)

# Prediction horizon: how many cycles ahead to forecast
FORECAST_HORIZON = 3      # predict 3 poll-cycles ahead
MIN_HISTORY       = 5     # minimum snapshots needed to forecast
EWMA_ALPHA        = 0.35  # exponential smoothing weight (higher = more reactive)


@dataclass
class PredictionResult:
    """Forecasted health state N steps ahead."""
    predicted_score:    float    # estimated health N cycles from now
    current_slope:      float    # positive=improving, negative=degrading
    risk_score:         float    # 0-1 composite risk (higher=worse)
    confidence:         float    # how confident we are (based on data quantity)
    horizon_cycles:     int      # how far ahead this predicts
    signals:            Dict[str, float]  # contributing signals
    action:             str      # "" | "preemptive_throttle" | "preemptive_safe_mode"
    reason:             str

    @property
    def is_actionable(self) -> bool:
        return bool(self.action) and self.confidence >= 0.60


class HealthPredictor:
    """
    Lightweight health trend analyzer and failure forecaster.
    
    Injected into MetaGovernor as an optional dependency.
    Called at the START of each _analyze() cycle.
    
    Usage:
        predictor = HealthPredictor()
        prediction = predictor.predict(telemetry)
        if prediction.is_actionable:
            # take preemptive action before actual degradation
    """

    def __init__(
        self,
        preemptive_throttle_threshold: float = 0.55,  # throttle if predicted to drop below
        preemptive_critical_threshold: float = 0.30,  # safe_mode if predicted to hit this
        forecast_horizon:              int   = FORECAST_HORIZON,
    ):
        self.throttle_threshold = preemptive_throttle_threshold
        self.critical_threshold = preemptive_critical_threshold
        self.horizon            = forecast_horizon
        self._predictions:      List[PredictionResult] = []
        self._max_predictions   = 200
        self._accuracy_tracker: Deque[float] = deque(maxlen=50)  # |predicted - actual|

        # Adaptive threshold adjustments
        self._throttle_history: List[bool] = []   # True = preemptive was justified

    def predict(self, telemetry) -> PredictionResult:
        """
        Forecast health trajectory from snapshot history.
        Returns PredictionResult; action="" if insufficient data or stable.
        """
        snapshots = list(telemetry._snapshots)

        if len(snapshots) < MIN_HISTORY:
            return PredictionResult(
                predicted_score=1.0, current_slope=0.0, risk_score=0.0,
                confidence=0.0, horizon_cycles=self.horizon,
                signals={}, action="", reason="insufficient_history",
            )

        scores = [s.global_score for s in snapshots]

        # Signal 1: Linear slope over last N points
        slope = self._linear_slope(scores[-min(10, len(scores)):])

        # Signal 2: EWMA — recent score weighted more
        ewma_score = self._ewma(scores)

        # Signal 3: Predicted score N cycles ahead (linear extrapolation)
        predicted = max(0.0, min(1.0, ewma_score + slope * self.horizon))

        # Signal 4: Volatility — std dev of recent scores
        recent = scores[-10:]
        mean_r = sum(recent) / len(recent)
        volatility = math.sqrt(sum((s - mean_r)**2 for s in recent) / max(len(recent), 1))

        # Signal 5: Latency trend
        lat_trend = self._latency_trend(telemetry)

        # Signal 6: Error rate trend
        err_trend = self._error_trend(telemetry)

        # Composite risk: weighted combination of negative signals
        risk_score = round(min(1.0, max(0.0,
            (1 - predicted) * 0.40 +
            max(0, -slope * 10) * 0.25 +   # slope contribution (negative slope = risk)
            volatility * 0.15 +
            lat_trend * 0.10 +
            err_trend * 0.10
        )), 4)

        # Confidence: scales with history length, caps at 0.90
        confidence = round(min(0.90, len(snapshots) / 30), 3)

        # Determine action
        action = ""
        reason = ""
        if predicted < self.critical_threshold and slope < -0.02 and confidence >= 0.60:
            action = "preemptive_safe_mode"
            reason = f"Predicted score {predicted:.3f} < critical={self.critical_threshold}, slope={slope:.4f}"
        elif predicted < self.throttle_threshold and slope < -0.01 and confidence >= 0.55:
            action = "preemptive_throttle"
            reason = f"Predicted score {predicted:.3f} < throttle={self.throttle_threshold}, slope={slope:.4f}"

        result = PredictionResult(
            predicted_score=round(predicted, 4),
            current_slope=round(slope, 5),
            risk_score=risk_score,
            confidence=confidence,
            horizon_cycles=self.horizon,
            signals={
                "ewma_score":   round(ewma_score, 4),
                "slope":        round(slope, 5),
                "volatility":   round(volatility, 4),
                "latency_trend": round(lat_trend, 4),
                "error_trend":  round(err_trend, 4),
            },
            action=action,
            reason=reason,
        )

        if len(self._predictions) >= self._max_predictions:
            self._predictions = self._predictions[-self._max_predictions:]
        self._predictions.append(result)

        if action:
            logger.info(
                f"[HealthPredictor] {action}: predicted={predicted:.3f} "
                f"slope={slope:.4f} conf={confidence:.2f} reason={reason}"
            )

        return result

    def record_actual(self, actual_score: float):
        """
        Called each cycle with the ACTUAL score to track prediction accuracy.
        Used to calibrate forecast confidence.
        """
        if self._predictions:
            # Compare last prediction to actual
            last = self._predictions[-1]
            error = abs(last.predicted_score - actual_score)
            self._accuracy_tracker.append(error)

    def get_forecast_accuracy(self) -> float:
        """Mean absolute prediction error. Lower is better."""
        if not self._accuracy_tracker:
            return 0.0
        return round(sum(self._accuracy_tracker) / len(self._accuracy_tracker), 4)

    def update_thresholds(self, throttle: float = None, critical: float = None):
        """Adjust thresholds within safe bounds."""
        if throttle is not None:
            self.throttle_threshold = round(min(0.75, max(0.35, throttle)), 3)
        if critical is not None:
            self.critical_threshold = round(min(0.45, max(0.10, critical)), 3)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_predictions":   len(self._predictions),
            "forecast_accuracy":   self.get_forecast_accuracy(),
            "throttle_threshold":  self.throttle_threshold,
            "critical_threshold":  self.critical_threshold,
            "horizon_cycles":      self.horizon,
            "preemptive_actions":  sum(1 for p in self._predictions if p.action),
        }

    # ── Internal computation ──────────────────────────────────────

    @staticmethod
    def _linear_slope(values: List[float]) -> float:
        """Least-squares slope of values list. Returns 0.0 for <2 values."""
        n = len(values)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        den = sum((i - x_mean)**2 for i in range(n))
        return num / den if den > 0 else 0.0

    @staticmethod
    def _ewma(values: List[float], alpha: float = EWMA_ALPHA) -> float:
        """Exponential weighted moving average. Most recent value weighted most."""
        if not values:
            return 1.0
        ewma = values[0]
        for v in values[1:]:
            ewma = alpha * v + (1 - alpha) * ewma
        return ewma

    def _latency_trend(self, telemetry) -> float:
        """Normalized latency trend: 0=stable/improving, 1=rapidly increasing."""
        latencies = list(telemetry._task_latencies)
        if len(latencies) < 4:
            return 0.0
        slope = self._linear_slope(latencies[-10:])
        # Normalize: 1000ms/cycle increase → 1.0 risk contribution
        return min(1.0, max(0.0, slope / 1000.0))

    def _error_trend(self, telemetry) -> float:
        """Normalized error rate trend: 0=stable/improving, 1=worsening."""
        successes = list(telemetry._task_successes)
        if len(successes) < 4:
            return 0.0
        # Convert to failure rates in windows of 5
        def chunk_fail_rate(chunk):
            return sum(1 for s in chunk if not s) / max(len(chunk), 1)
        n = len(successes)
        if n >= 10:
            early = chunk_fail_rate(successes[:n//2])
            late  = chunk_fail_rate(successes[n//2:])
            trend = late - early  # positive = worsening
        else:
            trend = chunk_fail_rate(successes)
        return round(min(1.0, max(0.0, trend)), 4)
