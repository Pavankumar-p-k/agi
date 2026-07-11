from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class GoogleCalendar:
    id: str
    summary: str
    description: str = ""
    time_zone: str = "UTC"
    access_role: str = "reader"
    primary: bool = False
    selected: bool = True


@dataclass
class CalendarEvent:
    id: str
    summary: str
    description: str = ""
    location: str = ""
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool = False
    calendar_id: str = "primary"
    creator: str = ""
    organizer: str = ""
    attendees: list[str] = field(default_factory=list)
    recurrence: list[str] = field(default_factory=list)
    html_link: str = ""
    status: str = "confirmed"
    reminders: dict[str, Any] = field(default_factory=dict)


def calendar_from_api(data: dict) -> GoogleCalendar:
    return GoogleCalendar(
        id=data.get("id", ""),
        summary=data.get("summary", ""),
        description=data.get("description", ""),
        time_zone=data.get("timeZone", "UTC"),
        access_role=data.get("accessRole", "reader"),
        primary=data.get("primary", False),
        selected=data.get("selected", True),
    )


def event_from_api(data: dict, calendar_id: str = "primary") -> CalendarEvent:
    start_info = data.get("start", {})
    end_info = data.get("end", {})

    start_dt = _parse_datetime(start_info)
    end_dt = _parse_datetime(end_info)
    all_day = "date" in start_info and "dateTime" not in start_info

    attendees = []
    for att in data.get("attendees", []):
        email = att.get("email", "")
        if email:
            attendees.append(email)

    return CalendarEvent(
        id=data.get("id", ""),
        summary=data.get("summary", ""),
        description=data.get("description", ""),
        location=data.get("location", ""),
        start=start_dt,
        end=end_dt,
        all_day=all_day,
        calendar_id=calendar_id,
        creator=data.get("creator", {}).get("email", ""),
        organizer=data.get("organizer", {}).get("email", ""),
        attendees=attendees,
        recurrence=data.get("recurrence", []),
        html_link=data.get("htmlLink", ""),
        status=data.get("status", "confirmed"),
        reminders=data.get("reminders", {}),
    )


def _parse_datetime(dt_info: dict) -> datetime | None:
    if "dateTime" in dt_info:
        try:
            from datetime import timezone
            return datetime.fromisoformat(dt_info["dateTime"].replace("Z", "+00:00"))
        except Exception:
            pass
    elif "date" in dt_info:
        try:
            return datetime.strptime(dt_info["date"], "%Y-%m-%d")
        except Exception:
            pass
    return None
