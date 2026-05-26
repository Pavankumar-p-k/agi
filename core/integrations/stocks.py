"""Stock price - free Yahoo Finance scraping (no API key)."""
import httpx
import re

def get_stock_price(symbol: str) -> str:
    """Get current stock price for a ticker from Yahoo Finance (free)."""
    symbol = symbol.upper().strip()
    
    try:
        r = httpx.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice", "N/A")
            prev_close = meta.get("previousClose", "N/A")
            currency = meta.get("currency", "USD")
            name = meta.get("shortName", symbol) or symbol
            if price != "N/A" and prev_close != "N/A":
                change = float(price) - float(prev_close) if prev_close != "N/A" else 0
                change_pct = (change / float(prev_close)) * 100 if prev_close != "N/A" and float(prev_close) != 0 else 0
                return (
                    f"{name} ({symbol}): ${price} {currency} "
                    f"({'▲' if change >= 0 else '▼'} {change:+.2f} / {change_pct:+.2f}%)"
                )
    except Exception:
        pass
    
    # Fallback: scrape Yahoo Finance page
    try:
        r = httpx.get(
            f"https://finance.yahoo.com/quote/{symbol}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        price_match = re.search(r'data-test="qsp-price"[^>]*data-value="([^"]+)"', r.text)
        name_match = re.search(r'"longName":"([^"]+)"', r.text)
        if price_match:
            price = price_match.group(1)
            name = name_match.group(1) if name_match else symbol
            return f"{name} ({symbol}): ${price}"
    except Exception:
        pass
    
    # Last resort: web search
    try:
        from tools.search_tool import search_engine
        results = search_engine.search(f"{symbol} stock price today")
        if results:
            return f"{symbol} stock: {results[0].snippet[:300]}"
        return f"Could not fetch stock price for {symbol}"
    except Exception:
        return f"Could not fetch stock price for {symbol}"
