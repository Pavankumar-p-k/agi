"""Redis-backed cache with an in-process fallback."""
from __future__ import annotations

try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    aioredis = None
    HAS_REDIS = False

from .local import LRUCache


class RedisCache:
    def __init__(self, url: str | None = None, maxsize: int = 1024):
        self.url = url
        self._local = LRUCache(maxsize=maxsize)
        self._redis = None
        self.is_connected = False

    async def connect(self) -> bool:
        if not self.url or not HAS_REDIS:
            return False
        try:
            self._redis = aioredis.Redis.from_url(self.url)
            await self._redis.ping()
            self.is_connected = True
            return True
        except Exception:
            self._redis = None
            self.is_connected = False
            return False

    async def get(self, key: str):
        if self.is_connected:
            try:
                value = await self._redis.get(key)
                return value
            except Exception:
                self.is_connected = False
        return await self._local.get(key)

    async def set(self, key: str, value, **kwargs) -> None:
        if self.is_connected:
            try:
                await self._redis.set(key, value, **kwargs)
                return
            except Exception:
                self.is_connected = False
        await self._local.set(key, value)

    async def delete(self, key: str) -> bool:
        if self.is_connected:
            try:
                return bool(await self._redis.delete(key))
            except Exception:
                self.is_connected = False
        return await self._local.delete(key)

    async def clear(self) -> None:
        if self.is_connected:
            try:
                await self._redis.flushdb()
                return
            except Exception:
                self.is_connected = False
        await self._local.clear()

    async def size(self) -> int:
        if self.is_connected:
            try:
                return int(await self._redis.dbsize())
            except Exception:
                self.is_connected = False
        return await self._local.size()

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
        self._redis = None
        self.is_connected = False
