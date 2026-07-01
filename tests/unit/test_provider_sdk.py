from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


class TestProviderManifest:
    def test_from_dict(self):
        from provider_sdk.manifest import ProviderManifest
        data = {
            "provider_id": "test_provider",
            "name": "Test Provider",
            "version": "2.0.0",
            "description": "A test provider",
            "author": "Test Author",
            "capabilities": ["search", "web"],
            "features": ["fast_search"],
            "languages": ["Python"],
            "adapter": "test_adapter.py",
            "adapter_type": "python",
            "priority": 50,
        }
        m = ProviderManifest.from_dict(data)
        assert m.provider_id == "test_provider"
        assert m.name == "Test Provider"
        assert m.version == "2.0.0"
        assert m.priority == 50

    def test_to_dict_roundtrip(self):
        from provider_sdk.manifest import ProviderManifest
        m = ProviderManifest(
            provider_id="test", name="Test", version="1.0.0",
            capabilities=["cap1", "cap2"],
            adapter="adapter.py",
        )
        d = m.to_dict()
        m2 = ProviderManifest.from_dict(d)
        assert m2.provider_id == "test"
        assert m2.capabilities == ["cap1", "cap2"]

    def test_validate_valid(self):
        from provider_sdk.manifest import ProviderManifest, validate_manifest
        m = ProviderManifest(
            provider_id="test", name="Test",
            capabilities=["cap1"], adapter="adapter.py",
        )
        errors = validate_manifest(m)
        assert len(errors) == 0

    def test_validate_missing_id(self):
        from provider_sdk.manifest import ProviderManifest, validate_manifest
        m = ProviderManifest(name="Test", capabilities=["cap1"], adapter="adapter.py")
        errors = validate_manifest(m)
        assert any("provider_id" in e for e in errors)

    def test_validate_missing_name(self):
        from provider_sdk.manifest import ProviderManifest, validate_manifest
        m = ProviderManifest(provider_id="test", capabilities=["cap1"], adapter="adapter.py")
        errors = validate_manifest(m)
        assert any("name" in e for e in errors)

    def test_validate_missing_capabilities(self):
        from provider_sdk.manifest import ProviderManifest, validate_manifest
        m = ProviderManifest(provider_id="test", name="Test", adapter="adapter.py")
        errors = validate_manifest(m)
        assert any("capability" in e for e in errors)

    def test_validate_missing_adapter(self):
        from provider_sdk.manifest import ProviderManifest, validate_manifest
        m = ProviderManifest(provider_id="test", name="Test", capabilities=["cap1"])
        errors = validate_manifest(m)
        assert any("adapter" in e for e in errors)

    def test_validate_bad_adapter_type(self):
        from provider_sdk.manifest import ProviderManifest, validate_manifest
        m = ProviderManifest(
            provider_id="test", name="Test",
            capabilities=["cap1"], adapter="a.py",
            adapter_type="unknown",
        )
        errors = validate_manifest(m)
        assert any("adapter_type" in e for e in errors)


class TestLoadManifest:
    def test_load_json(self):
        from provider_sdk.manifest import load_manifest
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({
                "provider_id": "test_json", "name": "Test JSON",
                "capabilities": ["json_cap"], "adapter": "test.py",
            }, f)
            path = f.name
        try:
            m = load_manifest(path)
            assert m.provider_id == "test_json"
            assert m.name == "Test JSON"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_load_not_found(self):
        from provider_sdk.manifest import load_manifest, ManifestError
        with pytest.raises(ManifestError):
            load_manifest("/nonexistent/manifest.json")

    def test_load_invalid_format(self):
        from provider_sdk.manifest import load_manifest, ManifestError
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("{}")
            path = f.name
        try:
            with pytest.raises(ManifestError):
                load_manifest(path)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_load_invalid_content(self):
        from provider_sdk.manifest import load_manifest, ManifestError
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("not json")
            path = f.name
        try:
            with pytest.raises((ManifestError, json.JSONDecodeError)):
                load_manifest(path)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_load_missing_required_fields(self):
        from provider_sdk.manifest import load_manifest, ManifestError
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"name": "Incomplete"}, f)
            path = f.name
        try:
            with pytest.raises(ManifestError):
                load_manifest(path)
        finally:
            Path(path).unlink(missing_ok=True)


