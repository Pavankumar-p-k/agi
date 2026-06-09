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
