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
            resp = requests.get(self.base_url, params=params, timeout=10)
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
                except:
                    pass
        return sorted(results, key=lambda x: x.score, reverse=True)

    def scrape_top(self, results: List[SearchResult], n: int = 3) -> List[str]:
        """Scrape full content from top results."""
        contents = []
        for r in results[:n]:
            try:
                downloaded = trafilatura.fetch_url(r.url)
                if downloaded:
                    content = trafilatura.extract(downloaded)
                    if content:
                        contents.append(f"SOURCE: {r.url}\nCONTENT: {content}")
            except:
                continue
        return contents

    async def multi_hop(self, query: str, max_iterations: int = 3) -> str:
        """
        Search -> read -> "what do I still not know?" -> search gap -> repeat.
        """
        # This would require an LLM to decide the 'next hop'
        # For now, a simple one-hop implementation
        results = self.search(query)
        if not results:
            return "No results found."
        
        scraped = self.scrape_top(results)
        return "\n\n".join(scraped)

# Instances
decision_gate = SearchDecisionGate()
search_engine = SearXNGSearch()
