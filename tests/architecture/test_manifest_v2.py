from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestManifestV2Schema:
    def test_parse_valid_v2(self, tmp_path):
        from provider_sdk.manifest_v2 import parse_and_validate, ProviderDescriptor
        data = {
            "id": "test-provider", "publisher": "jarvis-test",
            "version": "1.2.3",
            "sdk_version": 2, "api_version": 2, "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "adapter.py",
            "permissions": ["filesystem.read", "network.http"],
            "platforms": ["windows"],
            "capabilities": [{"id": "search", "version": 1}],
        }
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        (tmp_path / "adapter.py").write_text("class Provider: pass", encoding="utf-8")
        desc = parse_and_validate(str(path))
        assert isinstance(desc, ProviderDescriptor)
        assert desc.id == "test-provider"
        assert desc.publisher == "jarvis-test"
        assert desc.version == "1.2.3"
        assert desc.sdk_version == 2
        assert desc.transport == "python"
        assert "filesystem.read" in desc.permissions
        assert len(desc.declared_capabilities) == 1

    def test_parse_v2_missing_required(self, tmp_path):
        from provider_sdk.manifest_v2 import parse_and_validate, ManifestError
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"id": "test", "sdk_version": 2}), encoding="utf-8")
        with pytest.raises(ManifestError, match="Missing required"):
            parse_and_validate(str(path))

    def test_validate_v2_schema_pass(self):
        from provider_sdk.manifest_v2 import validate_v2_schema
        data = {
            "id": "x", "publisher": "p", "version": "1",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3",
            "transport": "python", "entrypoint": "e.py",
            "permissions": [], "platforms": ["windows"],
        }
        errors = validate_v2_schema(data)
        assert errors == []

    def test_validate_v2_schema_bad_id(self):
        from provider_sdk.manifest_v2 import validate_v2_schema
        data = {
            "id": "Bad_ID!", "publisher": "p", "version": "1",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3",
            "transport": "python", "entrypoint": "e.py",
            "permissions": [], "platforms": ["windows"],
        }
        errors = validate_v2_schema(data)
        assert any("Invalid id" in e for e in errors)

    def test_validate_v2_schema_bad_transport(self):
        from provider_sdk.manifest_v2 import validate_v2_schema
        data = {
            "id": "x", "publisher": "p", "version": "1",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3",
            "transport": "telepathy", "entrypoint": "e.py",
            "permissions": [], "platforms": ["windows"],
        }
        errors = validate_v2_schema(data)
        assert any("Invalid transport" in e for e in errors)

    def test_validate_v2_schema_bad_platform(self):
        from provider_sdk.manifest_v2 import validate_v2_schema
        data = {
            "id": "x", "publisher": "p", "version": "1",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3",
            "transport": "python", "entrypoint": "e.py",
            "permissions": [], "platforms": ["windows", "ios"],
        }
        errors = validate_v2_schema(data)
        assert any("Invalid platform" in e for e in errors)

    def test_descriptor_is_frozen(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        desc = ProviderDescriptor(
            id="t", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="e.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="abc", manifest_path="/x.json", metadata={},
        )
        with pytest.raises(Exception):
            desc.id = "changed"

    def test_fingerprint_stable(self, tmp_path):
        from provider_sdk.manifest_v2 import parse_and_validate
        data = {
            "id": "fp-test", "publisher": "jarvis-test",
            "version": "1.0.0",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "fp_adapter.py",
            "permissions": [], "platforms": ["windows"],
            "capabilities": [],
        }
        path = tmp_path / "fp.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        (tmp_path / "fp_adapter.py").write_text("class Provider: pass", encoding="utf-8")
        d1 = parse_and_validate(str(path))
        d2 = parse_and_validate(str(path))
        assert d1.fingerprint == d2.fingerprint

    def test_v1_to_v2_conversion(self):
        from provider_sdk.manifest_v2 import v1_to_v2
        v1 = {
            "provider_id": "legacy", "name": "Legacy",
            "version": "1.0.0", "capabilities": ["cap_a", "cap_b"],
            "adapter": "legacy.py", "priority": 50,
        }
        result = v1_to_v2(v1, "/tmp/manifest.json")
        assert result["id"] == "legacy"
        assert result["publisher"] == "jarvis-core"
        assert result["sdk_version"] == 1
        assert result["transport"] == "python"
        assert len(result["capabilities"]) == 2

    def test_v1_to_v2_missing_fields_defaulted(self):
        from provider_sdk.manifest_v2 import v1_to_v2
        result = v1_to_v2({}, "/tmp/empty.json")
        assert result["id"] == "empty"
        assert result["version"] == "1.0.0"
        assert result["permissions"] == []
