import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_PLUGIN_TOOL_HANDLERS: dict[str, Callable[..., Awaitable[tuple[str, dict]]]] = {}


def register_plugin_tool(name: str, handler: Callable[..., Awaitable[tuple[str, dict]]]) -> None:
    _PLUGIN_TOOL_HANDLERS[name] = handler
    logger.info("[PluginTools] Registered plugin tool: %s", name)


def unregister_plugin_tool(name: str) -> None:
    _PLUGIN_TOOL_HANDLERS.pop(name, None)
    logger.info("[PluginTools] Unregistered plugin tool: %s", name)
