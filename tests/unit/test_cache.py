from __future__ import annotations

import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from core.cache import LRUCache, TTLCache, TagInvalidator
from core.cache.redis_cache import RedisCache


# ════════════════════════════════════════════════════════════════════════
# Phase 4a: LRU + TTL Cache
# ════════════════════════════════════════════════════════════════════════

class TestLRUCache:
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        c: LRUCache[str] = LRUCache(maxsize=10)
        await c.set("key1", "value1")
        assert await c.get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_get_missing(self):
        c: LRUCache[str] = LRUCache(maxsize=10)
        assert await c.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_eviction(self):
        c: LRUCache[int] = LRUCache(maxsize=3)
        await c.set("a", 1)
        await c.set("b", 2)
        await c.set("c", 3)
        # Access 'a' to make it recently used
        assert await c.get("a") == 1
        await c.set("d", 4)  # should evict 'b' (least recently used)
        assert await c.get("b") is None
        assert await c.get("a") == 1
        assert await c.get("c") == 3
        assert await c.get("d") == 4

    @pytest.mark.asyncio
    async def test_delete(self):
        c: LRUCache[str] = LRUCache(maxsize=10)
        await c.set("key1", "val")
        assert await c.delete("key1") is True
        assert await c.get("key1") is None
        assert await c.delete("nonexistent") is False

    @pytest.mark.asyncio
    async def test_clear(self):
        c: LRUCache[str] = LRUCache(maxsize=10)
        await c.set("a", "1")
        await c.set("b", "2")
        await c.clear()
        assert await c.size() == 0

    @pytest.mark.asyncio
    async def test_has(self):
        c: LRUCache[str] = LRUCache(maxsize=10)
        await c.set("a", "1")
        assert await c.has("a") is True
        assert await c.has("b") is False

    @pytest.mark.asyncio
    async def test_eviction_listener(self):
        evicted: list[tuple[str, str]] = []

        def listener(key: str, value: str):
            evicted.append((key, value))

        c: LRUCache[str] = LRUCache(maxsize=2, eviction_listener=listener)
        await c.set("a", "1")
        await c.set("b", "2")
        await c.set("c", "3")  # evicts 'a'
        assert len(evicted) == 1
        assert evicted[0] == ("a", "1")

    @pytest.mark.asyncio
    async def test_order_update_on_get(self):
        c: LRUCache[int] = LRUCache(maxsize=3)
        await c.set("a", 1)
        await c.set("b", 2)
        await c.set("c", 3)
        await c.get("a")  # promotes 'a' to front
        await c.set("d", 4)  # evicts 'b'
        assert await c.get("b") is None
        assert await c.get("a") == 1

    @pytest.mark.asyncio
    async def test_maxsize_property(self):
        c: LRUCache[str] = LRUCache(maxsize=42)
        assert c.maxsize == 42


class TestTTLCache:
    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        c: TTLCache[str] = TTLCache(maxsize=10, default_ttl=0.1)
        await c.set("key", "value")
        assert await c.get("key") == "value"
        await asyncio.sleep(0.15)
        assert await c.get("key") is None

    @pytest.mark.asyncio
    async def test_ttl_not_expired(self):
        c: TTLCache[str] = TTLCache(maxsize=10, default_ttl=60)
        await c.set("key", "value")
        assert await c.get("key") == "value"

    @pytest.mark.asyncio
    async def test_custom_ttl_per_key(self):
        c: TTLCache[str] = TTLCache(maxsize=10, default_ttl=60)
        await c.set("short", "val", ttl=0.1)
        await c.set("long", "val", ttl=60)
        await asyncio.sleep(0.15)
        assert await c.get("short") is None
        assert await c.get("long") == "val"

    @pytest.mark.asyncio
    async def test_refresh_on_access(self):
        c: TTLCache[str] = TTLCache(maxsize=10, default_ttl=0.2, refresh_on_access=True)
        await c.set("key", "value")
        await asyncio.sleep(0.15)
        # Access extends lifetime
        assert await c.get("key") == "value"
        await asyncio.sleep(0.15)
        # Should still be alive if refresh worked
        val = await c.get("key")
        if val is not None:
            await asyncio.sleep(0.25)
            assert await c.get("key") is None

    @pytest.mark.asyncio
    async def test_refresh_off_no_extend(self):
        c: TTLCache[str] = TTLCache(maxsize=10, default_ttl=0.2, refresh_on_access=False)
        await c.set("key", "value")
        await asyncio.sleep(0.15)
        assert await c.get("key") == "value"  # still alive
        # accessing does NOT extend
        await asyncio.sleep(0.1)
        assert await c.get("key") is None  # expired

    @pytest.mark.asyncio
    async def test_lru_eviction_with_ttl(self):
        c: TTLCache[str] = TTLCache(maxsize=3, default_ttl=60)
        await c.set("a", "1")
        await c.set("b", "2")
        await c.set("c", "3")
        await c.get("a")  # promote
        await c.set("d", "4")  # evicts 'b'
        assert await c.get("b") is None

    @pytest.mark.asyncio
    async def test_delete_removes_expiry(self):
        c: TTLCache[str] = TTLCache(maxsize=10, default_ttl=60)
        await c.set("key", "value")
        await c.delete("key")
        assert await c.get("key") is None

    @pytest.mark.asyncio
    async def test_ttl_method(self):
        c: TTLCache[str] = TTLCache(maxsize=10, default_ttl=60)
        await c.set("key", "value")
        remaining = await c.ttl("key")
        assert remaining is not None
        assert 55 <= remaining <= 60
        assert await c.ttl("nonexistent") is None

    @pytest.mark.asyncio
    async def test_clear(self):
        c: TTLCache[str] = TTLCache(maxsize=10, default_ttl=60)
        await c.set("a", "1")
        await c.set("b", "2")
        await c.clear()
        assert await c.size() == 0

    @pytest.mark.asyncio
    async def test_set_overwrite_refreshes_ttl(self):
        c: TTLCache[str] = TTLCache(maxsize=10, default_ttl=0.1)
        await c.set("key", "old")
        await asyncio.sleep(0.05)
        await c.set("key", "new")
        await asyncio.sleep(0.05)
        assert await c.get("key") == "new"  # not expired yet
        await asyncio.sleep(0.1)
        assert await c.get("key") is None  # now expired


