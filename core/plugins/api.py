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

"""core.plugins.api — public plugin API surface, including CLI command registration."""
from __future__ import annotations

from typing import Any, Callable

from core.plugins.base import Plugin, PluginManifest, PluginRegistry, plugin_registry

# name -> {"handler": callable, "help_text": str, "category": str, "plugin_name": str}
CLI_COMMANDS: dict[str, dict[str, Any]] = {}


def register_cli_command(
    name: str,
    handler: Callable[..., Any],
    *,
    help_text: str = "",
    category: str = "custom",
    plugin_name: str = "",
) -> None:
    CLI_COMMANDS[name] = {
        "handler": handler,
        "help_text": help_text,
        "category": category,
        "plugin_name": plugin_name,
    }


def get_cli_commands() -> dict[str, dict[str, Any]]:
    return dict(CLI_COMMANDS)


def dispatch_cli_command(name: str, text: str) -> Any:
    entry = CLI_COMMANDS.get(name)
    if entry is None:
        return None
    return entry["handler"](text)


class PluginAPI:
    """Facade handed to plugins so they can register capabilities."""

    def __init__(self, plugin: Plugin, registry: PluginRegistry | None = None) -> None:
        self._plugin = plugin
        self._registry = registry or plugin_registry

    def register_cli_command(self, name: str, handler: Callable[..., Any], *,
                             help_text: str = "", category: str = "custom") -> None:
        register_cli_command(
            name, handler,
            help_text=help_text, category=category,
            plugin_name=self._plugin.manifest.name,
        )

    def register_http_route(self, method: str, path: str, handler: Callable[..., Any]) -> None:
        self._plugin.register_http_route(method, path, handler)

    @property
    def plugin(self) -> Plugin:
        return self._plugin


__all__ = [
    "CLI_COMMANDS", "PluginAPI",
    "register_cli_command", "get_cli_commands", "dispatch_cli_command",
    "Plugin", "PluginManifest", "PluginRegistry", "plugin_registry",
]
