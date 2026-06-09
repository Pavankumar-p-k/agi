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

from skills.utils import success_response, error_response, fetch_json

async def ip_lookup(params: dict) -> dict:
    ip = params.get("ip")
    if not ip:
        ipinfo = await fetch_json("https://api.ipify.org?format=json")
        if ipinfo and ipinfo.get("ip"):
            ip = ipinfo["ip"]
        else:
            return error_response("Could not determine current IP")
    data = await fetch_json(f"https://ipapi.co/{ip}/json/")
    if data and "error" not in data:
        return success_response({
            "ip": data.get("ip"),
            "city": data.get("city"),
            "region": data.get("region"),
            "country": data.get("country_name"),
            "isp": data.get("org"),
            "location": {"lat": data.get("latitude"), "lon": data.get("longitude")},
            "timezone": data.get("timezone"),
        })
    data2 = await fetch_json(f"http://ip-api.com/json/{ip}")
    if data2 and data2.get("status") == "success":
        return success_response({
            "ip": data2.get("query"),
            "city": data2.get("city"),
            "region": data2.get("regionName"),
            "country": data2.get("country"),
            "isp": data2.get("isp"),
            "location": {"lat": data2.get("lat"), "lon": data2.get("lon")},
            "timezone": data2.get("timezone"),
        })
    return error_response("Could not fetch IP information")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
