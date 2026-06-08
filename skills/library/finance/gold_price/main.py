from skills.utils import success_response, error_response, fetch_json, format_currency

ESTIMATED_PRICES_PER_GRAM = {
    "usd": 75.0, "inr": 6200.0, "eur": 69.0, "gbp": 59.0
}
CURRENCY_SYMBOLS = {"usd": "$", "inr": "\u20b9", "eur": "\u20ac", "gbp": "\u00a3"}

async def gold_price(params: dict) -> dict:
    currency = (params.get("currency", "inr")).lower()
    weight = float(params.get("weight", 10))
    action = params.get("action", "price")
    if currency not in ("inr", "usd", "eur", "gbp"):
        return error_response(f"Unsupported currency: {currency}")
    price_per_gram = None
    data_source = "api"
    url = "https://api.metals.live/v1/spot/gold"
    api_data = await fetch_json(url)
    if api_data:
        for entry in api_data if isinstance(api_data, list) else []:
            if isinstance(entry, dict) and entry.get("currency", "").lower() == currency:
                price_per_gram = entry.get("price")
                break
    if not price_per_gram:
        price_per_gram = ESTIMATED_PRICES_PER_GRAM.get(currency, 6200.0)
        data_source = "estimated"
    if action == "price":
        total_price = price_per_gram * weight
        return success_response({
            "price_per_gram": price_per_gram,
            "weight_grams": weight,
            "total_price": total_price,
            "currency": currency.upper(),
            "formatted": f"{CURRENCY_SYMBOLS.get(currency, '$')}{total_price:,.2f} for {weight}g",
            "source": data_source,
            "disclaimer": "Estimated price - may not reflect current market rates" if data_source == "estimated" else ""
        })
    elif action == "historical":
        return success_response({
            "currency": currency.upper(),
            "current_price_per_gram": price_per_gram,
            "source": data_source,
            "note": "Historical data available at https://www.metals.live/"
        })
    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
