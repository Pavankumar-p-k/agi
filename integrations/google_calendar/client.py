from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from .auth import GoogleCalendarAuth
from .types import CalendarEvent, GoogleCalendar, calendar_from_api, event_from_api

logger = logging.getLogger(__name__)


class GoogleCalendarClient:
    def __init__(self, auth: GoogleCalendarAuth | None = None):
        self._auth = auth or GoogleCalendarAuth()
        self._authenticated_once = False

    @property
    def service(self):
        return self._auth.service

    def authenticate(self, headless: bool = False) -> bool:
        ok = self._auth.authenticate(headless=headless)
        if ok:
            self._authenticated_once = True
        return ok

    def is_authenticated(self) -> bool:
        return self._auth.is_authenticated

    def health_check(self) -> dict[str, Any]:
        return self._auth.health_check()

    # ── Calendar CRUD ─────────────────────────────────────────

    def list_calendars(self) -> list[GoogleCalendar]:
        try:
            resp = self.service.calendarList().list().execute()
            return [calendar_from_api(c) for c in resp.get("items", [])]
        except Exception as e:
            logger.error("[GCalClient] list_calendars failed: %s", e)
            return []

    def get_calendar(self, calendar_id: str = "primary") -> GoogleCalendar | None:
        try:
            resp = self.service.calendars().get(calendarId=calendar_id).execute()
            return calendar_from_api(resp)
        except Exception as e:
            logger.error("[GCalClient] get_calendar(%s) failed: %s", calendar_id, e)
            return None

    # ── Event CRUD ────────────────────────────────────────────

    def list_events(
        self,
        calendar_id: str = "primary",
        max_results: int = 20,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        query: str = "",
        single_events: bool = True,
        order_by: str = "startTime",
    ) -> list[CalendarEvent]:
        try:
            kwargs: dict[str, Any] = dict(
                calendarId=calendar_id,
                maxResults=min(max_results, 250),
                singleEvents=single_events,
                orderBy=order_by,
            )
            if time_min:
                kwargs["timeMin"] = time_min.isoformat()
            else:
                kwargs["timeMin"] = datetime.utcnow().isoformat() + "Z"
            if time_max:
                kwargs["timeMax"] = time_max.isoformat()
            if query:
                kwargs["q"] = query

            resp = self.service.events().list(**kwargs).execute()
            return [event_from_api(e, calendar_id) for e in resp.get("items", [])]
        except Exception as e:
            logger.error("[GCalClient] list_events failed: %s", e)
            return []

    def get_event(self, event_id: str, calendar_id: str = "primary") -> CalendarEvent | None:
        try:
            resp = self.service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            return event_from_api(resp, calendar_id)
        except Exception as e:
            logger.error("[GCalClient] get_event(%s) failed: %s", event_id, e)
            return None

    def create_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        description: str = "",
        location: str = "",
        calendar_id: str = "primary",
        attendees: list[str] | None = None,
        recurrence: list[str] | None = None,
        all_day: bool = False,
    ) -> CalendarEvent | None:
        try:
            if all_day:
                start_body = {"date": start.strftime("%Y-%m-%d")}
                end_body = {"date": end.strftime("%Y-%m-%d")}
            else:
                start_body = {"dateTime": start.isoformat()}
                end_body = {"dateTime": end.isoformat()}

            body: dict[str, Any] = {
                "summary": summary,
                "start": start_body,
                "end": end_body,
            }
            if description:
                body["description"] = description
            if location:
                body["location"] = location
            if attendees:
                body["attendees"] = [{"email": a} for a in attendees]
            if recurrence:
                body["recurrence"] = recurrence

            resp = self.service.events().insert(
                calendarId=calendar_id, body=body
            ).execute()
            logger.info("[GCalClient] Created event %s in %s", resp.get("id"), calendar_id)
            return event_from_api(resp, calendar_id)
        except Exception as e:
            logger.error("[GCalClient] create_event failed: %s", e)
            return None

    def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        summary: str | None = None,
        description: str | None = None,
        location: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        attendees: list[str] | None = None,
    ) -> CalendarEvent | None:
        try:
            existing = self.get_event(event_id, calendar_id)
            if existing is None:
                return None

            body: dict[str, Any] = {}
            if summary is not None:
                body["summary"] = summary
            if description is not None:
                body["description"] = description
            if location is not None:
                body["location"] = location
            if start is not None:
                body["start"] = {"dateTime": start.isoformat()}
            if end is not None:
                body["end"] = {"dateTime": end.isoformat()}
            if attendees is not None:
                body["attendees"] = [{"email": a} for a in attendees]

            resp = self.service.events().patch(
                calendarId=calendar_id, eventId=event_id, body=body
            ).execute()
            logger.info("[GCalClient] Updated event %s", event_id)
            return event_from_api(resp, calendar_id)
        except Exception as e:
            logger.error("[GCalClient] update_event(%s) failed: %s", event_id, e)
            return None

    def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        try:
            self.service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            logger.info("[GCalClient] Deleted event %s", event_id)
            return True
        except Exception as e:
            logger.error("[GCalClient] delete_event(%s) failed: %s", event_id, e)
            return False

    def search_events(
        self,
        query: str,
        calendar_id: str = "primary",
        max_results: int = 20,
    ) -> list[CalendarEvent]:
        return self.list_events(
            calendar_id=calendar_id, max_results=max_results, query=query
        )

    def get_upcoming_events(
        self,
        calendar_id: str = "primary",
        max_results: int = 10,
        days_ahead: int = 7,
    ) -> list[CalendarEvent]:
        now = datetime.utcnow()
        end = now + timedelta(days=days_ahead)
        return self.list_events(
            calendar_id=calendar_id,
            max_results=max_results,
            time_min=now,
            time_max=end,
        )
