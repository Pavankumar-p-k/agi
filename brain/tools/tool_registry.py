from __future__ import annotations

import asyncio
import importlib
import logging
from typing import Any

from brain.executor.executor import executor, ActionResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Bridges the existing core/tools/ implementations into the brain.executor.

    Scans the existing `core/tools/implementations.py` for tool functions
    and registers them as async-compatible tools with the Executor.
    Also provides a discoverable list of available tools.
    """

    def __init__(self):
        self._tool_names: list[str] = []

    def register_implementation(self, name: str, module_path: str,
                                function_name: str) -> bool:
        """Register a tool from an existing implementation module.

        Args:
            name: Tool name for the Executor (e.g. 'create_file')
            module_path: Python module path (e.g. 'core.tools.document_tools')
            function_name: Function name in the module (e.g. 'do_create_document')
        """
        try:
            module = importlib.import_module(module_path)
            fn = getattr(module, function_name, None)
            if fn is None:
                logger.warning("[ToolRegistry] %s not found in %s", function_name, module_path)
                return False

            # Wrap sync functions for async execution
            if not asyncio.iscoroutinefunction(fn):

                async def _wrapper(**kwargs):
                    return await asyncio.to_thread(fn, **kwargs)

                _wrapper.__name__ = name
                executor.register_tool(name, _wrapper)
            else:
                executor.register_tool(name, fn)

            self._tool_names.append(name)
            logger.debug("[ToolRegistry] registered: %s -> %s.%s", name, module_path, function_name)
            return True

        except (ImportError, AttributeError) as e:
            logger.warning("[ToolRegistry] failed to register %s: %s", name, e)
            return False

    def register_direct(self, name: str, fn: Any) -> None:
        """Register a callable directly."""
        executor.register_tool(name, fn)
        self._tool_names.append(name)

    def list_tools(self) -> list[str]:
        return list(self._tool_names)

    def count(self) -> int:
        return len(self._tool_names)


def register_all_tools() -> ToolRegistry:
    """Register all available tools from the existing core/tools/ system.

    Call once at startup to make all tools available via the Executor.
    """
    reg = ToolRegistry()

    # File/document operations
    reg.register_implementation("create_file", "core.tools.document_tools", "do_create_document")
    reg.register_implementation("edit_file", "core.tools.document_tools", "do_edit_file")
    reg.register_implementation("read_file", "core.tools.document_tools", "do_read_file")

    # Search
    reg.register_implementation("search", "core.tools.document_tools", "do_semantic_search")

    # Settings
    reg.register_implementation("manage_settings", "core.tools.settings_tools", "do_manage_settings")

    # Skill management
    reg.register_implementation("create_skill", "core.tools.skill_tools", "do_create_skill")
    reg.register_implementation("manage_skills", "core.tools.skill_tools", "do_manage_skills")

    # Admin tools
    reg.register_implementation("manage_endpoints", "core.tools.admin_tools", "do_manage_endpoints")

    # Research
    reg.register_implementation("research", "core.tools.cookbook_tools", "do_trigger_research")

    logger.info("[ToolRegistry] registered %d tools from core/tools/", reg.count())
    return reg


tool_registry = ToolRegistry()
