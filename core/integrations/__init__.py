"""core/integrations/__init__.py - Real-time API connectors."""
from .weather import get_weather
from .news import get_news
from .stocks import get_stock_price
from .sports import get_sports_scores
from .timezone import get_time_info

__all__ = ["get_weather", "get_news", "get_stock_price", "get_sports_scores", "get_time_info", "get_info"]


_INTENT_MAP = {
    "weather": get_weather,
    "news": get_news,
    "stocks": get_stock_price,
    "sports": get_sports_scores,
    "time": get_time_info,
}


async def get_info(intent: str, target: str = "") -> str:
    """Route an info intent to the right integration handler."""
    handler = _INTENT_MAP.get(intent)
    if not handler:
        return f"Unknown info type: {intent}"
    return await handler(target)
