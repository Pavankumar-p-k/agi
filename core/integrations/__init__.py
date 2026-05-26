"""core/integrations/__init__.py - Real-time API connectors."""
from .weather import get_weather
from .news import get_news
from .stocks import get_stock_price
from .sports import get_sports_scores
from .timezone import get_time_info

__all__ = ["get_weather", "get_news", "get_stock_price", "get_sports_scores", "get_time_info"]
