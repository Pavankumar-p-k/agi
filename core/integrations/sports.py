"""Sports scores - free ESPN API (no key needed)."""
import httpx

ESPN_LEAGUES = {
    "nfl": ("football", "nfl"), "nba": ("basketball", "nba"),
    "mlb": ("baseball", "mlb"), "nhl": ("hockey", "nhl"),
    "ncaaf": ("football", "college-football"), "ncaab": ("basketball", "mens-college-basketball"),
    "ufc": ("mma", "ufc"), "soccer": ("soccer", "eng.1"),
    "tennis": ("tennis", "atp"), "golf": ("golf", "pga"),
}

def get_sports_scores(league: str = "nfl") -> str:
    """Get latest sports scores from free ESPN API."""
    league = league.lower().strip()
    
    espn = ESPN_LEAGUES.get(league)
    if not espn:
        # Try to find a match
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
        r = httpx.get(
            f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/scoreboard",
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            events = data.get("events", [])
            if events:
                lines = [f"{league.upper()} scores:"]
                for event in events[:5]:
                    comps = event.get("competitions", [{}])[0]
                    teams = comps.get("competitors", [])
                    status = comps.get("status", {}).get("displayClock", "Final")
                    if len(teams) >= 2:
                        t1 = f"{teams[0].get('team',{}).get('displayName','?')} {teams[0].get('score','?')}"
                        t2 = f"{teams[1].get('team',{}).get('displayName','?')} {teams[1].get('score','?')}"
                        lines.append(f"  {t1} vs {t2} ({status})")
                return "\n".join(lines)
            return f"No active {league.upper()} games right now"
    except Exception:
        pass
    
    # Fallback: search
    try:
        from tools.search_tool import search_engine
        results = search_engine.search(f"{league} scores today 2026")
        if results:
            lines = [f"Latest {league.upper()}:"]
            for r in results[:3]:
                lines.append(f"- {r.title}: {r.snippet[:200]}")
            return "\n".join(lines)
        return f"No scores found for {league}"
    except Exception:
        return f"No scores found for {league}"
