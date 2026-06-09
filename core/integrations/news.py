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
"""News - free RSS feeds + web search fallback."""
import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)
import xml.etree.ElementTree as ET

RSS_FEEDS = {
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "sports": "https://feeds.bbci.co.uk/sport/rss.xml",
    "ai": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
}

async def get_news(topic: str = "latest", max_results: int = 5) -> str:
    """Get latest news headlines for a topic from free RSS."""
    topic = topic.lower().strip()

    feed_url = None
    for key, url in RSS_FEEDS.items():
        if key in topic or topic in key:
            feed_url = url
            break
    if not feed_url:
        feed_url = RSS_FEEDS["technology"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(feed_url)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                items = root.findall(".//item") or root.findall(".//entry")
                if items:
                    lines = [f"Latest {topic} news:"]
                    for item in items[:max_results]:
                        title = item.findtext("title", "")
                        if title:
                            lines.append(f"- {title}")
                    return "\n".join(lines)
    except (httpx.HTTPError, ET.ParseError) as e:
        logger.exception("[news] RSS feed: %s", e)

    # Fallback: search
    try:
        from tools.search_tool import search_engine
        year = datetime.now().year
        sr = await search_engine.search(f"latest {topic} news {year}")
        if sr.is_err():
            logger.warning("[news] search fallback failed: %s", sr._error)
            results = []
        else:
            results = sr.unwrap()
        if results:
            lines = [f"Latest {topic} news:"]
            for r in results[:max_results]:
                lines.append(f"- {r.title}: {r.snippet[:200]}")
            return "\n".join(lines)
        return f"No news found for {topic}"
    except Exception as e:
        logger.exception("[news] search fallback: %s", e)
        return f"No news found for {topic}"
