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
"""Sports scores - free ESPN API (no key needed)."""
import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

ESPN_LEAGUES = {
    "nfl": ("football", "nfl"), "nba": ("basketball", "nba"),
    "mlb": ("baseball", "mlb"), "nhl": ("hockey", "nhl"),
    "ncaaf": ("football", "college-football"), "ncaab": ("basketball", "mens-college-basketball"),
    "ufc": ("mma", "ufc"), "soccer": ("soccer", "eng.1"),
    "tennis": ("tennis", "atp"), "golf": ("golf", "pga"),
}

async def get_sports_scores(league: str = "nfl") -> str:
    """Get latest sports scores from free ESPN API."""
    league = league.lower().strip()

    espn = ESPN_LEAGUES.get(league)
    if not espn:
        for key, (sport, _) in ESPN_LEAGUES.items():
            if key in league or league[:3] in key:
                espn = (sport, key)
                league = key
                break
        if not espn:
            espn = ("football", "nfl")
            league = "nfl"

    sport, league_slug = espn
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/scoreboard",
            )
            if r.status_code == 200:
                data = r.json()
                events = data.get("events", [])
                if events:
                    lines = [f"{league.upper()} scores:"]
                    for event in events[:5]:
                        comps = (event.get("competitions") or [{}])[0]
                        teams = comps.get("competitors", []) if comps else []
                        status_obj = comps.get("status") if comps else {}
                        if isinstance(status_obj, dict):
                            status = status_obj.get("displayClock", "Final")
                        else:
                            status = "Final"
                        if len(teams) >= 2:
                            t1_team = teams[0].get("team") or {}
                            t2_team = teams[1].get("team") or {}
                            t1 = f"{t1_team.get('displayName','?')} {teams[0].get('score','?')}"
                            t2 = f"{t2_team.get('displayName','?')} {teams[1].get('score','?')}"
                            lines.append(f"  {t1} vs {t2} ({status})")
                    return "\n".join(lines)
                return f"No active {league.upper()} games right now"
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        logger.exception("[sports] ESPN API: %s", e)

    # Fallback: search
    try:
        from tools.search_tool import search_engine
        year = datetime.now().year
        sr = await search_engine.search(f"{league} scores today {year}")
        if sr.is_err():
            logger.warning("[sports] search fallback failed: %s", sr._error)
            results = []
        else:
            results = sr.unwrap()
        if results:
            lines = [f"Latest {league.upper()}:"]
            for r in results[:3]:
                lines.append(f"- {r.title}: {r.snippet[:200]}")
            return "\n".join(lines)
        return f"No scores found for {league}"
    except Exception as e:
        logger.exception("[sports] search fallback: %s", e)
        return f"No scores found for {league}"
