"""Built-in tool implementations dispatched by core.tools.execution.

De-poisoned: the auto-reconstructed DynamicStub previously occupying this
module returned a fresh DynamicStub for *any* attribute (``__getattr__``), so
every tool name ``hasattr``-ed as implemented and every dispatch silently
"succeeded".  This module deliberately implements only the two built-ins the
committed contracts use (tests/unit/test_execution_dispatch.py,
tests/unit/test_workflow_email_artifacts.py) and delegates the browser tools
to the real implementations in core/tools/browser_tools.py — no parallel
implementation layer is created.

``patch("core.tools.implementations.do_search_chats", ...)`` keeps working
because the names below are plain module attributes (no ``__getattr__``).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "do_search_chats",
    "async_do_search_chats",
    "do_api_call",
    "async_do_api_call",
    "do_browser_screenshot",
    "async_do_browser_screenshot",
    "do_browser_snapshot",
    "async_do_browser_snapshot",
]


# ── Built-in: chat search ───────────────────────────────────────────────────


def do_search_chats(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Search stored chat messages (sync form used by dispatch fallbacks)."""
    try:
        from core.memory import search_chats  # existing memory layer
        return search_chats(*args, **kwargs)
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("[implementations] search_chats failed: %s", exc)
        return {"results": [], "error": str(exc)}
    return {"results": []}


async def async_do_search_chats(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Async chat search; honours the do_search_chats patch target."""
    func = globals().get("do_search_chats")
    if func is not None:
        outcome = func(*args, **kwargs)
        if hasattr(outcome, "__await__"):
            outcome = await outcome
        return outcome if isinstance(outcome, dict) else {"result": outcome}
    return {"results": []}


# ── Built-in: HTTP API call ─────────────────────────────────────────────────


def do_api_call(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Perform an HTTP request via the existing HTTP client utility."""
    try:
        from core.http_client import request  # existing utility
        return request(*args, **kwargs)
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("[implementations] api_call failed: %s", exc)
        return {"success": False, "error": str(exc)}
    return {"success": False, "error": "no HTTP backend available"}


async def async_do_api_call(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Async API call; honours the do_api_call patch target."""
    func = globals().get("do_api_call")
    if func is not None:
        outcome = func(*args, **kwargs)
        if hasattr(outcome, "__await__"):
            outcome = await outcome
        return outcome if isinstance(outcome, dict) else {"result": outcome}
    return {"success": False, "error": "no HTTP backend available"}


# ── Browser tools: delegate to the real implementations ────────────────────


def _browser(name: str):
    from core.tools import browser_tools  # real implementation module

    return getattr(browser_tools, name)


def do_browser_screenshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Screenshot via the real browser tools (sync callers; event-loop safe)."""
    return asyncio_run(_browser("do_browser_screenshot")(*args, **kwargs))


def do_browser_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Accessibility snapshot via the real browser tools (sync callers)."""
    return asyncio_run(_browser("do_browser_snapshot")(*args, **kwargs))


async def async_do_browser_screenshot(*args: Any, get_result: bool = False, **kwargs: Any) -> Any:
    result = await _browser("do_browser_screenshot")(*args, **kwargs)
    return (result, True) if get_result else result


async def async_do_browser_snapshot(*async_args: Any, get_result: bool = False, **kwargs: Any) -> Any:
    result = await _browser("do_browser_snapshot")(*async_args, **kwargs)
    return (result, True) if get_result else result


# ── Shared event-loop helper ────────────────────────────────────────────────


def asyncio_run(coro: Any) -> Any:
    """Run a coroutine on a fresh loop, tolerating a running one (threads)."""
    import asyncio as _asyncio

    try:
        loop = _asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        import concurrent.futures as _futures

        with _futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_asyncio.run, coro).result()
    return _asyncio.run(coro)
