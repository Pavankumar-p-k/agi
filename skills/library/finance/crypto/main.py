from skills.utils import success_response, error_response, fetch_json

COIN_IDS = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "cardano": "cardano", "ada": "cardano",
    "ripple": "ripple", "xrp": "ripple",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "litecoin": "litecoin", "ltc": "litecoin",
    "polkadot": "polkadot", "dot": "polkadot",
    "polygon": "matic-network", "matic": "matic-network"
}
COIN_NAMES = {
    "bitcoin": "Bitcoin", "ethereum": "Ethereum", "solana": "Solana",
    "cardano": "Cardano", "ripple": "Ripple", "dogecoin": "Dogecoin",
    "litecoin": "Litecoin", "polkadot": "Polkadot", "matic-network": "Polygon"
}

async def crypto(params: dict) -> dict:
    coin = params.get("coin", "bitcoin")
    currency = params.get("currency", "usd")
    action = params.get("action", "price")
    coin_id = COIN_IDS.get(coin.lower())
    if not coin_id:
        return error_response(f"Unsupported coin: {coin}")
    if action == "price":
        url = f"https://api.coingecko.com/api/v3/simple/price"
        data = await fetch_json(url, {"ids": coin_id, "vs_currencies": currency, "include_24hr_change": "true", "include_market_cap": "true"})
        if not data or coin_id not in data:
            return error_response("Could not fetch price data")
        info = data[coin_id]
        price_key = currency
        change_key = f"{currency}_24h_change"
        cap_key = f"{currency}_market_cap"
        return success_response({
            "coin": COIN_NAMES.get(coin_id, coin_id),
            "coin_id": coin_id,
            "currency": currency.upper(),
            "price": info.get(price_key),
            "change_24h": info.get(change_key),
            "market_cap": info.get(cap_key)
        })
    elif action == "info":
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        data = await fetch_json(url, {"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "false"})
        if not data:
            return error_response("Could not fetch coin info")
        return success_response({
            "coin": data.get("name", COIN_NAMES.get(coin_id, coin_id)),
            "symbol": data.get("symbol", "").upper(),
            "description": (data.get("description") or {}).get("en", ""),
            "homepage": (data.get("links") or {}).get("homepage", [""])[0],
            "genesis_date": data.get("genesis_date"),
            "market_data": {
                "current_price": data.get("market_data", {}).get("current_price", {}).get(currency),
                "market_cap": data.get("market_data", {}).get("market_cap", {}).get(currency),
                "total_volume": data.get("market_data", {}).get("total_volume", {}).get(currency),
                "high_24h": data.get("market_data", {}).get("high_24h", {}).get(currency),
                "low_24h": data.get("market_data", {}).get("low_24h", {}).get(currency),
                "circulating_supply": data.get("market_data", {}).get("circulating_supply"),
                "total_supply": data.get("market_data", {}).get("total_supply"),
                "ath": data.get("market_data", {}).get("ath", {}).get(currency),
            }
        })
    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
