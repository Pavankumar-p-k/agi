"""CapabilityCatalog — per-application capability profiles.

Combines the ApplicationRegistry with the AdapterRegistry into profiles
of what actions are genuinely supported per application, optionally
annotated with the safe TaskPacks declared for that application.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_KNOWN_ACTIONS = (
    "reveal", "open", "list", "read", "write", "edit", "type",
    "inspect", "running", "get", "set", "clear",
    "focus", "minimize", "maximize",
)


@dataclass
class CapabilityProfile:
    application: str
    adapter: Optional[str] = None
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

    def refresh(self, task_packs=None) -> list:
        """Rebuild profiles from the live registries; returns the profiles."""
        with self._lock:
            self._profiles.clear()
            packs = list(task_packs or [])
            try:
                apps = self._apps.list()
            except Exception:  # noqa: BLE001 — registry failure = no profiles
                apps = []
            for app in apps:
                profile = CapabilityProfile(application=app.name)
                try:
                    adapter = self._adapters.get(app.name)
                except Exception:  # noqa: BLE001
                    adapter = None
                if adapter is not None:
                    profile.adapter = str(getattr(adapter, "name", ""))
                    profile.supported_actions = [
                        action for action in _KNOWN_ACTIONS
                        if adapter.supports(app.name, action)]
                profile.safe_task_packs = [
                    pack.pack_id for pack in packs
                    if str(getattr(pack, "application", "")).lower()
                    == app.name.lower()]
                self._profiles[app.name.lower()] = profile
            self._save()
            return list(self._profiles.values())

    def _save(self) -> None:
        if not self._store_path:
            return
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"profiles": [p.to_dict()
                                 for p in self._profiles.values()]}
            self._store_path.write_text(json.dumps(data, indent=1),
                                        encoding="utf-8")
        except Exception:  # noqa: BLE001 — store is best-effort
            pass

    def list(self, query: Optional[str] = None) -> list:
        profiles = list(self._profiles.values())
        if query:
            q = str(query).lower()
            profiles = [p for p in profiles if q in p.application.lower()]
        return sorted(profiles, key=lambda p: p.application.lower())


__all__ = ["CapabilityCatalog", "CapabilityProfile"]
