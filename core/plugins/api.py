from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING


if TYPE_CHECKING:
    from core.plugins.base import Plugin

logger = logging.getLogger(__name__)

# Global CLI command registry populated by PluginAPI.register_cli_command.
# Maps command_name -> {handler, help_text, category, plugin_name}
CLI_COMMANDS: dict[str, dict] = {}


def get_cli_commands() -> dict[str, dict]:
    return dict(CLI_COMMANDS)


@dataclass
class PluginAPI:
    """Restricted API surface exposed to plugins.

    Plugins receive only this object — NOT access to ``core`` internals,
    ``os``, ``subprocess``, or the filesystem.  Import checks are handled
    by ``core.plugins.sandbox`` at load time.
    """

    plugin: Plugin
    brain: Any = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("plugin"))

    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable,
        input_schema: dict | None = None,
        category: str = "general",
    ) -> None:
        self.plugin._tools[name] = {
            "name": name,
            "description": description,
            "handler": handler,
            "input_schema": input_schema or {},
            "category": category,
        }
        logger.debug("[PluginAPI] %s registered tool: %s", self.plugin.manifest.name, name)

    def register_http_route(self, method: str, path: str, handler: Callable) -> None:
        self.plugin._http_routes.append((method, path, handler))
        logger.debug("[PluginAPI] %s registered route: %s %s", self.plugin.manifest.name, method, path)

    def register_provider(
        self,
        provider_type: str,
        name: str,
        models: list[str],
        handler: Callable | None = None,
    ) -> None:
        self.plugin._providers.append({
            "type": provider_type,
            "name": name,
            "models": models,
            "handler": handler,
        })
        logger.debug("[PluginAPI] %s registered provider: %s/%s", self.plugin.manifest.name, provider_type, name)

    def register_service(self, service_id: str, instance: Any) -> None:
        self.plugin._services[service_id] = instance
        logger.debug("[PluginAPI] %s registered service: %s", self.plugin.manifest.name, service_id)

    def register_channel(self, channel: Any) -> None:
        self.plugin._channels.append(channel)
        logger.debug("[PluginAPI] %s registered channel: %s", self.plugin.manifest.name, channel.id if hasattr(channel, "id") else "?")

    def register_cli_command(
        self,
        name: str,
        handler: Callable[[str], str],
        help_text: str = "",
        category: str = "custom",
    ) -> None:
        CLI_COMMANDS[name] = {
            "handler": handler,
            "help_text": help_text,
            "category": category,
            "plugin_name": self.plugin.manifest.name,
        }
        logger.debug(
            "[PluginAPI] %s registered CLI command /%s (%s)",
            self.plugin.manifest.name, name, category,
        )

    @property
    def config(self) -> dict:
        return dict(self.plugin._config)
