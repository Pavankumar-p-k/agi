"""Tag-based invalidation for cache instances."""
from __future__ import annotations

from collections import defaultdict


class TagInvalidator:
    def __init__(self):
        self._tag_registry: dict[str, list[tuple[object, str]]] = defaultdict(list)

    def tag_key(self, cache: object, key: str, tags: list[str]) -> None:
        for tag in tags:
            entry = (cache, key)
            if entry not in self._tag_registry[tag]:
                self._tag_registry[tag].append(entry)

    async def invalidate_tag(self, tag: str) -> int:
        entries = self._tag_registry.pop(tag, [])
        count = 0
        for cache, key in entries:
            if await cache.delete(key):
                count += 1
        return count

    async def invalidate_tags(self, tags: list[str]) -> int:
        total = 0
        for tag in tags:
            total += await self.invalidate_tag(tag)
        return total

    def clear(self) -> None:
        self._tag_registry.clear()
