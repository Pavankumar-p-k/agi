import os
import aiohttp
from skills.utils import success_response, error_response

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

async def weather(params: dict) -> dict:
    """Fetch current weather for a location."""
    location = params.get("location", params.get("query", params.get("target", "London")))
    
    if OPENWEATHER_API_KEY:
        try:
            url = "https://api.openweathermap.org/data/2.5/weather"
            payload = {"q": location, "appid": OPENWEATHER_API_KEY, "units": "metric"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=payload, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        desc = data["weather"][0]["description"].capitalize()
                        return success_response({
                            "location": data.get("name", location),
                            "country": data.get("sys", {}).get("country", ""),
                            "temperature": f'{data["main"]["temp"]}C',
                            "feels_like": f'{data["main"]["feels_like"]}C',
                            "humidity": f'{data["main"]["humidity"]}%',
                            "description": desc,
                            "wind_speed": f'{data["wind"]["speed"]} m/s',
                            "source": "openweathermap",
                        })
                    return error_response(f"Weather API error: {resp.status}")
        except Exception as e:
            return error_response(f"Weather fetch failed: {e}")
    
    from core.integrations.weather import get_weather
    try:
        result = await get_weather(location)
        return success_response({"result": result, "source": "local_integration"})
    except Exception as e:
        return success_response({
            "note": f"Weather for {location}",
            "detail": "API key not configured. Set OPENWEATHER_API_KEY in .env.local",
        })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        pass
