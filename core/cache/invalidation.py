from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from .local import LRUCache, TTLCache

logger = logging.getLogger("jarvis.cache.invalidation")


class TagInvalidator:
    """Tag-based cache invalidation registry.

    Allows caches to subscribe to tag-based invalidation events.
    When a tag is invalidated, all registered cache entries for that tag
    are evicted. Supports automatic tagging based on key patterns.

    Tags:
      - ``tools_change``: tool registry changes
      - ``settings_change``: config/settings updates
      - ``model_change``: model configuration changes
      - ``session_change``: session lifecycle events
    """

    def __init__(self):
        self._tag_registry: dict[str, list[tuple[LRUCache | TTLCache, str]]] = {}

    def tag_key(self, cache: LRUCache | TTLCache, key: str, tags: list[str]) -> None:
        """Associate a cache key with one or more tags."""
        for tag in tags:
            if tag not in self._tag_registry:
                self._tag_registry[tag] = []
            self._tag_registry[tag].append((cache, key))

    async def invalidate_tag(self, tag: str) -> int:
        """Invalidate (evict) all cache entries for a given tag.

        Returns the number of keys invalidated.
        """
        entries = self._tag_registry.pop(tag, [])
        count = 0
        for cache, key in entries:
            try:
                await cache.delete(key)
            except Exception as e:
                logger.warning("[INVAL] Failed to evict %s from %s: %s", key, type(cache).__name__, e)
            count += 1
        if count:
            logger.info("[INVAL] Invalidated tag '%s': %d entries", tag, count)
        return count

    async def invalidate_tags(self, tags: list[str]) -> int:
        """Invalidate multiple tags. Returns total entries invalidated."""
        total = 0
        for tag in tags:
            total += await self.invalidate_tag(tag)
        return total

    def clear(self) -> None:
        """Clear the entire tag registry."""
        self._tag_registry.clear()


tag_invalidator = TagInvalidator()
