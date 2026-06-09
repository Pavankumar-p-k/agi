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
"""core/llm_calls.py — LLM call functions (sync and async) with fallback.

Includes `llm_call`, `llm_call_async`, their fallback wrappers,
`list_model_ids`, and `normalize_model_id`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx
from fastapi import HTTPException

from core.model_context import get_context_length

from .llm_messages import _sanitize_llm_messages
from .llm_providers import (
    ANTHROPIC_MODELS,
    _build_anthropic_headers,
    _build_anthropic_payload,
    _build_ollama_payload,
    _detect_provider,
    _format_upstream_error,
    _normalize_anthropic_url,
    _normalize_ollama_url,
    _ollama_api_root,
    _parse_anthropic_response,
    _parse_ollama_response,
    _provider_headers,
    _restricts_temperature,
    _uses_max_completion_tokens,
)
from .llm_state import (
    DEAD_HOST_COOLDOWN,
    LLMConfig,
    _clear_host_dead,
    _get_cache_key,
    _get_cached_response,
    _get_http_client,
    _host_key,
    _is_host_dead,
    _mark_host_dead,
    _set_cached_response,
    note_model_activity,
)

logger = logging.getLogger(__name__)


def list_model_ids(base_chat_url: str, timeout: int = LLMConfig.DEFAULT_TIMEOUT, headers: dict | None = None) -> list[str]:
    provider = _detect_provider(base_chat_url)
    if provider == "anthropic":
        return list(ANTHROPIC_MODELS)
    try:
        h = {}
        if headers:
            h.update(headers)
        if provider == "ollama":
            models_url = _ollama_api_root(base_chat_url) + "/tags"
        else:
            models_url = base_chat_url.replace("/chat/completions", "/models")
        r = httpx.get(models_url, headers=h, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        model_ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        if not model_ids:
            model_ids = [
                m.get("name") or m.get("model")
                for m in (data.get("models") or [])
                if m.get("name") or m.get("model")
            ]
        return model_ids
    except Exception:
        logger.debug("_list_models primary endpoint failed", exc_info=True)
        try:
            if ":11434" in base_chat_url or "ollama" in base_chat_url.lower():
                root = base_chat_url.replace("/v1/chat/completions", "").replace("/chat/completions", "").rstrip("/")
                r = httpx.get(root + "/api/tags", timeout=timeout)
                r.raise_for_status()
                return [m.get("name") or m.get("model") for m in (r.json().get("models") or []) if m.get("name") or m.get("model")]
        except Exception:
            logger.debug("_list_models ollama fallback also failed", exc_info=True)
        return []


def normalize_model_id(endpoint_url: str, requested: str, timeout: int = LLMConfig.DEFAULT_TIMEOUT) -> str | None:
    avail = list_model_ids(endpoint_url, timeout)
    if not avail:
        return None
    if requested in avail:
        return requested
    import os as _os
    req_base = _os.path.basename(requested.rstrip("/"))
    for a in avail:
        if _os.path.basename(a.rstrip("/")) == req_base:
            return a
    return None


def _dedupe_candidates(candidates):
    seen = set()
    out = []
    for c in candidates or []:
        if not c or not c[0] or not c[1]:
            continue
        key = (c[0], c[1])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def llm_call(url: str, model: str, messages: list[dict], temperature: float = LLMConfig.DEFAULT_TEMPERATURE,
             max_tokens: int = LLMConfig.DEFAULT_MAX_TOKENS, headers: dict | None = None,
             timeout: int = LLMConfig.DEFAULT_TIMEOUT, prompt_type: str | None = None,
             response_format: dict | None = None,
             structured_output_model: type | None = None) -> str:
    h = _provider_headers(_detect_provider(url))
    if isinstance(headers, str):
        try:
            headers = json.loads(headers)
        except Exception:
            logger.debug("llm_call headers string parse failed", exc_info=True)
            headers = None
    if isinstance(headers, dict):
        h.update(headers)

    messages_copy = _sanitize_llm_messages(messages)

    sys_parts = []
    non_sys = []
    for m in messages_copy:
        if m.get("role") == "system":
            sys_parts.append(m["content"])
        else:
            non_sys.append(m)
    if sys_parts:
        messages_copy = [{"role": "system", "content": "\n\n".join(sys_parts)}] + non_sys
    else:
        messages_copy = non_sys

    if structured_output_model is not None and response_format is None:
        try:
            schema = structured_output_model.model_json_schema()
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": structured_output_model.__name__,
                    "schema": schema,
                    "strict": True,
                },
            }
        except Exception as e:
            logger.debug("Failed to build response_format from structured_output_model: %s", e)

    provider = _detect_provider(url)
    cache_key = _get_cache_key(url, model, messages_copy, temperature, max_tokens)
    cached_response = _get_cached_response(cache_key)
    if cached_response:
        logger.debug(f"Returning cached response for key: {cache_key}")
        return cached_response

    if provider == "anthropic":
        target_url = _normalize_anthropic_url(url)
        h = _build_anthropic_headers(headers)
        payload = _build_anthropic_payload(model, messages_copy, temperature, max_tokens)
    elif provider == "ollama":
        target_url = _normalize_ollama_url(url)
        payload = _build_ollama_payload(
            model, messages_copy, temperature, max_tokens,
            stream=False, num_ctx=get_context_length(url, model),
        )
    else:
        target_url = url
        payload = {
            "model": model,
            "messages": messages_copy,
            "temperature": temperature,
        }
        if _restricts_temperature(model):
            payload.pop("temperature", None)
        if max_tokens and max_tokens > 0:
            tok_key = "max_completion_tokens" if _uses_max_completion_tokens(model) else "max_tokens"
            payload[tok_key] = max_tokens
        if response_format:
            payload["response_format"] = response_format
    try:
        note_model_activity(target_url, model)
        r = httpx.post(target_url, headers=h, json=payload, timeout=timeout)
    except Exception as e:
        raise HTTPException(502, f"POST {target_url} failed: {e}")
    if not r.is_success:
        raise HTTPException(502, f"Upstream {target_url} -> {r.status_code}: {r.text}")
    data = r.json()
    try:
        if provider == "anthropic":
            response = _parse_anthropic_response(data)
        elif provider == "ollama":
            response = _parse_ollama_response(data)
        else:
            msg = data["choices"][0]["message"]
            response = msg.get("content") or msg.get("reasoning_content") or ""
        _set_cached_response(cache_key, response)
        return response
    except Exception:
        logger.debug("llm_call response parse failed", exc_info=True)
        raise HTTPException(502, f"Unexpected schema from {target_url}: {str(data)[:400]}")


def llm_call_with_fallback(candidates, messages, **kwargs) -> str:
    cands = _dedupe_candidates(candidates)
    if not cands:
        raise HTTPException(503, "No model endpoint configured")
    last_err = None
    for i, (url, model, headers) in enumerate(cands):
        try:
            return llm_call(url, model, messages, headers=headers, **kwargs)
        except Exception as e:
            last_err = e
            tag = "primary" if i == 0 else "candidate"
            logger.warning(f"[fallback] {tag} {model} failed ({type(e).__name__}); trying next")
            continue
    raise last_err if last_err else HTTPException(503, "All fallback candidates failed")


async def llm_call_async_with_fallback(candidates, messages, **kwargs) -> str:
    cands = _dedupe_candidates(candidates)
    if not cands:
        raise HTTPException(503, "No model endpoint configured")
    last_err = None
    for i, (url, model, headers) in enumerate(cands):
        try:
            return await llm_call_async(url, model, messages, headers=headers, **kwargs)
        except Exception as e:
            last_err = e
            tag = "primary" if i == 0 else "candidate"
            logger.warning(f"[fallback] {tag} {model} failed ({type(e).__name__}); trying next")
            continue
    raise last_err if last_err else HTTPException(503, "All fallback candidates failed")


async def llm_call_async(
    url: str,
    model: str,
    messages: list[dict],
    temperature: float = LLMConfig.DEFAULT_TEMPERATURE,
    max_tokens: int = LLMConfig.DEFAULT_MAX_TOKENS,
    headers: dict | None = None,
    timeout: int = LLMConfig.STREAM_TIMEOUT,
    max_retries: int = LLMConfig.MAX_RETRIES,
    prompt_type: str | None = None,
    response_format: dict | None = None,
    structured_output_model: type | None = None,
) -> str:
    provider = _detect_provider(url)
    messages_copy = _sanitize_llm_messages(messages)

    sys_parts = []
    non_sys = []
    for m in messages_copy:
        if m.get("role") == "system":
            sys_parts.append(m["content"])
        else:
            non_sys.append(m)
    if sys_parts:
        messages_copy = [{"role": "system", "content": "\n\n".join(sys_parts)}] + non_sys
    else:
        messages_copy = non_sys

    if structured_output_model is not None and response_format is None:
        try:
            schema = structured_output_model.model_json_schema()
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": structured_output_model.__name__,
                    "schema": schema,
                    "strict": True,
                },
            }
        except Exception as e:
            logger.debug("Failed to build response_format from structured_output_model: %s", e)

    cache_key = _get_cache_key(url, model, messages_copy, temperature, max_tokens)
    cached_response = _get_cached_response(cache_key)
    if cached_response:
        logger.debug(f"Returning cached response for key: {cache_key}")
        return cached_response

    if provider == "anthropic":
        target_url = _normalize_anthropic_url(url)
        h = _build_anthropic_headers(headers)
        payload = _build_anthropic_payload(model, messages_copy, temperature, max_tokens)
    elif provider == "ollama":
        target_url = _normalize_ollama_url(url)
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        payload = _build_ollama_payload(
            model, messages_copy, temperature, max_tokens,
            stream=False, num_ctx=get_context_length(url, model),
        )
    else:
        target_url = url
        h = _provider_headers(provider, headers)
        payload = {
            "model": model,
            "messages": messages_copy,
            "temperature": temperature,
        }
        if _restricts_temperature(model):
            payload.pop("temperature", None)
        if max_tokens and max_tokens > 0:
            tok_key = "max_completion_tokens" if _uses_max_completion_tokens(model) else "max_tokens"
            payload[tok_key] = max_tokens
        if response_format:
            payload["response_format"] = response_format

    if _is_host_dead(target_url):
        raise HTTPException(503, f"Upstream {_host_key(target_url)} marked unreachable (cooldown active)")

    call_timeout = httpx.Timeout(connect=3.0, read=float(timeout), write=10.0, pool=5.0)
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        start = time.time()
        try:
            note_model_activity(target_url, model)
            client = _get_http_client()
            r = await client.post(target_url, headers=h, json=payload, timeout=call_timeout)
            duration = time.time() - start
            if not r.is_success:
                friendly = _format_upstream_error(r.status_code, r.text, target_url)
                logger.warning(
                    f"LLM async call to {target_url} failed in {duration:.2f}s "
                    f"(attempt {attempt}): HTTP {r.status_code} {friendly}"
                )
                raise HTTPException(r.status_code, friendly)
            logger.info(f"LLM async call to {target_url} succeeded in {duration:.2f}s (attempt {attempt})")
            _clear_host_dead(target_url)
            data = r.json()
            try:
                if provider == "anthropic":
                    response = _parse_anthropic_response(data)
                elif provider == "ollama":
                    response = _parse_ollama_response(data)
                else:
                    msg = data["choices"][0]["message"]
                    response = msg.get("content") or msg.get("reasoning_content") or ""
                _set_cached_response(cache_key, response)
                return response
            except Exception:
                logger.debug("llm_async_call response parse failed", exc_info=True)
                raise HTTPException(502, f"Unexpected schema from {target_url}: {str(data)[:400]}")
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            _cooled = _mark_host_dead(target_url)
            duration = time.time() - start
            _tail = f" — host cooled for {DEAD_HOST_COOLDOWN:.0f}s" if _cooled else " — transient, will retry"
            logger.warning(f"LLM async connect to {target_url} failed after {duration:.2f}s: {e}{_tail}")
            raise HTTPException(503, f"Cannot reach {_host_key(target_url)}: {e}")
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            duration = time.time() - start
            logger.warning(f"LLM async call attempt {attempt} failed after {duration:.2f}s: {e}")
            if attempt >= max_retries:
                raise HTTPException(502, f"POST {target_url} failed after {max_retries} attempts: {e}")
            await asyncio.sleep(LLMConfig.RETRY_DELAY)
