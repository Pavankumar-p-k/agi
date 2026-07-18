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
from typing import Any

from core.plugins import AutomationPlugin, PluginManifest

logger = logging.getLogger(__name__)


class Plugin(AutomationPlugin):
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)
        self._agent = None
        self._governance = None
        self._last_action = None

    async def on_load(self, app_state: dict | None = None) -> None:
        await super().on_load(app_state)
        try:
            from core.desktop.controller import desktop_controller
            self._agent = desktop_controller
            logger.info("[PCAutomationPlugin] DesktopController acquired")
        except Exception as e:
            logger.warning("[PCAutomationPlugin] Could not acquire DesktopController: %s", e)
        try:
            from governance.GovernanceValidator import GovernanceValidator
            self._governance = GovernanceValidator()
            logger.info("[PCAutomationPlugin] GovernanceValidator acquired")
        except Exception as e:
            logger.warning("[PCAutomationPlugin] Could not acquire GovernanceValidator: %s", e)

    async def on_unload(self) -> None:
        self._agent = None
        self._governance = None
        self._last_action = None
        await super().on_unload()

    async def on_governance_check(self, action: str, context: dict) -> dict | None:
        if not self._governance:
            return None
        try:
            result = self._governance.validate(action, context)
            if not result.get("allowed", True):
                logger.warning("[PCAutomationPlugin] Governance blocked: %s", action[:80])
                return {"allowed": False, "reason": result.get("reason", "Governance violation")}
            return {"allowed": True}
        except Exception as e:
            logger.warning("[PCAutomationPlugin] Governance check failed: %s", e)
            return {"allowed": False, "reason": f"Governance error: {e}"}

    async def on_execute(self, action: str, params: dict) -> dict | None:
        if not self._agent:
            return None
        try:
            command = params.get("command", action).strip().lower()
            logger.info("[PCAutomationPlugin] Executing: %.80s", command)

            from core.desktop.controller import desktop_controller

            if command.startswith("open ") or command.startswith("launch "):
                app = command[5:] if command.startswith("open ") else command[7:]
                result = desktop_controller.launch_app(app.strip())
                self._last_action = {"command": command[:80], "status": "ok" if result.success else "failed"}
                return {"success": result.success, "result": result.details or f"Launched {app}"}
            if command.startswith("http://") or command.startswith("https://"):
                result = desktop_controller.open_url(command)
                self._last_action = {"command": command[:80], "status": "ok" if result.success else "failed"}
                return {"success": result.success, "result": f"Opened URL" if result.success else result.error}

            self._last_action = {"command": command[:80], "status": "unknown"}
            return {"success": False, "error": f"Unknown command: {command}"}
        except Exception as e:
            logger.warning("[PCAutomationPlugin] Execution failed: %s", e)
            self._last_action = {"command": action[:80], "status": "failed"}
            return {"success": False, "error": str(e)}

    async def health_check(self) -> dict:
        base = await super().health_check()
        base["agent_ready"] = self._agent is not None
        base["governance_ready"] = self._governance is not None
        base["last_action"] = self._last_action
        return base
