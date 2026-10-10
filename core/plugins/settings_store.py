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

"""core.plugins.settings_store — JSON-file-backed per-plugin settings."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PluginSettingsStore:
    """Simple key/value store scoped by plugin id, persisted as JSON."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    # ── API ─────────────────────────────────────────────────────────────────
    def set(self, plugin_id: str, key: str, value: Any) -> None:
        self._data.setdefault(plugin_id, {})[key] = value
        self._flush()

    def get(self, plugin_id: str, key: str, default: Any = None) -> Any:
        return self._data.get(plugin_id, {}).get(key, default)

    def get_all(self, plugin_id: str) -> dict[str, Any]:
        return dict(self._data.get(plugin_id, {}))

    def delete(self, plugin_id: str) -> None:
        self._data.pop(plugin_id, None)
        self._flush()


def get_settings_store() -> PluginSettingsStore:
    """Process-wide settings store at the default location."""
    global _singleton
    try:
        return _singleton  # noqa: PLW0603
    except NameError:
        _singleton = PluginSettingsStore(path=Path.home() / ".jarvis" / "plugin_settings.json")
        return _singleton


__all__ = ["PluginSettingsStore", "get_settings_store"]
