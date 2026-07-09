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
# core/plugins/loader.py
# PluginLoader — scans directories, dynamically loads modules, hot-reloads.
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys

from .compatibility import compatibility_checker
from .dependencies import dependency_resolver
from .manifest import PluginManifest
from .registry import get_plugin_registry

logger = logging.getLogger("jarvis.plugins.loader")

_MANIFEST_NAMES = ("plugin.json", "skill.json")


class PluginLoader:
    """
    Loads plugins from directories containing plugin.json / skill.json manifests.
    """

    def __init__(self):
        self._registry = get_plugin_registry()

    # ------------------------------------------------------------------ #
    # Scanning
    # ------------------------------------------------------------------ #

    def scan_directory(self, path: str) -> list[PluginManifest]:
        """
        Recursively scan *path* for plugin.json / skill.json files.
        Returns a list of parsed PluginManifest objects.
        """
        manifests: list[PluginManifest] = []
        if not os.path.isdir(path):
            logger.warning("scan_directory: %s does not exist", path)
            return manifests

        for root, _dirs, files in os.walk(path):
            for fname in files:
                if fname in _MANIFEST_NAMES:
                    full_path = os.path.join(root, fname)
                    try:
                        m = PluginManifest.from_file(full_path)
                        manifests.append(m)
                        logger.debug("Found manifest: %s (%s)", m.id, full_path)
                    except Exception as exc:
                        logger.error("Bad manifest at %s: %s", full_path, exc)
        return manifests

    # ------------------------------------------------------------------ #
    # Load / Unload / Reload
    # ------------------------------------------------------------------ #

    def load(self, manifest: PluginManifest, verify_version: bool = True, install_deps: bool = True) -> bool:
        """
        Dynamically import the entry module and register the plugin.
        Calls plugin.setup(registry) if the function exists.
        Returns True on success.
        """
        if not manifest.enabled:
            logger.info("Skipping disabled plugin: %s", manifest.id)
            return False

        # Version compatibility check
        if verify_version:
            compat_ok = compatibility_checker.check(manifest.id, manifest.min_jarvis_version, manifest.hooks)
            if not compat_ok:
                logger.warning("Version check failed for %s — loading anyway (warn mode)", manifest.id)

        # Deps resolution + install
        if install_deps and manifest.requires:
            ok = dependency_resolver.install(manifest.requires)
            if not ok:
                logger.error("Failed to install deps for %s — skipping", manifest.id)
                return False
            dependency_resolver.clear_session()

        try:
            module = importlib.import_module(manifest.entry)
        except ModuleNotFoundError:
            # Try to reload in case it was previously imported
            module = _force_import(manifest.entry)
            if module is None:
                logger.error("Cannot import entry '%s' for plugin %s", manifest.entry, manifest.id)
                return False

        # Call optional setup hook
        setup_fn = getattr(module, "setup", None)
        if setup_fn:
            try:
                setup_fn(self._registry)
            except Exception as exc:
                logger.error("Plugin %s setup() raised: %s", manifest.id, exc)

        self._registry.register(manifest, module)
        return True

    def load_all(self, path: str) -> list[str]:
        """Scan *path* and load every found plugin. Also scans entry points."""
        manifests = self.scan_directory(path)
        loaded = []
        for m in manifests:
            if self.load(m):
                loaded.append(m.id)

        # Load from entry points
        ep_loaded = self.load_from_entry_points()
        loaded.extend(ep_loaded)

        return loaded

    def load_from_entry_points(self) -> list[str]:
        """
        Discover and load plugins registered via entry points (pip-native).
        """
        import importlib.metadata
        loaded = []

        try:
            eps = importlib.metadata.entry_points()
            if hasattr(eps, 'select'): # Python 3.10+
                jarvis_plugins = eps.select(group='jarvis.plugins')
            else:
                jarvis_plugins = eps.get('jarvis.plugins', [])

            for ep in jarvis_plugins:
                try:
                    plugin_class = ep.load()
                    # Create a manifest shim
                    from .base import PluginManifest
                    hooks: list[str] = []
                    for attr_name in dir(plugin_class):
                        attr = getattr(plugin_class, attr_name, None)
                        hook_name = getattr(attr, "_jarvis_hook", None)
                        if hook_name and hook_name not in hooks:
                            hooks.append(hook_name)
                    m = PluginManifest(
                        id=ep.name,
                        name=getattr(plugin_class, "name", ep.name),
                        version=getattr(plugin_class, "version", "0.1.0"),
                        description=getattr(plugin_class, "description", ""),
                        hooks=hooks,
                        entry=ep.value,
                        enabled=True
                    )

                    # Instantiate and register
                    instance = plugin_class()

                    # Subscribe hooks to event bus
                    from core.event_bus import PluginEventBus
                    bus = PluginEventBus.instance()
                    for attr_name in dir(instance):
                        attr = getattr(instance, attr_name)
                        hook_name = getattr(attr, "_jarvis_hook", None)
                        if hook_name:
                            bus.subscribe(hook_name, attr)
                            logger.info("Registered hook: %s -> %s", hook_name, attr_name)

                    self._registry.register(m, instance)
                    loaded.append(m.id)
                    logger.info("Loaded entry point plugin: %s", m.id)
                except Exception as exc:
                    logger.error("Failed to load entry point plugin %s: %s", ep.name, exc)
        except Exception as exc:
            logger.error("Entry point discovery failed: %s", exc)

        return loaded

    def unload(self, plugin_id: str) -> bool:
        """
        Unregister a plugin. Also removes its module from sys.modules
        to allow clean re-import on reload.
        """
        manifest = self._registry.get_manifest(plugin_id)
        if not manifest:
            logger.warning("unload: unknown plugin %s", plugin_id)
            return False

        # Call optional teardown hook
        module = self._registry.get(plugin_id)
        if module:
            teardown_fn = getattr(module, "teardown", None)
            if teardown_fn:
                try:
                    teardown_fn()
                except Exception as exc:
                    logger.error("Plugin %s teardown() raised: %s", plugin_id, exc)
            # Remove from sys.modules to allow fresh reimport
            sys.modules.pop(manifest.entry, None)

        self._registry.unregister(plugin_id)
        logger.info("Unloaded plugin: %s", plugin_id)
        return True

    def reload(self, plugin_id: str) -> bool:
        """Hot-reload: unload then load again."""
        manifest = self._registry.get_manifest(plugin_id)
        if not manifest:
            logger.warning("reload: unknown plugin %s", plugin_id)
            return False
        m = manifest
        # Preserve module reference so re-import works even for injected modules
        old_module = self._registry.get(plugin_id)
        self.unload(plugin_id)
        if old_module is not None and manifest.entry not in sys.modules:
            sys.modules[manifest.entry] = old_module
        return self.load(m)

    # ------------------------------------------------------------------ #
    # Dependency installation (delegates to DependencyResolver)
    # ------------------------------------------------------------------ #

    def install_deps(self, manifest: PluginManifest) -> bool:
        """
        Install plugin dependencies via DependencyResolver.
        """
        return dependency_resolver.install(manifest.requires)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _is_installed(package_name: str) -> bool:
    """Check if a package can be imported (ignores version specifiers)."""
    name = package_name.split(">=")[0].split("<=")[0].split("==")[0].split("[")[0].strip()
    try:
        importlib.import_module(name.replace("-", "_"))
        return True
    except ImportError:
        return False


def _force_import(entry: str):
    """Last-resort import attempt after invalidating importlib caches."""
    try:
        importlib.invalidate_caches()
        return importlib.import_module(entry)
    except Exception as _e:
        logger.debug("plugins loader force_import failed: %s", _e)
        return None


# Singleton
_loader: PluginLoader | None = None


def get_plugin_loader() -> PluginLoader:
    global _loader
    if _loader is None:
        _loader = PluginLoader()
    return _loader
