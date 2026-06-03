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
