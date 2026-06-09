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

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


# ── Constants ──

DEAD_HOST_COOLDOWN: float = 60.0
_CACHE_MAXSIZE: int = 256


@dataclass
class LLMConfig:
    DEFAULT_TIMEOUT: int = 30
    STREAM_TIMEOUT: int = 120
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_MAX_TOKENS: int = 4096
    MAX_RETRIES: int = 2
    RETRY_DELAY: float = 1.0


# ── Response cache (LRU via OrderedDict) ──

_response_cache: OrderedDict[str, str] = OrderedDict()
_cache_lock = threading.Lock()


def _get_cache_key(url: str, model: str, messages: list, temperature: float, max_tokens: int) -> str:
    raw = json.dumps([url, model, messages, temperature, max_tokens], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_cached_response(key: str) -> str | None:
    with _cache_lock:
        val = _response_cache.get(key)
        if val is not None:
            _response_cache.move_to_end(key)
        return val


def _set_cached_response(key: str, value: str) -> None:
    with _cache_lock:
        if key in _response_cache:
            _response_cache.move_to_end(key)
        else:
            if len(_response_cache) >= _CACHE_MAXSIZE:
                _response_cache.popitem(last=False)
        _response_cache[key] = value


# ── HTTP client ──

_http_client: httpx.AsyncClient | None = None
_client_lock = threading.Lock()


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        with _client_lock:
            if _http_client is None:
                _http_client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0))
    return _http_client


# ── Dead-host tracking ──

_dead_hosts: dict[str, float] = {}
_dead_lock = threading.Lock()


def _host_key(url: str) -> str:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.hostname}:{parsed.port or 443}"
    except Exception:
        return url


def _is_host_dead(url: str) -> bool:
    key = _host_key(url)
    with _dead_lock:
        if key not in _dead_hosts:
            return False
        if time.time() >= _dead_hosts[key]:
            _dead_hosts.pop(key, None)
            return False
        return True


def _mark_host_dead(url: str) -> bool:
    key = _host_key(url)
    with _dead_lock:
        if key in _dead_hosts:
            return False
        _dead_hosts[key] = time.time() + DEAD_HOST_COOLDOWN
        return True


def _clear_host_dead(url: str) -> None:
    key = _host_key(url)
    with _dead_lock:
        _dead_hosts.pop(key, None)


def note_model_activity(url: str, model: str) -> None:
    logger.debug("Model activity: %s @ %s", model, url)
