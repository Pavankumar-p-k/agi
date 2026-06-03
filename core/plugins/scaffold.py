from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from string import Template

logger = logging.getLogger(__name__)

PLUGIN_TEMPLATE = '''"""$name — $description"""

from __future__ import annotations

import logging
from typing import Any

from core.plugins import Plugin, PluginManifest

logger = logging.getLogger(__name__)


class Plugin(Plugin):
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)
        self._my_state: dict = {}

    async def on_load(self, app_state: dict | None = None) -> None:
        await super().on_load(app_state)
        logger.info("[$name] Loaded")

    async def on_unload(self) -> None:
        logger.info("[$name] Unloaded")
        await super().on_unload()

    async def health_check(self) -> dict:
        base = await super().health_check()
        base["my_state_size"] = len(self._my_state)
        return base
'''

MANIFEST_TEMPLATE = '''{
  "name": "$name",
  "version": "$version",
  "description": "$description",
  "author": "$author",
  "entry_point": "$entry_point",
  "enabled": true,
  "hooks": ["on_load", "on_unload"],
  "dependencies": []
}
'''

TEST_TEMPLATE = '''"""Tests for $name plugin."""

import pytest

from core.plugins.testing import (
    create_test_plugin,
    create_test_registry,
    run_hook_test,
    assert_hook_called,
)


@pytest.mark.asyncio
async def test_plugin_load_unload():
    plugin = create_test_plugin(name="$name")
    registry, _ = create_test_registry()
    registry.register(plugin)
    await registry.load_all()
    assert plugin._loaded

    await registry.unload_all()
    assert not plugin._loaded


@pytest.mark.asyncio
async def test_plugin_hooks():
    plugin = create_test_plugin(name="$name")
    registry, _ = create_test_registry()
    registry.register(plugin)
    await registry.load_all()
    results = await registry.run_hook("on_load")
    assert assert_hook_called(registry, "on_load", "$name")
'''


def create_plugin(
    name: str,
    description: str = "",
    author: str = "JARVIS",
    version: str = "1.0.0",
    output_dir: str | Path | None = None,
) -> dict:
    if output_dir is None:
        output_dir = Path("plugins")
    output_dir = Path(output_dir)
    safe_name = name.replace(".", "_").replace("-", "_")
    plugin_dir = output_dir / safe_name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    entry_point = f"{safe_name}.py"
    manifest = {
        "name": name,
        "version": version,
        "description": description or f"{name} plugin",
        "author": author,
        "entry_point": entry_point,
        "enabled": True,
        "hooks": ["on_load", "on_unload"],
        "dependencies": [],
    }

    subs = {
        "name": name,
        "safe_name": safe_name,
        "description": description or f"{name} plugin",
        "author": author,
        "version": version,
        "entry_point": entry_point,
    }

    py_path = plugin_dir / entry_point
    py_path.write_text(Template(PLUGIN_TEMPLATE).safe_substitute(subs), encoding="utf-8")

    manifest_path = plugin_dir / f"{safe_name}.json"
    manifest_path.write_text(Template(MANIFEST_TEMPLATE).safe_substitute(subs), encoding="utf-8")

    test_path = plugin_dir / f"test_{safe_name}.py"
    test_path.write_text(Template(TEST_TEMPLATE).safe_substitute(subs), encoding="utf-8")

    init_path = plugin_dir / "__init__.py"
    init_path.write_text(f"from .{safe_name} import Plugin\n", encoding="utf-8")

    logger.info("[Scaffold] Created plugin %s in %s", name, plugin_dir)
    return {
        "name": name,
        "path": str(plugin_dir),
        "files": [str(py_path), str(manifest_path), str(test_path), str(init_path)],
    }


def list_templates() -> dict:
    return {
        "basic": "Basic plugin with load/unload hooks",
        "tool": "Plugin that registers tools",
        "channel": "Plugin that registers a messaging channel",
        "memory": "Plugin with memory hooks",
        "media": "Plugin that provides media generation",
    }
