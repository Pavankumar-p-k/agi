from __future__ import annotations

import hashlib
import json
import os
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from core.plugins.dependencies import DependencyResolver, _parse_package_name
from core.plugins.compatibility import CompatibilityChecker, CompatibilityMode
from core.plugins.verification import ManifestVerifier, VerificationMode
from core.plugins.marketplace import PluginMarketplace


# ════════════════════════════════════════════════════════════════════════
# Phase 3a: Dependency Resolution
# ════════════════════════════════════════════════════════════════════════

class TestDependencyResolver:
    def test_parse_package_name_simple(self):
        assert _parse_package_name("requests") == "requests"

    def test_parse_package_name_with_version(self):
        assert _parse_package_name("requests>=2.0") == "requests"
        assert _parse_package_name("numpy==1.24") == "numpy"
        assert _parse_package_name("pandas<=2.0") == "pandas"

    def test_parse_package_name_with_extra(self):
        assert _parse_package_name("bcrypt[bcrypt]>=4.0") == "bcrypt"

    def test_resolve_no_missing(self):
        resolver = DependencyResolver()
        result = resolver.resolve([])
        assert result == []

    def test_resolve_unknown_package(self):
        resolver = DependencyResolver()
        result = resolver.resolve(["nonexistent_package_xyz_999"])
        assert "nonexistent_package_xyz_999" in result

    def test_install_unknown_returns_false(self):
        resolver = DependencyResolver()
        result = resolver.install(["nonexistent_package_xyz_999"])
        assert result is False

    def test_install_empty_requires(self):
        resolver = DependencyResolver()
        assert resolver.install([]) is True

    @patch("core.plugins.dependencies.subprocess.check_call")
    def test_install_success(self, mock_check_call):
        resolver = DependencyResolver()
        resolver.resolve = MagicMock(return_value=["requests"])
        result = resolver.install(["requests"])
        assert result is True
        mock_check_call.assert_called_once()

    @patch("core.plugins.dependencies.subprocess.check_call")
    def test_install_rollback_on_failure(self, mock_check_call):
        import subprocess
        mock_check_call.side_effect = [
            None,  # first succeeds
            subprocess.CalledProcessError(1, "pip"),  # second fails
        ]
        resolver = DependencyResolver()
        resolver.resolve = MagicMock(return_value=["pkg1", "pkg2"])
        with patch.object(resolver, "uninstall") as mock_uninstall:
            result = resolver.install(["pkg1", "pkg2"])
            assert result is False
            mock_uninstall.assert_called_once_with(["pkg1"])


# ════════════════════════════════════════════════════════════════════════
# Phase 3b: Version Enforcement
# ════════════════════════════════════════════════════════════════════════

class TestCompatibilityChecker:
    def test_check_version_compatible(self):
        cc = CompatibilityChecker(current_version="1.0.0", mode="strict")
        assert cc.check_version("test", "1.0.0") is True

    def test_check_version_newer_jarvis(self):
        cc = CompatibilityChecker(current_version="2.0.0", mode="strict")
        assert cc.check_version("test", "1.0.0") is True

    def test_check_version_incompatible_strict(self):
        cc = CompatibilityChecker(current_version="1.0.0", mode="strict")
        from core.plugins.errors import PluginDependencyError
        with pytest.raises(PluginDependencyError):
            cc.check_version("test", "2.0.0")

    def test_check_version_incompatible_warn(self):
        cc = CompatibilityChecker(current_version="1.0.0", mode="warn")
        assert cc.check_version("test", "2.0.0") is False

    def test_check_version_off(self):
        cc = CompatibilityChecker(current_version="1.0.0", mode="off")
        assert cc.check_version("test", "99.0.0") is True

    def test_check_unknown_hooks(self):
        cc = CompatibilityChecker()
        unknown = cc.check_hooks("test", ["on_load", "on_unknown_hook"])
        assert "on_unknown_hook" in unknown
        assert "on_load" not in unknown

    def test_check_all_known_hooks(self):
        cc = CompatibilityChecker()
        unknown = cc.check_hooks("test", ["on_load", "on_unload"])
        assert unknown == []

    def test_check_full_pass(self):
        cc = CompatibilityChecker(current_version="1.0.0", mode="warn")
        assert cc.check("test", "1.0.0", ["on_load"]) is True


# ════════════════════════════════════════════════════════════════════════
# Phase 3c: Manifest Verification
# ════════════════════════════════════════════════════════════════════════

