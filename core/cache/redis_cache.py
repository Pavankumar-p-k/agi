from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .local import LRUCache

logger = logging.getLogger("jarvis.cache.redis")

try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    aioredis = None  # type: ignore
    HAS_REDIS = False


class RedisCache:
    """Redis-backed cache with graceful fallback to LRUCache.

    Uses a local LRU fallback when Redis is unavailable, misconfigured,
    or when the ``redis`` package is not installed.

    Configuration (via env / config):
      ``JARVIS_REDIS_URL`` (default: None → LRU-only)
      ``JARVIS_REDIS_PREFIX`` (default: ``jarvis:cache:``)
      ``JARVIS_REDIS_TIMEOUT`` (default: 2.0 seconds)
    """

    def __init__(
        self,
        url: Optional[str] = None,
        prefix: str = "jarvis:cache:",
        socket_timeout: float = 2.0,
        local_fallback_maxsize: int = 256,
    ):
        self._url = url
        self._prefix = prefix
        self._socket_timeout = socket_timeout
        self._redis: Optional[aioredis.Redis] = None
        self._local: LRUCache[Any] = LRUCache(maxsize=local_fallback_maxsize)
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Connect to Redis. Returns True if connected, False if fallback."""
        if not HAS_REDIS:
            logger.info("[REDIS] redis-py not installed — using LRU fallback")
            return False
        if not self._url:
            logger.info("[REDIS] No Redis URL configured — using LRU fallback")
            return False
        try:
            self._redis = aioredis.Redis.from_url(
                self._url,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_timeout,
                decode_responses=True,
            )
            await self._redis.ping()
            self._connected = True
            logger.info("[REDIS] Connected to %s", self._url)
            return True
        except Exception as e:
            logger.warning("[REDIS] Connection failed: %s — using LRU fallback", e)
            self._redis = None
            return False

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
            self._connected = False

    async def get(self, key: str) -> Optional[Any]:
        if self._connected and self._redis:
            try:
                val = await self._redis.get(self._prefix + key)
                if val is None:
                    return None
                return json.loads(val)
            except Exception as e:
                logger.warning("[REDIS] Get failed: %s — falling back to LRU", e)
                self._connected = False
        return await self._local.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        if self._connected and self._redis:
            try:
                await self._redis.set(
                    self._prefix + key,
                    json.dumps(value, default=str),
                    ex=int(ttl) if ttl is not None else None,
                )
                return
            except Exception as e:
                logger.warning("[REDIS] Set failed: %s — falling back to LRU", e)
                self._connected = False
        await self._local.set(key, value)

    async def delete(self, key: str) -> bool:
        if self._connected and self._redis:
            try:
                result = await self._redis.delete(self._prefix + key)
                return result > 0
            except Exception as e:
                logger.warning("[REDIS] Delete failed: %s — falling back to LRU", e)
                self._connected = False
        return await self._local.delete(key)

    async def clear(self) -> None:
        if self._connected and self._redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(
                        cursor=cursor, match=self._prefix + "*", count=100
                    )
                    if keys:
                        await self._redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning("[REDIS] Clear failed: %s", e)
        await self._local.clear()

    async def size(self) -> int:
        if self._connected and self._redis:
            try:
                cursor = 0
                count = 0
                while True:
                    cursor, keys = await self._redis.scan(
                        cursor=cursor, match=self._prefix + "*", count=1000
                    )
                    count += len(keys)
                    if cursor == 0:
                        break
                return count
            except Exception as _e:
                logger.debug("redis_cache size failed: %s", _e)
        return await self._local.size()

    async def ttl(self, key: str) -> Optional[float]:
        if self._connected and self._redis:
            try:
                remaining = await self._redis.ttl(self._prefix + key)
                return max(0.0, float(remaining)) if remaining >= 0 else None
            except Exception as _e:
                logger.debug("redis_cache ttl failed: %s", _e)
        return None
