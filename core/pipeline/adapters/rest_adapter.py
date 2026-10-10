"""core.pipeline.adapters.rest_adapter — REST transport adapter (canonical).

Self-contained implementation: the action parsers pinned by
``tests/unit/test_nlp_intent.py`` live here; the package ``__init__`` imports
this module eagerly and then rebinds the parent attribute so both entry
points resolve to the *function*:

    from core.pipeline.adapters import rest_adapter            # callable
    from core.pipeline.adapters.rest_adapter import _reminder_action
"""
from __future__ import annotations

import re
from typing import Any, Optional

__all__ = [
    "rest_adapter", "ws_adapter", "voice_adapter", "channel_adapter",
    "_desktop_action", "_reminder_action", "_needs_reminder_time",
    "_inline_reminder_action", "parse_desktop_actions",
]


# ═════════════════════════════ pipeline plumbing ════════════════════════════
async def _run_pipeline(text: str, transport: str, user_id: Optional[str] = None,
                        session_id: Optional[str] = None) -> Any:
    """Build a context for *transport* and execute the default pipeline."""
    import uuid
    from core.pipeline.context import PipelineContext
    from core.pipeline.pipeline import get_pipeline

    ctx = PipelineContext(
        request_id=uuid.uuid4().hex,
        transport=transport,
        user_id=user_id,
        session_id=session_id,
        raw_input=text,
    )
    return await get_pipeline().execute(ctx)


def _pipeline_text(result: Any) -> str:
    """Best-effort response text out of a pipeline PipelineContext."""
    formatted = getattr(result, "formatted_response", None)
    if isinstance(formatted, dict):
        return str(formatted.get("text", ""))
    execution = getattr(result, "execution_result", None)
    if isinstance(execution, dict):
        return str(execution.get("text", ""))
    return str(getattr(result, "raw_input", "") or "")


async def rest_adapter(message: str, user_id: Optional[str] = None,
                       session_id: Optional[str] = None,
                       **_: Any) -> dict[str, Any]:
    """HTTP entry point: pipeline text + model + metadata."""
    ctx = await _run_pipeline(message, "rest", user_id, session_id)
    return {"response": _pipeline_text(ctx), "model": "pipeline",
            "metadata": dict(getattr(ctx, "metrics", {}) or {})}


async def ws_adapter(text: str, user_id: Optional[str] = None,
                     session_id: Optional[str] = None,
                     **_: Any) -> dict[str, Any]:
    """WebSocket entry point: same dict shape as REST."""
    ctx = await _run_pipeline(text, "websocket", user_id, session_id)
    return {"response": _pipeline_text(ctx), "model": "pipeline",
            "metadata": dict(getattr(ctx, "metrics", {}) or {})}


async def voice_adapter(text: str, user_id: Optional[str] = None,
                        session_id: Optional[str] = None,
                        **_: Any) -> str:
    """Voice entry point: plain text (spoken output)."""
    ctx = await _run_pipeline(text, "voice", user_id, session_id)
    return _pipeline_text(ctx)


async def channel_adapter(text: str, source: str, channel_id: Optional[str] = None,
                          user_id: Optional[str] = None, user_name: Optional[str] = None,
                          **_: Any) -> str:
    """Channel (telegram/discord/...) entry point: plain text."""
    ctx = await _run_pipeline(text, source, user_id, channel_id)
    return _pipeline_text(ctx)


# ═════════════════════════════ desktop verbs ═══════════════════════════════
_DESKTOP_STATE_RE = re.compile(
    r"^what\s+(?:apps?|applications?|windows?|tabs?)(?:\s+(?:are\s+)?open)?", re.I)
_CLICK_RE = re.compile(r"^click(?:\s+at)?\s+(\d+)\s*[, ]\s*(\d+)", re.I)
_TYPE_RE = re.compile(r"^type\s+(?:\"([^\"]*)\"|'([^']*)'|(.+))", re.I)
_PRESS_RE = re.compile(r"^(?:press|hit)\s+(\S+)", re.I)


