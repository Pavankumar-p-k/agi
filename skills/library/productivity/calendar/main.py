from datetime import datetime

from skills.utils import success_response, error_response

_events = []

async def calendar(params: dict) -> dict:
    action = params.get("action", "list")

    if action == "list":
        date_filter = params.get("date", "").strip()
        if date_filter:
            filtered = [e for e in _events if e["date"] == date_filter]
        else:
            filtered = sorted(_events, key=lambda e: (e["date"], e.get("time", "")))
        return success_response({
            "events": filtered,
            "count": len(filtered),
        })

    elif action == "add":
        title = params.get("title", "").strip()
        if not title:
            return error_response("title is required")
        date_val = params.get("date", "").strip()
        if not date_val:
            return error_response("date is required (YYYY-MM-DD)")
        time_val = params.get("time", "").strip()
        duration = int(params.get("duration", 60))
        description = params.get("description", "").strip()

        event = {
            "id": len(_events) + 1,
            "title": title,
            "date": date_val,
            "time": time_val or "00:00",
            "duration_minutes": duration,
            "description": description,
        }
        _events.append(event)
        return success_response({"event": event})

    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest

    async def on_load(self):
        pass
