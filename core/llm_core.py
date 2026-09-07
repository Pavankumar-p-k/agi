"""Small deterministic response cache helpers used by the LLM client."""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict

_CACHE_MAXSIZE = 256
_response_cache: OrderedDict[str, str] = OrderedDict()


def _get_cache_key(
    base_url: str,
    model: str,
    messages,
    temperature: float,
    max_tokens: int,
) -> str:
    payload = {
        "base_url": base_url,
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _get_cached_response(key: str) -> str | None:
    value = _response_cache.pop(key, None)
    if value is not None:
        _response_cache[key] = value
    return value


def _set_cached_response(key: str, value: str) -> None:
    _response_cache.pop(key, None)
    _response_cache[key] = value
    while len(_response_cache) > _CACHE_MAXSIZE:
        _response_cache.popitem(last=False)
