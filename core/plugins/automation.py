from __future__ import annotations

import inspect
import logging
from typing import Any

from core.plugins.base import Plugin, PluginManifest

logger = logging.getLogger(__name__)


class AutomationPlugin(Plugin):
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)
        self._exec_hooks: list = []
        self._governance_hooks: list = []
        self._playbook_hooks: list = []

    async def on_load(self, app_state: dict | None = None) -> None:
        await super().on_load(app_state)
        logger.info("[AutomationPlugin] %s registered: %d hooks", self.manifest.name, self._hook_count())

    async def on_unload(self) -> None:
        self._exec_hooks.clear()
        self._governance_hooks.clear()
        self._playbook_hooks.clear()
        await super().on_unload()

    def _hook_count(self) -> int:
        return len(self._exec_hooks) + len(self._governance_hooks) + len(self._playbook_hooks)

    def register_exec_hook(self, hook: callable) -> None:
        self._exec_hooks.append(hook)

    def register_governance_hook(self, hook: callable) -> None:
        self._governance_hooks.append(hook)

    def register_playbook_hook(self, hook: callable) -> None:
        self._playbook_hooks.append(hook)

    async def on_execute(self, action: str, params: dict) -> dict | None:
        for hook in self._exec_hooks:
            try:
                result = await hook(action, params) if inspect.iscoroutinefunction(hook) else hook(action, params)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception("[AutomationPlugin] Exec hook failed: %s", e)
        return None

    async def on_governance_check(self, action: str, context: dict) -> dict | None:
        for hook in self._governance_hooks:
            try:
                result = await hook(action, context) if inspect.iscoroutinefunction(hook) else hook(action, context)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception("[AutomationPlugin] Governance hook failed: %s", e)
        return None

    async def on_playbook(self, playbook_name: str, params: dict) -> dict | None:
        for hook in self._playbook_hooks:
            try:
                result = await hook(playbook_name, params) if inspect.iscoroutinefunction(hook) else hook(playbook_name, params)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception("[AutomationPlugin] Playbook hook failed: %s", e)
        return None

    async def health_check(self) -> dict:
        base = await super().health_check()
        base["exec_hooks"] = len(self._exec_hooks)
        base["governance_hooks"] = len(self._governance_hooks)
        base["playbook_hooks"] = len(self._playbook_hooks)
        return base
