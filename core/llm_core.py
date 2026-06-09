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
"""core/llm_core.py — Thin re-export of all public LLM symbols.

Each symbol is imported from its domain-specific submodule and re-exported
here so that existing ``from core.llm_core import ...`` statements continue
to work without modification.
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

from core.llm_messages import _sanitize_llm_messages
from core.llm_providers import (
    _build_ollama_payload,
    _detect_provider,
    _is_ollama_native_url,
    _normalize_ollama_url,
    _ollama_api_root,
    _provider_headers,
)
from core.llm_state import (
    _CACHE_MAXSIZE,
    _clear_host_dead,
    _get_cache_key,
    _get_cached_response,
    _get_http_client,
    _host_key,
    _is_host_dead,
    _mark_host_dead,
    _response_cache,
    _set_cached_response,
    note_model_activity,
)
from core.model_context import get_context_length

logger = logging.getLogger(__name__)


async def stream_llm_with_fallback(
    candidates: list,
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    tools: list | None = None,
    timeout: int = 120,
    prompt_type: str | None = None,
):
    """Stream from the first healthy candidate; fall through on failure.
    Yields SSE-formatted strings: ``data: <json>``, ``data: [DONE]``, ``event: error``.
    """
    seen = set()
    cands = []
    for c in candidates or []:
        if not c or not c[0] or not c[1]:
            continue
        key = (c[0], c[1])
        if key in seen:
            continue
        seen.add(key)
        cands.append(c)

    if not cands:
        yield "event: error\ndata: No model endpoint configured\n\n"
        return

    last_err = None
    for i, (url, model, headers) in enumerate(cands):
        try:
            provider = _detect_provider(url)
            messages_copy = _sanitize_llm_messages(messages)

            sys_parts = [m["content"] for m in messages_copy if m.get("role") == "system"]
            non_sys = [m for m in messages_copy if m.get("role") != "system"]
            if sys_parts:
                messages_copy = [{"role": "system", "content": "\n\n".join(sys_parts)}] + non_sys

            if provider == "ollama":
                target_url = _normalize_ollama_url(url)
                h = {"Content-Type": "application/json"}
                if headers:
                    h.update(headers)
                payload = _build_ollama_payload(
                    model, messages_copy, temperature, max_tokens,
                    stream=True, tools=tools,
                    num_ctx=get_context_length(url, model),
                )
            else:
                target_url = url
                h = _provider_headers(provider, headers)
                payload = {
                    "model": model,
                    "messages": messages_copy,
                    "temperature": temperature,
                    "stream": True,
                }
                if max_tokens and max_tokens > 0:
                    payload["max_tokens"] = max_tokens
                if tools:
                    payload["tools"] = tools

            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=float(timeout), write=10.0)) as client:
                async with client.stream("POST", target_url, headers=h, json=payload) as resp:
                    if not resp.is_success:
                        body = await resp.aread()
                        err_text = body.decode(errors="replace")[:500]
                        logger.warning("[stream] %s candidate %s failed: HTTP %d %s",
                                       "primary" if i == 0 else "fallback", model, resp.status_code, err_text)
                        raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)

                    if provider == "ollama":
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                if data.get("done"):
                                    yield "data: [DONE]\n\n"
                                    return
                                content = data.get("message", {}).get("content", "") or data.get("response", "")
                                if content:
                                    yield f"data: {json.dumps({'delta': content})}\n\n"
                            except json.JSONDecodeError:
                                continue
                    else:
                        async for line in resp.aiter_lines():
                            if line.startswith("data: "):
                                chunk = line[6:]
                                if chunk.strip() == "[DONE]":
                                    yield "data: [DONE]\n\n"
                                    return
                                try:
                                    data = json.loads(chunk)
                                    choices = data.get("choices", [])
                                    for choice in choices:
                                        delta = choice.get("delta", {})
                                        content = delta.get("content") or ""
                                        if content:
                                            yield f"data: {json.dumps({'delta': content})}\n\n"
                                        tc_delta = delta.get("tool_calls")
                                        if tc_delta:
                                            yield f"data: {json.dumps({'type': 'tool_call_delta', 'name': tc_delta[0].get('function', {}).get('name', ''), 'arg_delta': tc_delta[0].get('function', {}).get('arguments', '')})}\n\n"
                                except json.JSONDecodeError:
                                    continue
                    yield "data: [DONE]\n\n"
                    return

        except Exception as e:
            last_err = e
            tag = "primary" if i == 0 else "fallback"
            logger.warning("[stream] %s candidate %s failed: %s", tag, model, e)
            yield f"event: error\ndata: {tag} {model} failed: {e}\n\n"
            continue

    if last_err:
        yield f"event: error\ndata: All candidates failed: {last_err}\n\n"
