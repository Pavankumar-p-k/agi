from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.plugins.base import PluginRegistry

logger = logging.getLogger(__name__)


class PluginWatchdog:
    """Background watchdog that periodically checks plugin health
    and disables unresponsive plugins.

    Runs as an asyncio task.  Uses ``plugin_registry.run_hook("health_check")``
    and marks any plugin that fails or times out consecutively as unhealthy.
    After ``max_failures`` consecutive failures the plugin is automatically
    disabled.
    """

    def __init__(
        self,
        registry: PluginRegistry,
        interval: float = 30.0,
        max_failures: int = 3,
    ):
        self._registry = registry
        self._interval = interval
        self._max_failures = max_failures
        self._failure_count: dict[str, int] = {}
        self._task: asyncio.Task | None = None
        self._enabled = False

    @property
    def is_running(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if self._enabled:
            return
        self._enabled = True
        self._task = asyncio.ensure_future(self._run())
        logger.info("[PluginWatchdog] Started (interval=%ss, max_failures=%d)", self._interval, self._max_failures)

    async def stop(self) -> None:
        self._enabled = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("[PluginWatchdog] Stopped")

    async def _run(self) -> None:
        while self._enabled:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("[PluginWatchdog] Tick failed")
            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        for name, plugin in self._registry.plugins.items():
            if not plugin.enabled:
                continue
            try:
                result = await plugin.health_check()
                healthy = result.get("healthy", False)
            except Exception:
                healthy = False

            if healthy:
                self._failure_count.pop(name, None)
            else:
                count = self._failure_count.get(name, 0) + 1
                self._failure_count[name] = count
                logger.warning(
                    "[PluginWatchdog] %s health check failed (%d/%d)",
                    name, count, self._max_failures,
                )
                if count >= self._max_failures:
                    logger.error("[PluginWatchdog] Disabling unresponsive plugin: %s", name)
                    try:
                        await self._registry.disable_plugin(name)
                    except Exception as e:
                        logger.error("[PluginWatchdog] Failed to disable %s: %s", name, e)
                    self._failure_count.pop(name, None)
