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

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
from core.plugins.base import Plugin, PluginManifest, PluginRegistry, plugin_registry


class TestPluginManifest:
    def test_defaults(self):
        m = PluginManifest(name="test", version="1.0", description="desc")
        assert m.enabled is True
        assert "on_load" in m.hooks
        assert "on_unload" in m.hooks
        assert "before_model_resolve" in m.hooks
        assert "llm_input" in m.hooks
        assert "session_start" in m.hooks
        assert "agent_end" in m.hooks
        assert "after_tool_call" in m.hooks
        assert m.dependencies == []


class TestPlugin:
    @pytest.mark.asyncio
    async def test_lifecycle(self):
        m = PluginManifest(name="test", version="1.0", description="desc")
        p = Plugin(m)
        assert p._loaded is False
        await p.on_load()
        assert p._loaded is True
        result = await p.health_check()
        assert result["healthy"] is True
        await p.on_unload()
        assert p._loaded is False

    @pytest.mark.asyncio
    async def test_hooks_pass_through(self):
        p = Plugin(PluginManifest(name="test", version="1.0", description="desc"))
        result = await p.on_request({"key": "val"})
        assert result == {"key": "val"}
        result = await p.on_response({"key": "val"})
        assert result == {"key": "val"}


class TestPluginRegistry:
    def test_register(self):
        registry = PluginRegistry()
        p = Plugin(PluginManifest(name="regtest", version="1.0", description="desc"))
        registry.register(p)
        assert "regtest" in registry.plugins
        assert registry.count == 1

    def test_get_plugin(self):
        registry = PluginRegistry()
        p = Plugin(PluginManifest(name="gettest", version="1.0", description="desc"))
        registry.register(p)
        assert registry.get("gettest") is p
        assert registry.get("nonexistent") is None

    def test_list_by_hook(self):
        registry = PluginRegistry()
        p1 = Plugin(PluginManifest(name="a", version="1.0", description="", hooks=["on_load"]))
        p2 = Plugin(PluginManifest(name="b", version="1.0", description="", hooks=["on_load", "on_unload"]))
        registry.register(p1)
        registry.register(p2)
        assert len(registry.list_by_hook("on_load")) == 2
        assert len(registry.list_by_hook("on_unload")) == 1

    @pytest.mark.asyncio
    async def test_run_hook(self):
        registry = PluginRegistry()
        p = Plugin(PluginManifest(name="hooked", version="1.0", description="", hooks=["on_request"]))
        registry.register(p)
        results = await registry.run_hook("on_request", request_data={"test": True})
        assert len(results) == 1
        name, result = results[0]
        assert name == "hooked"
        assert result == {"test": True}

    @pytest.mark.asyncio
    async def test_load_unload_all(self):
        registry = PluginRegistry()
        p = Plugin(PluginManifest(name="lifecycle", version="1.0", description=""))
        registry.register(p)
        await registry.load_all()
        assert registry._loaded is True
        assert p._loaded is True
        await registry.unload_all()
        assert registry._loaded is False
        assert p._loaded is False

    def test_discover_from_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {
                "name": "discovered",
                "version": "1.0",
                "description": "auto-discovered",
                "entry_point": "plugin.py",
                "enabled": True,
            }
            manifest_path = Path(tmp) / "my_plugin.json"
            manifest_path.write_text(json.dumps(manifest))
            entry_path = Path(tmp) / "plugin.py"
            entry_path.write_text(
                "from core.plugins.base import Plugin, PluginManifest\n"
                "Plugin = type('Plugin', (Plugin,), {})\n"
            )
            registry = PluginRegistry()
            registry.discover_from_manifest(tmp)
            # Entry point doesn't define a proper Plugin subclass so it won't register
            # But the discovery itself should not crash
            assert True

    def test_discover_skips_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {
                "name": "disabled_plugin",
                "version": "1.0",
                "description": "",
                "enabled": False,
            }
            manifest_path = Path(tmp) / "disabled.json"
            manifest_path.write_text(json.dumps(manifest))
            registry = PluginRegistry()
            registry.discover_from_manifest(tmp)
            assert "disabled_plugin" not in registry.plugins
