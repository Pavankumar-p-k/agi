"""tools/search_fallback.py
Unified web search with automatic fallback chain:
1. SearXNG (port 8888) — best privacy, self-hosted
2. duckduckgo-search (DDGS) — free, no API key
3. Google URL fallback — last resort, opens browser
"""

import logging
import urllib.parse
from typing import List, Dict, Optional

import httpx

logger = logging.getLogger("search_fallback")

SEARXNG_URL = "http://localhost:8888/search"
DDGS_AVAILABLE = False

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        pass


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


def search_ddgs(query: str, max_results: int = 5) -> List[Dict]:
    """Search via duckduckgo-search library. Returns list of {title, content, url} dicts."""
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
        logger.warning(f"DDGS error: {e}")
    return []


def format_results(results: List[Dict], max_len: int = 300) -> str:
    """Format search results into a single string for LLM context."""
    if not results:
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
    return ""
