"""Integrated native application capability profiles."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import os
from pathlib import Path

from core.desktop.adapters import AdapterRegistry
from core.desktop.applications import ApplicationRegistry, ApplicationRecord
from core.desktop.task_packs import TaskPack


CAPABILITY_ACTIONS = (
    "open", "reveal", "invoke", "read", "write", "clear",
    "list", "find", "is_running", "focus", "minimize", "maximize",
)


@dataclass
class CapabilityProfile:
    application: str
    installed: bool
    version: str = ""
    adapter: str | None = None
    supported_actions: list[str] = field(default_factory=list)
    safe_task_packs: list[str] = field(default_factory=list)
    approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapabilityCatalog:
    def __init__(
        self,
        applications: ApplicationRegistry,
        adapters: AdapterRegistry,
        path: str | Path,
    ):
        self.applications = applications
        self.adapters = adapters
        self.path = Path(path)
        self.profiles: dict[str, CapabilityProfile] = {}
        self._load()

    def refresh(self, packs: list[TaskPack] | None = None) -> list[CapabilityProfile]:
        pack_map: dict[str, list[str]] = {}
        for pack in packs or []:
            pack.validate()
            pack_map.setdefault(pack.application.casefold(), []).append(pack.pack_id)
        profiles = []
        for record in self.applications.list():
            adapter = self.adapters.get(record.name)
            actions = []
            if adapter:
                for action in CAPABILITY_ACTIONS:
                    if adapter.supports(action):
                        actions.append(action)
            profile = CapabilityProfile(
                application=record.name,
                installed=True,
                version=record.version,
                adapter=adapter.application if adapter else None,
                supported_actions=actions,
                safe_task_packs=pack_map.get(record.name.casefold(), []),
                approved=record.approved,
            )
            self.profiles[record.name.casefold()] = profile
            profiles.append(profile)
        # A registered adapter is itself an explicit capability boundary, even
        # when Windows does not expose the corresponding shell component in the
        # uninstall registry.
        for application in self.adapters.applications():
            adapter = self.adapters.get(application)
            actions = [
                action for action in CAPABILITY_ACTIONS
                if adapter is not None and adapter.supports(action)
            ]
            existing = self.profiles.get(application)
            profile = CapabilityProfile(
                application=application,
                installed=True,
                version=existing.version if existing else "",
                adapter=application,
                supported_actions=actions,
                safe_task_packs=pack_map.get(application, []),
                approved=existing.approved if existing else False,
            )
            self.profiles[application] = profile
            profiles.append(profile)
        self._save()
        return self.list()

    def get(self, application: str) -> CapabilityProfile | None:
        return self.profiles.get(application.casefold())

    def list(self, query: str | None = None) -> list[CapabilityProfile]:
        profiles = list(self.profiles.values())
        if query:
            profiles = [p for p in profiles if query.casefold() in p.application.casefold()]
        return sorted(profiles, key=lambda item: item.application.casefold())

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({k: v.to_dict() for k, v in self.profiles.items()}, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.profiles = {key: CapabilityProfile(**value) for key, value in data.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self.profiles = {}
