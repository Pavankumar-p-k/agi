"""DEPRECATED — use `core.routing.request_classifier.classify_request()` instead.

This module is a backward-compatibility shim. The `extract_intent()`
function now delegates to the modern `classify_request()` with a mapping
layer that preserves the legacy dict format.

Deprecated: v3.2
Remove after: v4.0
"""
from __future__ import annotations

import logging
import re
import warnings
from typing import Any

from core.routing.request_classifier import RequestMode, classify_request

logger = logging.getLogger("intent_router")

_warned = False


def _warn() -> None:
    global _warned
    if not _warned:
        warnings.warn(
            "core.intent_router is deprecated. "
            "Use 'from core.routing import classify_request' instead.",
            DeprecationWarning, stacklevel=3,
        )
        _warned = True


# ── Legacy intent mapping table ─────────────────────────────────────────────
# Maps (RequestMode, sub_type) -> legacy intent string.
# For DIRECT mode, we re-check the message text against known patterns
# to recover the specific intent (weather, news, stocks, sports, time, etc.).

def _legacy_intent(message: str, mode: RequestMode, sub_type: str | None) -> str:
    m = message.lower()
    if mode == RequestMode.DIRECT:
        if m.startswith("search ") or m.startswith("search for ") or m.startswith("look up "):
            return "web_search"
        if any(k in m for k in ("weather", "temperature", "forecast", "rain", "sunny", "humidity")):
            return "weather"
        if any(k in m for k in ("news", "headlines", "what's happening")):
            return "news"
        if re.search(r'\b[A-Z]{2,5}\b stock|stock price|share price', message):
            return "stocks"
        if any(k in m for k in ("scores", "nba", "game", "who won", "match")):
            return "sports"
        if "time" in m and "what time" in m:
            return "time"
        if m.startswith("play ") and "search" not in m:
            return "play_media"
        if "remind me" in m or "reminder" in m:
            return "reminder"
        if "send an email" in m or "send email" in m:
            return "message"
        return "web_search"

    if mode == RequestMode.ACTION:
        st = sub_type or ""
        st_short = st.removeprefix("ACTION_").lower() if st else ""
        if st_short == "browser":
            if any(k in m for k in ("sign up", "register", "login", "log in", "add to cart", "fill out", "fill", "submit", "checkout")):
                return "browser_task"
            if any(k in m for k in ("open chrome", "open browser", "vision agent", "control browser")):
                return "vision_browser"
            if m.startswith("play ") and "search" not in m:
                return "play_media"
            return "open_url"
        if st_short in ("file", "system"):
            return "pc_control"
        if st_short == "shell":
            return "build"

    if mode == RequestMode.CODEBASE:
        # Check if it's actually a web search (classifier confuses "search for X" with codebase search)
        if any(k in m for k in ("news", "weather", "stock", "price", "score")):
            return "web_search"
        return "code_task"

    if mode == RequestMode.AGENT:
        if any(m.startswith(w) for w in ("build", "create", "make", "generate")):
            return "build"
        return "chat"

    return "chat"


# ── Public API (backward-compatible) ────────────────────────────────────────

async def extract_intent(message: str) -> dict[str, Any]:
    """Classify user message into an intent dict (legacy format).

    Returns dict with keys: intent, target, parameters.
    Falls back to {'intent': 'chat', 'target': message, 'parameters': {}} on error.
    """
    _warn()
    try:
        classification = classify_request(message)
        intent = _legacy_intent(message, classification.mode, classification.sub_type)

        # Build parameters from sub_type where applicable
        params: dict[str, Any] = {}
        if classification.sub_type:
            params["sub_type"] = classification.sub_type

        return {
            "intent": intent,
            "target": message,
            "parameters": params,
        }
    except Exception as e:
        logger.warning("[intent_router] classify_request failed: %s", e)
        return {"intent": "chat", "target": message, "parameters": {}}
