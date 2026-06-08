"""routers/dot_routes.py — Real data endpoints for the Electron dot panels."""
from __future__ import annotations

import logging
from fastapi import APIRouter, Query
import httpx
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dot", tags=["dot"])


@router.get("/stocks")
async def dot_stocks(symbol: str = Query("AAPL", description="Stock ticker")):
    """Real-time stock price from Yahoo Finance (free, no key)."""
    symbol = symbol.upper().strip()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code == 200:
                data = r.json()
                result = (data.get("chart") or {}).get("result")
                if result:
                    meta = result[0].get("meta", {})
                    price = meta.get("regularMarketPrice")
                    prev_close = meta.get("previousClose")
                    name = meta.get("shortName", symbol) or symbol
                    currency = meta.get("currency", "USD")
                    if price is not None:
                        price_f = float(price)
                        change = None
                        change_pct = None
                        if prev_close is not None and float(prev_close) != 0:
                            prev_f = float(prev_close)
                            change = round(price_f - prev_f, 2)
                            change_pct = round((change / prev_f) * 100, 2)
                        return {
                            "symbol": symbol,
                            "name": name,
                            "price": f"${price_f}",
                            "change": f"{'+' if change and change >= 0 else ''}{change}" if change is not None else None,
                            "change_pct": f"{'+' if change_pct and change_pct >= 0 else ''}{change_pct}%" if change_pct is not None else None,
                            "currency": currency,
                        }
    except Exception as e:
        logger.exception("[dot_stocks] Yahoo Finance: %s", e)
    return {"symbol": symbol, "name": symbol, "price": "—", "change": None, "change_pct": None, "currency": "USD", "error": "Could not fetch"}


@router.get("/news")
async def dot_news(topic: str = Query("technology", description="News topic")):
    """Latest headlines from BBC RSS (free, no key)."""
    RSS_FEEDS = {
        "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        "sports": "https://feeds.bbci.co.uk/sport/rss.xml",
        "ai": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    }
    feed_url = None
    for key, url in RSS_FEEDS.items():
        if key in topic or topic in key:
            feed_url = url
            break
    if not feed_url:
        feed_url = RSS_FEEDS["technology"]

    articles = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(feed_url)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                items = root.findall(".//item") or root.findall(".//entry")
                for item in items[:10]:
                    title = item.findtext("title", "")
                    if not title:
                        continue
                    pub = item.findtext("pubDate", item.findtext("published", ""))
                    if pub:
                        try:
                            from datetime import datetime
                            dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
                            pub = dt.strftime("%b %d, %Y")
                        except Exception:
                            pass
                    articles.append({
                        "title": title,
                        "source": feed_url.split("/")[2] if "//" in feed_url else "News",
                        "published": pub or "",
                    })
    except Exception as e:
        logger.exception("[dot_news] RSS: %s", e)

    if not articles:
        articles.append({"title": f"No {topic} news available right now", "source": "JARVIS", "published": ""})
    return {"articles": articles}
