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

import asyncio
import os
from skills.utils import success_response, error_response

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

async def news(params: dict) -> dict:
    """Fetch latest news. Uses NewsAPI if key available, falls back to web search."""
    category = params.get("category", "general")
    query = params.get("query", params.get("target", ""))
    country = params.get("country", "us")
    max_results = params.get("max_results", 5)
    
    if NEWS_API_KEY:
        import aiohttp
        url = "https://newsapi.org/v2/top-headlines"
        payload = {
            "country": country,
            "pageSize": max_results,
            "apiKey": NEWS_API_KEY,
        }
        if category and category != "general":
            payload["category"] = category
        if query:
            payload["q"] = query
            url = "https://newsapi.org/v2/everything"
            payload = {"q": query, "pageSize": max_results, "apiKey": NEWS_API_KEY}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=payload, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        articles = data.get("articles", [])
                        result = []
                        for a in articles[:max_results]:
                            result.append({
                                "title": a.get("title", ""),
                                "source": a.get("source", {}).get("name", ""),
                                "url": a.get("url", ""),
                                "published": a.get("publishedAt", "")[:10],
                            })
                        return success_response({"articles": result, "count": len(result), "source": "newsapi"})
                    return error_response(f"NewsAPI error: {resp.status}")
        except Exception as e:
            return error_response(f"NewsAPI failed: {e}")
    
    from tools.search_tool import search_engine
    search_query = query or f"latest {category} news"
    result = await search_engine.search(search_query, max_results)
    if result.is_ok():
        articles = [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in result.unwrap()]
        return success_response({"articles": articles, "count": len(articles), "source": "web_search"})
    return error_response("No news available")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        pass
