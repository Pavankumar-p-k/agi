from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts import ToolSpec
from .legacy_automation import LegacyAutomationAdapter
from .legacy_contacts import LegacyContactsAdapter
from .legacy_memory import LegacyAGIMemoryAdapter
from .legacy_reminders import LegacyRemindersAdapter


class CompatibilityBridge:
    def __init__(self, backend_root: Path) -> None:
        self.backend_root = Path(backend_root)
        self.legacy_contacts = LegacyContactsAdapter(self.backend_root)
        self.legacy_memory = LegacyAGIMemoryAdapter(self.backend_root)
        self.legacy_reminders = LegacyRemindersAdapter(self.backend_root)
        self.legacy_automation = LegacyAutomationAdapter(self.backend_root)

    def register_tools(self, registry: Any) -> None:
        registry.register(
            ToolSpec(
                "legacy_contacts_list",
                "List contacts from the legacy automation contacts store.",
                [],
                category="communication",
                read_only=True,
                keywords=["legacy", "contacts", "list"],
            ),
            lambda **_: self.legacy_contacts.list_all(),
        )
        registry.register(
            ToolSpec(
                "legacy_contacts_search",
                "Search contacts from the legacy automation contacts store.",
                ["query"],
                parameters={"query": {"type": "string", "required": True}},
                category="communication",
                read_only=True,
                keywords=["legacy", "contacts", "search"],
            ),
            lambda query, **_: self.legacy_contacts.search(query),
        )
        registry.register(
            ToolSpec(
                "legacy_contacts_upsert",
                "Create or update a contact in the legacy automation contacts store.",
                ["name", "phone", "instagram", "whatsapp", "email", "notes"],
                parameters={
                    "name": {"type": "string", "required": True},
                    "phone": {"type": "string", "required": False, "default": ""},
                    "instagram": {"type": "string", "required": False, "default": ""},
                    "whatsapp": {"type": "string", "required": False, "default": ""},
                    "email": {"type": "string", "required": False, "default": ""},
                    "notes": {"type": "string", "required": False, "default": ""},
                },
                category="communication",
                permission="elevated",
                keywords=["legacy", "contacts", "save"],
            ),
            lambda name, phone="", instagram="", whatsapp="", email="", notes="", **_: self.legacy_contacts.upsert(
                name=name,
                phone=phone,
                instagram=instagram,
                whatsapp=whatsapp,
                email=email,
                notes=notes,
            ),
        )
        registry.register(
            ToolSpec(
                "legacy_contacts_delete",
                "Delete a contact from the legacy automation contacts store.",
                ["name"],
                parameters={"name": {"type": "string", "required": True}},
                category="communication",
                permission="elevated",
                keywords=["legacy", "contacts", "delete"],
            ),
            lambda name, **_: self.legacy_contacts.delete(name),
        )
        registry.register(
            ToolSpec(
                "legacy_reminders_list",
                "List reminders from the legacy reminders database.",
                ["limit"],
                parameters={"limit": {"type": "integer", "required": False, "default": 50}},
                category="automation",
                read_only=True,
                keywords=["legacy", "reminders", "list"],
            ),
            lambda limit=50, **_: self.legacy_reminders.list_all(limit=limit),
        )
        registry.register(
            ToolSpec(
                "legacy_reminders_pending_count",
                "Count pending reminders from the legacy reminders database.",
                [],
                category="automation",
                read_only=True,
                keywords=["legacy", "reminders", "pending"],
            ),
            lambda **_: self.legacy_reminders.pending_count(),
        )
        registry.register(
            ToolSpec(
                "legacy_reminders_create",
                "Create a reminder in the legacy reminders database.",
                ["title", "remind_at", "description", "repeat", "user_uid", "email", "display_name"],
                parameters={
                    "title": {"type": "string", "required": True},
                    "remind_at": {"type": "string", "required": True},
                    "description": {"type": "string", "required": False, "default": ""},
                    "repeat": {"type": "string", "required": False, "default": "none"},
                    "user_uid": {"type": "string", "required": False, "default": "legacy-default"},
                    "email": {"type": "string", "required": False, "default": "legacy@example.com"},
                    "display_name": {"type": "string", "required": False, "default": "Legacy User"},
                },
                category="automation",
                permission="elevated",
                keywords=["legacy", "reminders", "create"],
            ),
            lambda title, remind_at, description="", repeat="none", user_uid="legacy-default", email="legacy@example.com", display_name="Legacy User", **_: self.legacy_reminders.create(
                title=title,
                remind_at=remind_at,
                description=description,
                repeat=repeat,
                user_uid=user_uid,
                email=email,
                display_name=display_name,
            ),
        )
        registry.register(
            ToolSpec(
                "legacy_reminders_delete",
                "Delete a reminder from the legacy reminders database.",
                ["reminder_id"],
                parameters={"reminder_id": {"type": "integer", "required": True}},
                category="automation",
                permission="elevated",
                keywords=["legacy", "reminders", "delete"],
            ),
            lambda reminder_id, **_: self.legacy_reminders.delete(reminder_id),
        )
        registry.register(
            ToolSpec(
                "legacy_automation_command",
                "Run a command through the legacy PC automation engine.",
                ["command"],
                parameters={"command": {"type": "string", "required": True}},
                category="automation",
                permission="elevated",
                keywords=["legacy", "automation", "command"],
            ),
            lambda command, **_: self.legacy_automation.execute(command),
        )
        registry.register(
            ToolSpec(
                "legacy_agi_memory_stats",
                "Read stats from the legacy AGI memory store.",
                [],
                category="memory",
                read_only=True,
                keywords=["legacy", "agi", "memory"],
            ),
            lambda **_: self.legacy_memory.stats(),
        )
        registry.register(
            ToolSpec(
                "legacy_agi_recent_events",
                "Read recent events from the legacy AGI memory store.",
                ["limit"],
                parameters={"limit": {"type": "integer", "required": False, "default": 10}},
                category="memory",
                read_only=True,
                keywords=["legacy", "agi", "events"],
            ),
            lambda limit=10, **_: self.legacy_memory.recent_events(limit=limit),
        )
        registry.register(
            ToolSpec(
                "legacy_agi_latest_mood",
                "Read the latest mood from the legacy AGI memory store.",
                [],
                category="memory",
                read_only=True,
                keywords=["legacy", "agi", "mood"],
            ),
            lambda **_: self.legacy_memory.latest_mood(),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "backend_root": str(self.backend_root),
            "adapters": [
                self.legacy_contacts.status(),
                self.legacy_memory.status(),
                self.legacy_reminders.status(),
                self.legacy_automation.status(),
            ],
        }