def _desktop_action(slot: str, session_id: Optional[str] = None) -> dict[str, Any]:
    """Parse one desktop-verb slot into an action dict (or a no-op chat)."""
    text = (slot or "").strip()
    if _DESKTOP_STATE_RE.match(text):
        return {"action": "desktop_state", "session_id": session_id}
    m = _CLICK_RE.match(text)
    if m:
        return {"action": "click", "session_id": session_id,
                "params": {"x": int(m.group(1)), "y": int(m.group(2))}}
    m = _TYPE_RE.match(text)
    if m:
        body = m.group(1) or m.group(2) or m.group(3) or ""
        return {"action": "type_text", "session_id": session_id,
                "params": {"text": body.strip()}}
    m = _PRESS_RE.match(text)
    if m:
        return {"action": "press_key", "session_id": session_id,
                "params": {"key": m.group(1).lower()}}
    return {"action": "chat", "session_id": session_id, "params": {"text": text}}


_ACTION_START_RE = re.compile(
    r"\b(?:what\s+(?:apps?|applications?|windows?|tabs?)(?:\s+(?:are\s+)?open)?|"
    r"open|launch|start|play|click|type|write|press|hit)\b", re.I)


def parse_desktop_actions(message: str, session_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Split a mixed command chain into per-verb desktop action dicts."""
    text = message or ""
    starts = list(_ACTION_START_RE.finditer(text))
    actions: list[dict[str, Any]] = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        slot = text[m.start():end].strip()
        if slot:
            actions.append(_desktop_action(slot, session_id))
    return actions or [{"action": "chat", "session_id": session_id, "params": {"text": text}}]


# ═════════════════════════════ reminder parsing ════════════════════════════
_REL_MINUTES_RE = re.compile(r"\bin\s+(\d+)\s+min(?:ute)?s?\b", re.I)
_CLOCK_RE = re.compile(r"\bat\s+(\d{1,2})(?:[: ](\d{1,2}))?\b")
_TITLE_SPLIT_RE = re.compile(r"\b(?:to|that)\s+", re.I)
_MISSPELL_RE = re.compile(r"\breaminder\b", re.I)


def _needs_reminder_time(message: str) -> bool:
    """True when the request is a reminder that has NOT carried a time."""
    text = _MISSPELL_RE.sub("reminder", message or "")
    if not re.search(r"\bremind(?:er)?\b", text, re.I):
        return False
    if _REL_MINUTES_RE.search(text):
        return False
    if _CLOCK_RE.search(text):
        return False
    return True


def _reminder_title(message: str) -> str:
    """Text after ``to``/``that`` minus any trailing time marker."""
    text = (message or "").strip()
    m = _TITLE_SPLIT_RE.search(text)
    if m:
        text = text[m.end():]
    text = _REL_MINUTES_RE.sub("", text)
    text = _CLOCK_RE.sub("", text)
    return text.strip(" .!,:") or "reminder"


def _reminder_params(message: str, user_id: Optional[str]) -> dict[str, Any]:
    params: dict[str, Any] = {"title": _reminder_title(message),
                              "user_id": user_id}
    m = _REL_MINUTES_RE.search(message or "")
    if m:
        params["in_minutes"] = int(m.group(1))
        return params
    m = _CLOCK_RE.search(message or "")
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2)) if m.group(2) else 0
        params["at_time"] = {"hour": hh, "minute": mm}
    return params


def _reminder_action(message: str, user_id: Optional[str] = None) -> dict[str, Any]:
    """Parse a ``remind me ...`` request into a create_reminder action."""
    return {"action": "create_reminder", "params": _reminder_params(message, user_id)}


def _inline_reminder_action(message: str, user_id: Optional[str] = None) -> dict[str, Any]:
    """Shorthand ``reminder <title> at <h>[:mm]`` form (time trailing)."""
    text = (message or "").strip()
    text = re.sub(r"^reminders?\b[:\s]*", "", text, flags=re.I)
    params = _reminder_params(text, user_id)
    return {"action": "create_reminder", "params": params}
