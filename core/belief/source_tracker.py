"""Source reliability tracking for the Belief Quality Engine."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.belief.models import SourceProfile, SourceType

_PRIOR = 0.5
_PRIOR_WEIGHT = 5.0


class SourceTracker:
    """Track per-source reliability using a Bayesian prior."""

    def __init__(self, profiles: Optional[List[SourceProfile]] = None) -> None:
        self._profiles: Dict[str, SourceProfile] = {}
        if profiles:
            self.set_profiles(profiles)

    # ── internals ────────────────────────────────────────────────────

    def _normalize_source_type(self, source_type) -> SourceType:
        if isinstance(source_type, SourceType):
            return source_type
        if source_type:
            try:
                return SourceType(source_type)
            except ValueError:
                pass
        return SourceType.TOOL

    def _get_or_create(
        self, source_id: str, source_type=None
    ) -> SourceProfile:
        profile = self._profiles.get(source_id)
        if profile is None:
            profile = SourceProfile(
                source_id=source_id,
                source_type=self._normalize_source_type(source_type),
            )
            self._profiles[source_id] = profile
        elif source_type is not None:
            profile.source_type = self._normalize_source_type(source_type)
        return profile

    def _recompute(self, profile: SourceProfile) -> None:
        total = profile.total_references
        correct = profile.correct_references
        if total <= 0:
            return
        profile.reliability_score = (correct + _PRIOR * _PRIOR_WEIGHT) / (
            total + _PRIOR_WEIGHT
        )
        profile.last_updated = datetime.now(timezone.utc)

    # ── public API ───────────────────────────────────────────────────

    def get_reliability(self, source_id: str) -> float:
        profile = self._profiles.get(source_id)
        if profile is None:
            return _PRIOR
        if profile.total_references <= 0:
            return profile.reliability_score
        return profile.reliability_score

    def record_reference(
        self,
        source_id: str,
        was_correct: Optional[bool] = None,
        domain: Optional[str] = None,
        source_type=None,
    ) -> SourceProfile:
        profile = self._get_or_create(source_id, source_type)
        profile.total_references += 1
        if was_correct is True:
            profile.correct_references += 1
        self._recompute(profile)
        if domain:
            profile.domain_scores[domain] = profile.reliability_score
        return profile

    def record_contradiction(
        self, source_id: str, domain: Optional[str] = None, source_type=None
    ) -> SourceProfile:
        profile = self._get_or_create(source_id, source_type)
        profile.total_references += 1
        profile.contradictory_references += 1
        self._recompute(profile)
        if domain:
            profile.domain_scores[domain] = profile.reliability_score
        return profile

    def get_profile(self, source_id: str) -> SourceProfile:
        return self._get_or_create(source_id)

    def get_all_profiles(self) -> List[SourceProfile]:
        return list(self._profiles.values())

    def profile_count(self) -> int:
        return len(self._profiles)

    def clear(self) -> None:
        self._profiles.clear()

    def set_profiles(self, profiles: List[SourceProfile]) -> None:
        self._profiles = {}
        for profile in profiles or []:
            if isinstance(profile, dict):
                profile = SourceProfile.from_dict(profile)
            self._profiles[profile.source_id] = profile
