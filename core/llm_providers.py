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
"""core/llm_providers.py — Provider detection, payload builders, response parsers.

Anthropic, Ollama, and OpenAI-compatible provider adapters.
"""
from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

from core.model_context import DEFAULT_CONTEXT

logger = logging.getLogger(__name__)


ANTHROPIC_MODELS = [
    "claude-opus-4-20250514", "claude-opus-4",
    "claude-sonnet-4-20250514", "claude-sonnet-4", "claude-sonnet-4-5-20250929", "claude-sonnet-4-5",
    "claude-haiku-4-20250514", "claude-haiku-4", "claude-haiku-3-5-20241022", "claude-haiku-3-5",
]


def _host_match(url: str, *domains: str) -> bool:
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
    except Exception as e:
        logger.warning("[core.llm_providers] host_match urlparse failed: %s", e)
        return False
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in domains)


def _is_ollama_native_url(url: str) -> bool:
    try:
        parsed = urlparse(url or "")
    except Exception as e:
        logger.warning("[core.llm_providers] ollama URL urlparse failed: %s", e)
        return False
    host = parsed.hostname or ""
    path = (parsed.path or "").rstrip("/")
    if _host_match(url, "ollama.com"):
        return True
    if parsed.port == 11434:
        return True
    local_ollama_host = host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    return local_ollama_host and (path == "/api" or path.startswith("/api/"))


def _ollama_api_root(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    parsed = urlparse(url)
    path = (parsed.path or "").rstrip("/")
    if path.endswith("/api/chat"):
        return url[: -len("/chat")]
    if path.endswith("/api/tags"):
        return url[: -len("/tags")]
    if path.endswith("/api/generate"):
        return url[: -len("/generate")]
    if path.endswith("/api"):
        return url
    if _host_match(url, "ollama.com"):
        root = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "https://ollama.com"
        return root.rstrip("/") + "/api"
    _host = parsed.hostname or ""
    _base_path = (parsed.path or "").rstrip("/")
    if (parsed.port == 11434 or _host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}) and not _base_path:
        return url.rstrip("/") + "/api"
    return url


def _normalize_ollama_url(url: str) -> str:
    base = _ollama_api_root(url)
    return base.rstrip("/") + "/chat"


def _ollama_normalize_tool_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages or []:
        tcs = m.get("tool_calls") if isinstance(m, dict) else None
        if not tcs:
            out.append(m)
            continue
        new_calls = []
        for tc in tcs:
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except (json.JSONDecodeError, TypeError):
                    args = {}
            call: dict = {"function": {"name": fn.get("name", ""), "arguments": args or {}}}
            if tc.get("id"):
                call["id"] = tc["id"]
            new_calls.append(call)
        nm = dict(m)
        nm["tool_calls"] = new_calls
        out.append(nm)
    return out


def _build_ollama_payload(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    stream: bool = False,
    tools: list[dict] | None = None,
    num_ctx: int | None = None,
) -> dict:
    payload: dict = {
        "model": model,
        "messages": _ollama_normalize_tool_messages(messages),
        "stream": stream,
    }
    options: dict = {}
    if temperature is not None:
        options["temperature"] = temperature
    if max_tokens and max_tokens > 0:
        options["num_predict"] = max_tokens
    if num_ctx is not None and num_ctx > 0 and num_ctx != DEFAULT_CONTEXT:
        options["num_ctx"] = num_ctx
    if options:
        payload["options"] = options
    if tools:
        payload["tools"] = tools
    # Keep model loaded in GPU between requests
    # Validate duration string — Ollama rejects "-1" and other invalid formats
    try:
        from core.config_registry import config as _cfg
        _ka = _cfg.get("ollama.keep_alive") or "5m"
    except Exception:
        _ka = "5m"
    # Ensure value is a valid duration (positive integer + unit suffix)
    _valid_keep_alive = False
    if isinstance(_ka, str) and _ka.strip():
        import re as _re
        _m = _re.match(r'^(\d+)([smhd])$', _ka.strip())
        if _m and int(_m.group(1)) > 0:
            _valid_keep_alive = True
    if not _valid_keep_alive:
        _ka = "5m"
    payload["keep_alive"] = _ka
    return payload


