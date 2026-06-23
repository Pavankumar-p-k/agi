"""FreshnessScorer — time-based evidence decay for belief quality.

Different knowledge categories decay at different rates:
  - Research facts: 180-day half-life (slow decay — URLs persist)
  - Patterns: 120-day half-life (moderate — tool behavior changes)
  - Principles: 365-day half-life (slow — architectural truths)
  - Heuristics: 90-day half-life (faster — empirical observations)
  - Warnings: 60-day half-life (fast — conditions change)
  - Factoids: 180-day half-life (slow — factual claims)
  - Research facts (stored): 180-day half-life
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.belief.models import BeliefCategory

# Half-lives in days per belief category
DEFAULT_HALF_LIVES: dict[str, float] = {
    BeliefCategory.PATTERN.value: 120.0,
    BeliefCategory.PRINCIPLE.value: 365.0,
    BeliefCategory.HEURISTIC.value: 90.0,
    BeliefCategory.FACTOID.value: 180.0,
    BeliefCategory.WARNING.value: 60.0,
    BeliefCategory.RESEARCH_FACT.value: 180.0,
}

DEFAULT_HALF_LIFE = 90.0
# Never drop below this freshness even for very old evidence
MINIMUM_FRESHNESS = 0.10
# Evidence created within this window (seconds) is considered current
CURRENT_WINDOW_SECONDS = 3600  # 1 hour


class FreshnessScorer:
    """Computes a freshness score [0.1, 1.0] for a piece of evidence.

    Uses exponential decay with configurable half-life per category:

        freshness = 2^(-age / half_life)

    where age is the time since created_at or last_validated.
    """

    def __init__(self, half_lives: dict[str, float] | None = None):
        self._half_lives = {**DEFAULT_HALF_LIVES, **(half_lives or {})}

    def score(
        self,
        created_at: datetime | None = None,
        last_validated: datetime | None = None,
        category: str = BeliefCategory.HEURISTIC.value,
    ) -> float:
        """Compute freshness score for evidence with given timestamps.

        Uses last_validated if available, otherwise created_at.
        Returns 1.0 if neither timestamp is available (unknown = current).
        """
        ref_time = last_validated or created_at
        if ref_time is None:
            return 1.0

        now = datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            now = now.replace(tzinfo=None)

        age_seconds = (now - ref_time).total_seconds()
        if age_seconds <= 0:
            return 1.0

        age_days = age_seconds / 86400.0
        half_life = self._half_lives.get(category, DEFAULT_HALF_LIFE)

        return self._decay(age_days, half_life)

    def score_many(
        self,
        timestamps: list[datetime | None],
        category: str = BeliefCategory.HEURISTIC.value,
    ) -> float:
        """Compute combined freshness for multiple pieces of evidence.

        Returns the max freshness (most recent evidence dominates).
        """
        if not timestamps:
            return 1.0
        scores = [self.score(created_at=t, category=category) for t in timestamps]
        return max(scores)

    def get_decay_factor(self, age_days: float, category: str) -> float:
        """Compute the raw decay factor for a given age and category."""
        half_life = self._half_lives.get(category, DEFAULT_HALF_LIFE)
        return self._decay(age_days, half_life)

    def get_half_life(self, category: str) -> float:
        return self._half_lives.get(category, DEFAULT_HALF_LIFE)

    def set_half_life(self, category: str, days: float) -> None:
        self._half_lives[category] = days

    def _decay(self, age_days: float, half_life: float) -> float:
        if half_life <= 0:
            return MINIMUM_FRESHNESS
        factor = 2.0 ** (-age_days / half_life)
        return max(factor, MINIMUM_FRESHNESS)
