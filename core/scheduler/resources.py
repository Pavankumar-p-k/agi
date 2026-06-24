"""ResourceEstimate — predict and calibrate resource usage per activity type.

Phase 8.3C: extends ActivityIntelligence with cost prediction.

Tracks per node_type:
  - token_cost (estimated LLM tokens)
  - api_cost (estimated API call count)
  - browser_steps (estimated browser navigation steps)
  - memory_mb (estimated peak memory in MB)

Prediction method: historical averages (same pattern as duration prediction).
Calibration method: self-correcting multiplier per dimension.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default priors for unknown activity types
DEFAULT_TOKENS = 500
DEFAULT_API_COST = 0.0
DEFAULT_MEMORY_MB = 50.0
DEFAULT_BROWSER_STEPS = 2

# Resource weight in priority scoring
RESOURCE_PENALTY_PER_UNIT = 1
MAX_RESOURCE_PENALTY = 30

# Resource dimension weights for composite cost (relative importance)
RESOURCE_DIM_WEIGHTS: dict[str, float] = {
    "tokens": 0.30,
    "api_cost": 0.25,
    "memory_mb": 0.15,
    "browser_steps": 0.30,
}


@dataclass
class ResourceEstimate:
    """Predicted resource usage for an activity before execution.

    Each dimension has a predicted value and the confidence in that prediction.
    """
    token_cost: float = DEFAULT_TOKENS
    api_cost: float = DEFAULT_API_COST
    memory_mb: float = DEFAULT_MEMORY_MB
    browser_steps: float = DEFAULT_BROWSER_STEPS
    confidence: float = 0.0
    sample_size: int = 0
    node_type: str = ""


@dataclass
class ResourceUsage:
    """Actual resource usage recorded after execution."""
    token_cost: float = 0.0
    api_cost: float = 0.0
    memory_mb: float = 0.0
    browser_steps: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "token_cost": self.token_cost,
            "api_cost": self.api_cost,
            "memory_mb": self.memory_mb,
            "browser_steps": self.browser_steps,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> ResourceUsage:
        return ResourceUsage(
            token_cost=float(d.get("token_cost", 0)),
            api_cost=float(d.get("api_cost", 0)),
            memory_mb=float(d.get("memory_mb", DEFAULT_MEMORY_MB)),
            browser_steps=float(d.get("browser_steps", DEFAULT_BROWSER_STEPS)),
        )


@dataclass
class ResourceCalibration:
    """Calibration for resource predictions per node_type.

    Each dimension has a multiplier: if predictions consistently underestimate,
    the multiplier (>1.0) corrects them. Multiplier < 1.0 means overestimation.
    """
    node_type: str = ""
    sample_count: int = 0
    token_multiplier: float = 1.0
    api_cost_multiplier: float = 1.0
    memory_multiplier: float = 1.0
    browser_steps_multiplier: float = 1.0
    overall_accuracy: float = 0.5  # 0.0-1.0

    # Predicted vs actual columns for the SQL query
    _DIMENSIONS = ["tokens", "api_cost", "memory_mb", "browser_steps"]

    @property
    def dims(self) -> list[str]:
        return list(self._DIMENSIONS)


# Column names for DB migration and queries
PRED_COLS = ["predicted_tokens", "predicted_api_cost", "predicted_memory_mb", "predicted_browser_steps"]
ACTUAL_COLS = ["actual_tokens", "actual_api_cost", "actual_memory_mb", "actual_browser_steps"]
ALL_RESOURCE_COLS = PRED_COLS + ACTUAL_COLS

RESOURCE_MIGRATIONS: list[tuple[str, str]] = [
    ("predicted_tokens", "INTEGER"),
    ("predicted_api_cost", "REAL"),
    ("predicted_memory_mb", "REAL"),
    ("predicted_browser_steps", "INTEGER"),
    ("actual_tokens", "INTEGER"),
    ("actual_api_cost", "REAL"),
    ("actual_memory_mb", "REAL"),
    ("actual_browser_steps", "INTEGER"),
]


def compute_resource_cost(estimate: ResourceEstimate) -> float:
    """Compute a normalized resource cost from a ResourceEstimate.

    Returns a float representing relative cost, scaled to match
    the priority penalty range (~0-30).
    """
    weights = RESOURCE_DIM_WEIGHTS
    cost = (
        estimate.token_cost * weights["tokens"] / 1000.0
        + estimate.api_cost * weights["api_cost"] / 10.0
        + estimate.memory_mb * weights["memory_mb"] / 100.0
        + estimate.browser_steps * weights["browser_steps"] / 5.0
    )
    return cost


class ResourcePredictor:
    """Predicts resource usage per node_type from historical data.

    Stateless. Reads from the activity_stats table via provided connection.
    """

    @staticmethod
    def predict_from_stats(
        node_type: str,
        row: tuple | None,
        sample_count: int,
    ) -> ResourceEstimate:
        """Build a ResourceEstimate from a DB aggregate row or defaults.

        Args:
            node_type: The activity type
            row: Tuple from SQL (avg_tokens, avg_api_cost, avg_memory_mb, avg_browser_steps)
                 or None if no data
            sample_count: Number of historical samples
        """
        from core.scheduler.intelligence import CONFIDENCE_SATURATION

        confidence = min(sample_count / CONFIDENCE_SATURATION, 1.0) if sample_count > 0 else 0.0

        if row is None or sample_count == 0:
            return ResourceEstimate(
                node_type=node_type,
                confidence=0.0,
                sample_size=0,
            )

        return ResourceEstimate(
            token_cost=float(row[0] or DEFAULT_TOKENS),
            api_cost=float(row[1] or DEFAULT_API_COST),
            memory_mb=float(row[2] or DEFAULT_MEMORY_MB),
            browser_steps=float(row[3] or DEFAULT_BROWSER_STEPS),
            confidence=confidence,
            sample_size=sample_count,
            node_type=node_type,
        )

    @staticmethod
    def calibrate(
        pairs: list[tuple[float, float, float, float, float, float, float, float]],
    ) -> ResourceCalibration:
        """Compute calibration multipliers from (predicted, actual) pairs.

        Args:
            pairs: List of (pred_tokens, actual_tokens, pred_api_cost, actual_api_cost,
                           pred_memory_mb, actual_memory_mb, pred_browser_steps, actual_browser_steps)
                   tuples.

        Returns:
            ResourceCalibration with per-dimension multipliers.
        """
        if not pairs:
            return ResourceCalibration()

        n = len(pairs)
        ratios = {"tokens": [], "api_cost": [], "memory_mb": [], "browser_steps": []}
        errors = []

        for p in pairs:
            pred_t, act_t, pred_a, act_a, pred_m, act_m, pred_b, act_b = p

            # Tokens
            if act_t > 0 and pred_t > 0:
                ratios["tokens"].append(act_t / pred_t)
                errors.append(abs(pred_t - act_t) / max(act_t, 1))
            if act_a > 0 and pred_a > 0:
                ratios["api_cost"].append(act_a / pred_a)
            if act_m > 0 and pred_m > 0:
                ratios["memory_mb"].append(act_m / pred_m)
            if act_b > 0 and pred_b > 0:
                ratios["browser_steps"].append(act_b / pred_b)

        def _median(vals: list[float]) -> float:
            if not vals:
                return 1.0
            s = sorted(vals)
            return s[len(s) // 2]

        avg_error = sum(errors) / max(len(errors), 1) if errors else 0.0
        overall_accuracy = max(0.0, 1.0 - avg_error)

        return ResourceCalibration(
            sample_count=n,
            token_multiplier=round(_median(ratios["tokens"]), 4),
            api_cost_multiplier=round(_median(ratios["api_cost"]), 4),
            memory_multiplier=round(_median(ratios["memory_mb"]), 4),
            browser_steps_multiplier=round(_median(ratios["browser_steps"]), 4),
            overall_accuracy=round(overall_accuracy, 4),
        )

    @staticmethod
    def apply_calibration(
        estimate: ResourceEstimate,
        cal: ResourceCalibration,
    ) -> ResourceEstimate:
        """Apply calibration multipliers to an estimate."""
        if cal.sample_count < 3:
            return estimate
        return ResourceEstimate(
            token_cost=estimate.token_cost * cal.token_multiplier,
            api_cost=estimate.api_cost * cal.api_cost_multiplier,
            memory_mb=estimate.memory_mb * cal.memory_multiplier,
            browser_steps=estimate.browser_steps * cal.browser_steps_multiplier,
            confidence=estimate.confidence,
            sample_size=estimate.sample_size,
            node_type=estimate.node_type,
        )
