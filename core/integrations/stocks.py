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
"""Stock price - free Yahoo Finance scraping (no API key)."""
import logging
import re

import httpx

logger = logging.getLogger(__name__)

async def get_stock_price(symbol: str) -> str:
    """Get current stock price for a ticker from Yahoo Finance (free)."""
    symbol = symbol.upper().strip()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code == 200:
                data = r.json()
                chart = data.get("chart")
                if not chart:
                    return f"Could not fetch stock price for {symbol}"
                result = chart.get("result")
                if not result:
                    return f"Could not fetch stock price for {symbol}"
                meta = result[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                prev_close = meta.get("previousClose")
                currency = meta.get("currency", "USD")
                name = meta.get("shortName", symbol) or symbol
                if price is not None and prev_close is not None and prev_close != 0:
                    price_f = float(price)
                    prev_f = float(prev_close)
                    change = price_f - prev_f
                    change_pct = (change / prev_f) * 100
                    return (
                        f"{name} ({symbol}): ${price_f} {currency} "
                        f"({'▲' if change >= 0 else '▼'} {change:+.2f} / {change_pct:+.2f}%)"
                    )
    except Exception as e:
        logger.exception("[stocks] Yahoo Finance API: %s", e)

    # Fallback: scrape Yahoo Finance page
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://finance.yahoo.com/quote/{symbol}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            price_match = re.search(r'data-test="qsp-price"[^>]*data-value="([^"]+)"', r.text)
            name_match = re.search(r'"longName":"([^"]+)"', r.text)
            if price_match:
                price = price_match.group(1)
                name = name_match.group(1) if name_match else symbol
                return f"{name} ({symbol}): ${price}"
    except Exception as e:
        logger.exception("[stocks] Yahoo Finance scrape: %s", e)

    # Last resort: web search
    try:
        from tools.search_tool import search_engine
        sr = await search_engine.search(f"{symbol} stock price today")
        if sr.is_err():
            logger.warning("[stocks] search fallback failed: %s", sr._error)
            results = []
        else:
            results = sr.unwrap()
        if results:
            return f"{symbol} stock: {results[0].snippet[:300]}"
        return f"Could not fetch stock price for {symbol}"
    except Exception as e:
        logger.exception("[stocks] search fallback: %s", e)
        return f"Could not fetch stock price for {symbol}"
