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
import json
import os
import logging
import trafilatura
from typing import List, Dict, Optional
from datetime import datetime

import httpx
import requests
import asyncio

from core.result import Ok, Err, Result
from core.errors import ProviderError

logger = logging.getLogger(__name__)

class SearchResult:
    def __init__(self, title: str, url: str, snippet: str, content: str = "", score: float = 1.0, published_date: str = ""):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.content = content
        self.score = score
        self.published_date = published_date

class SearchDecisionGate:
    def should_search(self, query: str, confidence: float) -> bool:
        search_keywords = ["latest", "current", "today", "2026", "recent", "now", "price", "score", "news", "who is", "weather"]
        query_lower = query.lower()
        if any(kw in query_lower for kw in search_keywords):
            return True
        if confidence < 0.75:
            return True
        if any(char.isupper() for char in query if char.isalpha()) and len(query.split()) > 2:
            return True
        return False

class DuckDuckGoFallback:
    async def search(self, query: str, max_results: int = 10) -> Result[List[SearchResult], ProviderError]:
        try:
            url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for i, result_div in enumerate(soup.select('.result')):
                if len(results) >= max_results:
                    break
                title_el = result_div.select_one('.result__title a')
                snippet_el = result_div.select_one('.result__snippet')
                if title_el and snippet_el:
                    title = title_el.get_text(strip=True)
                    href = title_el.get('href', '')
                    snippet = snippet_el.get_text(strip=True)
                    results.append(SearchResult(title=title, url=href, snippet=snippet))
            if not results:
                for i, a in enumerate(soup.select('a[href^="http"]')):
                    if len(results) >= max_results:
                        break
                    text = a.get_text(strip=True)
                    if text and len(text) > 10:
                        results.append(SearchResult(title=text, url=a['href'], snippet=""))
            return Ok(results)
        except ImportError:
            logger.warning("[Search] BeautifulSoup not installed for DuckDuckGo fallback")
            return Err(ProviderError("BeautifulSoup not installed"))
        except Exception as e:
            logger.warning("[Search] DuckDuckGo fallback failed: %s", e)
            return Err(ProviderError(f"DuckDuckGo fallback failed: {e}"))

class SearXNGSearch:
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.getenv("SEARXNG_URL", "http://localhost:8888")
        self._http = httpx.AsyncClient(timeout=10)
        self._fallback = DuckDuckGoFallback()

    def search_sync(self, query: str, max_results: int = 10) -> Result[List[SearchResult], ProviderError]:
        try:
            params = {
                "q": query,
                "format": "json",
                "engines": "google,bing,duckduckgo",
            }
            resp = requests.get(self.base_url.rstrip('/') + "/search", params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            results = []
            for r in data.get("results", [])[:max_results]:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                    published_date=r.get("publishedDate", "")
                ))
            return Ok(self._score_results(results))
        except Exception as e:
            logger.warning("[Search] SearXNG search error: %s", e)
            logger.info("[Search] Falling back to DuckDuckGo for: %s", query)
            return asyncio.run(self._fallback.search(query, max_results))

    async def search(self, query: str, max_results: int = 10) -> Result[List[SearchResult], ProviderError]:
        try:
            params = {
                "q": query,
                "format": "json",
                "engines": "google,bing,duckduckgo",
            }
            resp = await self._http.get(self.base_url.rstrip('/') + "/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            results = []
            for r in data.get("results", [])[:max_results]:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                    published_date=r.get("publishedDate", "")
                ))
            return Ok(self._score_results(results))
        except Exception as e:
            logger.warning("[Search] SearXNG search error: %s", e)
            logger.info("[Search] Falling back to DuckDuckGo for: %s", query)
            return await self._fallback.search(query, max_results)

    def _score_results(self, results: List[SearchResult]) -> List[SearchResult]:
        now = datetime.now()
        for r in results:
            if r.published_date:
                try:
                    pub_date = datetime.fromisoformat(r.published_date.replace("Z", "+00:00"))
                    age_days = (now - pub_date).days
                    if age_days > 180:
                        r.score *= 0.8
                    if age_days > 365:
                        r.score *= 0.5
                except Exception as e:
                    logger.warning("[tools.search_tool] perform_search failed: %s", e)
        return sorted(results, key=lambda x: x.score, reverse=True)

    async def scrape_top(self, results: List[SearchResult], n: int = 3) -> List[str]:
        contents = []
        try:
            from tools.crawl4ai_tool import get_crawler
            crawler = get_crawler()
            urls = [r.url for r in results[:n]]
            scraped = await crawler.scrape_multi(urls)
            for s in scraped:
                if s.get("success") and s.get("content"):
                    contents.append(f"SOURCE: {s['url']}\nTITLE: {s.get('title', '')}\nCONTENT: {s['content'][:3000]}")
                elif s.get("success") and s.get("markdown"):
                    contents.append(f"SOURCE: {s['url']}\nCONTENT: {s['markdown'][:3000]}")
        except Exception as e:
            logger.warning("Crawl4AI scrape failed, falling back: %s", e, exc_info=True)

        if len(contents) < n:
            for r in results[:n]:
                if any(r.url in c for c in contents):
                    continue
                try:
                    downloaded = trafilatura.fetch_url(r.url)
                    if downloaded:
                        content = trafilatura.extract(downloaded)
                        if content:
                            contents.append(f"SOURCE: {r.url}\nCONTENT: {content}")
                except Exception as exc:
                    logger.warning("[tools.search_tool] scrape trafilatura failed: %s", exc)
                    continue
        return contents

    async def multi_hop(self, query: str, max_iterations: int = 3) -> str:
        all_content = []
        current_query = query
        for hop in range(max_iterations):
            search_result = await self.search(current_query)
            if hasattr(search_result, 'is_err') and search_result.is_err():
                break
            results = search_result.unwrap() if hasattr(search_result, 'unwrap') else search_result
            if not results:
                break
            scraped = await self.scrape_top(results)
            all_content.extend(scraped)
            if hop < max_iterations - 1:
                gap_prompt = (
                    f"Based on what I found: {' '.join(scraped[:2])} "
                    f"What important aspect of '{query}' is still missing? "
                    f"Answer with a search query only."
                )
                gap_query = await self._refine_gap(gap_prompt, current_query)
                if gap_query and gap_query != current_query:
                    current_query = gap_query
                else:
                    break
        return "\n\n".join(all_content)

    async def _refine_gap(self, prompt: str, query: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    'http://localhost:11434/api/generate',
                    json={"model": "mistral:7b", "prompt": prompt, "stream": False},
                )
                data = resp.json()
                return data.get("response", "").strip().strip('"')
        except Exception:
            logger.warning("[SEARCH] _refine_gap LLM call failed, returning original query")
            return query

decision_gate = SearchDecisionGate()
search_engine = SearXNGSearch()
