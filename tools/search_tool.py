import os
import requests
import trafilatura
from typing import List, Dict, Optional
from datetime import datetime

class SearchResult:
    def __init__(self, title: str, url: str, snippet: str, content: str = "", score: float = 1.0, published_date: str = ""):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.content = content
        self.score = score
        self.published_date = published_date

class SearchDecisionGate:
    """
    Decides if a search is needed.
    """
    def should_search(self, query: str, confidence: float) -> bool:
        search_keywords = ["latest", "current", "today", "2026", "recent", "now", "price", "score", "news", "who is", "weather"]
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in search_keywords):
            return True
        
        if confidence < 0.75:
            return True
        
        # Heuristic for specific entities
        if any(char.isupper() for char in query if char.isalpha()) and len(query.split()) > 2:
            return True
            
        return False

class SearXNGSearch:
    """
    SearXNG integration for JARVIS.
    """
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.getenv("SEARXNG_URL", "http://localhost:8888")

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
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
            
            return self._score_results(results)
        except Exception as e:
            print(f"[Search] SearXNG error: {e}")
            return []

    def _score_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Apply freshness scoring."""
        now = datetime.now()
        for r in results:
            if r.published_date:
                try:
                    # Very simple date parsing
                    pub_date = datetime.fromisoformat(r.published_date.replace("Z", "+00:00"))
                    age_days = (now - pub_date).days
                    if age_days > 180: # Older than 6 months
                        r.score *= 0.8
                    if age_days > 365: # Older than a year
                        r.score *= 0.5
                except Exception:
                    pass
        return sorted(results, key=lambda x: x.score, reverse=True)

    async def scrape_top(self, results: List[SearchResult], n: int = 3) -> List[str]:
        """Scrape full content from top results using Crawl4AI with trafilatura fallback."""
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
            print(f"[Search] Crawl4AI scrape failed, falling back to trafilatura: {e}")

        # Fallback to trafilatura for any results crawl4ai missed
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
                except Exception:
                    continue
        return contents

    async def multi_hop(self, query: str, max_iterations: int = 3) -> str:
        """
        Search -> read -> "what do I still not know?" -> search gap -> repeat.
        """
        all_content = []
        current_query = query

        for hop in range(max_iterations):
            results = self.search(current_query)
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
                gap_query = self._refine_gap(gap_prompt)
                if gap_query and gap_query != current_query:
                    current_query = gap_query
                else:
                    break

        return "\n\n".join(all_content)

    def _refine_gap(self, prompt: str) -> str:
        """Generate follow-up search query for missing info."""
        try:
            req = urllib.request.Request(
                'http://localhost:11434/api/generate',
                data=json.dumps({"model": "mistral:7b", "prompt": prompt, "stream": False}).encode(),
                headers={'Content-Type': 'application/json'}
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
            return resp.get("response", "").strip().strip('"')
        except Exception:
            return ""

# Instances
decision_gate = SearchDecisionGate()
search_engine = SearXNGSearch()
