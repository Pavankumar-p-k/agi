"""Weather - free wttr.in API (no key needed)."""
import httpx

def get_weather(location: str) -> str:
    """Get current weather for a location using wttr.in (free, no API key)."""
    if not location or location == "local":
        location = ""
    try:
        r = httpx.get(
            f"https://wttr.in/{location}?format=%l:+%c+%t,+%h+humidity,+%w+wind",
            timeout=10,
        )
        if r.status_code == 200 and r.text.strip():
            return f"Weather: {r.text.strip()}"
    except Exception:
        pass

    # Fallback: web search
    try:
        from tools.search_tool import search_engine
        results = search_engine.search(f"weather in {location} today")
        if results:
            return f"Weather in {location}: {results[0].snippet[:300]}"
        return f"Could not get weather for {location}"
    except Exception:
        return f"Could not get weather for {location}"
