# core/plugins/registry.py
# Thin backward-compatible re-export — the canonical PluginRegistry is now in base.py.
from core.plugins.base import PluginRegistry, plugin_registry, _validate_json_schema


ModulePluginRegistry = PluginRegistry


def get_plugin_registry() -> PluginRegistry:
    return plugin_registry
