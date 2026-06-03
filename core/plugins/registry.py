# core/plugins/registry.py
# PluginRegistry — singleton that tracks all loaded plugins and dispatches hooks.
from __future__ import annotations
import asyncio
import inspect
import json
import logging
from typing import Any

from .manifest import PluginManifest
from .settings_store import get_settings_store

logger = logging.getLogger("jarvis.plugins.registry")


class _PluginRecord:
    __slots__ = ("manifest", "module")

    def __init__(self, manifest: PluginManifest, module: Any):
        self.manifest = manifest
        self.module   = module


class PluginRegistry:
    """Singleton registry for all loaded JARVIS plugins."""

    def __init__(self):
        self._plugins: dict[str, _PluginRecord] = {}
        self._settings = get_settings_store()

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #

    def register(self, manifest: PluginManifest, module: Any) -> None:
        self._plugins[manifest.id] = _PluginRecord(manifest, module)
        logger.info("Registered plugin: %s v%s", manifest.id, manifest.version)

    def unregister(self, plugin_id: str) -> None:
        self._plugins.pop(plugin_id, None)

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #

    def get(self, plugin_id: str) -> Any | None:
        record = self._plugins.get(plugin_id)
        return record.module if record else None

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        record = self._plugins.get(plugin_id)
        return record.manifest if record else None

    def list_plugins(self) -> list[dict]:
        return [
            {
                "id":      r.manifest.id,
                "name":    r.manifest.name,
                "version": r.manifest.version,
                "enabled": r.manifest.enabled,
                "hooks":   r.manifest.hooks,
            }
            for r in self._plugins.values()
        ]

    # ------------------------------------------------------------------ #
    # Enable / Disable
    # ------------------------------------------------------------------ #

    def enable(self, plugin_id: str) -> bool:
        record = self._plugins.get(plugin_id)
        if not record:
            return False
        record.manifest.enabled = True
        logger.info("Plugin enabled: %s", plugin_id)
        return True

    def disable(self, plugin_id: str) -> bool:
        record = self._plugins.get(plugin_id)
        if not record:
            return False
        record.manifest.enabled = False
        logger.info("Plugin disabled: %s", plugin_id)
        return True

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #

    def get_settings(self, plugin_id: str) -> dict:
        return self._settings.get_all(plugin_id)

    def update_settings(self, plugin_id: str, settings: dict) -> bool:
        record = self._plugins.get(plugin_id)
        if not record:
            logger.warning("update_settings: unknown plugin %s", plugin_id)
            return False
        schema = record.manifest.settings_schema
        if schema:
            ok, err = _validate_json_schema(settings, schema)
            if not ok:
                logger.error("Settings validation failed for %s: %s", plugin_id, err)
                return False
        self._settings.set_all(plugin_id, settings)
        return True

    # ------------------------------------------------------------------ #
    # Hook dispatch
    # ------------------------------------------------------------------ #

    async def run_hook(self, hook_name: str, **kwargs) -> list[tuple[str, Any]]:
        """
        Call every enabled plugin subscribed to *hook_name*.
        Returns [(plugin_id, result), ...].
        Plugin errors are caught and logged — never propagated.
        """
        results: list[tuple[str, Any]] = []
        for record in list(self._plugins.values()):
            if not record.manifest.enabled:
                continue
            if hook_name not in record.manifest.hooks:
                continue
            handler = getattr(record.module, hook_name, None)
            if handler is None:
                continue
            try:
                if inspect.iscoroutinefunction(handler):
                    result = await handler(**kwargs)
                else:
                    result = handler(**kwargs)
                results.append((record.manifest.id, result))
            except Exception as exc:
                logger.error(
                    "Plugin %s raised in hook %s: %s",
                    record.manifest.id, hook_name, exc, exc_info=True
                )
        return results


# ------------------------------------------------------------------ #
# JSON Schema mini-validator (no external deps)
# ------------------------------------------------------------------ #

def _validate_json_schema(data: dict, schema: dict) -> tuple[bool, str]:
    """Minimal validation: checks 'required' fields and basic types."""
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    for field in required:
        if field not in data:
            return False, f"Missing required field: {field}"
    for key, val in data.items():
        prop_schema = properties.get(key, {})
        expected_type = prop_schema.get("type")
        if expected_type:
            type_map = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
            py_type = type_map.get(expected_type)
            if py_type and not isinstance(val, py_type):
                return False, f"Field '{key}' expected {expected_type}, got {type(val).__name__}"
    return True, ""


# ------------------------------------------------------------------ #
# Singleton
# ------------------------------------------------------------------ #

_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


# Backward-compatible alias: `from core.plugins import plugin_registry`
plugin_registry: PluginRegistry = None  # type: ignore

def _init_alias():
    global plugin_registry
    plugin_registry = get_plugin_registry()

_init_alias()
