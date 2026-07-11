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
# Auto-generated schema definitions for manage_calendar, manage_notes
FUNCTION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "manage_calendar",
            "description": "Manage calendar events: list events in a date range, create, update, delete. Each event can carry a tag/category (event_type) and importance level. Use ISO 8601 datetimes; for all-day events set all_day=true and pass YYYY-MM-DD. For event reminders/alarms, pass reminder_minutes; the tool creates the Odysseus note reminder, so do not also call manage_notes for the same reminder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string",
                               "enum": ["list_events", "create_event", "update_event", "delete_event", "list_calendars"],
                               "description": "Action to perform"},
                    "summary": {"type": "string", "description": "Event title (for create/update)"},
                    "dtstart": {"type": "string", "description": "Start ISO datetime, or YYYY-MM-DD if all_day"},
                    "dtend": {"type": "string", "description": "End ISO datetime; defaults to +1h (or +1 day for all_day)"},
                    "all_day": {"type": "boolean", "description": "Whether this is an all-day event"},
                    "description": {"type": "string", "description": "Event description / notes"},
                    "location": {"type": "string", "description": "Event location"},
                    "uid": {"type": "string", "description": "Event UID (for update/delete)"},
                    "calendar_href": {"type": "string", "description": "Specific calendar URL (optional; defaults to first calendar)"},
                    "calendar": {"type": "string", "description": "Filter list_events by calendar name or href"},
                    "start": {"type": "string", "description": "list_events range start (ISO datetime); defaults to today"},
                    "end": {"type": "string", "description": "list_events range end (ISO datetime); defaults to +14 days"},
                    "event_type": {"type": "string", "description": "Tag / category for the event. Common values: work, personal, health, travel, meal, social, admin, other. Aliases accepted: tag, category, type."},
                    "importance": {"type": "string", "enum": ["low", "normal", "high", "critical"], "description": "Priority level (defaults to 'normal')"},
                    "reminder_minutes": {"type": "integer", "description": "For create_event: create an Odysseus reminder this many minutes before the event, e.g. 5 for 'reminder 5 min before'."},
                    "rrule": {"type": "string", "description": "Recurrence rule in iCalendar RRULE format, e.g. 'FREQ=WEEKLY;BYDAY=MO' for weekly on Monday. Use with create_event or update_event."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_notes",
            "description": "Manage notes and checklists (Google Keep-style): list, add, update, delete, toggle_item. IMPORTANT: For to-do lists / checklists, set note_type='checklist' and pass the items as the `checklist_items` array — do NOT serialize them into `content` as plain text. For freeform notes, use note_type='note' and put the body in `content`. `due_date` accepts natural language like 'tomorrow at 9am' (parsed in the user's timezone) and fires a notification — do not also create a calendar event for the same reminder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string",
                               "enum": ["list", "add", "update", "delete", "toggle_item"],
                               "description": "The action to perform"},
                    "id": {"type": "string", "description": "Note id (for update/delete/toggle_item); 8-char prefix is fine"},
                    "title": {"type": "string", "description": "Note title (for add/update)"},
                    "content": {"type": "string", "description": "Freeform body text. Use this for note_type='note'. Do NOT use this for checklists — pass `checklist_items` instead."},
                    "note_type": {"type": "string", "enum": ["note", "checklist"],
                                  "description": "'note' = freeform text in `content`. 'checklist' = structured to-do items in `checklist_items`. Defaults to 'checklist' if checklist_items is supplied, else 'note'."},
                    "checklist_items": {"type": "array",
                                        "items": {"type": "object",
                                                  "properties": {
                                                      "text": {"type": "string", "description": "The to-do item text"},
                                                      "done": {"type": "boolean", "description": "Whether the item is checked off"}
                                                  },
                                                  "required": ["text"]},
                                        "description": "Checklist items for note_type='checklist'. Each item is {text, done}. REQUIRED for checklists — leaving this empty produces a blank note."},
                    "color": {"type": "string", "description": "Optional color label (e.g. 'yellow', 'blue', 'green')"},
                    "label": {"type": "string", "description": "Optional category label (also used as a list filter)"},
                    "pinned": {"type": "boolean", "description": "Pin the note to the top"},
                    "archived": {"type": "boolean", "description": "For update: archive/unarchive. For list: show archived notes when true."},
                    "due_date": {"type": "string", "description": "Reminder time. Accepts natural language ('tomorrow at 9am', '11pm today') or ISO 8601. Fires a notification at that time."},
                    "index": {"type": "integer", "description": "Checklist item index (for toggle_item, 0-based)"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_google_calendar",
            "description": "Manage Google Calendar events: list calendars, list events, create, update, delete. Uses Google Calendar API (not local CalDAV). Supports all-day events with YYYY-MM-DD dates. For event reminders, pass reminder_minutes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string",
                               "enum": ["list_calendars", "list_events", "create_event", "update_event", "delete_event"],
                               "description": "Action to perform"},
                    "calendar_id": {"type": "string", "description": "Calendar ID (defaults to 'primary')"},
                    "summary": {"type": "string", "description": "Event title (for create/update)"},
                    "start": {"type": "string", "description": "Start ISO datetime, or YYYY-MM-DD if all_day"},
                    "end": {"type": "string", "description": "End ISO datetime; defaults to +1h (or +1 day for all_day)"},
                    "all_day": {"type": "boolean", "description": "Whether this is an all-day event"},
                    "description": {"type": "string", "description": "Event description / notes"},
                    "location": {"type": "string", "description": "Event location"},
                    "event_id": {"type": "string", "description": "Event ID (for update/delete)"},
                    "attendees": {"type": "array", "items": {"type": "string"}, "description": "Attendee email addresses"},
                    "recurrence": {"type": "array", "items": {"type": "string"}, "description": "Recurrence rules (RRULE format)"},
                    "query": {"type": "string", "description": "Search query for list_events"},
                    "max_results": {"type": "integer", "description": "Max events to return (default 20)"},
                },
                "required": ["action"]
            }
        }
    },
]
