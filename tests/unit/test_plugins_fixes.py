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

"""Tests for plugin subsystem fixes: HTTP method validation, hook failure, etc."""
import pytest
from unittest.mock import patch, MagicMock
from core.plugins.base import Plugin, PluginManifest, PluginRegistry, _HookFailed, _VALID_HTTP_METHODS


class TestPluginHttpRoutes:
    def test_valid_http_methods(self):
        """All standard HTTP methods are accepted."""
        p = Plugin(PluginManifest(name="test", version="1.0", description=""))
        for method in _VALID_HTTP_METHODS:
            p.register_http_route(method, f"/{method.lower()}", lambda: None)
        assert len(p.http_routes) == len(_VALID_HTTP_METHODS)

    def test_invalid_http_method_rejected(self):
        """Invalid methods are rejected with a warning."""
        p = Plugin(PluginManifest(name="test", version="1.0", description=""))
        with patch("core.plugins.base.logger") as mock_log:
            p.register_http_route("FOO", "/foo", lambda: None)
            mock_log.warning.assert_called_once()
        assert len(p.http_routes) == 0

    def test_case_insensitive_method(self):
        """Lowercase methods are normalized to uppercase."""
        p = Plugin(PluginManifest(name="test", version="1.0", description=""))
        p.register_http_route("get", "/get", lambda: None)
        assert p.http_routes[0][0] == "GET"

    def test_route_logs_warning_when_no_app(self):
        """load_all warns when routes exist but no FastAPI app in app_state."""
        registry = PluginRegistry()
        p = Plugin(PluginManifest(name="router", version="1.0", description="", hooks=["on_load"]))
        p.register_http_route("GET", "/test", lambda: None)
        registry.register(p)
        with patch("core.plugins.base.logger") as mock_log:
            import asyncio
            asyncio.run(registry.load_all(app_state={}))
            found = any("not attached" in str(call) for call in mock_log.warning.call_args_list)
            assert found, "Expected warning about routes not being attached"


class TestRunHook:
    @pytest.mark.asyncio
    async def test_hook_missing_not_in_results(self):
        """Hooks not in manifest don't appear in results at all."""
        registry = PluginRegistry()
        p = Plugin(PluginManifest(name="basic", version="1.0", description="", hooks=["on_load"]))
        registry.register(p)
        results = await registry.run_hook("on_unload")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_hook_failed_wrapped_in_sentinel(self):
        """Hook failures return _HookFailed sentinel, not None."""
        registry = PluginRegistry()

        class FailPlugin(Plugin):
            async def on_load(self, app_state=None):
                msg = "deliberate failure"
                raise RuntimeError(msg)

        p = FailPlugin(PluginManifest(name="failer", version="1.0", description="", hooks=["on_load"]))
        registry.register(p)
        results = await registry.run_hook("on_load")
        assert len(results) == 1
        name, result = results[0]
        assert name == "failer"
        assert isinstance(result, _HookFailed)
        assert "deliberate failure" in str(result.exception)


class TestRegisterChannel:
    @pytest.mark.asyncio
    async def test_register_channel_no_channels_package(self):
        """register_channel fails gracefully without channels package."""
        p = Plugin(PluginManifest(name="test", version="1.0", description=""))
        with patch("core.plugins.base.logger") as mock_log:
            with patch.dict("sys.modules", {"channels": None}):
                with patch("builtins.__import__", side_effect=ImportError("no channels")):
                    p.register_channel("not-a-channel")
                    mock_log.warning.assert_called_once()


class TestDiscoverFromManifest:
    def test_missing_fields_skipped(self):
        """Manifests missing required fields are skipped with warning."""
        import tempfile, json
        from pathlib import Path
        registry = PluginRegistry()
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "bad.json"
            manifest_path.write_text(json.dumps({"name": "no-version"}))
            with patch("core.plugins.base.logger") as mock_log:
                registry.discover_from_manifest(tmp)
                found = any("missing fields" in str(call) for call in mock_log.warning.call_args_list)
                assert found, "Expected warning about missing fields"
            assert "no-version" not in registry.plugins


class TestSandbox:
    def test_validate_catches_dunder_import(self):
        """validate_manifest_imports catches __import__() calls."""
        from core.plugins.sandbox import validate_manifest_imports
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            plugin_path = Path(tmp) / "bad_plugin.py"
            plugin_path.write_text('__import__("os")\n')
            disallowed = validate_manifest_imports(str(plugin_path))
            assert "os" in disallowed

    def test_validate_catches_importlib_import_module(self):
        """validate_manifest_imports catches importlib.import_module()."""
        from core.plugins.sandbox import validate_manifest_imports
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            plugin_path = Path(tmp) / "bad_plugin.py"
            plugin_path.write_text('import importlib; importlib.import_module("subprocess")\n')
            disallowed = validate_manifest_imports(str(plugin_path))
            assert "subprocess" in disallowed


class TestWakeWordPlugin:
    @pytest.mark.asyncio
    async def test_on_stt_handles_sync_and_async(self):
        """on_stt handles both sync and async transcribe results."""
        from plugins.wake_word_plugin import Plugin as WakeWordPlugin
        from core.plugins.base import PluginManifest

        p = WakeWordPlugin(PluginManifest(name="ww", version="1.0", description=""))

        # Sync provider
        sync_stt = MagicMock()
        sync_stt.transcribe = MagicMock(return_value="hello")
        p._stt = sync_stt
        result = await p.on_stt(b"audio")
        assert result == "hello"

        # Async provider
        async def async_transcribe(_data):
            return "async hello"
        async_stt = MagicMock()
        async_stt.transcribe = async_transcribe
        p._stt = async_stt
        result = await p.on_stt(b"audio")
        assert result == "async hello"

        # Provider returns None
        none_stt = MagicMock()
        none_stt.transcribe = MagicMock(return_value=None)
        p._stt = none_stt
        result = await p.on_stt(b"audio")
        assert result is None

        # No STT provider
        p._stt = None
        result = await p.on_stt(b"audio")
        assert result is None
