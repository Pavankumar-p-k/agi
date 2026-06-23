"""SourceTracker — tracks source reliability across all knowledge-producing systems.

Maintains SourceProfile objects that answer:
  - Which sources are usually correct?
  - Which sources produce contradictory information?
  - How reliable is this source in this domain?

Reliability is computed as:

    reliability = correct_ratio × min(refs / ramp_refs, 1.0)

where correct_ratio smooths from a prior of 0.5 toward the observed rate.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.belief.models import SourceProfile, SourceType

logger = logging.getLogger(__name__)

# Minimum references before reliability is trusted over the prior
PRIOR_WEIGHT = 5.0
# Prior probability (before any evidence, assume 50% reliable)
PRIOR_RELIABILITY = 0.5
# Smoothing factor for domain scores (how many refs to reach 90% weight)
DOMAIN_RAMP_REFS = 10.0
# Maximum references considered for the reliability score (prevents lock-in)
MAX_REFS_FOR_RELIABILITY = 100


class SourceTracker:
    """Tracks source reliability profiles.

    Thread-safe if the caller holds the store's lock externally.
    """

    def __init__(self):
        self._profiles: dict[str, SourceProfile] = {}

    def get_profile(self, source_id: str) -> SourceProfile | None:
        return self._profiles.get(source_id)

    def get_or_create(
        self, source_id: str, source_type: SourceType = SourceType.RESEARCH_URL
    ) -> SourceProfile:
        if source_id not in self._profiles:
            self._profiles[source_id] = SourceProfile(
                source_id=source_id,
                source_type=source_type,
                first_seen=datetime.now(timezone.utc),
            )
        return self._profiles[source_id]

    def record_reference(
        self,
        source_id: str,
        source_type: SourceType = SourceType.RESEARCH_URL,
        domain: str = "general",
        was_correct: bool | None = None,
    ) -> SourceProfile:
        """Record a reference from a source, optionally noting correctness.

        If was_correct is None, we just increment total_references without
        affecting the correctness ratio (used for neutral references).
        """
        profile = self.get_or_create(source_id, source_type)
        profile.total_references += 1
        profile.last_seen = datetime.now(timezone.utc)

        if was_correct is not None:
            profile.correct_references += 1 if was_correct else 0

        profile.reliability_score = self._compute_reliability(profile)
        return profile

    def record_contradiction(
        self,
        source_id: str,
        source_type: SourceType = SourceType.RESEARCH_URL,
        domain: str = "general",
    ) -> SourceProfile:
        """Record that this source produced a contradictory claim."""
        profile = self.get_or_create(source_id, source_type)
        profile.contradictory_references += 1
        profile.last_seen = datetime.now(timezone.utc)
        return profile

    def get_reliability(
        self, source_id: str, domain: str | None = None
    ) -> float:
        """Get reliability score for a source, optionally per-domain.

        Returns PRIOR_RELIABILITY (0.5) for unknown sources.
        """
        profile = self._profiles.get(source_id)
        if profile is None:
            return PRIOR_RELIABILITY

        if domain and domain in profile.domain_scores:
            return profile.domain_scores[domain]

        return profile.reliability_score

    def get_all_profiles(self) -> list[SourceProfile]:
        return list(self._profiles.values())

    def profile_count(self) -> int:
        return len(self._profiles)

    def clear(self) -> None:
        self._profiles.clear()

    def set_profiles(self, profiles: list[SourceProfile]) -> None:
        self._profiles = {p.source_id: p for p in profiles}

    def _compute_reliability(self, profile: SourceProfile) -> float:
        """Compute smoothed reliability with a prior.

        Uses Bayesian-ish smoothing:
            reliability = (correct + prior_weight * prior)
                          / (total + prior_weight)

        This prevents single references from driving reliability to 0.0 or 1.0.
        """
        total = min(profile.total_references, MAX_REFS_FOR_RELIABILITY)
        if total == 0:
            return PRIOR_RELIABILITY

        weight = PRIOR_WEIGHT
        smoothed = (
            profile.correct_references + weight * PRIOR_RELIABILITY
        ) / (total + weight)

        return max(0.0, min(1.0, smoothed))
