# tests/unit/test_plugin_system.py
"""
Unit tests for the JARVIS Plugin System.
Run with:  pytest tests/unit/test_plugin_system.py -v
"""
import asyncio
import json
import os
import sys
import types
import tempfile
import pytest

# ---------------------------------------------------------------------------
# Helpers — create a fake module to simulate a plugin entry point
# ---------------------------------------------------------------------------

def _make_fake_module(name: str, has_setup: bool = True) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.setup_called = False
    mod.teardown_called = False
    mod.hook_calls = []

    if has_setup:
        def setup(registry=None):
            mod.setup_called = True
        mod.setup = setup

    def teardown():
        mod.teardown_called = True
    mod.teardown = teardown

    async def on_intent(intent=None, text=None, **kwargs):
        mod.hook_calls.append(("on_intent", intent, text))
        return f"handled:{intent}"
    mod.on_intent = on_intent

    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_registry():
    from core.plugins.registry import PluginRegistry
    return PluginRegistry()


@pytest.fixture
def sample_manifest(tmp_path):
    from core.plugins.manifest import PluginManifest
    return PluginManifest(
        id          = "test_plugin",
        name        = "Test Plugin",
        version     = "1.2.3",
        description = "A test plugin",
        author      = "tester",
        entry       = "fake.test.module",
        hooks       = ["on_intent", "on_decision"],
        settings_schema = {
            "type": "object",
            "required": ["api_key"],
            "properties": {
                "api_key": {"type": "string"},
                "count":   {"type": "integer"},
            }
        },
        requires    = [],
        enabled     = True,
    )


@pytest.fixture
def fake_module():
    mod = _make_fake_module("fake.test.module")
    sys.modules["fake.test.module"] = mod
    yield mod
    sys.modules.pop("fake.test.module", None)


# ---------------------------------------------------------------------------
# PluginManifest tests
# ---------------------------------------------------------------------------

class TestPluginManifest:
    def test_from_dict_roundtrip(self, sample_manifest):
        d = sample_manifest.to_dict()
        from core.plugins.manifest import PluginManifest
        restored = PluginManifest.from_dict(d)
        assert restored.id == sample_manifest.id
        assert restored.version == sample_manifest.version
        assert restored.hooks == sample_manifest.hooks

    def test_from_file(self, tmp_path, sample_manifest):
        path = str(tmp_path)
        sample_manifest.save(path)
        assert os.path.exists(os.path.join(path, "plugin.json"))
        from core.plugins.manifest import PluginManifest
        loaded = PluginManifest.from_file(os.path.join(path, "plugin.json"))
        assert loaded.id == sample_manifest.id

    def test_missing_required_fields(self):
        from core.plugins.manifest import PluginManifest
        with pytest.raises(TypeError):
            PluginManifest.from_dict({})   # missing id, name, entry


# ---------------------------------------------------------------------------
# PluginRegistry tests
# ---------------------------------------------------------------------------

