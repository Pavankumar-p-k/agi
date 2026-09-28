"""CapabilityCatalog — per-application capability profiles.

Combines the ApplicationRegistry with the AdapterRegistry into profiles
of what actions are genuinely supported per application, persisted to
data/desktop_capabilities.json.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CapabilityProfile:
    application: str
    adapter: str = ""
    supported_actions: list = field(default_factory=list)
    safe_task_packs: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "application": self.application,
            "adapter": self.adapter,
            "supported_actions": list(self.supported_actions),
            "safe_task_packs": list(self.safe_task_packs),
        }


class CapabilityCatalog:
    """Refreshable catalog of application capability profiles."""

    def __init__(self, application_registry, adapter_registry,
                 store_path: Optional[Path] = None) -> None:
        self._apps = application_registry
        self._adapters = adapter_registry
        self._store_path = Path(store_path) if store_path else None
        self._profiles: dict[str, CapabilityProfile] = {}
        self._lock = threading.Lock()
        self.refresh()

    def refresh(self) -> None:
        """Rebuild profiles from the persisted store + live registries."""
        with self._lock:
            self._profiles.clear()
            if self._store_path and self._store_path.exists():
                try:
                    data = json.loads(
                        self._store_path.read_text(encoding="utf-8"))
                    for item in data.get("profiles", []):
                        profile = CapabilityProfile(
                            application=str(item.get("application", "")),
                            adapter=str(item.get("adapter", "")),
                            supported_actions=list(item.get("supported_actions", [])),
                            safe_task_packs=list(item.get("safe_task_packs", [])),
                        )
                        if profile.application:
                            self._profiles[profile.application.lower()] = profile
                except Exception:  # noqa: BLE001
                    pass

            # Merge adapter-declared capabilities for registered apps.
            try:
                for app in self._apps.list():
                    for adapter_name in self._adapters.applications():
                        actions = self._actions_for(adapter_name)
                        if actions and self._adapters.supports(adapter_name, actions[0]):
                            key = app.name.lower()
                            profile = self._profiles.setdefault(
                                key, CapabilityProfile(application=app.name))
                            if not profile.adapter:
                                profile.adapter = adapter_name
                            for action in actions:
                                if action not in profile.supported_actions:
                                    profile.supported_actions.append(action)
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _actions_for(adapter_name: str) -> list:
        # Mirror of the adapter declarations in core.desktop.adapters.
        known = {
            "explorer": ["reveal", "open", "list"],
            "text_editor": ["open", "edit", "type"],
            "process_inspection": ["list", "inspect", "running"],
            "clipboard": ["get", "set"],
            "window_management": ["focus", "close", "minimize",
                                  "maximize", "list"],
        }
        return known.get(adapter_name, [])

    def list(self, query: Optional[str] = None) -> list:
        profiles = list(self._profiles.values())
        if query:
            q = str(query).lower()
            profiles = [p for p in profiles if q in p.application.lower()]
        return sorted(profiles, key=lambda p: p.application.lower())


__all__ = ["CapabilityCatalog", "CapabilityProfile"]
