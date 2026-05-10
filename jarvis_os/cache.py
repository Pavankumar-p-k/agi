"""Small in-process caches used by the JARVIS OS runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Awaitable, Callable, Dict, Tuple


class TTLCache:
    def __init__(self, ttl_s: int = 120, max_entries: int = 512):
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any:
        async with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at < time.time():
                self._data.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any, ttl_s: int | None = None) -> Any:
        async with self._lock:
            if len(self._data) >= self.max_entries:
                oldest_key = min(self._data, key=lambda current: self._data[current][0])
                self._data.pop(oldest_key, None)
            self._data[key] = (time.time() + (ttl_s or self.ttl_s), value)
        return value

    async def get_or_set(
        self,
        key: str,
        producer: Callable[[], Awaitable[Any]],
        ttl_s: int | None = None,
    ) -> Any:
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await producer()
        return await self.set(key, value, ttl_s=ttl_s)


def fingerprint(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