class TestManifestVerifier:
    def test_verify_no_checksum_permissive(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"id": "test", "name": "Test"}, f)
            path = f.name

        try:
            verifier = ManifestVerifier(mode="permissive")
            assert verifier.verify_manifest_integrity(path) is True
        finally:
            os.unlink(path)

    def test_verify_no_checksum_strict(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"id": "test", "name": "Test"}, f)
            path = f.name

        try:
            verifier = ManifestVerifier(mode="strict")
            assert verifier.verify_manifest_integrity(path) is False
        finally:
            os.unlink(path)

    def test_verify_correct_checksum(self):
        data = {"id": "test", "name": "Test"}
        manifest_bytes = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        checksum = hashlib.sha256(manifest_bytes).hexdigest()
        data["checksum_sha256"] = checksum

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name

        try:
            verifier = ManifestVerifier(mode="strict")
            assert verifier.verify_manifest_integrity(path) is True
        finally:
            os.unlink(path)

    def test_verify_tampered_checksum(self):
        data = {"id": "test", "name": "Test"}
        manifest_bytes = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        checksum = hashlib.sha256(manifest_bytes).hexdigest()
        data["checksum_sha256"] = checksum
        data["name"] = "Tampered"  # tamper after checksum

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name

        try:
            verifier = ManifestVerifier(mode="strict")
            assert verifier.verify_manifest_integrity(path) is False
        finally:
            os.unlink(path)

    def test_verify_off_mode(self):
        verifier = ManifestVerifier(mode="off")
        assert verifier.verify_manifest_integrity("/nonexistent/path") is True

    def test_compute_and_verify_roundtrip(self):
        data = {"id": "test", "name": "Test", "version": "1.0.0"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name

        try:
            verifier = ManifestVerifier(mode="strict")
            checksum = verifier.compute_manifest_checksum(path)
            # Re-read and check the checksum was computed correctly
            with open(path) as f:
                loaded = json.load(f)
            assert "checksum_sha256" not in loaded  # not injected yet
            assert len(checksum) == 64  # SHA-256 hex

            # Roundtrip: inject -> verify
            verifier.inject_checksum(path)
            assert verifier.verify_manifest_integrity(path) is True
        finally:
            os.unlink(path)

    def test_verify_file_checksum(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello world")
            path = f.name

        try:
            expected = hashlib.sha256(b"hello world").hexdigest()
            verifier = ManifestVerifier()
            assert verifier.verify_file_checksum(path, expected) is True
            assert verifier.verify_file_checksum(path, "0" * 64) is False
        finally:
            os.unlink(path)


# ════════════════════════════════════════════════════════════════════════
# Phase 3d: Plugin Marketplace
# ════════════════════════════════════════════════════════════════════════

class TestPluginMarketplace:
    @pytest.mark.asyncio
    async def test_refresh_index_httpx_not_available(self):
        mp = PluginMarketplace()
        with patch("core.plugins.marketplace.httpx", None):
            result = await mp.refresh_index()
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_index_network_error(self):
        mp = PluginMarketplace()
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("connection failed")
        mp._http_client = mock_client
        result = await mp.refresh_index()
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_index_304(self):
        mp = PluginMarketplace()
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(status_code=304)
        mp._http_client = mock_client
        mp._index.etag = "abc"
        result = await mp.refresh_index()
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_index_success(self):
        mp = PluginMarketplace()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"plugins": {"test-plugin": [{"version": "1.0.0", "name": "Test"}]}}
        mock_response.headers = {"etag": "xyz"}
        mock_client.get.return_value = mock_response
        mp._http_client = mock_client

        result = await mp.refresh_index()
        assert result is True
        assert "test-plugin" in mp._index.plugins
        assert mp._index.etag == "xyz"

    def test_search_exact_match(self):
        mp = PluginMarketplace()
        mp._index.plugins = {
            "plugin-a": [{"version": "1.0", "name": "Plugin A", "description": "AI helper"}],
            "plugin-b": [{"version": "2.0", "name": "Plugin B", "description": "Data tool"}],
        }
        results = mp.search("plugin-a")
        assert len(results) == 1
        assert results[0]["id"] == "plugin-a"

    def test_search_partial_match(self):
        mp = PluginMarketplace()
        mp._index.plugins = {
            "weather": [{"version": "1.0", "name": "Weather Plugin", "description": "Shows weather"}],
            "calendar": [{"version": "1.0", "name": "Calendar Plugin", "description": "Manages events"}],
        }
        results = mp.search("weath")
        assert len(results) == 1
        assert results[0]["id"] == "weather"

    def test_search_description_match(self):
        mp = PluginMarketplace()
        mp._index.plugins = {
            "helper": [{"version": "1.0", "name": "Helper", "description": "AI assistant tool"}],
        }
        results = mp.search("ai assistant")
        assert len(results) == 1

    def test_search_no_match(self):
        mp = PluginMarketplace()
        mp._index.plugins = {"a": [{"version": "1.0", "name": "A"}]}
        results = mp.search("nonexistent")
        assert results == []

    def test_list_versions(self):
        mp = PluginMarketplace()
        mp._index.plugins = {
            "test": [
                {"version": "1.0.0", "name": "Test"},
                {"version": "2.0.0", "name": "Test"},
            ],
        }
        versions = mp.list_versions("test")
        assert len(versions) == 2

        versions = mp.list_versions("unknown")
        assert versions == []

    def test_info_latest(self):
        mp = PluginMarketplace()
        mp._index.plugins = {
            "test": [
                {"version": "1.0.0", "name": "Test"},
                {"version": "2.0.0", "name": "Test"},
            ],
        }
        info = mp.info("test")
        assert info["version"] == "2.0.0"

    def test_info_specific_version(self):
        mp = PluginMarketplace()
        mp._index.plugins = {
            "test": [
                {"version": "1.0.0", "name": "Test"},
                {"version": "2.0.0", "name": "Test"},
            ],
        }
        info = mp.info("test", "1.0.0")
        assert info["version"] == "1.0.0"

    def test_info_unknown(self):
        mp = PluginMarketplace()
        assert mp.info("nonexistent") == {}

    @pytest.mark.asyncio
    async def test_download_no_meta(self):
        mp = PluginMarketplace()
        result = await mp.download("nonexistent", "1.0.0", "/tmp")
        assert result is None

    @pytest.mark.asyncio
    async def test_download_no_download_url(self):
        mp = PluginMarketplace()
        mp._index.plugins = {"test": [{"version": "1.0.0", "name": "Test"}]}
        result = await mp.download("test", "1.0.0", "/tmp")
        assert result is None

    @pytest.mark.asyncio
    async def test_close(self):
        mp = PluginMarketplace()
        mock_client = AsyncMock()
        mp._http_client = mock_client
        await mp.close()
        mock_client.aclose.assert_awaited_once()
        assert mp._http_client is None

    @pytest.mark.asyncio
    async def test_close_no_client(self):
        mp = PluginMarketplace()
        await mp.close()  # should not raise
