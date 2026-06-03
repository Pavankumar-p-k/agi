# core/plugins/settings_store.py
# Persists per-plugin settings to ~/.jarvis/plugin_settings.json
from __future__ import annotations
import json
import logging
import os
from typing import Any

logger = logging.getLogger("jarvis.plugins.settings")

_DEFAULT_PATH = os.path.join(os.path.expanduser("~"), ".jarvis", "plugin_settings.json")


class PluginSettingsStore:
    """
    Flat JSON-backed key/value store for plugin settings.
    Structure:  { "plugin_id": { "key": value, ... }, ... }
    """

    def __init__(self, path: str = _DEFAULT_PATH):
        self._path = path
        self._data: dict[str, dict[str, Any]] = {}
        self.load()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def load(self) -> None:
        if not os.path.exists(self._path):
            self._data = {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception as exc:
            logger.warning("Could not load plugin settings from %s: %s", self._path, exc)
            self._data = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as exc:
            logger.error("Could not save plugin settings to %s: %s", self._path, exc)

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    def get(self, plugin_id: str, key: str, default: Any = None) -> Any:
        return self._data.get(plugin_id, {}).get(key, default)

    def set(self, plugin_id: str, key: str, value: Any) -> None:
        self._data.setdefault(plugin_id, {})[key] = value
        self.save()

    def get_all(self, plugin_id: str) -> dict[str, Any]:
        return dict(self._data.get(plugin_id, {}))

    def set_all(self, plugin_id: str, settings: dict[str, Any]) -> None:
        self._data[plugin_id] = settings
        self.save()

    def delete(self, plugin_id: str) -> None:
        self._data.pop(plugin_id, None)
        self.save()


# Singleton
_store: PluginSettingsStore | None = None


def get_settings_store() -> PluginSettingsStore:
    global _store
    if _store is None:
        _store = PluginSettingsStore()
    return _store
