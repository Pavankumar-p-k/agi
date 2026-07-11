from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from integrations.google_calendar import GoogleCalendarClient

logger = logging.getLogger(__name__)


async def do_manage_google_calendar(content: str, owner: str | None = None) -> dict:
    try:
        args = json.loads(content) if isinstance(content, str) else content
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    action = (args.get("action") or "list_events").replace("-", "_").strip().lower()
    action_aliases = {
        "create": "create_event",
        "update": "update_event",
        "delete": "delete_event",
        "list": "list_events",
    }
    action = action_aliases.get(action, action)

    client = GoogleCalendarClient()
    if not client.is_authenticated():
        ok = await client.authenticate()
        if not ok:
            return {
                "error": "Google Calendar not authenticated. Place gcal_credentials.json in ~/.jarvis/ and run authenticate.",
                "exit_code": 1,
            }

    try:
        if action == "list_calendars":
            cals = await client.list_calendars()
            return {
                "calendars": [
                    {"id": c.id, "summary": c.summary, "primary": c.primary}
                    for c in cals
                ],
                "count": len(cals),
                "exit_code": 0,
            }

        calendar_id = args.get("calendar_id", "primary")

        if action == "list_events":
            start_str = args.get("start") or args.get("time_min")
            end_str = args.get("end") or args.get("time_max")
            max_results = int(args.get("max_results", 20))
            query = args.get("query", "")

            time_min = None
            time_max = None
            if start_str:
                try:
                    time_min = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            if end_str:
                try:
                    time_max = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            events = await client.list_events(
                calendar_id=calendar_id,
                max_results=max_results,
                time_min=time_min,
                time_max=time_max,
                query=query,
            )
            return {
                "events": [
                    {
                        "id": e.id,
                        "summary": e.summary,
                        "start": e.start.isoformat() if e.start else None,
                        "end": e.end.isoformat() if e.end else None,
                        "all_day": e.all_day,
                        "location": e.location,
                        "status": e.status,
                    }
                    for e in events
                ],
                "count": len(events),
                "exit_code": 0,
            }

        if action == "create_event":
            summary = args.get("summary", "")
            if not summary:
                return {"error": "summary is required for create_event", "exit_code": 1}

            start_str = args.get("start") or args.get("dtstart")
            end_str = args.get("end") or args.get("dtend")
            all_day = bool(args.get("all_day", False))
            description = args.get("description", "")
            location = args.get("location", "")
            attendees = args.get("attendees")
            recurrence = args.get("recurrence") or args.get("rrule")

            if not start_str:
                return {"error": "start/dtstart is required for create_event", "exit_code": 1}

            if all_day:
                start = datetime.strptime(start_str[:10], "%Y-%m-%d")
                end = (datetime.strptime((end_str or start_str)[:10], "%Y-%m-%d") + timedelta(days=1)) if end_str else (start + timedelta(days=1))
            else:
                try:
                    start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                except Exception:
                    return {"error": f"Invalid start datetime: {start_str}", "exit_code": 1}
                try:
                    end = datetime.fromisoformat(end_str.replace("Z", "+00:00")) if end_str else (start + timedelta(hours=1))
                except Exception:
                    end = start + timedelta(hours=1)

            event = await client.create_event(
                summary=summary,
                start=start,
                end=end,
                description=description,
                location=location,
                calendar_id=calendar_id,
                attendees=attendees,
                recurrence=[recurrence] if isinstance(recurrence, str) else recurrence,
                all_day=all_day,
            )
            if event:
                return {
                    "event": {
                        "id": event.id,
                        "summary": event.summary,
                        "start": event.start.isoformat() if event.start else None,
                        "end": event.end.isoformat() if event.end else None,
                        "html_link": event.html_link,
                    },
                    "exit_code": 0,
                }
            return {"error": "Failed to create event", "exit_code": 1}

        if action == "update_event":
            event_id = args.get("event_id") or args.get("uid")
            if not event_id:
                return {"error": "event_id/uid is required for update_event", "exit_code": 1}

            summary = args.get("summary")
            description = args.get("description")
            location = args.get("location")

            start = None
            start_str = args.get("start") or args.get("dtstart")
            if start_str:
                try:
                    start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            end = None
            end_str = args.get("end") or args.get("dtend")
            if end_str:
                try:
                    end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            attendees = args.get("attendees")

            event = await client.update_event(
                event_id=event_id,
                calendar_id=calendar_id,
                summary=summary,
                description=description,
                location=location,
                start=start,
                end=end,
                attendees=attendees,
            )
            if event:
                return {
                    "event": {
                        "id": event.id,
                        "summary": event.summary,
                        "start": event.start.isoformat() if event.start else None,
                        "end": event.end.isoformat() if event.end else None,
                    },
                    "exit_code": 0,
                }
            return {"error": f"Failed to update event {event_id}", "exit_code": 1}

        if action == "delete_event":
            event_id = args.get("event_id") or args.get("uid")
            if not event_id:
                return {"error": "event_id/uid is required for delete_event", "exit_code": 1}
            ok = await client.delete_event(event_id=event_id, calendar_id=calendar_id)
            if ok:
                return {"deleted": event_id, "exit_code": 0}
            return {"error": f"Failed to delete event {event_id}", "exit_code": 1}

        return {"error": f"Unknown action: {action}", "exit_code": 1}

    except Exception as e:
        logger.exception("[GCalTool] %s failed: %s", action, e)
        return {"error": str(e), "exit_code": 1}