def _parse_ollama_response(data: dict) -> str:
    message = data.get("message") or {}
    return message.get("content") or data.get("response") or ""


def _detect_provider(url: str) -> str:
    if _is_ollama_native_url(url):
        return "ollama"
    if _host_match(url, "anthropic.com"):
        return "anthropic"
    if _host_match(url, "openrouter.ai"):
        return "openrouter"
    if _host_match(url, "groq.com"):
        return "groq"
    return "openai"


def _provider_headers(provider: str, headers: dict | None = None) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if isinstance(headers, dict):
        h.update(headers)
    if provider == "openrouter":
        h.setdefault("HTTP-Referer", "https://github.com/pewdiepie-archdaemon/odysseus")
        h.setdefault("X-OpenRouter-Title", "Odysseus")
    return h


def _provider_label(url: str) -> str:
    if not url:
        return "provider"
    if _host_match(url, "anthropic.com"): return "Anthropic"
    if _host_match(url, "ollama.com"): return "Ollama Cloud"
    if _host_match(url, "x.ai"): return "xAI"
    if _host_match(url, "openai.com"): return "OpenAI"
    if _host_match(url, "openrouter.ai"): return "OpenRouter"
    if _host_match(url, "groq.com"): return "Groq"
    if _host_match(url, "mistral.ai"): return "Mistral"
    if _host_match(url, "deepseek.com"): return "DeepSeek"
    if _host_match(url, "googleapis.com"): return "Google"
    if _host_match(url, "together.xyz", "together.ai"): return "Together"
    if _host_match(url, "fireworks.ai"): return "Fireworks"
    if _is_ollama_native_url(url): return "Ollama"
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception as e:
        logger.warning("[core.llm_providers] provider_label urlparse failed: %s", e)
        return "provider"
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return "local endpoint"
    return host or "provider"


def _format_upstream_error(status: int, body: bytes | str, url: str) -> str:
    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning("[core.llm_providers] upstream error body decode failed: %s", e)
            body = str(body)
    provider = _provider_label(url)
    detail = ""
    try:
        j = json.loads(body) if body else {}
        if isinstance(j, dict):
            err = j.get("error") or j
            if isinstance(err, dict):
                detail = (err.get("message") or err.get("detail") or "").strip()
            elif isinstance(err, str):
                detail = err.strip()
    except Exception as e:
        logger.warning("[core.llm_providers] upstream error JSON parse failed: %s", e)
        detail = (body or "").strip()[:240]

    if status in (401, 403):
        msg = f"{provider} rejected the API key"
        if status == 403:
            msg = f"{provider} denied access (403)"
        if detail:
            msg += f" — {detail}"
        msg += f". Check Model Endpoints → {provider} and re-paste the key."
        return msg
    if status == 404:
        return f"{provider} returned 404 — check the base URL and model name." + (f" ({detail})" if detail else "")
    if status == 429:
        return f"{provider} rate-limited the request (429)." + (f" {detail}" if detail else "")
    if status >= 500:
        return f"{provider} is having an outage (HTTP {status})." + (f" {detail}" if detail else "")
    return f"{provider} returned HTTP {status}" + (f": {detail}" if detail else "")


# Model behavior helpers

_MAX_COMPLETION_TOKENS_MODELS = {"o1", "o3", "o4", "gpt-4.5", "gpt-5"}


def _uses_max_completion_tokens(model: str) -> bool:
    if not model:
        return False
    m = model.lower()
    return any(m.startswith(p) or f"/{p}" in m for p in _MAX_COMPLETION_TOKENS_MODELS)


_FIXED_TEMPERATURE_MODELS = ("o1", "o3", "o4", "gpt-5")


def _restricts_temperature(model: str) -> bool:
    if not model:
        return False
    m = model.lower()
    return any(m.startswith(p) or f"/{p}" in m for p in _FIXED_TEMPERATURE_MODELS)


