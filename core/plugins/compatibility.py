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
from __future__ import annotations

import logging
from enum import StrEnum

from .errors import PluginDependencyError

logger = logging.getLogger("jarvis.plugins.compatibility")

try:
    from packaging.version import InvalidVersion, Version
except ImportError:
    Version = None  # type: ignore
    InvalidVersion = ValueError  # type: ignore


class CompatibilityMode(StrEnum):
    STRICT = "strict"
    WARN = "warn"
    OFF = "off"


class CompatibilityChecker:
    """Enforce min_jarvis_version and plugin API compatibility.

    Phases 3b: Version enforcement for plugins.
    Checks that a plugin's ``min_jarvis_version`` is satisfied by the
    current JARVIS version, and that the plugin's hook set matches
    the expected API surface.
    """

    def __init__(self, current_version: str = "1.0.0", mode: str = "warn"):
        self._current_version = current_version
        self._mode = CompatibilityMode(mode)
        self._known_hooks: set[str] = {
            "on_load", "on_unload", "on_enable", "on_disable",
            "on_install", "on_uninstall",
            "before_model_resolve", "llm_input", "llm_output",
            "message_received", "before_dispatch",
            "session_start", "session_end",
            "after_tool_call",
            "on_stt", "on_tts", "on_wake_word",
            "on_execute", "on_governance_check",
            "on_routing_decision", "on_redact",
            "on_store", "on_recall", "on_consolidate",
        }

    def check_version(self, plugin_id: str, min_version: str) -> bool:
        """Check if *min_version* is compatible with the current JARVIS version.

        Returns True if compatible.
        If mode is STRICT and incompatible, raises PluginDependencyError.
        If mode is WARN and incompatible, logs a warning and returns False.
        If mode is OFF, always returns True.
        """
        if self._mode == CompatibilityMode.OFF:
            return True

        if not Version:
            logger.warning("packaging library not available — skipping version check")
            return True

        try:
            current = Version(self._current_version)
            required = Version(min_version)
        except InvalidVersion:
            logger.warning("Invalid version string: current=%s required=%s", self._current_version, min_version)
            return True

        if current >= required:
            return True

        msg = f"Plugin '{plugin_id}' requires JARVIS >= {min_version} (current: {self._current_version})"
        if self._mode == CompatibilityMode.STRICT:
            raise PluginDependencyError(dependency=plugin_id, message=msg)

        logger.warning("[COMPAT] %s", msg)
        return False

    def check_hooks(self, plugin_id: str, hooks: list[str]) -> list[str]:
        """Check that all declared hooks are known to this JARVIS version.

        Returns a list of unknown hooks (empty = all known).
        Unknown hooks are ignored at runtime but logged.
        """
        unknown = [h for h in hooks if h not in self._known_hooks]
        if unknown:
            logger.warning(
                "[COMPAT] Plugin '%s' declares unknown hooks: %s — these will be ignored",
                plugin_id, unknown,
            )
        return unknown

    def check(self, plugin_id: str, min_version: str, hooks: list[str]) -> bool:
        """Run all compatibility checks for a plugin.

        Returns True if all checks pass (or mode is OFF).
        """
        version_ok = self.check_version(plugin_id, min_version)
        self.check_hooks(plugin_id, hooks)
        return version_ok


compatibility_checker = CompatibilityChecker()
