from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.plugins.base import Plugin, PluginManifest, PluginRegistry

logger = logging.getLogger(__name__)


class MockPluginRegistry(PluginRegistry):
    def __init__(self):
        super().__init__(strict_sandbox=False)
        self._hook_log: list[tuple[str, str, dict]] = []

    async def run_hook(self, hook: str, **kwargs: Any) -> list[tuple[str, Any]]:
        results = []
        for plugin in self.list_by_hook(hook):
            hook_fn = getattr(plugin, hook, None)
            if hook_fn is None:
                continue
            try:
                result = await hook_fn(**kwargs)
                results.append((plugin.manifest.name, result))
                self._hook_log.append((hook, plugin.manifest.name, kwargs))
            except Exception as e:
                self._hook_log.append((hook, plugin.manifest.name, {"error": str(e)}))
                results.append((plugin.manifest.name, None))
        return results

    @property
    def hook_log(self) -> list[tuple[str, str, dict]]:
        return list(self._hook_log)

    def clear_hook_log(self) -> None:
        self._hook_log.clear()


def create_test_plugin(
    name: str = "test.plugin",
    version: str = "1.0.0",
    hooks: list[str] | None = None,
) -> Plugin:
    class _TestPlugin(Plugin):
        async def on_load(self, app_state: dict | None = None) -> None:
            self._load_called = True
            await super().on_load(app_state)

        async def on_unload(self) -> None:
            self._unload_called = True
            await super().on_unload()

    p = _TestPlugin(PluginManifest(
        name=name,
        version=version,
        description="Test plugin",
        hooks=hooks or ["on_load", "on_unload"],
    ))
    p._load_called = False
    p._unload_called = False
    return p


def create_test_registry() -> tuple[MockPluginRegistry, list[Plugin]]:
    registry = MockPluginRegistry()
    return registry, []


async def run_hook_test(
    registry: MockPluginRegistry,
    hook: str,
    **kwargs: Any,
) -> list[tuple[str, Any]]:
    return await registry.run_hook(hook, **kwargs)


def assert_hook_called(registry: MockPluginRegistry, hook: str, plugin_name: str) -> bool:
    return any(h == hook and p == plugin_name for h, p, _ in registry.hook_log)


def assert_hook_not_called(registry: MockPluginRegistry, hook: str, plugin_name: str) -> bool:
    return not any(h == hook and p == plugin_name for h, p, _ in registry.hook_log)


def create_plugin_manifest(
    name: str = "test.plugin",
    version: str = "1.0.0",
    dependencies: list[str] | None = None,
) -> PluginManifest:
    return PluginManifest(
        name=name,
        version=version,
        description=f"Test: {name}",
        dependencies=dependencies or [],
    )
