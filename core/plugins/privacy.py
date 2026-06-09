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

import inspect
import logging

from core.plugins.base import Plugin, PluginManifest

logger = logging.getLogger(__name__)


class PrivacyPlugin(Plugin):
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)
        self._redact_hooks: list = []
        self._audit_hooks: list = []
        self._routing_hooks: list = []

    async def on_load(self, app_state: dict | None = None) -> None:
        await super().on_load(app_state)
        logger.info("[PrivacyPlugin] %s registered: %d hooks", self.manifest.name, self._hook_count())

    async def on_unload(self) -> None:
        self._redact_hooks.clear()
        self._audit_hooks.clear()
        self._routing_hooks.clear()
        await super().on_unload()

    def _hook_count(self) -> int:
        return len(self._redact_hooks) + len(self._audit_hooks) + len(self._routing_hooks)

    def register_redact_hook(self, hook: callable) -> None:
        self._redact_hooks.append(hook)

    def register_audit_hook(self, hook: callable) -> None:
        self._audit_hooks.append(hook)

    def register_routing_hook(self, hook: callable) -> None:
        self._routing_hooks.append(hook)

    async def on_redact(self, text: str, context: dict | None = None) -> str | None:
        for hook in self._redact_hooks:
            try:
                result = await hook(text, context) if inspect.iscoroutinefunction(hook) else hook(text, context)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception("[PrivacyPlugin] Redact hook failed: %s", e)
        return None

    async def on_audit(self, event: dict) -> None:
        for hook in self._audit_hooks:
            try:
                if inspect.iscoroutinefunction(hook):
                    await hook(event)
                else:
                    hook(event)
            except Exception as e:
                logger.exception("[PrivacyPlugin] Audit hook failed: %s", e)

    async def on_routing_decision(self, tier: str, text: str, metadata: dict) -> str | None:
        for hook in self._routing_hooks:
            try:
                result = await hook(tier, text, metadata) if inspect.iscoroutinefunction(hook) else hook(tier, text, metadata)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception("[PrivacyPlugin] Routing hook failed: %s", e)
        return None

    async def health_check(self) -> dict:
        base = await super().health_check()
        base["redact_hooks"] = len(self._redact_hooks)
        base["audit_hooks"] = len(self._audit_hooks)
        base["routing_hooks"] = len(self._routing_hooks)
        return base
