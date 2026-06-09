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

"""core/llm_state.py — Shared mutable state for LLM operations.

Holds the LRU+TTL response cache (persistent), dead-host cooldown tracking,
model activity timestamps, and the shared HTTP client.
"""
from __future__ import annotations

import os
import time
import hashlib
import json
import threading
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Dict, List

import httpx

logger = logging.getLogger(__name__)


class LLMConfig:
    DEFAULT_TIMEOUT = 30
    DEFAULT_TEMPERATURE = 1.0
    DEFAULT_MAX_TOKENS = 0
    MAX_RETRIES = 3
    RETRY_DELAY = 0.5
    STREAM_TIMEOUT = 300


_CACHE_MAXSIZE = 256
_CACHE_TTL = 3600.0
_cache_lock = threading.Lock()
_cache_dir = Path(os.environ.get("JARVIS_DATA_DIR", "data")).resolve()
_cache_path = _cache_dir / "llm_response_cache.json"


def _get_cache_key(url: str, model: str, messages: List[Dict],
                   temperature: float, max_tokens: int) -> str:
    hashable_messages = []
    for msg in messages:
        sorted_items = tuple(sorted(msg.items()))
        hashable_messages.append(sorted_items)
    content = json.dumps({
        'url': url,
        'model': model,
        'messages': hashable_messages,
        'temp': temperature,
        'max_tokens': max_tokens,
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


_response_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()


def _load_cache() -> None:
    if not _cache_path.exists():
        return
    try:
        raw = _cache_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        now = time.monotonic()
        for key, (expires_at, value) in data.items():
            if now < expires_at:
                _response_cache[key] = (expires_at, value)
        # enforce max size
        while len(_response_cache) > _CACHE_MAXSIZE:
            _response_cache.popitem(last=False)
        logger.debug("Loaded %d cache entries from %s", len(_response_cache), _cache_path)
    except Exception as e:
        logger.warning("Failed to load response cache: %s", e)


def _save_cache() -> None:
    try:
        _cache_dir.mkdir(parents=True, exist_ok=True)
        data = dict(_response_cache)
        _cache_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except Exception as e:
        logger.debug("Failed to save response cache: %s", e)


# Load existing cache on module import
_load_cache()


def _get_cached_response(cache_key: str) -> Optional[str]:
    with _cache_lock:
        entry = _response_cache.get(cache_key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            _response_cache.pop(cache_key, None)
            return None
        _response_cache.move_to_end(cache_key)
        return value


def _set_cached_response(cache_key: str, response: str) -> None:
    with _cache_lock:
        if cache_key in _response_cache:
            _response_cache.move_to_end(cache_key)
            expires_at, _ = _response_cache[cache_key]
            _response_cache[cache_key] = (expires_at, response)
        else:
            while len(_response_cache) >= _CACHE_MAXSIZE:
                _response_cache.popitem(last=False)
            _response_cache[cache_key] = (time.monotonic() + _CACHE_TTL, response)
    _save_cache()


DEAD_HOST_COOLDOWN = 20.0
_HOST_FAIL_THRESHOLD = 2
_dead_hosts: Dict[str, float] = {}
_host_fails: Dict[str, int] = {}
_host_health_lock = threading.Lock()
_model_activity: Dict[str, float] = {}


def _model_activity_key(url: str, model: str) -> str:
    return f"{(url or '').strip().rstrip()}|{(model or '').strip()}"


def note_model_activity(url: str, model: str):
    if not url or not model:
        return
    _model_activity[_model_activity_key(url, model)] = time.time()


def seconds_since_model_activity(url: str, model: str) -> Optional[float]:
    ts = _model_activity.get(_model_activity_key(url, model))
    if not ts:
        return None
    return max(0.0, time.time() - ts)


def _host_key(url: str) -> str:
    from urllib.parse import urlsplit
    s = urlsplit(url)
    return f"{s.scheme}://{s.netloc}" if s.scheme and s.netloc else url


def _is_host_dead(url: str) -> bool:
    key = _host_key(url)
    with _host_health_lock:
        exp = _dead_hosts.get(key)
        if exp is None:
            return False
        if time.time() >= exp:
            _dead_hosts.pop(key, None)
            return False
        return True


def _mark_host_dead(url: str) -> bool:
    key = _host_key(url)
    with _host_health_lock:
        n = _host_fails.get(key, 0) + 1
        _host_fails[key] = n
        if n >= _HOST_FAIL_THRESHOLD:
            _dead_hosts[key] = time.time() + DEAD_HOST_COOLDOWN
            return True
        return False


def _clear_host_dead(url: str) -> None:
    key = _host_key(url)
    with _host_health_lock:
        _dead_hosts.pop(key, None)
        _host_fails.pop(key, None)


_http_client: Optional[httpx.AsyncClient] = None
_http_limits = httpx.Limits(max_connections=100, max_keepalive_connections=30, keepalive_expiry=30.0)


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(limits=_http_limits, http2=False)
    return _http_client
