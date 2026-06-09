# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""core/integrations/__init__.py - Real-time API connectors."""
import json
import logging

from .news import get_news
from .sports import get_sports_scores
from .stocks import get_stock_price
from .timezone import get_time_info
from .weather import get_weather

logger = logging.getLogger(__name__)

__all__ = [
    "get_weather", "get_news", "get_stock_price", "get_sports_scores", "get_time_info",
    "get_info", "get_integrations_prompt", "execute_api_call", "load_integrations",
]


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


def get_integrations_prompt() -> str:
    return (
        "You have access to live data integrations:\n"
        "- weather: get current weather for any location\n"
        "- news: get latest news on any topic\n"
        "- stocks: get stock prices by symbol\n"
        "- sports: get sports scores by league\n"
        "- time: get time info for any location"
    )


async def execute_api_call(content: str) -> dict:
    try:
        args = json.loads(content) if isinstance(content, str) else content
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid JSON", "exit_code": 1}
    integration = args.get("integration", "")
    if integration == "weather":
        from core.integrations import get_weather
        location = args.get("location", "")
        result = await get_weather(location)
        return {"output": result, "exit_code": 0}
    elif integration == "news":
        from core.integrations import get_news
        topic = args.get("topic", "")
        result = await get_news(topic)
        return {"output": result, "exit_code": 0}
    elif integration == "stocks":
        from core.integrations import get_stock_price
        symbol = args.get("symbol", "")
        result = await get_stock_price(symbol)
        return {"output": result, "exit_code": 0}
    elif integration == "sports":
        from core.integrations import get_sports_scores
        league = args.get("league", "")
        result = await get_sports_scores(league)
        return {"output": result, "exit_code": 0}
    elif integration == "time":
        from core.integrations import get_time_info
        location = args.get("location", "")
        result = await get_time_info(location)
        return {"output": result, "exit_code": 0}
    return {"error": f"Unknown integration: {integration}", "exit_code": 1}


def load_integrations() -> list[dict]:
    return [
        {"name": "weather", "description": "Get weather for a location"},
        {"name": "news", "description": "Get news for a topic"},
        {"name": "stocks", "description": "Get stock price for a symbol"},
        {"name": "sports", "description": "Get sports scores for a league"},
        {"name": "time", "description": "Get time info for a location"},
    ]
