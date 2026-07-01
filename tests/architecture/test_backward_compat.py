from __future__ import annotations

import json

import pytest


V1_MANIFEST_DATA = {
    "provider_id": "legacy-provider",
    "name": "Legacy Provider",
    "version": "1.0.0",
    "description": "A v1 manifest",
    "author": "JARVIS Core",
    "capabilities": ["legacy-cap-a", "legacy-cap-b"],
    "features": ["fast_stuff"],
    "languages": ["Python"],
    "adapter": "legacy_adapter.py",
    "adapter_type": "python",
    "priority": 50,
}


class TestBackwardCompat:
    def test_v1_manifest_loads_as_v2(self, tmp_path):
        from provider_sdk.manifest_v2 import parse_and_validate, detect_manifest_version
        from provider_sdk.manifest import load_manifest

        manifest_path = tmp_path / "legacy.json"
        manifest_path.write_text(json.dumps(V1_MANIFEST_DATA), encoding="utf-8")
        (tmp_path / "legacy_adapter.py").write_text("class Provider: pass", encoding="utf-8")

        desc = parse_and_validate(str(manifest_path))
        assert desc.id == "legacy-provider"
        assert desc.version == "1.0.0"
        assert desc.sdk_version == 1
        assert desc.transport == "python"
        assert len(desc.declared_capabilities) == 2

    def test_v1_manifest_detected_as_v1(self, tmp_path):
        from provider_sdk.manifest_v2 import load_raw_manifest, detect_manifest_version
        path = tmp_path / "v1_test.json"
        path.write_text(json.dumps(V1_MANIFEST_DATA), encoding="utf-8")
        raw = load_raw_manifest(str(path))
        version = detect_manifest_version(raw)
        assert version == 1

    def test_v1_manifest_pipeline_upgrades_success(self, tmp_path):
        from provider_sdk.lifecycle import lifecycle_manager
        from provider_sdk.registration import TemporaryRegistry
        TemporaryRegistry.clear()

        manifest_path = tmp_path / "legacy-pipeline.json"
        manifest_path.write_text(json.dumps(V1_MANIFEST_DATA), encoding="utf-8")
        (tmp_path / "legacy_adapter.py").write_text(
            "from __future__ import annotations\n"
            "from core.providers.base import ExecutionProvider, ProviderCapabilities, ProviderHealth, ProviderHealthStatus, ExecutionResult\n"
            "class Provider(ExecutionProvider):\n"
            "    provider_id = 'legacy-provider'\n"
            "    name = 'Legacy Provider'\n"
            "    def capabilities(self):\n"
            "        return ProviderCapabilities(capability_names=['legacy-cap-a'])\n"
            "    async def health(self):\n"
            "        return ProviderHealth(status=ProviderHealthStatus.HEALTHY)\n"
            "    async def execute(self, task, context=None):\n"
            "        return ExecutionResult(success=True, output='ok', exit_code=0)\n",
            encoding="utf-8",
        )

        record = lifecycle_manager.run_pipeline(str(manifest_path))
        assert record.state == "ACTIVE", f"Expected ACTIVE, got {record.state}: {record.diagnostics}"
        assert record.provider_id == "legacy-provider"

    def test_v1_load_manifest_function_still_works(self, tmp_path):
        from provider_sdk.manifest import load_manifest
        path = tmp_path / "v1_load.json"
        path.write_text(json.dumps(V1_MANIFEST_DATA), encoding="utf-8")
        m = load_manifest(str(path))
        assert m.provider_id == "legacy-provider"
        assert m.name == "Legacy Provider"
        assert m.capabilities == ["legacy-cap-a", "legacy-cap-b"]

    def test_v1_manifest_old_bootstrap_still_works(self):
        from provider_sdk.manifest import load_manifest, ProviderManifest, validate_manifest
        m = ProviderManifest(
            provider_id="old-school", name="Old School",
            capabilities=["old-cap"], adapter="old.py",
        )
        errors = validate_manifest(m)
        assert errors == []

    def test_v1_and_v2_coexist(self, tmp_path):
        from provider_sdk.manifest_v2 import parse_and_validate
        v1_path = tmp_path / "v1.json"
        v1_path.write_text(json.dumps(V1_MANIFEST_DATA), encoding="utf-8")
        (tmp_path / "legacy_adapter.py").write_text("class Provider: pass", encoding="utf-8")

        v2_data = {
            "id": "v2-coexist", "publisher": "jarvis-test",
            "version": "2.0.0",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "v2_adapter.py",
            "permissions": ["filesystem.read"],
            "platforms": ["windows"],
            "capabilities": [{"id": "v2-cap", "version": 1}],
        }
        v2_path = tmp_path / "v2.json"
        v2_path.write_text(json.dumps(v2_data), encoding="utf-8")
        (tmp_path / "v2_adapter.py").write_text("class Provider: pass", encoding="utf-8")

        d1 = parse_and_validate(str(v1_path))
        d2 = parse_and_validate(str(v2_path))
        assert d1.sdk_version == 1
        assert d2.sdk_version == 2
        assert d1.id == "legacy-provider"
        assert d2.id == "v2-coexist"
