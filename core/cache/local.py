"""Async in-process LRU and TTL caches."""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class LRUCache(Generic[T]):
    def __init__(self, maxsize: int = 128, eviction_listener: Callable | None = None):
        self.maxsize = maxsize
        self.eviction_listener = eviction_listener
        self._data: OrderedDict[str, T] = OrderedDict()

    async def get(self, key: str) -> T | None:
        if key not in self._data:
            return None
        value = self._data.pop(key)
        self._data[key] = value
        return value

    async def set(self, key: str, value: T) -> None:
        self._data.pop(key, None)
        self._data[key] = value
        while len(self._data) > self.maxsize:
            old_key, old_value = self._data.popitem(last=False)
            if self.eviction_listener:
                self.eviction_listener(old_key, old_value)

    async def delete(self, key: str) -> bool:
        return self._data.pop(key, None) is not None

    async def clear(self) -> None:
        self._data.clear()

    async def has(self, key: str) -> bool:
        return key in self._data

    async def size(self) -> int:
        return len(self._data)


class TTLCache(LRUCache[T]):
    def __init__(self, maxsize: int = 128, default_ttl: float = 60.0, refresh_on_access: bool = False):
        super().__init__(maxsize)
        self.default_ttl = default_ttl
        self.refresh_on_access = refresh_on_access
        self._expiry: dict[str, float] = {}

    async def get(self, key: str) -> T | None:
        expiry = self._expiry.get(key)
        if expiry is not None and expiry <= time.monotonic():
            await self.delete(key)
            return None
        value = await super().get(key)
        if value is not None and self.refresh_on_access:
            self._expiry[key] = time.monotonic() + self.default_ttl
        return value

    async def set(self, key: str, value: T, ttl: float | None = None) -> None:
        await super().set(key, value)
        self._expiry[key] = time.monotonic() + (self.default_ttl if ttl is None else ttl)

    async def delete(self, key: str) -> bool:
        self._expiry.pop(key, None)
        return await super().delete(key)

    async def clear(self) -> None:
        self._expiry.clear()
        await super().clear()

    async def ttl(self, key: str) -> float | None:
        if await self.get(key) is None:
            return None
        return max(0.0, self._expiry[key] - time.monotonic())
