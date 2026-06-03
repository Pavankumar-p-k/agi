"""Weather - free wttr.in API (no key needed)."""
import logging
import httpx

logger = logging.getLogger(__name__)

async def get_weather(location: str) -> str:
    """Get current weather for a location using wttr.in (free, no API key)."""
    if not location or location == "local":
        location = ""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://wttr.in/{location}?format=%l:+%c+%t,+%h+humidity,+%w+wind",
            )
            if r.status_code == 200 and r.text.strip():
                return f"Weather: {r.text.strip()}"
    except Exception as e:
        logger.exception("[weather] wttr.in: %s", e)

    # Fallback: web search
    try:
        from tools.search_tool import search_engine
        sr = await search_engine.search(f"weather in {location} today")
        if sr.is_err():
            logger.warning("[weather] search fallback failed: %s", sr._error)
            results = []
        else:
            results = sr.unwrap()
        if results:
            return f"Weather in {location}: {results[0].snippet[:300]}"
        return f"Could not get weather for {location}"
    except Exception as e:
        logger.exception("[weather] search fallback: %s", e)
        return f"Could not get weather for {location}"
