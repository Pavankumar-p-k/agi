from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PreferenceEntry:
    topic: str
    value: str
    confidence: float = 0.5
    last_asserted: float = 0.0
    assertion_count: int = 1
    source_fact_ids: list[str] = field(default_factory=list)


class PreferenceProfile:
    """Aggregates preference-type facts into a per-user preference profile.

    The profile is built from the FactStore on demand and provides
    topic→value mappings with confidence scores.
    """

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._preferences: dict[str, PreferenceEntry] = {}

    def build(self, fact_store: Any | None = None) -> PreferenceProfile:
        """Build the profile by querying the FactStore for preference facts.

        Returns self for chaining.
        """
        if fact_store is None:
            from memory.fact_store import get_fact_store
            fact_store = get_fact_store()

        facts = fact_store.get_user_facts(self.user_id, category="preference", limit=200)
        self._preferences = {}

        for fact in facts:
            topic = fact.get("subject", "").lower()
            value = fact.get("object", "")
            confidence = fact.get("confidence", 0.5)
            fact_id = fact.get("id", "")
            updated_at = fact.get("updated_at", 0.0)

            if topic == "user":
                # Extract topic from object phrasing: "I like X" → topic=X
                # For now, use the first meaningful word of the object as a topic hint
                obj_lower = value.lower()
                topic = self._infer_topic(obj_lower)

            if topic in self._preferences:
                existing = self._preferences[topic]
                if confidence > existing.confidence:
                    existing.value = value
                    existing.confidence = confidence
                existing.assertion_count += 1
                existing.last_asserted = max(existing.last_asserted, updated_at)
                if fact_id:
                    existing.source_fact_ids.append(fact_id)
            else:
                self._preferences[topic] = PreferenceEntry(
                    topic=topic,
                    value=value,
                    confidence=confidence,
                    last_asserted=updated_at,
                    assertion_count=1,
                    source_fact_ids=[fact_id] if fact_id else [],
                )

        return self

    @staticmethod
    def _infer_topic(obj_lower: str) -> str:
        """Infer a topic key from an object string like 'dark mode' or 'Python'."""
        stop_words = frozenset({
            "the", "a", "an", "to", "for", "of", "in", "on", "at", "by",
            "with", "and", "or", "but", "is", "are", "was", "were",
        })
        words = obj_lower.split()
        meaningful = [w for w in words if w not in stop_words and len(w) > 2]
        if meaningful:
            return meaningful[0]
        if words:
            return words[0]
        return obj_lower

    # ── Queries ──────────────────────────────────────────────────────────────

    @property
    def topics(self) -> list[str]:
        return list(self._preferences.keys())

    def get(self, topic: str, default: str | None = None) -> str | None:
        entry = self._preferences.get(topic.lower())
        return entry.value if entry else default

    def get_entry(self, topic: str) -> PreferenceEntry | None:
        return self._preferences.get(topic.lower())

    def all_entries(self) -> list[PreferenceEntry]:
        return list(self._preferences.values())

    def to_dict(self) -> dict[str, str]:
        return {t: e.value for t, e in self._preferences.items()}

    def format_context(self) -> str:
        """Format known preferences as an LLM-readable string."""
        if not self._preferences:
            return ""
        lines = ["## Known User Preferences"]
        for topic, entry in sorted(self._preferences.items()):
            confidence_label = "high" if entry.confidence >= 0.7 else "medium" if entry.confidence >= 0.4 else "low"
            lines.append(f"- {topic}: {entry.value} (confidence: {confidence_label})")
        return "\n".join(lines)
