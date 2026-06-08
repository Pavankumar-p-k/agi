"""core/llm_stream.py — LLM streaming functions with fallback.

Includes `stream_llm` and `stream_llm_with_fallback`.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

import httpx

from core.model_context import get_context_length
from .llm_state import (
    LLMConfig, _is_host_dead, _mark_host_dead, _clear_host_dead, DEAD_HOST_COOLDOWN,
    _get_http_client, note_model_activity, _host_key,
)
from .llm_providers import (
    _detect_provider, _provider_headers, _normalize_ollama_url, _normalize_anthropic_url,
    _build_ollama_payload, _build_anthropic_payload, _build_anthropic_headers,
    _format_upstream_error, _supports_thinking, _restricts_temperature, _uses_max_completion_tokens,
)
from .llm_messages import _sanitize_llm_messages
from .llm_calls import _dedupe_candidates

logger = logging.getLogger(__name__)


async def stream_llm(url: str, model: str, messages: List[Dict], temperature: float = LLMConfig.DEFAULT_TEMPERATURE,
                     max_tokens: int = LLMConfig.DEFAULT_MAX_TOKENS, headers: Optional[Dict] = None,
                     timeout: int = LLMConfig.STREAM_TIMEOUT, prompt_type: Optional[str] = None,
                     tools: Optional[List[Dict]] = None,
                     response_format: Optional[Dict] = None,
                     structured_output_model: Optional[type] = None):
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

    if provider == "anthropic":
        target_url = _normalize_anthropic_url(url)
        h = _build_anthropic_headers(headers)
        payload = _build_anthropic_payload(model, messages_copy, temperature, max_tokens, stream=True, tools=tools)
    elif provider == "ollama":
        target_url = _normalize_ollama_url(url)
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        payload = _build_ollama_payload(
            model, messages_copy, temperature, max_tokens,
            stream=True, tools=tools, num_ctx=get_context_length(url, model),
        )
    else:
        target_url = url
        payload = {
            "model": model,
            "messages": messages_copy,
            "temperature": temperature,
            "stream": True,
        }
        if _restricts_temperature(model):
            payload.pop("temperature", None)
        if provider not in {"openrouter", "groq"}:
            payload["stream_options"] = {"include_usage": True}
        if max_tokens and max_tokens > 0:
            tok_key = "max_completion_tokens" if _uses_max_completion_tokens(model) else "max_tokens"
            payload[tok_key] = max_tokens
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format
        h = _provider_headers(provider, headers)

    stream_timeout = httpx.Timeout(connect=3.0, read=float(timeout), write=30.0, pool=5.0)

    if _is_host_dead(target_url):
        yield f'event: error\ndata: {json.dumps({"error": f"Upstream {_host_key(target_url)} unreachable (cooldown active)", "status": 503})}\n\n'
        return
    note_model_activity(target_url, model)

    # ── Native Ollama streaming ──
    if provider == "ollama":
        _ollama_tool_calls: List[Dict] = []
        try:
            client = _get_http_client()
            async with client.stream('POST', target_url, json=payload, headers=h, timeout=stream_timeout) as r:
                _clear_host_dead(target_url)
                if r.status_code != 200:
                    raw = (await r.aread()).decode(errors="replace")
                    friendly = _format_upstream_error(r.status_code, raw, target_url)
                    yield f'event: error\ndata: {json.dumps({"status": r.status_code, "text": friendly, "raw": raw[:500]})}\n\n'
                    return
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        j = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = j.get("message") or {}
                    thinking = message.get("thinking") or ""
                    if thinking:
                        yield f'data: {json.dumps({"delta": thinking, "thinking": True})}\n\n'
                    content = message.get("content") or ""
                    if content:
                        yield f'data: {json.dumps({"delta": content})}\n\n'
                    for tc in message.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            _ollama_tool_calls.append({
                                "id": tc.get("id") or f"call_{len(_ollama_tool_calls)}",
                                "name": fn.get("name") or "",
                                "arguments": json.dumps(fn.get("arguments") or {}),
                            })
                    if j.get("done"):
                        if _ollama_tool_calls:
                            yield f'data: {json.dumps({"type": "tool_calls", "calls": _ollama_tool_calls})}\n\n'
                        if j.get("prompt_eval_count") is not None or j.get("eval_count") is not None:
                            yield f'data: {json.dumps({"type": "usage", "data": {"input_tokens": j.get("prompt_eval_count", 0), "output_tokens": j.get("eval_count", 0)}})}\n\n'
                        yield "data: [DONE]\n\n"
                        return
                yield "data: [DONE]\n\n"
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            _cooled = _mark_host_dead(target_url)
            _tail = f" — host cooled for {DEAD_HOST_COOLDOWN:.0f}s" if _cooled else " — transient, will retry"
            logger.warning(f"Ollama stream connect to {target_url} failed: {e}{_tail}")
            yield f'event: error\ndata: {json.dumps({"error": f"Cannot reach {_host_key(target_url)}", "status": 503})}\n\n'
        except httpx.ReadTimeout:
            yield f'event: error\ndata: {json.dumps({"error": "Read timeout", "status": 504})}\n\n'
        except httpx.NetworkError:
            yield f'event: error\ndata: {json.dumps({"error": "Network error", "status": 502})}\n\n'
        except Exception as e:
            logger.error(f"Ollama stream error: {e}")
            yield f'event: error\ndata: {json.dumps({"error": str(e), "status": 502})}\n\n'
        return

    # ── Anthropic streaming ──
    if provider == "anthropic":
        _anth_input_tokens = 0
        _anth_output_tokens = 0
        _anth_tool_blocks: Dict[int, Dict] = {}
        _anth_block_idx = -1
        _anth_block_type = ""
        try:
            client = _get_http_client()
            async with client.stream('POST', target_url, json=payload, headers=h, timeout=stream_timeout) as r:
                _clear_host_dead(target_url)
                if r.status_code != 200:
                    raw = (await r.aread()).decode(errors="replace")
                    friendly = _format_upstream_error(r.status_code, raw, target_url)
                    yield f'event: error\ndata: {json.dumps({"status": r.status_code, "text": friendly, "raw": raw[:500]})}\n\n'
                    return
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or not data.startswith("{"):
                        continue
                    try:
                        j = json.loads(data)
                        evt = j.get("type", "")
                        if evt == "content_block_start":
                            _anth_block_idx = j.get("index", _anth_block_idx + 1)
                            cb = j.get("content_block") or {}
                            _anth_block_type = cb.get("type", "text")
                            if _anth_block_type == "tool_use":
                                _anth_tool_blocks[_anth_block_idx] = {
                                    "id": cb.get("id") or f"call_{_anth_block_idx}",
                                    "name": cb.get("name") or "",
                                    "arguments": "",
                                }
                        elif evt == "content_block_delta":
                            delta = j.get("delta") or {}
                            delta_type = delta.get("type", "")
                            if delta_type == "text_delta":
                                text = delta.get("text") or ""
                                if text:
                                    yield f'data: {json.dumps({"delta": text})}\n\n'
                            elif delta_type == "input_json_delta":
                                idx = j.get("index", _anth_block_idx)
                                if idx in _anth_tool_blocks:
                                    partial = delta.get("partial_json") or ""
                                    _anth_tool_blocks[idx]["arguments"] += partial
                                    if partial and _anth_tool_blocks[idx].get("name") in ("create_document", "update_document", "edit_document"):
                                        yield f'data: {json.dumps({"type": "tool_call_delta", "index": idx, "name": _anth_tool_blocks[idx]["name"], "arg_delta": partial})}\n\n'
                        elif evt == "message_start":
                            _u = j.get("message", {}).get("usage", {})
                            _anth_input_tokens = _u.get("input_tokens", 0)
                            _c_read = _u.get("cache_read_input_tokens", 0)
                            _c_write = _u.get("cache_creation_input_tokens", 0)
                            if _c_read or _c_write:
                                logger.info(
                                    "[anthropic-cache] read=%s write=%s fresh_input=%s",
                                    _c_read, _c_write, _anth_input_tokens,
                                )
                        elif evt == "message_delta":
                            _anth_output_tokens = j.get("usage", {}).get("output_tokens", 0)
                        elif evt == "message_stop":
                            if _anth_tool_blocks:
                                calls = []
                                for idx in sorted(_anth_tool_blocks):
                                    tb = _anth_tool_blocks[idx]
                                    calls.append({
                                        "id": tb["id"],
                                        "name": tb["name"],
                                        "arguments": tb["arguments"],
                                    })
                                yield f'data: {json.dumps({"type": "tool_calls", "calls": calls})}\n\n'
                            if _anth_input_tokens or _anth_output_tokens:
                                yield f'data: {json.dumps({"type": "usage", "data": {"input_tokens": _anth_input_tokens, "output_tokens": _anth_output_tokens}})}\n\n'
                            yield "data: [DONE]\n\n"
                            return
                        elif evt == "error":
                            err_msg = j.get("error", {}).get("message", "Unknown error")
                            yield f'event: error\ndata: {json.dumps({"error": err_msg, "status": 400})}\n\n'
                            return
                    except json.JSONDecodeError:
                        continue
                yield "data: [DONE]\n\n"
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            _cooled = _mark_host_dead(target_url)
            _tail = f" — host cooled for {DEAD_HOST_COOLDOWN:.0f}s" if _cooled else " — transient, will retry"
            logger.warning(f"Anthropic stream connect to {target_url} failed: {e}{_tail}")
            yield f'event: error\ndata: {json.dumps({"error": f"Cannot reach {_host_key(target_url)}", "status": 503})}\n\n'
        except httpx.ReadTimeout:
            yield f'event: error\ndata: {json.dumps({"error": "Read timeout", "status": 504})}\n\n'
        except httpx.NetworkError:
            yield f'event: error\ndata: {json.dumps({"error": "Network error", "status": 502})}\n\n'
        except Exception as e:
            logger.error(f"Anthropic stream error: {e}")
            yield f'event: error\ndata: {json.dumps({"error": str(e), "status": 502})}\n\n'
        return

    # ── OpenAI-compatible streaming ──
    _tc_acc: Dict[int, Dict] = {}
    _tc_last_idx = [-1]
    _thinking_model = _supports_thinking(model)
    _first_content_sent = False

    def _emit_tool_calls():
        if not _tc_acc:
            return None
        calls = [_tc_acc[i] for i in sorted(_tc_acc)]
        return f'data: {json.dumps({"type": "tool_calls", "calls": calls})}\n\n'

    try:
        client = _get_http_client()
        async with client.stream('POST', target_url, json=payload, headers=h, timeout=stream_timeout) as r:
            _clear_host_dead(target_url)
            if r.status_code != 200:
                raw = (await r.aread()).decode(errors="replace")
                friendly = _format_upstream_error(r.status_code, raw, target_url)
                yield f'event: error\ndata: {json.dumps({"status": r.status_code, "text": friendly, "raw": raw[:500]})}\n\n'
                return

            async for line in r.aiter_lines():
                if not line:
                    continue

                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data == "[DONE]":
                        tc_event = _emit_tool_calls()
                        if tc_event:
                            yield tc_event
                        yield "data: [DONE]\n\n"
                        return

                    try:
                        if data.strip():
                            if data.startswith("{"):
                                j = json.loads(data)
                                _choices = j.get("choices") or []
                                _delta0 = _choices[0].get("delta") if _choices else None
                                _delta_has_output = isinstance(_delta0, dict) and (
                                    _delta0.get("content")
                                    or _delta0.get("reasoning_content")
                                    or _delta0.get("reasoning")
                                    or _delta0.get("tool_calls")
                                )
                                if "usage" in j and not _delta_has_output:
                                    u = j["usage"]
                                    _usage_data = {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0)}
                                    _tm = j.get("timings")
                                    if isinstance(_tm, dict):
                                        if _tm.get("predicted_per_second"):
                                            _usage_data["gen_tps"] = round(_tm["predicted_per_second"], 2)
                                        if _tm.get("prompt_per_second"):
                                            _usage_data["prefill_tps"] = round(_tm["prompt_per_second"], 2)
                                    yield f'data: {json.dumps({"type": "usage", "data": _usage_data})}\n\n'
                                elif "choices" in j:
                                    delta = j["choices"][0].get("delta") or {}
                                    if isinstance(delta, dict):
                                        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                                        if reasoning:
                                            yield f'data: {json.dumps({"delta": reasoning, "thinking": True})}\n\n'
                                        content = delta.get("content") or ""
                                        if content:
                                            if _thinking_model and not _first_content_sent and content.lstrip().lower().startswith("</think"):
                                                content = "<think>" + content
                                            _first_content_sent = True
                                            yield f'data: {json.dumps({"delta": content})}\n\n'
                                        for tc in delta.get("tool_calls") or []:
                                            func = tc.get("function") or {}
                                            raw_idx = tc.get("index")
                                            if raw_idx is None:
                                                if func.get("name") or _tc_last_idx[0] < 0:
                                                    idx = max(_tc_acc, default=-1) + 1
                                                else:
                                                    idx = _tc_last_idx[0]
                                            else:
                                                idx = raw_idx
                                            _tc_last_idx[0] = idx
                                            if idx not in _tc_acc:
                                                _tc_acc[idx] = {"id": "", "name": "", "arguments": ""}
                                            if tc.get("id"):
                                                _tc_acc[idx]["id"] = tc["id"]
                                            if tc.get("extra_content"):
                                                _tc_acc[idx]["extra_content"] = tc["extra_content"]
                                            if func.get("name"):
                                                _tc_acc[idx]["name"] = func["name"]
                                            if "arguments" in func:
                                                _tc_acc[idx]["arguments"] += func["arguments"]
                                                if func["arguments"] and _tc_acc[idx].get("name") in ("create_document", "update_document", "edit_document"):
                                                    yield f'data: {json.dumps({"type": "tool_call_delta", "index": idx, "name": _tc_acc[idx]["name"], "arg_delta": func["arguments"]})}\n\n'
                                    elif "text" in j:
                                        if j["text"]:
                                            yield f'data: {json.dumps({"delta": j["text"]})}\n\n'
                            else:
                                if data.strip():
                                    yield f'data: {json.dumps({"delta": data})}\n\n'
                    except Exception as e:
                        logger.error(f"Error parsing stream data: {e}")
                        continue

            tc_event = _emit_tool_calls()
            if tc_event:
                yield tc_event
            yield "data: [DONE]\n\n"

    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        _cooled = _mark_host_dead(target_url)
        _tail = f" — host cooled for {DEAD_HOST_COOLDOWN:.0f}s" if _cooled else " — transient, will retry"
        logger.warning(f"Stream connect to {target_url} failed: {e}{_tail}")
        yield f'event: error\ndata: {json.dumps({"error": f"Cannot reach {_host_key(target_url)}", "status": 503})}\n\n'
    except httpx.ReadTimeout:
        yield f'event: error\ndata: {json.dumps({"error": "Read timeout", "status": 504})}\n\n'
    except httpx.NetworkError:
        yield f'event: error\ndata: {json.dumps({"error": "Network error", "status": 502})}\n\n'
    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield f'event: error\ndata: {json.dumps({"error": str(e), "status": 502})}\n\n'


def _summarize_stream_error(err_chunk: Optional[str]) -> str:
    if not err_chunk:
        return "primary model failed"
    try:
        for line in err_chunk.split("\n"):
            if line.startswith("data: "):
                j = json.loads(line[6:])
                txt = j.get("text") or j.get("error") or ""
                status = j.get("status")
                msg = (f"HTTP {status}: " if status else "") + str(txt)
                return msg[:200].strip() or "primary model failed"
    except Exception:
        logger.debug("_summarize_stream_error parse failed", exc_info=True)
    return "primary model failed"


async def stream_llm_with_fallback(candidates, messages, **kwargs):
    cands = _dedupe_candidates(candidates)
    if not cands:
        yield f'event: error\ndata: {json.dumps({"error": "No model endpoint configured", "status": 503})}\n\n'
        return

    primary_model = cands[0][1]
    last_error = None
    for i, (url, model, headers) in enumerate(cands):
        is_last = (i == len(cands) - 1)
        emitted = False
        retried = False
        async for chunk in stream_llm(url, model, messages, headers=headers, **kwargs):
            if chunk.startswith("event: error"):
                if not emitted and not is_last:
                    last_error = chunk
                    retried = True
                    if i == 0:
                        logger.warning(f"[fallback] primary {model} failed before output; trying fallback")
                    else:
                        logger.warning(f"[fallback] candidate {model} failed; trying next")
                    break
                yield chunk
                continue
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                if not emitted and i > 0:
                    yield ('data: ' + json.dumps({
                        "type": "fallback",
                        "selected_model": primary_model,
                        "answered_by": model,
                        "reason": _summarize_stream_error(last_error),
                    }) + '\n\n')
                emitted = True
            yield chunk
        if not retried:
            return
    if last_error:
        yield last_error
