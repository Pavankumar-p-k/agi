import httpx
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

async def fetch_json(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Optional[dict]:
    """Helper to fetch JSON from an API."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error(f"API request failed to {url}: {e}")
        return None

def format_currency(amount: float, currency: str = "INR") -> str:
    """Helper to format currency amounts."""
    if currency == "INR":
        return f"₹{amount:,.2f}"
    return f"${amount:,.2f}"

def success_response(data: Any, message: str = "Success") -> dict:
    return {"status": "success", "message": message, "data": data}

def error_response(message: str) -> dict:
    return {"status": "error", "message": message}