_THINKING_MODEL_PATTERNS = ("qwen3", "qwq", "deepseek-r1", "deepseek-reasoner", "minimax", "m2-reap", "gemma")


def _supports_thinking(model: str) -> bool:
    if not model:
        return False
    m = model.lower()
    return any(p in m for p in _THINKING_MODEL_PATTERNS)


# Anthropic adapter


def _convert_openai_content_to_anthropic(content):
    if not isinstance(content, list):
        return content
    converted = []
    for block in content:
        if not isinstance(block, dict):
            converted.append(block)
            continue
        if block.get("type") == "image_url":
            url = (block.get("image_url") or {}).get("url", "")
            if url.startswith("data:"):
                try:
                    header, b64_data = url.split(",", 1)
                    media_type = header.split(";")[0].replace("data:", "")
                except (ValueError, IndexError):
                    continue
                converted.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64_data},
                })
            else:
                converted.append({
                    "type": "image",
                    "source": {"type": "url", "url": url},
                })
        elif block.get("type") == "text":
            converted.append(block)
        else:
            converted.append(block)
    return converted


def _build_anthropic_payload(model, messages, temperature, max_tokens, stream=False, tools=None):
    system_parts = []
    chat_messages = []
    for m in messages:
        if m.get("role") == "system":
            system_parts.append(m["content"])
        elif m.get("role") == "tool":
            chat_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": m.get("content", ""),
                }],
            })
        elif m.get("role") == "assistant" and isinstance(m.get("tool_calls"), list):
            content = []
            if m.get("content"):
                content.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                fn = tc.get("function") or {}
                args_str = fn.get("arguments") or "{}"
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except (json.JSONDecodeError, TypeError):
                    args = {}
                content.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": args,
                })
            chat_messages.append({"role": "assistant", "content": content})
        else:
            content = _convert_openai_content_to_anthropic(m["content"])
            chat_messages.append({"role": m["role"], "content": content})
    if temperature is not None:
        temperature = max(0.0, min(temperature, 1.0))
    payload = {
        "model": model,
        "messages": chat_messages,
        "max_tokens": max_tokens if max_tokens and max_tokens > 0 else 4096,
        "temperature": temperature,
    }
    if system_parts:
        system_text = "\n\n".join(system_parts)
        system_block = {"type": "text", "text": system_text}
        if tools or len(system_text) > 4000:
            system_block["cache_control"] = {"type": "ephemeral"}
        payload["system"] = [system_block]
    if stream:
        payload["stream"] = True
    if tools:
        anthropic_tools = []
        for t in tools:
            if t.get("type") == "function":
                fn = t["function"]
                anthropic_tools.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })
        if anthropic_tools:
            anthropic_tools[-1]["cache_control"] = {"type": "ephemeral"}
            payload["tools"] = anthropic_tools
    # Add cache_control to the last TEXT-based user message (not a tool_result wrapper).
    # This lets Anthropic cache system prompt + tools + conversation history up to that point.
    if chat_messages and anthropic_tools:
        for i in range(len(chat_messages) - 1, -1, -1):
            msg = chat_messages[i]
            if msg["role"] != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                # Skip tool_result-only messages
                has_text = any(
                    isinstance(b, dict) and b.get("type") == "text"
                    for b in content
                )
                if not has_text:
                    continue
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        block["cache_control"] = {"type": "ephemeral"}
                        break
            elif isinstance(content, str):
                msg["cache_control"] = {"type": "ephemeral"}
            break
    return payload


def _build_anthropic_headers(headers):
    h = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
    if headers:
        for k, v in headers.items():
            if k.lower() == "authorization" and isinstance(v, str) and v.startswith("Bearer "):
                h["x-api-key"] = v[7:]
            else:
                h[k] = v
    return h


def _parse_anthropic_response(data: dict) -> str:
    return "".join(
        block.get("text", "")
        for block in data.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _normalize_anthropic_url(url: str) -> str:
    url = url.rstrip("/")
    if url.endswith("/v1/messages"):
        return url
    if url.endswith("/v1"):
        return url + "/messages"
    return url + "/v1/messages"
