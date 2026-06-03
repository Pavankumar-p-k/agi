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
            from pc_agent.computer_agent import ComputerAgent
            self._agent = ComputerAgent()
            logger.info("[PCAutomationPlugin] ComputerAgent acquired")
        except Exception as e:
            logger.warning("[PCAutomationPlugin] Could not acquire ComputerAgent: %s", e)
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
            command = params.get("command", action)
            logger.info("[PCAutomationPlugin] Executing: %.80s", command)
            result = await self._agent.execute_command(command)
            self._last_action = {"command": command[:80], "status": "ok"}
            return {"success": True, "result": str(result)}
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
