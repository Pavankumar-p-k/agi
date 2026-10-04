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
        from memory.memory_facade import memory

        results = memory.search_all(
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


async def do_browser_screenshot(**kwargs: Any) -> dict[str, Any]:
    """Delegate to the real browser backend (core.tools.browser_tools)."""
    from core.tools.browser_tools import do_browser_screenshot as _impl

    return await _impl(**kwargs)


async def do_browser_snapshot(**kwargs: Any) -> dict[str, Any]:
    """Delegate to the real browser backend (core.tools.browser_tools)."""
    from core.tools.browser_tools import do_browser_snapshot as _impl

    return await _impl(**kwargs)
