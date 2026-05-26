"""News - free RSS feeds + web search fallback."""
import httpx
import xml.etree.ElementTree as ET

RSS_FEEDS = {
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "sports": "https://feeds.bbci.co.uk/sport/rss.xml",
    "ai": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
}

def get_news(topic: str = "latest", max_results: int = 5) -> str:
    """Get latest news headlines for a topic from free RSS."""
    topic = topic.lower().strip()
    
    # Try RSS feeds
    feed_url = None
    for key, url in RSS_FEEDS.items():
        if key in topic or topic in key:
            feed_url = url
            break
    if not feed_url:
        feed_url = RSS_FEEDS.get("technology", list(RSS_FEEDS.values())[0])
    
    try:
        r = httpx.get(feed_url, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            items = root.findall(".//item") or root.findall(".//entry")
            if items:
                lines = [f"Latest {topic} news:"]
                for item in items[:max_results]:
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    if title:
                        lines.append(f"- {title}")
                return "\n".join(lines)
    except Exception:
        pass
    
    # Fallback: search
    try:
        from tools.search_tool import search_engine
        results = search_engine.search(f"latest {topic} news 2026")
        if results:
            lines = [f"Latest {topic} news:"]
            for r in results[:max_results]:
                lines.append(f"- {r.title}: {r.snippet[:200]}")
            return "\n".join(lines)
        return f"No news found for {topic}"
    except Exception:
        return f"No news found for {topic}"
