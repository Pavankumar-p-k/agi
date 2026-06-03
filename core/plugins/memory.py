from __future__ import annotations

import inspect
import logging
from typing import Any

from core.plugins.base import Plugin, PluginManifest

logger = logging.getLogger(__name__)


class MemoryPlugin(Plugin):
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)
        self._store_hooks: list = []
        self._recall_hooks: list = []
        self._consolidate_hooks: list = []

    async def on_load(self, app_state: dict | None = None) -> None:
        await super().on_load(app_state)
        logger.info("[MemoryPlugin] %s registered: %d hooks", self.manifest.name, self._hook_count())

    async def on_unload(self) -> None:
        self._store_hooks.clear()
        self._recall_hooks.clear()
        self._consolidate_hooks.clear()
        await super().on_unload()

    def _hook_count(self) -> int:
        return len(self._store_hooks) + len(self._recall_hooks) + len(self._consolidate_hooks)

    def register_store_hook(self, hook: callable) -> None:
        self._store_hooks.append(hook)

    def register_recall_hook(self, hook: callable) -> None:
        self._recall_hooks.append(hook)

    def register_consolidate_hook(self, hook: callable) -> None:
        self._consolidate_hooks.append(hook)

    async def on_store(self, memory: dict) -> str | None:
        for hook in self._store_hooks:
            try:
                result = await hook(memory) if inspect.iscoroutinefunction(hook) else hook(memory)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception("[MemoryPlugin] Store hook failed: %s", e)
        return None

    async def on_recall(self, query: str, limit: int = 10) -> list | None:
        for hook in self._recall_hooks:
            try:
                result = await hook(query, limit) if inspect.iscoroutinefunction(hook) else hook(query, limit)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception("[MemoryPlugin] Recall hook failed: %s", e)
        return None

    async def on_consolidate(self) -> None:
        for hook in self._consolidate_hooks:
            try:
                if inspect.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                logger.exception("[MemoryPlugin] Consolidate hook failed: %s", e)

    async def health_check(self) -> dict:
        base = await super().health_check()
        base["store_hooks"] = len(self._store_hooks)
        base["recall_hooks"] = len(self._recall_hooks)
        base["consolidate_hooks"] = len(self._consolidate_hooks)
        return base
