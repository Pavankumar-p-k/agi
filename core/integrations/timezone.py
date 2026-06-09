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
"""Timezone / world clock - free WorldTimeAPI (no key)."""
import logging

import httpx

logger = logging.getLogger(__name__)
from datetime import datetime

WORLD_TIME_API = "https://worldtimeapi.org/api"

async def get_time_info(location: str = "") -> str:
    """Get current time for a location using free WorldTimeAPI."""
    if not location:
        now = datetime.now()
        return f"Local time: {now.strftime('%Y-%m-%d %H:%M:%S')}"

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{WORLD_TIME_API}/timezone")
            if r.status_code == 200:
                timezones = r.json()
                loc_lower = location.lower()
                matches = [tz for tz in timezones if loc_lower in tz.lower()]
                if matches:
                    tz_name = matches[0]
                    r2 = await client.get(f"{WORLD_TIME_API}/timezone/{tz_name}")
                    if r2.status_code == 200:
                        data = r2.json()
                        return (
                            f"Time in {data.get('timezone', location)}: "
                            f"{data.get('datetime','')[:19]} "
                            f"(UTC{data.get('utc_offset','')})"
                        )
        except Exception as e:
            logger.exception("[timezone] timezone lookup: %s", e)

    return f"Could not determine time for '{location}'. Local time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
