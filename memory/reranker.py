from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class ReRanker:
    """Lightweight re-ranker for memory recall results.

    Scores each item on a combination of:
    - **Similarity**: word overlap with the query
    - **Recency**: more recent items score higher
    - **Confidence**: items with explicit confidence get a boost
    - **Preference match**: items matching known user preferences get a boost
    """

    def __init__(
        self,
        similarity_weight: float = 0.5,
        recency_weight: float = 0.3,
        confidence_weight: float = 0.1,
        preference_weight: float = 0.1,
        recency_half_life_days: float = 7.0,
    ) -> None:
        self.similarity_weight = similarity_weight
        self.recency_weight = recency_weight
        self.confidence_weight = confidence_weight
        self.preference_weight = preference_weight
        self.recency_half_life_seconds = recency_half_life_days * 86400

    def rerank(
        self,
        query: str,
        items: list[dict[str, Any]],
        user_preferences: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Re-rank memory items by relevance to the query.

        Args:
            query: The user's input text.
            items: List of memory item dicts.
            user_preferences: Optional dict of topic→value preferences.

        Returns:
            Items sorted by composite score descending, with a ``_score`` key added.
        """
        if not items:
            return []

        query_lower = query.lower()
        query_words = set(query_lower.split())
        now = time.time()

        scored: list[tuple[float, dict[str, Any]]] = []
        for item in items:
            sim_score = self._similarity_score(item, query_lower, query_words)
            recency_score = self._recency_score(item, now)
            confidence_score = self._confidence_score(item)
            preference_score = self._preference_score(item, user_preferences)

            combined = (
                self.similarity_weight * sim_score
                + self.recency_weight * recency_score
                + self.confidence_weight * confidence_score
                + self.preference_weight * preference_score
            )

            item["_score"] = round(combined, 4)
            scored.append((combined, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    # ── Scoring components ──────────────────────────────────────────────────

    @staticmethod
    def _similarity_score(item: dict[str, Any], query_lower: str, query_words: set[str]) -> float:
        """Word overlap between query and item text/content."""
        text_parts = [
            item.get("text", "") or "",
            item.get("content", "") or item.get("message", "") or "",
            item.get("object", "") or "",
        ]
        combined = " ".join(text_parts)
        if not combined.strip():
            return 0.0

        item_words = set(combined.lower().split())
        if not item_words:
            return 0.0

        intersection = query_words & item_words
        return len(intersection) / max(len(query_words), 1)

    def _recency_score(self, item: dict[str, Any], now: float) -> float:
        """Score based on recency (newer = higher)."""
        age_seconds = self._item_age_seconds(item, now)
        if age_seconds < 0:
            return 1.0
        return max(0.0, 1.0 - age_seconds / self.recency_half_life_seconds)

    @staticmethod
    def _confidence_score(item: dict[str, Any]) -> float:
        """Score based on explicit confidence field."""
        confidence = item.get("confidence", None)
        if confidence is not None:
            return float(confidence)
        return 0.5  # default neutral

    @staticmethod
    def _preference_score(
        item: dict[str, Any],
        user_preferences: dict[str, str] | None,
    ) -> float:
        """Boost if the item content matches known user preferences."""
        if not user_preferences:
            return 0.0

        text = (
            item.get("text", "")
            or item.get("content", "")
            or item.get("object", "")
            or ""
        ).lower()

        for topic, value in user_preferences.items():
            topic_lower = topic.lower()
            value_lower = value.lower()
            if topic_lower in text or value_lower in text:
                return 0.8

        return 0.0

    @staticmethod
    def _item_age_seconds(item: dict[str, Any], now: float) -> float:
        """Extract or infer item age from various timestamp fields."""
        for key in ("timestamp", "created_at", "updated_at", "last_asserted"):
            ts = item.get(key, None)
            if ts is not None:
                try:
                    return now - float(ts)
                except (TypeError, ValueError):
                    continue
        return float("inf")
