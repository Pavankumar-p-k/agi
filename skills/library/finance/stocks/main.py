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

import os
import aiohttp
from skills.utils import success_response, error_response

ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")

async def stocks(params: dict) -> dict:
    """Fetch stock price information."""
    ticker = params.get("ticker", params.get("query", params.get("target", ""))).upper().strip()
    if not ticker:
        return success_response({
            "note": "Stock data available",
            "usage": "Provide a ticker symbol (e.g., AAPL, TSLA, GOOGL)",
        })
    
    if ALPHA_VANTAGE_KEY:
        try:
            url = "https://www.alphavantage.co/query"
            payload = {
                "function": "GLOBAL_QUOTE",
                "symbol": ticker,
                "apikey": ALPHA_VANTAGE_KEY,
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=payload, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        quote = data.get("Global Quote", {})
                        if quote:
                            return success_response({
                                "ticker": ticker,
                                "price": quote.get("05. price", "N/A"),
                                "change": quote.get("09. change", "N/A"),
                                "change_percent": quote.get("10. change percent", "N/A"),
                                "high": quote.get("03. high", "N/A"),
                                "low": quote.get("04. low", "N/A"),
                                "volume": quote.get("06. volume", "N/A"),
                                "source": "alphavantage",
                            })
                        return error_response(f"No data for {ticker}")
        except Exception as e:
            return error_response(f"Stock fetch failed: {e}")
    
    from core.integrations.stocks import get_stock_price
    try:
        result = await get_stock_price(ticker)
        return success_response({"result": result, "source": "local_integration"})
    except Exception as e:
        return success_response({
            "ticker": ticker,
            "note": f"Stock data for {ticker}. Set ALPHA_VANTAGE_KEY in .env.local for live data.",
        })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        pass
