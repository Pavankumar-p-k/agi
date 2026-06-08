"""core/llm_core.py — Thin re-export of all public LLM symbols.

Each symbol is imported from its domain-specific submodule and re-exported
here so that existing ``from core.llm_core import ...`` statements continue
to work without modification.
"""
from __future__ import annotations

# ── State ──
from .llm_state import (
    LLMConfig,
    _CACHE_MAXSIZE,
    _get_cache_key,
    _get_cached_response,
    _response_cache,
    _set_cached_response,
    note_model_activity,
    seconds_since_model_activity,
)

# ── Providers ──
from .llm_providers import (
    ANTHROPIC_MODELS,
    _detect_provider,
    _format_upstream_error,
    _host_match,
    _is_ollama_native_url,
    _provider_headers,
    _provider_label,
    _restricts_temperature,
    _supports_thinking,
    _uses_max_completion_tokens,
)

# ── Messages ──
from .llm_messages import (
    _sanitize_llm_messages,
)

# ── Calls ──
from .llm_calls import (
    _dedupe_candidates,
    list_model_ids,
    llm_call,
    llm_call_async,
    llm_call_async_with_fallback,
    llm_call_with_fallback,
    normalize_model_id,
)

# ── Stream ──
from .llm_stream import (
    _summarize_stream_error,
    stream_llm,
    stream_llm_with_fallback,
)
