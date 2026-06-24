"""Opportunity Forecasting (Phase 21) — predicts future high-value opportunities.

The architecture now answers:
  Phase 17: What opportunities exist?
  Phase 19: How do they depend on each other?
  Phase 22: Which bottlenecks constrain the system?
  Phase 23: What sequence should we follow?

Phase 21 answers: What will likely become important next?

Formula:
  future_score = current_score × (1 + trend_factor) × (1 + bottleneck_factor)
                 × unlock_value_influence

Where:
  trend_factor:        derived from historical score changes
                       (positive = scores rising = improving = lower future opp)
                       (negative = scores falling = worsening = higher future opp)
  bottleneck_factor:   downstream pressure from Phase 22
  unlock_value_influence: future potential from Phase 19

The system moves from reactive optimization to anticipatory optimization.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

# Trend classification thresholds
TREND_IMPROVING_THRESHOLD = 0.02   # scores rising faster than this → improving
TREND_DECLINING_THRESHOLD = -0.02  # scores falling faster than this → declining

# Time horizon thresholds (in arbitrary score-change units)
SHORT_TERM_THRESHOLD = 0.15   # high urgency
MEDIUM_TERM_THRESHOLD = 0.05  # moderate urgency

# Default velocity when no historical data
DEFAULT_VELOCITY = 0.0

# Weight of bottleneck pressure in the forecast formula
BOTTLENECK_WEIGHT = 0.30

# Weight of unlock value in the forecast formula
UNLOCK_WEIGHT = 0.20


# ── Models ────────────────────────────────────────────────────────────


class ForecastHorizon(str):
    """Time horizon for a forecasted opportunity."""

    SHORT_TERM = "short_term"    # urgent, actionable now
    MEDIUM_TERM = "medium_term"  # emerging, plan for next cycle
    LONG_TERM = "long_term"      # speculative but high potential


class ForecastTrend(str):
    """Direction of historical score movement."""

    IMPROVING = "improving"   # scores rising → system getting better
    DECLINING = "declining"   # scores falling → system getting worse
    STABLE = "stable"         # no significant trend


@dataclass
class HistoricalDataPoint:
    """A single historical observation for a system.

    Attributes:
        timestamp: when this was recorded
        opportunity_score: the opportunity score at that time
        source: where the observation came from
    """

    timestamp: str
    opportunity_score: float
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "score": round(self.opportunity_score, 3),
            "source": self.source,
        }


@dataclass
class ForecastedOpportunity:
    """A predicted future opportunity for a subsystem.

    Attributes:
        target_system: canonical system name
        current_score: current Phase 17 opportunity score
        predicted_score: forecasted score for the next cycle
        confidence: 0.0–1.0 confidence in this forecast
        horizon: short/medium/long term
        trend: improving/declining/stable
        velocity: rate of score change per unit time
        unlock_value: how much this unlocks (Phase 19)
        bottleneck_pressure: bottleneck total_constrained_value (Phase 22)
        rationale: why this forecast was made
        evidence: supporting data points
    """

    target_system: str
    current_score: float
    predicted_score: float
    confidence: float = 0.5
    horizon: str = ForecastHorizon.MEDIUM_TERM
    trend: str = ForecastTrend.STABLE
    velocity: float = 0.0
    unlock_value: float = 1.0
    bottleneck_pressure: float = 0.0
    rationale: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.target_system,
            "current_score": round(self.current_score, 3),
            "predicted_score": round(self.predicted_score, 3),
            "confidence": round(self.confidence, 3),
            "horizon": self.horizon,
            "trend": self.trend,
            "velocity": round(self.velocity, 4),
            "unlock_value": round(self.unlock_value, 3),
            "bottleneck_pressure": round(self.bottleneck_pressure, 3),
            "rationale": self.rationale,
        }


@dataclass
class ForecastResult:
    """Complete forecast output for all subsystems.

    Attributes:
        forecasts: list of scored ForecastedOpportunity
        generated_at: when this forecast was made
        total_systems: number of systems analyzed
        average_confidence: mean confidence across all forecasts
    """

    forecasts: list[ForecastedOpportunity] = field(default_factory=list)
    generated_at: datetime | None = None
    total_systems: int = 0
    average_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "forecasts": [f.to_dict() for f in sorted(
                self.forecasts, key=lambda x: x.predicted_score, reverse=True
            )],
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "total_systems": self.total_systems,
            "average_confidence": round(self.average_confidence, 3),
        }

    def top(self, n: int = 5) -> list[ForecastedOpportunity]:
        """Return the n highest-scored forecasts."""
        return sorted(self.forecasts, key=lambda f: f.predicted_score, reverse=True)[:n]


# ── Forecasting Engine ────────────────────────────────────────────────


class ForecastingEngine:
    """Predicts future opportunity scores using trend + bottleneck + unlock analysis.

    Usage:
        engine = ForecastingEngine()
        result = engine.forecast(
            opportunities=opportunities,
            graph=opportunity_graph,
            bottlenecks=bottleneck_list,
            history_store=opportunity_store,    # optional
        )
        for f in result.top(5):
            print(f"{f.target_system}: {f.predicted_score:.3f} ({f.horizon})")
    """

    def __init__(
        self,
        bottleneck_weight: float = BOTTLENECK_WEIGHT,
        unlock_weight: float = UNLOCK_WEIGHT,
    ):
        self.bottleneck_weight = bottleneck_weight
        self.unlock_weight = unlock_weight

    def forecast(
        self,
        opportunities: list[Any],
        graph: Any,
        bottlenecks: list[Any] | None = None,
        history_store: Any | None = None,
    ) -> ForecastResult:
        """Generate forecasts for all subsystems with opportunities.

        Args:
            opportunities: Phase 17 Opportunity list
            graph: Phase 19/20 OpportunityGraph
            bottlenecks: Phase 22 Bottleneck list (optional)
            history_store: Phase 17.1 OpportunityStore for historical data (optional)

        Returns:
            ForecastResult with scored forecasts
        """
        now = datetime.now(timezone.utc)

        # Build bottleneck map
        bottleneck_map: dict[str, float] = {}
        if bottlenecks:
            for b in bottlenecks:
                bottleneck_map[b.subsystem] = b.total_constrained_value

        # Build historical data map
        history_map: dict[str, list[HistoricalDataPoint]] = {}
        if history_store:
            history_map = self._collect_history(history_store, graph)

        forecasts: list[ForecastedOpportunity] = []

        for opp in opportunities:
            system = opp.target_system
            node = graph.get_node(system)
            if node is None:
                continue

            current_score = opp.opportunity_score
            unlock_value = node.unlock_value
            bottleneck_pressure = bottleneck_map.get(system, 0.0)
            history = history_map.get(system, [])

            # Compute trend and velocity from history
            velocity, trend = self._compute_trend(history)
            if velocity == 0.0:
                velocity, trend = self._estimate_velocity(
                    current_score, unlock_value, bottleneck_pressure
                )

            # Compute forecast
            predicted_score, confidence = self._compute_forecast(
                current_score, velocity, trend, unlock_value,
                bottleneck_pressure, history,
            )

            horizon = self._classify_horizon(
                current_score, velocity, bottleneck_pressure, unlock_value
            )

            rationale = self._build_rationale(
                system, current_score, predicted_score, velocity, trend,
                horizon, unlock_value, bottleneck_pressure, confidence,
            )

            evidence = self._build_evidence(
                history, velocity, bottleneck_pressure, unlock_value
            )

            forecasts.append(ForecastedOpportunity(
                target_system=system,
                current_score=round(current_score, 3),
                predicted_score=round(predicted_score, 3),
                confidence=round(confidence, 3),
                horizon=horizon,
                trend=trend,
                velocity=round(velocity, 4),
                unlock_value=round(unlock_value, 3),
                bottleneck_pressure=round(bottleneck_pressure, 3),
                rationale=rationale,
                evidence=evidence,
            ))

        avg_conf = (
            sum(f.confidence for f in forecasts) / len(forecasts)
            if forecasts else 0.0
        )

        # Sort descending by predicted_score
        forecasts.sort(key=lambda f: f.predicted_score, reverse=True)

        return ForecastResult(
            forecasts=forecasts,
            generated_at=now,
            total_systems=len(forecasts),
            average_confidence=avg_conf,
        )

    # ── Trend Analysis ──────────────────────────────────────────────

    def _compute_trend(
        self, history: list[HistoricalDataPoint]
    ) -> tuple[float, str]:
        """Compute velocity (score change per point) and trend direction.

        Uses simple linear regression on the last N data points.
        If insufficient data, returns (0.0, STABLE).
        """
        if len(history) < 2:
            return DEFAULT_VELOCITY, ForecastTrend.STABLE

        # Simple: compute average delta between consecutive points
        deltas = []
        sorted_h = sorted(history, key=lambda h: h.timestamp)
        for i in range(1, len(sorted_h)):
            delta = sorted_h[i].opportunity_score - sorted_h[i - 1].opportunity_score
            deltas.append(delta)

        if not deltas:
            return DEFAULT_VELOCITY, ForecastTrend.STABLE

        velocity = sum(deltas) / len(deltas)

        if velocity > TREND_IMPROVING_THRESHOLD:
            trend = ForecastTrend.IMPROVING
        elif velocity < TREND_DECLINING_THRESHOLD:
            trend = ForecastTrend.DECLINING
        else:
            trend = ForecastTrend.STABLE

        return velocity, trend

    def _estimate_velocity(
        self,
        current_score: float,
        unlock_value: float,
        bottleneck_pressure: float,
    ) -> tuple[float, str]:
        """Estimate velocity when no historical data exists.

        Uses heuristics: high bottleneck pressure + high unlock value
        suggests the system is likely declining (being constrained).
        """
        estimated = DEFAULT_VELOCITY

        # High bottleneck pressure + high unlock → likely declining
        if bottleneck_pressure > 0.3 and unlock_value > 1.5:
            estimated = -0.03
        # High current score + low unlock → likely stable/improving
        elif current_score > 0.5 and unlock_value < 1.2:
            estimated = 0.01

        trend = ForecastTrend.STABLE
        if estimated > TREND_IMPROVING_THRESHOLD:
            trend = ForecastTrend.IMPROVING
        elif estimated < TREND_DECLINING_THRESHOLD:
            trend = ForecastTrend.DECLINING

        return estimated, trend

    # ── Forecasting Formula ─────────────────────────────────────────

    def _compute_forecast(
        self,
        current_score: float,
        velocity: float,
        trend: str,
        unlock_value: float,
        bottleneck_pressure: float,
        history: list[HistoricalDataPoint],
    ) -> tuple[float, float]:
        """Compute predicted future score and confidence.

        Formula:
            future_score = current_score × (1 + trend_factor) × (1 + bottleneck_factor)
                          × unlock_factor

        Where:
            trend_factor = -velocity (if improving, future opportunity shrinks)
            bottleneck_factor = bottleneck_pressure × BOTTLENECK_WEIGHT
            unlock_factor = 1 + (unlock_value - 1) × UNLOCK_WEIGHT
        """
        # Trend factor: if system is improving, future opportunity decreases
        # If system is declining, future opportunity increases
        trend_factor = -velocity  # negative velocity → positive factor

        # Bottleneck factor: more downstream pressure → higher opportunity
        bottleneck_factor = bottleneck_pressure * self.bottleneck_weight

        # Unlock factor: higher unlock → more future potential
        unlock_factor = 1.0 + (unlock_value - 1.0) * self.unlock_weight

        predicted = current_score * (1.0 + trend_factor) * (1.0 + bottleneck_factor) * unlock_factor

        # Clamp to reasonable range
        predicted = max(0.01, min(1.0, predicted))

        # Confidence: based on data volume and signal quality
        confidence = self._compute_confidence(history, velocity, len(history))

        return round(predicted, 3), round(confidence, 3)

    def _compute_confidence(
        self,
        history: list[HistoricalDataPoint],
        velocity: float,
        data_points: int,
    ) -> float:
        """Compute forecast confidence from data quality.

        Base 0.30. Bonuses for:
          - Historical data (up to +0.40 for 10+ points)
          - Clear trend signal (up to +0.20 for non-zero velocity)
          - Multiple data sources (up to +0.10)
        """
        conf = 0.30  # base

        # Data volume bonus
        if data_points >= 10:
            conf += 0.40
        elif data_points >= 5:
            conf += 0.30
        elif data_points >= 2:
            conf += 0.15

        # Trend signal bonus
        if abs(velocity) > 0.01:
            conf += 0.20

        return min(1.0, conf)

    # ── Horizon Classification ──────────────────────────────────────

    def _classify_horizon(
        self,
        current_score: float,
        velocity: float,
        bottleneck_pressure: float,
        unlock_value: float,
    ) -> str:
        """Classify the opportunity into short/medium/long term.

        Short-term: high current score, declining, high bottleneck pressure
        Long-term:  lower current score but high unlock value
        Default:    medium-term
        """
        # Short-term signals
        if velocity < TREND_DECLINING_THRESHOLD and bottleneck_pressure > 0.3:
            return ForecastHorizon.SHORT_TERM
        if current_score > SHORT_TERM_THRESHOLD and bottleneck_pressure > 0.5:
            return ForecastHorizon.SHORT_TERM

        # Long-term signals
        if current_score < MEDIUM_TERM_THRESHOLD and unlock_value > 2.0:
            return ForecastHorizon.LONG_TERM
        if unlock_value > 3.0:
            return ForecastHorizon.LONG_TERM

        return ForecastHorizon.MEDIUM_TERM

    # ── History Collection ──────────────────────────────────────────

    def _collect_history(
        self,
        history_store: Any,
        graph: Any,
    ) -> dict[str, list[HistoricalDataPoint]]:
        """Collect historical opportunity scores from the store.

        Groups records by target_system and sorts by time.
        """
        history_map: dict[str, list[HistoricalDataPoint]] = defaultdict(list)

        try:
            records = history_store.list_records(limit=1000)
            if not records:
                return dict(history_map)

            for record in records:
                system = record.target_system
                if graph.get_node(system) is None:
                    continue
                ts = record.completed_at or record.selected_at or ""
                if not ts:
                    continue
                score = record.predicted_score
                history_map[system].append(HistoricalDataPoint(
                    timestamp=ts,
                    opportunity_score=score,
                    source=record.source,
                ))

        except Exception as e:
            logger.warning(f"History collection error: {e}")

        return dict(history_map)

    # ── Rationale ───────────────────────────────────────────────────

    def _build_rationale(
        self,
        system: str,
        current: float,
        predicted: float,
        velocity: float,
        trend: str,
        horizon: str,
        unlock_value: float,
        bottleneck_pressure: float,
        confidence: float,
    ) -> str:
        parts = [f"{system}: {current:.3f} -> {predicted:.3f} (conf={confidence:.2f})"]

        if trend == ForecastTrend.DECLINING:
            parts.append("Declining trend suggests increasing urgency.")
        elif trend == ForecastTrend.IMPROVING:
            parts.append("Improving trend suggests decreasing opportunity.")

        if bottleneck_pressure > 0.3:
            parts.append(f"High bottleneck pressure ({bottleneck_pressure:.2f}).")
        if unlock_value > 1.5:
            parts.append(f"High unlock value ({unlock_value:.2f}).")

        horizon_labels = {
            ForecastHorizon.SHORT_TERM: "Act now.",
            ForecastHorizon.MEDIUM_TERM: "Plan for next cycle.",
            ForecastHorizon.LONG_TERM: "Monitor; high future potential.",
        }
        parts.append(horizon_labels.get(horizon, ""))

        return " ".join(parts)

    def _build_evidence(
        self,
        history: list[HistoricalDataPoint],
        velocity: float,
        bottleneck_pressure: float,
        unlock_value: float,
    ) -> list[str]:
        evidence = []
        if history:
            evidence.append(f"{len(history)} historical data points")
            evidence.append(f"Velocity: {velocity:.4f}")
        if bottleneck_pressure > 0:
            evidence.append(f"Bottleneck pressure: {bottleneck_pressure:.3f}")
        if unlock_value != 1.0:
            evidence.append(f"Unlock value: {unlock_value:.3f}")
        return evidence
