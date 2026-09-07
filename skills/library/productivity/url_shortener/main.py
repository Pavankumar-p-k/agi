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

import logging
from skills.utils import success_response, error_response, fetch_json
logger = logging.getLogger(__name__)

async def url_shortener(params: dict) -> dict:
    action = params.get("action", "shorten")
    url = params.get("url", "").strip()
    if not url:
        return error_response("url is required")
    if action == "shorten":
        try:
            data = await fetch_json(
                "https://is.gd/create.php",
                params={"format": "json", "url": url},
            )
            if data and "shorturl" in data:
                return success_response({"original": url, "short": data["shorturl"], "service": "is.gd"})
        except Exception as e:
            logger.warning("[skills.library.productivity.url_shortener.main] shorten_url failed: %s", e)
        try:
            async with __import__("httpx").AsyncClient(timeout=10) as client:
                r = await client.get("https://tinyurl.com/api-create.php", params={"url": url})
                short = r.text.strip()
                if short.startswith("http"):
                    return success_response({"original": url, "short": short, "service": "tinyurl"})
        except Exception as e:
            logger.warning("[skills.url_shortener] shorten_url failed: %s", e)
        return error_response("Failed to shorten URL with available services")
    elif action == "expand":
        try:
            async with __import__("httpx").AsyncClient(timeout=10, follow_redirects=False) as client:
                r = await client.get(url)
                return success_response({"short": url, "original": r.headers.get("Location", url)})
        except Exception as e:
            return error_response(f"Failed to expand URL: {e}")
    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest

    async def on_load(self):
        pass
