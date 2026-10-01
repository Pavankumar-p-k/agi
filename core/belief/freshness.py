"""Time-based evidence decay for the Belief Quality Engine."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

_MIN_FRESHNESS = 0.10
_DEFAULT_HALF_LIFE = 180.0
_DEFAULT_HALF_LIVES: Dict[str, float] = {
    "pattern": 180.0,
    "principle": 365.0,
    "warning": 60.0,
    "heuristic": 120.0,
}


def _category_value(category) -> Optional[str]:
    if category is None:
        return None
    value = getattr(category, "value", category)
    return str(value)


class FreshnessScorer:
    """Exponentially decay evidence confidence over time."""

    def __init__(self, half_lives: Optional[Dict[str, float]] = None) -> None:
        self._half_lives: Dict[str, float] = dict(_DEFAULT_HALF_LIVES)
        if half_lives:
            self._half_lives.update(
                {str(k): float(v) for k, v in half_lives.items()}
            )

    def get_half_life(self, category=None) -> float:
        key = _category_value(category)
        if key is None:
            return _DEFAULT_HALF_LIFE
        return self._half_lives.get(key, _DEFAULT_HALF_LIFE)

    def set_half_life(self, category, days: float) -> None:
        self._half_lives[str(_category_value(category))] = float(days)

    def score(
        self,
        created_at: Optional[datetime] = None,
        last_validated: Optional[datetime] = None,
        category=None,
    ) -> float:
        reference = last_validated or created_at
        if reference is None:
            return 1.0
        if isinstance(reference, str):
            try:
                reference = datetime.fromisoformat(reference)
            except ValueError:
                return 1.0
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)

        half_life = self.get_half_life(category)
        if half_life <= 0:
            return _MIN_FRESHNESS

        now = datetime.now(timezone.utc)
        age_days = max(0.0, (now - reference).total_seconds() / 86400.0)
        value = 0.5 ** (age_days / half_life)
        return max(_MIN_FRESHNESS, min(1.0, value))

    def score_many(
        self, timestamps: Iterable[Optional[datetime]], category=None
    ) -> float:
        scores = [
            self.score(created_at=ts, category=category) for ts in timestamps
        ]
        if not scores:
            return 1.0
        return max(scores)
