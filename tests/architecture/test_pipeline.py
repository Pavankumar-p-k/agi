from __future__ import annotations

import json
from pathlib import Path

import pytest


ADAPTER_CODE = """\
from __future__ import annotations
from core.providers.base import ExecutionProvider, ProviderCapabilities, ProviderHealth, ProviderHealthStatus, ExecutionResult

class Provider(ExecutionProvider):
    provider_id = "pipeline-test"
    name = "Pipeline Test"
    def capabilities(self):
        return ProviderCapabilities(capability_names=["pipeline-cap"])
    async def health(self):
        return ProviderHealth(status=ProviderHealthStatus.HEALTHY)
    async def execute(self, task, context=None):
        return ExecutionResult(success=True, output="ok", exit_code=0)
"""


@pytest.fixture
def valid_v2_manifest(tmp_path):
    data = {
        "id": "pipeline-test", "publisher": "jarvis-test",
        "version": "2.0.0",
        "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3.0.0",
        "transport": "python", "entrypoint": "adapter.py",
        "permissions": ["filesystem.read", "network.http"],
        "platforms": ["windows"],
        "capabilities": [{"id": "pipeline-cap", "version": 1}],
    }
    manifest_path = tmp_path / "pipeline-test.json"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "adapter.py").write_text(ADAPTER_CODE, encoding="utf-8")
    return str(manifest_path)


class TestPipelineStages:
    def test_full_pipeline_success(self, valid_v2_manifest):
        from provider_sdk.lifecycle import lifecycle_manager
        from provider_sdk.registration import TemporaryRegistry
        TemporaryRegistry.clear()
        record = lifecycle_manager.run_pipeline(valid_v2_manifest)
        assert record.state == "ACTIVE"
        assert record.provider_id == "pipeline-test"
        assert record.diagnostics

    def test_discovery_rejects_nonexistent(self):
        from provider_sdk.stages import DiscoveryStage
        stage = DiscoveryStage()
        result = stage.run("/nonexistent/manifest.json")
        assert not result.success
        assert result.next_state == "REJECTED"

    def test_validation_rejects_bad_v2_schema(self, tmp_path):
        from provider_sdk.stages import ManifestValidationStage
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"id": "bad", "sdk_version": 2}), encoding="utf-8")
        from provider_sdk.manifest_v2 import load_raw_manifest, detect_manifest_version
        raw = load_raw_manifest(str(path))
        stage = ManifestValidationStage()
        result, desc = stage.run(raw, str(path))
        assert not result.success
        assert desc is None

    def test_compatibility_rejects_unsupported_transport(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor, StageResult
        from provider_sdk.stages import CompatibilityStage
        desc = ProviderDescriptor(
            id="bad", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="telepathy",
            entrypoint="e.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
        )
        stage = CompatibilityStage()
        result = stage.run(desc)
        assert not result.success
        assert "Unsupported transport" in result.diagnostics[0]

    def test_compatibility_rejects_sdk_version_too_high(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor, PIPELINE_VERSION
        from provider_sdk.stages import CompatibilityStage
        desc = ProviderDescriptor(
            id="high", publisher="p", version="1",
            sdk_version=PIPELINE_VERSION + 1, api_version=1, transport="python",
            entrypoint="e.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
        )
        stage = CompatibilityStage()
        result = stage.run(desc)
        assert not result.success
        assert "sdk_version" in result.diagnostics[0]

    def test_compatibility_passes(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.stages import CompatibilityStage
        desc = ProviderDescriptor(
            id="good", publisher="p", version="1",
            sdk_version=1, api_version=1, transport="python",
            entrypoint="e.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
        )
        stage = CompatibilityStage()
        result = stage.run(desc)
        assert result.success

    def test_permission_declaration_rejects_wildcard(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.stages import PermissionDeclarationStage
        desc = ProviderDescriptor(
            id="wild", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="e.py", permissions=frozenset({"all"}),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
        )
        stage = PermissionDeclarationStage()
        result = stage.run(desc)
        assert not result.success
        assert "Wildcard" in result.diagnostics[0]

    def test_provider_load_fails_no_file(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.stages import ProviderLoadStage
        desc = ProviderDescriptor(
            id="missing", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="/nonexistent/adapter.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
        )
        stage = ProviderLoadStage()
        result, new_desc = stage.run(desc)
        assert not result.success
        assert "not found" in result.diagnostics[0]

    def test_provider_load_fails_no_provider_class(self, tmp_path):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.stages import ProviderLoadStage
        adapter_path = tmp_path / "noclass.py"
        adapter_path.write_text("# no Provider class", encoding="utf-8")
        desc = ProviderDescriptor(
            id="noclass", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="python",
            entrypoint=str(adapter_path), permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path=str(tmp_path / "m.json"), metadata={},
        )
        stage = ProviderLoadStage()
        result, new_desc = stage.run(desc)
        assert not result.success

    def test_self_verification_fails_no_instance(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.stages import SelfVerificationStage
        desc = ProviderDescriptor(
            id="noinst", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="e.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
        )
        stage = SelfVerificationStage()
        result = stage.run(desc)
        assert not result.success
        assert "No provider instance" in result.diagnostics[0]

    def test_capability_discovery_fails_no_instance(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.stages import CapabilityDiscoveryStage
        desc = ProviderDescriptor(
            id="noinst2", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="e.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
        )
        stage = CapabilityDiscoveryStage()
        result = stage.run(desc)
        assert not result.success

    def test_atomic_registration_fails_unstaged(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.stages import AtomicRegistrationStage
        from provider_sdk.registration import TemporaryRegistry
        TemporaryRegistry.clear()
        desc = ProviderDescriptor(
            id="unstaged", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="e.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
        )
        stage = AtomicRegistrationStage()
        result = stage.run(desc)
        assert not result.success
