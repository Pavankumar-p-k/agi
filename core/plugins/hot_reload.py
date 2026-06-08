from __future__ import annotations

import importlib
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

from core.plugins.base import Plugin

logger = logging.getLogger(__name__)


class _FileSnapshot:
    def __init__(self, path: Path):
        self.path = path
        self._mtime: float = 0.0
        self._size: int = 0
        self._refresh()

    def _refresh(self) -> None:
        try:
            s = self.path.stat()
            self._mtime = s.st_mtime
            self._size = s.st_size
        except OSError:
            self._mtime = 0.0
            self._size = 0

    def changed(self) -> bool:
        old_mtime, old_size = self._mtime, self._size
        self._refresh()
        return self._mtime != old_mtime or self._size != old_size

    def __repr__(self) -> str:
        return f"_FileSnapshot({self.path.name}, mtime={self._mtime})"


class _ModuleTracker:
    def __init__(self, module_name: str, path: Path):
        self.module_name = module_name
        self.file = _FileSnapshot(path)
        self.loaded = False

    def changed(self) -> bool:
        return self.file.changed()


class HotReloader:
    def __init__(self, registry=None, poll_interval: float = 2.0):
        self._registry = registry
        self._poll_interval = poll_interval
        self._tracked: dict[str, _ModuleTracker] = {}
        self._config_files: list[_FileSnapshot] = []
        self._watcher_task: asyncio.Task | None = None
        self._running = False
        self._reload_callbacks: list[Callable] = []
        self._on_config_change: list[Callable] = []
        self._last_reload: dict[str, float] = {}
        self._debounce_seconds = 1.0

    @property
    def is_running(self) -> bool:
        return self._running

    def set_registry(self, registry) -> None:
        self._registry = registry

    def track_plugin(self, plugin_name: str, module_name: str | None = None, file_path: str | Path | None = None) -> None:
        if module_name is None:
            module_name = plugin_name
        if file_path is None:
            for mod_name, mod in sys.modules.items():
                if mod_name == module_name or mod_name.endswith("." + module_name):
                    try:
                        f = getattr(mod, "__file__", None)
                        if f:
                            file_path = Path(f)
                            break
                    except Exception as _e:
                        logger.debug("plugins hot_reload resolve path failed: %s", _e)
                        continue
        if file_path is None:
            logger.warning("[HotReload] Cannot resolve path for plugin %s (module %s)", plugin_name, module_name)
            return
        self._tracked[plugin_name] = _ModuleTracker(module_name, Path(file_path))
        logger.info("[HotReload] Tracking plugin %s -> %s", plugin_name, file_path)

    def untrack_plugin(self, plugin_name: str) -> None:
        self._tracked.pop(plugin_name, None)

    def watch_config(self, path: str | Path) -> None:
        p = Path(path)
        if p.exists():
            self._config_files.append(_FileSnapshot(p))
            logger.info("[HotReload] Watching config: %s", p)
        else:
            logger.warning("[HotReload] Config not found: %s", p)

    def on_reload(self, callback: Callable) -> None:
        self._reload_callbacks.append(callback)

    def on_config_change(self, callback: Callable) -> None:
        self._on_config_change.append(callback)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._watcher_task = asyncio.create_task(self._poll_loop())
        logger.info("[HotReload] Started (interval=%ss)", self._poll_interval)

    async def stop(self) -> None:
        self._running = False
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass
            self._watcher_task = None
        logger.info("[HotReload] Stopped")

    async def reload_plugin(self, plugin_name: str) -> bool:
        if not self._registry:
            logger.warning("[HotReload] No registry set")
            return False
        tracker = self._tracked.get(plugin_name)
        if not tracker:
            logger.warning("[HotReload] Plugin %s not tracked", plugin_name)
            return False

        now = time.monotonic()
        last = self._last_reload.get(plugin_name, 0.0)
        if now - last < self._debounce_seconds:
            return False
        self._last_reload[plugin_name] = now

        plugin = self._registry.get(plugin_name)
        if plugin is None:
            logger.warning("[HotReload] Plugin %s not in registry", plugin_name)
            return False

        try:
            logger.info("[HotReload] Reloading %s ...", plugin_name)
            await plugin.on_unload()
            old_routes = list(plugin.http_routes)
            old_tools = dict(plugin.tools)

            mod = sys.modules.get(tracker.module_name)
            if mod:
                importlib.reload(mod)
                new_class = getattr(mod, "Plugin", None)
                if new_class and issubclass(new_class, Plugin):
                    from core.plugins.api import PluginAPI
                    new_instance = new_class(plugin.manifest)
                    new_instance._api = PluginAPI(plugin=new_instance)
                    if hasattr(plugin, "_config"):
                        new_instance._config = dict(plugin._config)
                    self._registry._plugins[plugin_name] = new_instance
                    app_state = getattr(self._registry, "_app_state", None)
                    await new_instance.on_load(app_state or {})
                    for cb in self._reload_callbacks:
                        try:
                            await cb(plugin_name, old_routes, old_tools, new_instance)
                        except Exception as e:
                            logger.warning("[HotReload] Reload callback failed: %s", e)
                    logger.info("[HotReload] %s reloaded successfully", plugin_name)
                    return True
                else:
                    logger.warning("[HotReload] No Plugin class in reloaded module %s", tracker.module_name)
                    await plugin.on_load()
                    return False
            else:
                logger.warning("[HotReload] Module %s not in sys.modules", tracker.module_name)
                return False
        except Exception as e:
            logger.exception("[HotReload] Failed to reload %s: %s", plugin_name, e)
            return False

    async def reload_all(self) -> dict[str, bool]:
        results = {}
        for name in list(self._tracked.keys()):
            results[name] = await self.reload_plugin(name)
        return results

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._check_plugin_files()
                await self._check_config_files()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[HotReload] Poll error: %s", e)
            await asyncio.sleep(self._poll_interval)

    async def _check_plugin_files(self) -> None:
        for plugin_name, tracker in list(self._tracked.items()):
            if tracker.changed():
                logger.info("[HotReload] Detected change in %s (%s)", plugin_name, tracker.file.path)
                await self.reload_plugin(plugin_name)

    async def _check_config_files(self) -> None:
        for cf in self._config_files:
            if cf.changed():
                logger.info("[HotReload] Config changed: %s", cf.path)
                for cb in self._on_config_change:
                    try:
                        await cb(str(cf.path))
                    except Exception as e:
                        logger.warning("[HotReload] Config change callback failed: %s", e)
