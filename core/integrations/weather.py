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