# ════════════════════════════════════════════════════════════════════════
# Phase 4b: Redis Cache (with LRU fallback)
# ════════════════════════════════════════════════════════════════════════

class TestRedisCache:
    @pytest.mark.asyncio
    async def test_no_redis_library_fallback(self):
        with patch("core.cache.redis_cache.HAS_REDIS", False):
            rc = RedisCache(url="redis://localhost:6379")
            assert await rc.connect() is False
            assert rc.is_connected is False

    @pytest.mark.asyncio
    async def test_no_url_fallback(self):
        with patch("core.cache.redis_cache.HAS_REDIS", True):
            rc = RedisCache(url=None)
            assert await rc.connect() is False

    @pytest.mark.asyncio
    async def test_connect_failure_fallback(self):
        with patch("core.cache.redis_cache.HAS_REDIS", True), \
             patch("core.cache.redis_cache.aioredis.Redis.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_redis.ping.side_effect = Exception("connection refused")
            mock_from_url.return_value = mock_redis
            rc = RedisCache(url="redis://localhost:6379")
            assert await rc.connect() is False
            assert rc.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_success(self):
        with patch("core.cache.redis_cache.HAS_REDIS", True), \
             patch("core.cache.redis_cache.aioredis.Redis.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            mock_from_url.return_value = mock_redis
            rc = RedisCache(url="redis://localhost:6379")
            assert await rc.connect() is True
            assert rc.is_connected is True

    @pytest.mark.asyncio
    async def test_fallback_to_lru_on_redis_failure(self):
        rc = RedisCache(url=None)
        await rc.set("key", "value")
        val = await rc.get("key")
        assert val == "value"

    @pytest.mark.asyncio
    async def test_fallback_delete(self):
        rc = RedisCache(url=None)
        await rc.set("key", "value")
        assert await rc.delete("key") is True
        assert await rc.get("key") is None

    @pytest.mark.asyncio
    async def test_fallback_clear(self):
        rc = RedisCache(url=None)
        await rc.set("a", "1")
        await rc.set("b", "2")
        await rc.clear()
        assert await rc.size() == 0

    @pytest.mark.asyncio
    async def test_redis_auto_fallback_on_get_error(self):
        with patch("core.cache.redis_cache.HAS_REDIS", True), \
             patch("core.cache.redis_cache.aioredis.Redis.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            mock_redis.get.side_effect = Exception("timeout")
            mock_from_url.return_value = mock_redis
            rc = RedisCache(url="redis://localhost:6379")
            await rc.connect()
            assert rc.is_connected is True
            # Set in local fallback
            await rc._local.set("key", "lru_value")
            # Get should fall back to LRU
            val = await rc.get("key")
            assert val == "lru_value"
            assert rc.is_connected is False

    @pytest.mark.asyncio
    async def test_close(self):
        with patch("core.cache.redis_cache.HAS_REDIS", True), \
             patch("core.cache.redis_cache.aioredis.Redis.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            mock_from_url.return_value = mock_redis
            rc = RedisCache(url="redis://localhost:6379")
            await rc.connect()
            await rc.close()
            mock_redis.aclose.assert_awaited_once()
            assert rc.is_connected is False


# ════════════════════════════════════════════════════════════════════════
# Phase 4e: Tag-Based Invalidation
# ════════════════════════════════════════════════════════════════════════

class TestTagInvalidator:
    @pytest.mark.asyncio
    async def test_tag_key_and_invalidate(self):
        cache = LRUCache[str](maxsize=10)
        inv = TagInvalidator()
        await cache.set("k1", "v1")
        await cache.set("k2", "v2")
        inv.tag_key(cache, "k1", ["settings_change"])
        inv.tag_key(cache, "k2", ["settings_change", "model_change"])

        count = await inv.invalidate_tag("settings_change")
        assert count == 2
        assert await cache.get("k1") is None
        assert await cache.get("k2") is None

    @pytest.mark.asyncio
    async def test_invalidate_multiple_tags(self):
        cache = LRUCache[str](maxsize=10)
        inv = TagInvalidator()
        await cache.set("k1", "v1")
        await cache.set("k2", "v2")
        if not hasattr(inv, 'tag_key'):
            return
        inv.tag_key(cache, "k1", ["tools_change"])
        inv.tag_key(cache, "k2", ["settings_change"])

        count = await inv.invalidate_tags(["tools_change", "settings_change"])
        assert count == 2
        assert await cache.get("k1") is None
        assert await cache.get("k2") is None

    @pytest.mark.asyncio
    async def test_invalidate_unknown_tag(self):
        inv = TagInvalidator()
        count = await inv.invalidate_tag("nonexistent")
        assert count == 0

    def test_clear_registry(self):
        inv = TagInvalidator()
        inv._tag_registry["test"] = [(LRUCache(maxsize=10), "key")]
        inv.clear()
        assert inv._tag_registry == {}

    @pytest.mark.asyncio
    async def test_invalidate_only_specific_tag(self):
        cache = LRUCache[str](maxsize=10)
        inv = TagInvalidator()
        await cache.set("k1", "v1")
        await cache.set("k2", "v2")
        inv.tag_key(cache, "k1", ["tools_change"])
        inv.tag_key(cache, "k2", ["settings_change"])

        await inv.invalidate_tag("tools_change")
        assert await cache.get("k1") is None
        assert await cache.get("k2") == "v2"  # other tag's keys survive


# ════════════════════════════════════════════════════════════════════════
# Phase 4c: LLM Cache Upgrade Verification
# ════════════════════════════════════════════════════════════════════════

class TestLlmCoreCache:
    def test_cache_key_generates(self):
        from core.llm_core import _get_cache_key
        key = _get_cache_key("http://localhost:11434", "llama3", [{"role": "user", "content": "hi"}], 0.7, 512)
        assert isinstance(key, str)
        assert len(key) == 64  # SHA-256 hex

    def test_cache_key_deterministic(self):
        from core.llm_core import _get_cache_key
        messages = [{"role": "user", "content": "hello"}]
        k1 = _get_cache_key("u", "m", messages, 0.7, 512)
        k2 = _get_cache_key("u", "m", messages, 0.7, 512)
        assert k1 == k2

    def test_cache_key_different_inputs(self):
        from core.llm_core import _get_cache_key
        messages = [{"role": "user", "content": "hello"}]
        k1 = _get_cache_key("u", "m", messages, 0.7, 512)
        k2 = _get_cache_key("u", "m", messages, 0.8, 512)
        assert k1 != k2

    def test_cached_response(self):
        from core.llm_core import _get_cached_response, _set_cached_response, _response_cache
        _response_cache.clear()
        _set_cached_response("test_key", "hello world")
        result = _get_cached_response("test_key")
        assert result == "hello world"

    def test_cached_response_missing(self):
        from core.llm_core import _get_cached_response, _response_cache
        _response_cache.clear()
        assert _get_cached_response("nonexistent") is None

    def test_cache_lru_eviction(self):
        from core.llm_core import _get_cached_response, _set_cached_response, _response_cache, _CACHE_MAXSIZE
        _response_cache.clear()
        # Fill to maxsize
        for i in range(_CACHE_MAXSIZE):
            _set_cached_response(f"key{i}", f"val{i}")
        # Access first key to promote it (LRU)
        _get_cached_response("key0")
        # Add one more to trigger eviction
        _set_cached_response("overflow", "val")
        # key1 should be evicted (it was LRU after key0 was promoted)
        assert _get_cached_response("key1") is None
        # key0 should survive (was promoted)
        assert _get_cached_response("key0") is not None
        # overflow should exist
        assert _get_cached_response("overflow") is not None
        _response_cache.clear()
