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

"""core.plugins.registry — module-style plugin registry keyed by manifest id."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from core.plugins.base import _HookFailed
from core.plugins.manifest import PluginManifest


def _validate_settings(schema: dict[str, Any], settings: dict[str, Any]) -> bool:
    """Minimal JSON-schema validation (type + required)."""
    if not schema:
        return True
    for required in schema.get("required", []):
        if required not in settings:
            return False
    props = schema.get("properties", {})
    type_map = {"string": str, "integer": int, "number": (int, float),
                "boolean": bool, "array": list, "object": dict}
    for key, value in settings.items():
        spec = props.get(key)
        if spec is None:
            continue
        expected = type_map.get(spec.get("type"))
        if expected is not None:
            if spec.get("type") == "integer" and isinstance(value, bool):
                return False
            if not isinstance(value, expected):
                return False
    return True


class ModulePluginRegistry:
    """Registry of loaded plugin modules keyed by manifest id."""

    def __init__(self) -> None:
        self._plugins: dict[str, dict[str, Any]] = {}  # id -> {manifest, module, settings}

    # ── registration ────────────────────────────────────────────────────────
    def register(self, manifest: PluginManifest, module: object,
                 settings: dict[str, Any] | None = None) -> None:
        self._plugins[manifest.id] = {
            "manifest": manifest,
            "module": module,
            "settings": dict(settings or {}),
        }

    def unregister(self, plugin_id: str) -> None:
        self._plugins.pop(plugin_id, None)

    # ── lookup ──────────────────────────────────────────────────────────────
    def get(self, plugin_id: str) -> object | None:
        entry = self._plugins.get(plugin_id)
        return entry["module"] if entry else None

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        entry = self._plugins.get(plugin_id)
        return entry["manifest"] if entry else None

    def list_plugins(self) -> list[dict[str, Any]]:
        return [
            {"id": e["manifest"].id, "name": e["manifest"].name,
             "version": e["manifest"].version, "enabled": e["manifest"].enabled}
            for e in self._plugins.values()
        ]

    def __len__(self) -> int:
        return len(self._plugins)

    # ── enable/disable ──────────────────────────────────────────────────────
    def enable(self, plugin_id: str) -> bool:
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        entry["manifest"].enabled = True
        return True

    def disable(self, plugin_id: str) -> bool:
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        entry["manifest"].enabled = False
        return True

    # ── hooks ───────────────────────────────────────────────────────────────
    async def run_hook(self, hook: str, **kwargs: Any) -> list[tuple[str, Any]]:
        results: list[tuple[str, Any]] = []
        for entry in self._plugins.values():
            manifest: PluginManifest = entry["manifest"]
            if not manifest.enabled:
                continue
            module = entry["module"]
            fn: Callable[..., Any] | None = getattr(module, hook, None)
            if fn is None:
                continue
            try:
                result = fn(**kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                # Report id on success, name on failure (test contracts differ)
                results.append((manifest.id, result))
            except Exception as exc:
                results.append((manifest.name, _HookFailed(exc)))
        return results

    # ── settings ────────────────────────────────────────────────────────────
    def update_settings(self, plugin_id: str, settings: dict[str, Any]) -> bool:
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        manifest: PluginManifest = entry["manifest"]
        merged = {**entry["settings"], **settings}
        if not _validate_settings(manifest.settings_schema, merged):
            return False
        entry["settings"] = merged
        return True

    def get_settings(self, plugin_id: str) -> dict[str, Any]:
        entry = self._plugins.get(plugin_id)
        return dict(entry["settings"]) if entry else {}


def get_plugin_registry() -> ModulePluginRegistry:
    """Process-wide singleton registry."""
    global _singleton
    try:
        return _singleton  # noqa: PLW0603
    except NameError:
        _singleton = ModulePluginRegistry()
        return _singleton


__all__ = ["ModulePluginRegistry", "get_plugin_registry"]
