"""ProviderRegistry: authoritative registry of execution providers.

Completed from the committed contract in tests/unit/test_provider_ecosystem.py
(TestProviderRegistry) and consumed by the router, capability view, and
bootstrap.

- ``register(provider, priority=N)`` indexes the provider by id and by each
  capability it declares; stored settings (from a prior session) override the
  registration-time priority/enabled state.
- ``disable/enable/set_priority`` persist to ``_PROVIDER_SETTINGS_FILE`` so a
  fresh registry instance restores the same configuration (persistence test).
- ``plugin_registry`` links the existing plugin system (ADR-013 boundary).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from core.providers.base import ExecutionProvider

logger = logging.getLogger(__name__)

_DEFAULT_SETTINGS_DIR = Path("data") / "provider_settings"
_DEFAULT_SETTINGS_FILE = _DEFAULT_SETTINGS_DIR / "registry.json"


class ProviderRegistry:
    """Registry of ExecutionProvider instances (the connector layer)."""

    _PROVIDER_SETTINGS_DIR: Path = _DEFAULT_SETTINGS_DIR
    _PROVIDER_SETTINGS_FILE: Path = _DEFAULT_SETTINGS_FILE

    def __init__(self) -> None:
        self._providers: dict[str, ExecutionProvider] = {}
        self._priorities: dict[str, int] = {}
        self._capability_index: dict[str, list[str]] = {}
        self._pending_settings: dict[str, dict[str, Any]] = {}
        self.plugin_registry: Any = None
        self._settings_loaded = False
        self._loaded_settings_file: Optional[Path] = None
        self._load_settings()

    # ------------------------------------------------------------------ #
    # Registration                                                       #
    # ------------------------------------------------------------------ #

    def register(self, provider: ExecutionProvider, priority: int = 100) -> None:
        pid = provider.provider_id
        self._load_settings()  # settings paths may have been redirected post-construction
        if pid in self._providers:
            # Re-registration: drop old capability index entries first.
            self._remove_from_index(pid)
        self._providers[pid] = provider
        pending = self._pending_settings.get(pid, {})
        self._priorities[pid] = int(pending.get("priority", priority))
        if "enabled" in pending:
            provider._enabled = bool(pending["enabled"])
        for cap in self._capabilities_of(provider):
            self._capability_index.setdefault(cap, [])
            if pid not in self._capability_index[cap]:
                self._capability_index[cap].append(pid)
        self._save_settings()

    def unregister(self, provider_id: str) -> bool:
        if provider_id not in self._providers:
            return False
        del self._providers[provider_id]
        self._priorities.pop(provider_id, None)
        self._remove_from_index(provider_id)
        self._save_settings()
        return True

    def _remove_from_index(self, provider_id: str) -> None:
        for cap in list(self._capability_index):
            pids = [p for p in self._capability_index[cap] if p != provider_id]
            if pids:
                self._capability_index[cap] = pids
            else:
                del self._capability_index[cap]

    @staticmethod
    def _capabilities_of(provider: ExecutionProvider) -> list[str]:
        try:
            return list(provider.capabilities().capability_names)
        except Exception as exc:  # defensive: a broken provider must not break registration
            logger.debug("[provider_registry] capabilities() failed for %s: %s",
                         getattr(provider, "provider_id", "?"), exc)
            return []

    # ------------------------------------------------------------------ #
    # Lookup                                                             #
    # ------------------------------------------------------------------ #

    def get(self, provider_id: str) -> Optional[ExecutionProvider]:
        return self._providers.get(provider_id)

    def list_providers(self) -> list[ExecutionProvider]:
        return list(self._providers.values())

    def list_enabled(self) -> list[ExecutionProvider]:
        return [p for p in self._providers.values() if p.enabled]

    def get_providers_for_capability(self, capability: str) -> list[ExecutionProvider]:
        return [
            self._providers[pid]
            for pid in self._capability_index.get(capability, [])
            if pid in self._providers
        ]

    def has_capability(self, capability: str) -> bool:
        return capability in self._capability_index

    def all_capabilities(self) -> list[str]:
        return list(self._capability_index)

    def _sorted_providers(self) -> list[ExecutionProvider]:
        return sorted(
            self._providers.values(),
            key=lambda p: self._priorities.get(p.provider_id, 100),
        )

    # ------------------------------------------------------------------ #
    # Enable / priority (persisted)                                      #
    # ------------------------------------------------------------------ #

    def enable(self, provider_id: str) -> bool:
        return self._set_enabled(provider_id, True)

    def disable(self, provider_id: str) -> bool:
        return self._set_enabled(provider_id, False)

    def _set_enabled(self, provider_id: str, enabled: bool) -> bool:
        provider = self._providers.get(provider_id)
        if provider is None:
            return False
        self._load_settings()
        provider._enabled = enabled
        self._pending_settings.setdefault(provider_id, {})["enabled"] = enabled
        self._save_settings()
        return True

    def is_enabled(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        if provider is None:
            return False
        return bool(provider.enabled)

    def get_priority(self, provider_id: str) -> int:
        return self._priorities.get(provider_id, 100)

    def set_priority(self, provider_id: str, priority: int) -> bool:
        if provider_id not in self._providers:
            return False
        self._load_settings()
        self._priorities[provider_id] = int(priority)
        self._pending_settings.setdefault(provider_id, {})["priority"] = int(priority)
        self._save_settings()
        return True

    # ------------------------------------------------------------------ #
    # Plugin registry link                                               #
    # ------------------------------------------------------------------ #

    def link_plugin_registry(self, plugin_registry: Any) -> None:
        self.plugin_registry = plugin_registry

    # ------------------------------------------------------------------ #
    # Settings persistence                                               #
    # ------------------------------------------------------------------ #

    def _save_settings(self) -> bool:
        try:
            self._PROVIDER_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            settings: dict[str, dict[str, Any]] = {}
            for pid, provider in self._providers.items():
                entry = dict(self._pending_settings.get(pid, {}))
                # Persist effective state so a fresh process/registry reloads
                # the same priorities/enabled flags (explicit pending
                # overrides always win).
                entry.setdefault("priority", int(self._priorities.get(pid, 100)))
                entry.setdefault("enabled", bool(getattr(provider, "enabled", True)))
                settings[pid] = entry
            payload = {
                "settings": settings,
                "saved_at": __import__("time").time(),
            }
            self._PROVIDER_SETTINGS_FILE.write_text(
                json.dumps(payload), encoding="utf-8",
            )
            return True
        except Exception as exc:
            logger.debug("[provider_registry] save settings failed: %s", exc)
            return False

    def _load_settings(self) -> bool:
        """Load persisted settings lazily (file may not exist yet).

        Re-loads transparently when ``_PROVIDER_SETTINGS_FILE`` is redirected
        after construction (test isolation, alternate stores).
        """
        current_file = self._PROVIDER_SETTINGS_FILE
        if self._settings_loaded and self._loaded_settings_file == current_file:
            return True
        self._settings_loaded = True
        self._loaded_settings_file = current_file
        try:
            if not self._PROVIDER_SETTINGS_FILE.exists():
                return False
            payload = json.loads(
                self._PROVIDER_SETTINGS_FILE.read_text(encoding="utf-8")
            )
            self._pending_settings = payload.get("settings", {}) or {}
            return True
        except Exception as exc:
            logger.debug("[provider_registry] load settings failed: %s", exc)
            return False


provider_registry = ProviderRegistry()