class TestPluginRegistry:
    def test_register_and_get(self, fresh_registry, sample_manifest, fake_module):
        fresh_registry.register(sample_manifest, fake_module)
        assert fresh_registry.get("test_plugin") is fake_module

    def test_list_plugins(self, fresh_registry, sample_manifest, fake_module):
        fresh_registry.register(sample_manifest, fake_module)
        plugins = fresh_registry.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["id"] == "test_plugin"
        assert plugins[0]["version"] == "1.2.3"

    def test_enable_disable(self, fresh_registry, sample_manifest, fake_module):
        fresh_registry.register(sample_manifest, fake_module)
        assert fresh_registry.disable("test_plugin")
        assert fresh_registry.get_manifest("test_plugin").enabled is False
        assert fresh_registry.enable("test_plugin")
        assert fresh_registry.get_manifest("test_plugin").enabled is True

    def test_enable_unknown(self, fresh_registry):
        assert fresh_registry.enable("nonexistent") is False

    def test_run_hook(self, fresh_registry, sample_manifest, fake_module):
        fresh_registry.register(sample_manifest, fake_module)
        results = asyncio.get_event_loop().run_until_complete(
            fresh_registry.run_hook("on_intent", intent="play_music", text="play something")
        )
        assert len(results) == 1
        plugin_id, result = results[0]
        assert plugin_id == "test_plugin"
        assert result == "handled:play_music"

    def test_hook_skips_disabled(self, fresh_registry, sample_manifest, fake_module):
        fresh_registry.register(sample_manifest, fake_module)
        fresh_registry.disable("test_plugin")
        results = asyncio.get_event_loop().run_until_complete(
            fresh_registry.run_hook("on_intent", intent="play_music")
        )
        assert results == []

    def test_hook_error_does_not_crash(self, fresh_registry, sample_manifest, fake_module):
        async def bad_hook(**kwargs):
            raise RuntimeError("boom")
        fake_module.on_intent = bad_hook
        fresh_registry.register(sample_manifest, fake_module)
        # Should not raise
        results = asyncio.get_event_loop().run_until_complete(
            fresh_registry.run_hook("on_intent")
        )
        assert results == []

    def test_settings_validation_pass(self, fresh_registry, sample_manifest, fake_module):
        fresh_registry.register(sample_manifest, fake_module)
        ok = fresh_registry.update_settings("test_plugin", {"api_key": "abc123", "count": 5})
        assert ok is True
        settings = fresh_registry.get_settings("test_plugin")
        assert settings["api_key"] == "abc123"

    def test_settings_validation_fail_wrong_type(self, fresh_registry, sample_manifest, fake_module):
        fresh_registry.register(sample_manifest, fake_module)
        ok = fresh_registry.update_settings("test_plugin", {"api_key": "abc", "count": "not_an_int"})
        assert ok is False

    def test_settings_validation_fail_missing_required(self, fresh_registry, sample_manifest, fake_module):
        fresh_registry.register(sample_manifest, fake_module)
        ok = fresh_registry.update_settings("test_plugin", {})
        assert ok is False


# ---------------------------------------------------------------------------
# PluginLoader tests
# ---------------------------------------------------------------------------

class TestPluginLoader:
    def test_scan_directory(self, tmp_path, sample_manifest):
        sub = tmp_path / "my_plugin"
        sub.mkdir()
        sample_manifest.save(str(sub))

        from core.plugins.loader import PluginLoader
        loader = PluginLoader()
        manifests = loader.scan_directory(str(tmp_path))
        assert len(manifests) == 1
        assert manifests[0].id == "test_plugin"

    def test_scan_missing_dir(self):
        from core.plugins.loader import PluginLoader
        loader = PluginLoader()
        assert loader.scan_directory("/nonexistent/path/xyz") == []

    def test_load_unload(self, tmp_path, sample_manifest, fake_module):
        from core.plugins.loader import PluginLoader
        from core.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        loader = PluginLoader()
        loader._registry = registry

        ok = loader.load(sample_manifest)
        assert ok is True
        assert fake_module.setup_called is True
        assert registry.get("test_plugin") is not None

        ok = loader.unload("test_plugin")
        assert ok is True
        assert fake_module.teardown_called is True
        assert registry.get("test_plugin") is None

    def test_reload(self, sample_manifest, fake_module):
        from core.plugins.loader import PluginLoader
        from core.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        loader = PluginLoader()
        loader._registry = registry
        loader.load(sample_manifest)
        ok = loader.reload("test_plugin")
        assert ok is True

    def test_disabled_plugin_skipped(self, sample_manifest, fake_module):
        from core.plugins.loader import PluginLoader
        from core.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        loader = PluginLoader()
        loader._registry = registry
        sample_manifest.enabled = False
        ok = loader.load(sample_manifest)
        assert ok is False
        assert registry.get("test_plugin") is None


