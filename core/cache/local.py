# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class LRUCache(Generic[T]):
    """Generic typed LRU cache with asyncio.Lock for thread-safety.

    Evicts the least-recently-used entry when maxsize is exceeded.
    Optionally calls an eviction listener callback on each eviction.
    """

    def __init__(self, maxsize: int = 256, eviction_listener: Callable[[str, T], None] | None = None):
        self._maxsize = maxsize
        self._eviction_listener = eviction_listener
        self._store: dict[str, T] = {}
        self._order: list[str] = []
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T | None:
        async with self._lock:
            if key not in self._store:
                return None
            self._order.remove(key)
            self._order.append(key)
            return self._store[key]

    async def set(self, key: str, value: T) -> None:
        async with self._lock:
            if key in self._store:
                self._order.remove(key)
            elif len(self._store) >= self._maxsize:
                self._evict_one()
            self._store[key] = value
            self._order.append(key)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key not in self._store:
                return False
            del self._store[key]
            self._order.remove(key)
            return True

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
            self._order.clear()

    async def has(self, key: str) -> bool:
        async with self._lock:
            return key in self._store

    async def size(self) -> int:
        async with self._lock:
            return len(self._store)

    @property
    def maxsize(self) -> int:
        return self._maxsize

    def _evict_one(self) -> None:
        if not self._order:
            return
        oldest = self._order.pop(0)
        value = self._store.pop(oldest, None)
        if value is not None and self._eviction_listener:
            self._eviction_listener(oldest, value)


class TTLCache(LRUCache[T]):
    """LRU cache with per-key TTL and optional refresh-on-access.

    Extends LRUCache: entries expire after *default_ttl* seconds.
    When *refresh_on_access* is True, a cache hit extends the entry's lifetime.
    """

    def __init__(
        self,
        maxsize: int = 256,
        default_ttl: float = 3600.0,
        refresh_on_access: bool = False,
        eviction_listener: Callable[[str, T], None] | None = None,
    ):
        super().__init__(maxsize=maxsize, eviction_listener=eviction_listener)
        self._default_ttl = default_ttl
        self._refresh_on_access = refresh_on_access
        self._expires: dict[str, float] = {}

    async def get(self, key: str) -> T | None:
        async with self._lock:
            if key not in self._store:
                return None
            if self._is_expired(key):
                self._remove_immediate(key)
                return None
            self._order.remove(key)
            self._order.append(key)
            if self._refresh_on_access:
                self._expires[key] = time.monotonic() + self._default_ttl
            return self._store[key]

    async def set(self, key: str, value: T, ttl: float | None = None) -> None:
        async with self._lock:
            if key in self._store:
                self._order.remove(key)
            elif len(self._store) >= self._maxsize:
                self._evict_one()
            self._store[key] = value
            self._order.append(key)
            self._expires[key] = time.monotonic() + (ttl if ttl is not None else self._default_ttl)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key not in self._store:
                return False
            self._remove_immediate(key)
            return True

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
            self._order.clear()
            self._expires.clear()

    async def size(self) -> int:
        async with self._lock:
            self._evict_expired()
            return len(self._store)

    async def ttl(self, key: str) -> float | None:
        """Return seconds until *key* expires, or None if missing."""
        async with self._lock:
            if key not in self._expires:
                return None
            remaining = self._expires[key] - time.monotonic()
            return max(0.0, remaining)

    def _is_expired(self, key: str) -> bool:
        expiry = self._expires.get(key)
        if expiry is None:
            return False
        return time.monotonic() >= expiry

    def _remove_immediate(self, key: str) -> None:
        self._store.pop(key, None)
        self._expires.pop(key, None)
        try:
            self._order.remove(key)
        except ValueError:
            pass

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, exp in self._expires.items() if now >= exp]
        for k in expired:
            self._remove_immediate(k)
