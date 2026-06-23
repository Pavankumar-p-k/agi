"""FactRetriever — multi-source fact retrieval and grouping."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

from core.research.models import Fact
from core.research.storage import FactStore

logger = logging.getLogger(__name__)


class FactRetriever:
    """Retrieves and groups facts across sources for comparison and synthesis.

    Wraps FactStore with topic-aware queries, source grouping,
    and entity mention extraction.
    """

    def __init__(self, store: FactStore):
        self._store = store

    def retrieve(self, topic: str, *,
                 sources: list[str] | None = None,
                 categories: list[str] | None = None,
                 limit: int = 50) -> list[Fact]:
        """Retrieve facts matching a topic, optionally filtered by source or category."""
        # Search by topic as a query
        all_facts = self._store.search_facts(topic, limit=limit * 2)

        # Also search each major word in the topic for wider recall
        words = [w for w in re.split(r'\s+', topic) if len(w) > 3]
        for word in words[:5]:
            word_facts = self._store.search_facts(word, limit=limit // 2)
            seen_ids = {f.fact_id for f in all_facts}
            for f in word_facts:
                if f.fact_id not in seen_ids:
                    all_facts.append(f)
                    seen_ids.add(f.fact_id)

        # Apply filters
        if sources:
            source_set = set(sources)
            all_facts = [f for f in all_facts if f.source_url in source_set]
        if categories:
            cat_set = set(categories)
            all_facts = [f for f in all_facts if f.category in cat_set]

        # Deduplicate and sort by confidence
        seen: set[str] = set()
        deduped: list[Fact] = []
        for f in all_facts:
            if f.fact_id not in seen:
                seen.add(f.fact_id)
                deduped.append(f)
        deduped.sort(key=lambda x: x.confidence, reverse=True)

        return deduped[:limit]

    def retrieve_for_comparison(self, sources: list[str], topic: str) -> dict[str, list[Fact]]:
        """Retrieve facts about a topic grouped by source for side-by-side comparison."""
        all_facts = self.retrieve(topic, sources=sources)
        return self.group_by_source(all_facts)

    def group_by_source(self, facts: list[Fact]) -> dict[str, list[Fact]]:
        """Group a list of facts by source URL."""
        groups: dict[str, list[Fact]] = defaultdict(list)
        for f in facts:
            groups[f.source_url].append(f)
        return dict(groups)

    def get_sources_for_topic(self, topic: str) -> list[str]:
        """List unique source URLs that have facts about a topic."""
        facts = self.retrieve(topic, limit=200)
        seen: set[str] = set()
        sources: list[str] = []
        for f in facts:
            if f.source_url not in seen:
                seen.add(f.source_url)
                sources.append(f.source_url)
        return sources

    def get_entity_mentions(self, entity: str) -> list[Fact]:
        """Get all facts mentioning a specific entity."""
        return self._store.search_facts(entity, limit=100)

    def count_by_source(self, topic: str) -> dict[str, int]:
        """Count facts per source for a given topic."""
        facts = self.retrieve(topic, limit=500)
        counts: dict[str, int] = {}
        for f in facts:
            counts[f.source_url] = counts.get(f.source_url, 0) + 1
        return counts
