"""Concrete tool implementations resolved by core.tools.execution dispatch.

The dispatcher resolves ``do_<tool>`` attributes on this module at call
time (never at import time), so tests can patch
``core.tools.implementations.<fn>`` directly.

Deliberately NO ``async_do_<tool>`` variants: the dispatcher prefers them
over ``do_<tool>``, which would make direct patches of the ``do_`` names
ineffective.  Every entry point here is already async.
"""
from __future__ import annotations

from typing import Any


async def do_search_chats(
    query: str = "",
    limit: int = 10,
    owner: str | None = None,
    user_id: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Search stored chat/memory history via the shared memory facade."""
    try:
        from memory import memory_facade

        results = memory_facade.memory.search_all(
            str(query or ""),
            limit=max(int(limit or 10), 1),
            user_id=str(user_id or owner or "default"),
        )
        results = list(results or [])
        return {"results": results, "query": query, "count": len(results)}
    except Exception as exc:  # noqa: BLE001 — honest error, never fake results
        return {"results": [], "query": query, "count": 0, "error": str(exc)}


async def do_api_call(
    url: str | None = None,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: Any = None,
    input: str | None = None,
    owner: str | None = None,
    timeout: float = 15.0,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Perform a single HTTP request (stdlib-safe via ``requests``).

    ``input`` accepts the bare ``"GET /path"`` shape for callers that pass
    command-style content; without a host it fails honestly.
    """
    if not url and isinstance(input, str) and input.strip():
        parts = input.split()
        if len(parts) >= 2 and parts[0].upper() in (
            "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD",
        ):
            method = parts[0].upper()
            url = parts[1]
    if not url:
        return {"error": "url is required", "exit_code": 1}
    try:
        import requests

        kwargs: dict[str, Any] = {"timeout": timeout}
        if headers:
            kwargs["headers"] = dict(headers)
        data = None
        if body is not None:
            if isinstance(body, (dict, list)):
                kwargs["json"] = body
            else:
                data = body
        resp = requests.request(str(method or "GET").upper(), url,
                                data=data, **kwargs)
        text = resp.text or ""
        if len(text) > 100000:
            text = text[:100000] + "...[truncated]"
        return {
            "status": resp.status_code,
            "reason": resp.reason,
            "url": str(resp.url),
            "body": text,
        }
    except Exception as exc:  # noqa: BLE001 — honest error, never fake success
        return {"error": f"{type(exc).__name__}: {exc}", "exit_code": 1}


def _live_browser_session(session_id: str) -> bool:
    """True when a browser session for *session_id* is already live."""
    try:
        from core.browser_manager import BrowserManager

        session = BrowserManager.instance().get_session(session_id)
        return session is not None and bool(session.alive)
    except Exception:  # noqa: BLE001 — no manager means no session
        return False


def _no_session_error(session_id: str) -> dict[str, Any]:
    return {
        "status": "error",
        "error": (
            f"no live browser session '{session_id}' — establish a browser "
            "session before capturing"
        ),
        "error_type": "BrowserUnavailable",
    }


async def do_browser_screenshot(session_id: str = "default",
                                **kwargs: Any) -> dict[str, Any]:
    """Screenshot the live session's page; fail fast without one.

    This dispatch layer never spawns a browser implicitly — callers
    establish a session first (browser flows), and a request without a
    live session fails honestly instead of blocking on a cold launch.
    """
    if not _live_browser_session(session_id):
        return _no_session_error(session_id)
    from core.tools.browser_tools import do_browser_screenshot as _impl

    return await _impl(session_id=session_id, **kwargs)


async def do_browser_snapshot(session_id: str = "default",
                              **kwargs: Any) -> dict[str, Any]:
    """Snapshot the live session's page; fail fast without one."""
    if not _live_browser_session(session_id):
        return _no_session_error(session_id)
    from core.tools.browser_tools import do_browser_snapshot as _impl

    return await _impl(session_id=session_id, **kwargs)
