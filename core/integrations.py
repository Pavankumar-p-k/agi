"""core.integrations — info-intent handlers (weather / news / stocks / sports / time).

Rebuilt from the committed contracts:

- tests/integration/test_get_info_routing.py —
      patch.dict("core.integrations._INTENT_MAP", {"weather": mock_fn})
      await get_info("weather", "London") -> handler result, called with
      exactly one positional arg (the query).
      Unknown intent -> string containing "Unknown info type".
- core/main.py execute_action dispatches info intents here.

Default handlers: weather uses the keyless wttr.in service; time is local
clock; news/stocks/sports return honest "not configured" messages until a
provider is wired (they were never implemented in this repo).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Awaitable, Callable, Dict
from urllib.parse import quote

logger = logging.getLogger(__name__)


async def _weather(query: str) -> str:
    """Keyless weather via wttr.in (one-line format)."""
    q = (query or "").strip()
    if not q:
        return "Weather: no location given."
    try:
        import httpx

        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"https://wttr.in/{quote(q)}?format=3")
            response.raise_for_status()
            return response.text.strip()
    except Exception as exc:  # noqa: BLE001 - honest degradation
        logger.warning("[integrations] weather lookup failed: %s", exc)
        return f"Weather lookup failed for {q!r}: {exc}"


async def _news(query: str) -> str:
    return (f"News lookup is not configured yet (no news provider wired); "
            f"query was {query!r}.")


async def _stocks(query: str) -> str:
    return (f"Stocks lookup is not configured yet (no market-data provider "
            f"wired); query was {query!r}.")


async def _sports(query: str) -> str:
    return (f"Sports lookup is not configured yet (no sports provider wired); "
            f"query was {query!r}.")


async def _time(query: str) -> str:
    now = datetime.now().astimezone()
    base = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    q = (query or "").strip()
    return f"Local time: {base}" + (f" (requested: {q})" if q else "")


# Intent -> async handler(query) -> str. Patchable via patch.dict in tests.
_INTENT_MAP: Dict[str, Callable[[str], Awaitable[str]]] = {
    "weather": _weather,
    "news": _news,
    "stocks": _stocks,
    "sports": _sports,
    "time": _time,
}


async def get_info(intent: str, query: str) -> str:
    """Dispatch an info intent to its handler; honest string for unknowns."""
    handler = _INTENT_MAP.get(intent)
    if handler is None:
        return f"Unknown info type: {intent}"
    result = await handler(query)
    return str(result)


__all__ = ["get_info", "_INTENT_MAP"]
