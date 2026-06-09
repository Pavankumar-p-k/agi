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
"""tools/crawl4ai_tool.py — Advanced web scraping with Crawl4AI.
Replaces trafilatura with JS-rendered, LLM-extractable crawling.

Usage:
    crawler = Crawl4AITool()
    result = await crawler.scrape("https://example.com")
    results = await crawler.scrape_multi(["https://a.com", "https://b.com"])
"""
import asyncio
import threading
from typing import List, Optional
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode


class Crawl4AITool:
    """Wrapper around Crawl4AI's AsyncWebCrawler for JARVIS."""

    def __init__(self):
        self._crawler: Optional[AsyncWebCrawler] = None

    async def _ensure(self):
        if self._crawler is None:
            self._crawler = AsyncWebCrawler()
            await self._crawler.__aenter__()

    async def scrape(
        self,
        url: str,
        js_code: Optional[str] = None,
        wait_for: Optional[str] = None,
        word_count_threshold: int = 50,
        cache_mode: CacheMode = CacheMode.ENABLED,
    ) -> dict:
        """Scrape a single URL with optional JS execution.

        Args:
            url: Target URL
            js_code: JS to execute before extraction (e.g. "document.querySelector('button').click()")
            wait_for: CSS selector to wait for (e.g. ".content-loaded")
            word_count_threshold: Min words per block (filters noise)
            cache_mode: CacheMode.ENABLED or .DISABLED

        Returns:
            dict with keys: url, title, content, markdown, success, error
        """
        await self._ensure()
        config = CrawlerRunConfig(
            word_count_threshold=word_count_threshold,
            cache_mode=cache_mode,
            js_code=js_code,
            css_selector=wait_for,
            exclude_domains={"youtube.com", "facebook.com", "instagram.com"},
        )
        try:
            result = await self._crawler.arun(url=url, config=config)
            return {
                "url": url,
                "title": result.metadata.get("title", "") if result.metadata else "",
                "content": result.extracted_content or "",
                "markdown": result.markdown or "",
                "success": result.success,
                "error": result.error_message if hasattr(result, "error_message") else None,
            }
        except Exception as e:
            return {"url": url, "success": False, "error": str(e)}

    async def scrape_multi(
        self,
        urls: List[str],
        word_count_threshold: int = 50,
    ) -> List[dict]:
        """Scrape multiple URLs in parallel."""
        tasks = [self.scrape(url, word_count_threshold=word_count_threshold) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self):
        if self._crawler:
            await self._crawler.__aexit__(None, None, None)
            self._crawler = None


_crawler_instance: Optional[Crawl4AITool] = None
_crawler_lock = threading.Lock()


def get_crawler() -> Crawl4AITool:
    global _crawler_instance
    if _crawler_instance is None:
        with _crawler_lock:
            if _crawler_instance is None:
                _crawler_instance = Crawl4AITool()
    return _crawler_instance
