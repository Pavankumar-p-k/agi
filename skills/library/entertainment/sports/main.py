from skills.utils import success_response, error_response

SPORTS_DATA = {
    "cricket": {
        "description": "Cricket is a bat-and-ball game played between two teams of 11 players on a field with a 22-yard pitch.",
        "upcoming": ["India vs Australia - WTC Final (June 2025)", "Ashes 2025-26 (Nov 2025)", "IPL 2026 (March 2026)", "T20 World Cup 2026 (Oct 2026)"],
        "standings": "Top Test teams: 1. Australia, 2. India, 3. England, 4. South Africa, 5. New Zealand",
        "rules": "Two teams bat and bowl in innings. The batting team scores runs, the bowling team takes wickets. Formats: Test (5 days), ODI (50 overs), T20 (20 overs).",
        "players": ["Virat Kohli (India)", "Pat Cummins (Australia)", "Joe Root (England)", "Babar Azam (Pakistan)", "Steve Smith (Australia)"]
    },
    "football": {
        "description": "Football (soccer) is a team sport played between two teams of 11 players with a spherical ball.",
        "upcoming": ["UEFA Champions League Final 2025 (May 2025)", "FIFA World Cup 2026 (June 2026)", "Premier League 2025-26 (Aug 2025)", "Copa America 2025 (June 2025)"],
        "standings": "Top leagues: Premier League (England), La Liga (Spain), Serie A (Italy), Bundesliga (Germany), Ligue 1 (France)",
        "rules": "11 players per side, 90 minutes play, aim to score goals. No hands (except goalkeeper). Offside, fouls, and cards regulate play.",
        "players": ["Lionel Messi (Argentina)", "Cristiano Ronaldo (Portugal)", "Kylian Mbappe (France)", "Erling Haaland (Norway)", "Jude Bellingham (England)"]
    },
    "basketball": {
        "description": "Basketball is played between two teams of 5 players, scoring by shooting a ball through the opponent's hoop.",
        "upcoming": ["NBA Finals 2025 (June 2025)", "FIBA Asia Cup 2025 (July 2025)", "NBA Season 2025-26 (Oct 2025)", "FIBA World Cup 2026 (Aug 2026)"],
        "standings": "NBA Top Teams: 1. Boston Celtics, 2. Denver Nuggets, 3. Milwaukee Bucks, 4. Golden State Warriors, 5. LA Lakers",
        "rules": "5 players per team, 4 quarters of 12 minutes. Shoot from court (2/3 pts) or free throws (1 pt). Dribbling required when moving.",
        "players": ["LeBron James (USA)", "Stephen Curry (USA)", "Giannis Antetokounmpo (Greece)", "Nikola Jokic (Serbia)", "Luka Doncic (Slovenia)"]
    },
    "tennis": {
        "description": "Tennis is a racket sport played individually (singles) or in pairs (doubles) on a rectangular court.",
        "upcoming": ["Wimbledon 2025 (July 2025)", "US Open 2025 (Aug 2025)", "Australian Open 2026 (Jan 2026)", "French Open 2026 (May 2026)"],
        "standings": "ATP Rankings Top: 1. Novak Djokovic, 2. Carlos Alcaraz, 3. Jannik Sinner, 4. Daniil Medvedev, 5. Alexander Zverev",
        "rules": "Players use rackets to hit ball over net. Points: 15-30-40-game. Best of 3 or 5 sets. Ball must land in court boundaries.",
        "players": ["Novak Djokovic (Serbia)", "Carlos Alcaraz (Spain)", "Iga Swiatek (Poland)", "Jannik Sinner (Italy)", "Coco Gauff (USA)"]
    },
    "f1": {
        "description": "Formula 1 is the highest class of international auto racing for single-seater formula racing cars.",
        "upcoming": ["Monaco Grand Prix 2025 (May 2025)", "British Grand Prix 2025 (July 2025)", "Italian Grand Prix 2025 (Sept 2025)", "Abu Dhabi Grand Prix 2025 (Dec 2025)"],
        "standings": "Constructors: 1. Red Bull, 2. Ferrari, 3. Mercedes, 4. McLaren, 5. Aston Martin. Drivers: 1. Max Verstappen, 2. Lewis Hamilton, 3. Charles Leclerc",
        "rules": "20 drivers race on circuits. Points system: 1st=25, 2nd=18, 3rd=15 down to 10th=1. Fastest lap bonus. Pit stops for tires.",
        "players": ["Max Verstappen (Netherlands)", "Lewis Hamilton (UK)", "Charles Leclerc (Monaco)", "Lando Norris (UK)", "Fernando Alonso (Spain)"]
    }
}

async def sports(params: dict) -> dict:
    sport = params.get("sport", "").lower()
    action = params.get("action", "overview").lower()
    if sport not in SPORTS_DATA:
        return error_response(f"Unknown sport '{sport}'. Choose from: {', '.join(SPORTS_DATA.keys())}")
    data = SPORTS_DATA[sport]
    valid_actions = {"overview", "upcoming", "standings", "rules", "players"}
    if action not in valid_actions:
        return error_response(f"Unknown action '{action}'. Choose from: {', '.join(valid_actions)}")
    if action == "overview":
        return success_response({"sport": sport, "description": data["description"], "upcoming": data["upcoming"], "standings": data["standings"], "rules": data["rules"], "players": data["players"]})
    return success_response({"sport": sport, "action": action, "data": data[action]})

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
