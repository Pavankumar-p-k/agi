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

from skills.utils import fetch_json, success_response, error_response
import urllib.parse

async def wikipedia(params: dict) -> dict:
    """Fetch a summary from Wikipedia."""
    query = params.get("query")
    if not query:
        return error_response("No query provided")
    
    encoded_query = urllib.parse.quote(query)
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_query}"
    
    data = await fetch_json(url)
    if data and "extract" in data:
        return success_response({
            "title": data.get("title"),
            "summary": data.get("extract"),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page")
        })
    
    return error_response(f"Could not find Wikipedia entry for '{query}'")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Tools are registered in skill_manager automatically via entry_point
        pass
