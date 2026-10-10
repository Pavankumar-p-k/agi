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

"""core.plugins.loader — discovers manifests and manages plugin module lifecycle."""
from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

from core.plugins.manifest import PluginManifest
from core.plugins.registry import ModulePluginRegistry

logger = logging.getLogger(__name__)


class PluginLoader:
    """Scans directories for plugin.json manifests and loads their entry modules."""

    def __init__(self, registry: ModulePluginRegistry | None = None) -> None:
        self._registry = registry if registry is not None else ModulePluginRegistry()

    # ── discovery ───────────────────────────────────────────────────────────
    def scan_directory(self, directory: str | Path) -> list[PluginManifest]:
        root = Path(directory)
        if not root.is_dir():
            return []
        manifests: list[PluginManifest] = []
        for manifest_path in root.rglob("plugin.json"):
            try:
                manifests.append(PluginManifest.from_file(manifest_path))
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("Skipping invalid manifest %s: %s", manifest_path, exc)
        return manifests

    # ── lifecycle ───────────────────────────────────────────────────────────
    def load(self, manifest: PluginManifest) -> bool:
        if not manifest.enabled:
            logger.info("Plugin %s is disabled — skip load", manifest.id)
            return False
        try:
            module = importlib.import_module(manifest.entry)
        except Exception as exc:
            logger.warning("Failed to import plugin %s (%s): %s", manifest.id, manifest.entry, exc)
            return False

        setup = getattr(module, "setup", None)
        if callable(setup):
            try:
                setup(registry=self._registry)
            except Exception as exc:
                logger.warning("Plugin %s setup() failed: %s", manifest.id, exc)
                return False
        self._registry.register(manifest, module)
        return True

    def unload(self, plugin_id: str) -> bool:
        manifest = self._registry.get_manifest(plugin_id)
        module = self._registry.get(plugin_id)
        if module is None:
            return False
        teardown = getattr(module, "teardown", None)
        if callable(teardown):
            try:
                teardown()
            except Exception as exc:
                logger.warning("Plugin %s teardown() failed: %s", plugin_id, exc)
        self._registry.unregister(plugin_id)
        return True

    def reload(self, plugin_id: str) -> bool:
        manifest = self._registry.get_manifest(plugin_id)
        if manifest is None:
            return False
        module = self._registry.get(plugin_id)
        if module is not None:
            self.unload(plugin_id)
        try:
            fresh = importlib.import_module(manifest.entry)
            if fresh.__name__ in sys.modules:
                try:
                    importlib.reload(fresh)
                except (AttributeError, ImportError, KeyError) as exc:
                    # reload can fail for synthetic parent packages; re-import suffices
                    logger.debug("reload() fell back to re-import for %s: %s", manifest.entry, exc)
        except Exception as exc:
            logger.warning("Failed to reload plugin %s: %s", plugin_id, exc)
            return False
        self._registry.register(manifest, fresh)
        setup = getattr(fresh, "setup", None)
        if callable(setup):
            try:
                setup(registry=self._registry)
            except Exception as exc:
                logger.warning("Plugin %s setup() failed on reload: %s", plugin_id, exc)
        return True


def get_plugin_loader() -> PluginLoader:
    """Process-wide singleton loader bound to the process-wide registry."""
    global _singleton
    try:
        return _singleton  # noqa: PLW0603
    except NameError:
        from core.plugins.registry import get_plugin_registry

        _singleton = PluginLoader(get_plugin_registry())
        return _singleton


__all__ = ["PluginLoader", "get_plugin_loader"]