# ---------------------------------------------------------------------------
# PluginSettingsStore tests
# ---------------------------------------------------------------------------

class TestPluginSettingsStore:
    def test_set_get_persist(self, tmp_path):
        from core.plugins.settings_store import PluginSettingsStore
        path = str(tmp_path / "settings.json")
        store = PluginSettingsStore(path=path)
        store.set("my_plugin", "volume", 42)
        assert store.get("my_plugin", "volume") == 42

        # Reload from disk
        store2 = PluginSettingsStore(path=path)
        assert store2.get("my_plugin", "volume") == 42

    def test_get_all(self, tmp_path):
        from core.plugins.settings_store import PluginSettingsStore
        path = str(tmp_path / "settings.json")
        store = PluginSettingsStore(path=path)
        store.set("p1", "a", 1)
        store.set("p1", "b", 2)
        all_settings = store.get_all("p1")
        assert all_settings == {"a": 1, "b": 2}

    def test_delete(self, tmp_path):
        from core.plugins.settings_store import PluginSettingsStore
        path = str(tmp_path / "settings.json")
        store = PluginSettingsStore(path=path)
        store.set("p1", "x", 99)
        store.delete("p1")
        assert store.get_all("p1") == {}

    def test_missing_file_ok(self, tmp_path):
        from core.plugins.settings_store import PluginSettingsStore
        store = PluginSettingsStore(path=str(tmp_path / "nonexistent.json"))
        assert store.get("any", "key", "default") == "default"


# ---------------------------------------------------------------------------
# CloudMemory tests (mocked Supabase)
# ---------------------------------------------------------------------------

class TestCloudMemory:
    def setup_method(self):
        """Ensure Supabase is NOT connected during tests."""
        import core.cloud.supabase_client as sc
        sc._connected = False
        sc._client    = None

    def test_set_get_sqlite(self, tmp_path):
        from core.cloud.cloud_memory import CloudMemory
        db = str(tmp_path / "test_mem.db")
        mem = CloudMemory(local_db_path=db)

        asyncio.get_event_loop().run_until_complete(
            mem.set("greeting", {"text": "Hello JARVIS"})
        )
        val = asyncio.get_event_loop().run_until_complete(mem.get("greeting"))
        assert val == {"text": "Hello JARVIS"}

    def test_delete_sqlite(self, tmp_path):
        from core.cloud.cloud_memory import CloudMemory
        db = str(tmp_path / "test_mem.db")
        mem = CloudMemory(local_db_path=db)
        asyncio.get_event_loop().run_until_complete(mem.set("k", {"v": 1}))
        asyncio.get_event_loop().run_until_complete(mem.delete("k"))
        val = asyncio.get_event_loop().run_until_complete(mem.get("k"))
        assert val is None

    def test_list_sqlite(self, tmp_path):
        from core.cloud.cloud_memory import CloudMemory
        db = str(tmp_path / "test_mem.db")
        mem = CloudMemory(local_db_path=db)
        asyncio.get_event_loop().run_until_complete(mem.set("user:1", {"name": "Pavan"}))
        asyncio.get_event_loop().run_until_complete(mem.set("user:2", {"name": "JARVIS"}))
        asyncio.get_event_loop().run_until_complete(mem.set("system:config", {"debug": True}))

        user_rows = asyncio.get_event_loop().run_until_complete(mem.list("user:"))
        assert len(user_rows) == 2

    def test_search_sqlite(self, tmp_path):
        from core.cloud.cloud_memory import CloudMemory
        db = str(tmp_path / "test_mem.db")
        mem = CloudMemory(local_db_path=db)
        asyncio.get_event_loop().run_until_complete(mem.set("note:1", {"text": "buy groceries"}))
        asyncio.get_event_loop().run_until_complete(mem.set("note:2", {"text": "study ML models"}))

        results = asyncio.get_event_loop().run_until_complete(mem.search("groceries"))
        assert len(results) == 1
        assert results[0]["key"] == "note:1"
