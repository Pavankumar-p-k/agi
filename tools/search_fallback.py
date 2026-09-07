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
"""tools/search_fallback.py
Unified web search with automatic fallback chain:
1. SearXNG (port 8888) — best privacy, self-hosted
2. duckduckgo-search (DDGS) — free, no API key (with retry+backoff)
3. Page content extraction for top results via httpx
"""

import logging
import urllib.parse
import time
import re
from typing import List, Dict, Optional

import httpx

logger = logging.getLogger("search_fallback")

SEARXNG_URL = "http://localhost:8888/search"
DDGS_AVAILABLE = False
MAX_RETRIES = 3
BACKOFF_BASE = 2.0

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        pass


def _extract_page_content(url: str, max_chars: int = 2000) -> str:
    """Fetch a URL and extract meaningful text content."""
    try:
        resp = httpx.get(
            url,
            timeout=15,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            },
        )
        if resp.status_code != 200:
            logger.warning("[SEARCH] _extract_page_content status %s for %s", resp.status_code, url)
            return ""
        text = resp.text

        # Strip script/style tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Strip HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)

        # Decode HTML entities
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#39;', "'")

        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text[:max_chars]
    except Exception as e:
        logger.debug(f"Page content extraction failed for {url}: {e}")
        logger.warning("[SEARCH] _extract_page_content exception for %s: %s", url, e)
        return ""


def search_searxng(query: str, max_results: int = 5) -> List[Dict]:
    """Search via SearXNG. Returns list of {title, content, url} dicts."""
    try:
        q = urllib.parse.quote(query)
        r = httpx.get(
            f"{SEARXNG_URL}?q={q}&format=json&engines=google,bing,duckduckgo",
            timeout=15,
        )
        data = r.json()
        results = []
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "url": item.get("url", ""),
            })
        if results:
            logger.debug(f"SearXNG returned {len(results)} results for: {query}")
            return results
        logger.info(f"SearXNG returned 0 results for: {query}")
    except httpx.ConnectError:
        logger.info(f"SearXNG not reachable (port 8888)")
    except Exception as e:
        logger.warning(f"SearXNG error: {e}")
    return []


def search_ddgs(query: str, max_results: int = 5, attempt: int = 1) -> List[Dict]:
    """Search via duckduckgo-search with exponential backoff retry."""
    if not DDGS_AVAILABLE:
        return []
    try:
        results = []
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                if i >= max_results:
                    break
                results.append({
                    "title": r.get("title", ""),
                    "content": r.get("body", ""),
                    "url": r.get("href", ""),
                })
        if results:
            logger.debug(f"DDGS returned {len(results)} results for: {query}")
            return results
        logger.info(f"DDGS returned 0 results for: {query}")
    except Exception as e:
        err_str = str(e).lower()
        if attempt < MAX_RETRIES and any(w in err_str for w in ("ratelimit", "rate limit", "429", "timeout", "time out")):
            delay = BACKOFF_BASE ** attempt
            logger.warning(f"DDGS rate-limited (attempt {attempt}/{MAX_RETRIES}), retrying in {delay:.1f}s...")
            time.sleep(delay)
            return search_ddgs(query, max_results, attempt + 1)
        logger.warning(f"DDGS error: {e}")
    return []


def search_with_content(query: str, max_results: int = 5) -> List[Dict]:
    """Search and enrich results with full page content extraction."""
    results = search(query, max_results)
    if not results:
        return []
    enriched = []
    for r in results:
        url = r.get("url", "")
        if url and not r.get("content", ""):
            page_text = _extract_page_content(url)
            if page_text:
                r["content"] = page_text
        enriched.append(r)
    return enriched


def format_results(results: List[Dict], max_len: int = 300) -> str:
    """Format search results into a single string for LLM context."""
    if not results:
        logger.warning("[SEARCH] format_results called with no results")
        return ""
    parts = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        content = r.get("content", "").strip()[:max_len]
        url = r.get("url", "").strip()
        if title or content:
            line = f"{i}. {title}" if title else ""
            if content:
                line += f": {content}" if line else content
            if url:
                line += f" ({url})"
            parts.append(line)
    return "\n".join(parts)


def search(query: str, max_results: int = 5) -> List[Dict]:
    """Unified search: tries SearXNG first, then DDGS fallback."""
    results = search_searxng(query, max_results)
    if results:
        return results
    results = search_ddgs(query, max_results)
    if results:
        return results
    return []


def search_formatted(query: str, max_results: int = 5) -> str:
    """Search and return formatted results string, or empty if nothing found."""
    results = search(query, max_results)
    if results:
        return format_results(results)
    logger.warning("[SEARCH] search_formatted: no results for query")
    return ""