class TestProviderLoader:
    def test_load_python_adapter_not_found(self):
        from provider_sdk.manifest import ProviderManifest
        from provider_sdk.loader import ProviderLoader
        manifest = ProviderManifest(
            provider_id="missing", name="Missing",
            capabilities=["cap"], adapter="/nonexistent/adapter.py",
        )
        loader = ProviderLoader()
        instance = loader.load_adapter(manifest)
        assert instance is None

    def test_load_python_adapter_no_provider_class(self):
        from provider_sdk.manifest import ProviderManifest
        from provider_sdk.loader import ProviderLoader
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("# just a comment, no Provider class\n")
            path = f.name
        try:
            manifest = ProviderManifest(
                provider_id="noclass", name="No Class",
                capabilities=["cap"], adapter=path,
            )
            loader = ProviderLoader()
            instance = loader.load_adapter(manifest)
            assert instance is None
        finally:
            Path(path).unlink(missing_ok=True)

    def test_load_python_adapter_valid(self):
        from provider_sdk.manifest import ProviderManifest
        from provider_sdk.loader import ProviderLoader
        code = """from __future__ import annotations
from core.providers.base import ExecutionProvider, ProviderCapabilities, ProviderHealth, ProviderHealthStatus, ExecutionResult
class Provider(ExecutionProvider):
    provider_id = "test_dynamic"
    name = "Test Dynamic"
    def capabilities(self):
        return ProviderCapabilities(capability_names=["test"])
    async def health(self):
        return ProviderHealth(status=ProviderHealthStatus.HEALTHY)
    async def execute(self, task, context=None):
        return ExecutionResult(success=True, output="ok", exit_code=0)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            path = f.name
        try:
            manifest = ProviderManifest(
                provider_id="test_dynamic", name="Test Dynamic",
                capabilities=["test"], adapter=path,
            )
            loader = ProviderLoader()
            instance = loader.load_adapter(manifest)
            assert instance is not None
            assert instance.provider_id == "test_dynamic"
        finally:
            Path(path).unlink(missing_ok=True)


class TestProviderDiscovery:
    def test_discover_manifests_empty(self):
        from provider_sdk.discovery import ProviderDiscovery
        discovery = ProviderDiscovery()
        manifests = discovery.discover_manifests()
        assert isinstance(manifests, list)

    def test_discover_from_temp_dir(self):
        from provider_sdk.discovery import ProviderDiscovery, ProviderManifest
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "test_provider.json"
            manifest_path.write_text(json.dumps({
                "provider_id": "discovered_test", "name": "Discovered",
                "capabilities": ["disc_cap"], "adapter": "disc.py",
            }), encoding="utf-8")

            discovery = ProviderDiscovery()
            discovery.add_search_dir(tmpdir)
            manifests = discovery.discover_manifests()
            ids = [m.provider_id for m in manifests]
            assert "discovered_test" in ids

    def test_get_cached(self):
        from provider_sdk.discovery import ProviderDiscovery
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "cache_test.json"
            manifest_path.write_text(json.dumps({
                "provider_id": "cached_provider", "name": "Cached",
                "capabilities": ["cached"], "adapter": "cached.py",
            }), encoding="utf-8")

            discovery = ProviderDiscovery()
            discovery.add_search_dir(tmpdir)
            discovery.discover_manifests()
            cached = discovery.get_cached("cached_provider")
            assert cached is not None
            assert cached.name == "Cached"

    def test_clear_cache(self):
        from provider_sdk.discovery import ProviderDiscovery
        discovery = ProviderDiscovery()
        discovery._cached["test"] = "dummy"
        assert len(discovery.list_cached()) == 1
        discovery.clear_cache()
        assert len(discovery.list_cached()) == 0


class TestProviderRegistration:
    def test_pipeline_no_duplicate(self):
        from provider_sdk.registration import ProviderRegistrationPipeline
        from provider_sdk.manifest import ProviderManifest
        pipeline = ProviderRegistrationPipeline()
        manifest = ProviderManifest(
            provider_id="__test_reg", name="Test Reg",
            capabilities=["test_reg_cap"], adapter="/nonexistent",
        )
        result = pipeline.register_from_manifest(manifest)
        assert result is False  # adapter not found

    def test_pipeline_discover_and_register_empty(self):
        from provider_sdk.registration import ProviderRegistrationPipeline
        pipeline = ProviderRegistrationPipeline()
        count = pipeline.discover_and_register()
        assert isinstance(count, int)
