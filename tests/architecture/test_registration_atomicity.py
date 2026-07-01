from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


class TestTemporaryRegistry:
    def test_stage_and_commit(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.registration import TemporaryRegistry
        TemporaryRegistry.clear()

        desc = ProviderDescriptor(
            id="atomic-test", publisher="jarvis-test", version="1.0.0",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="adapter.py",
            permissions=frozenset(),
            declared_capabilities=(),
            platforms=("windows",),
            fingerprint="abc123",
            manifest_path="/tmp/manifest.json",
            metadata={},
        )
        TemporaryRegistry.stage(desc)
        mock_instance = MagicMock()
        mock_instance.provider_id = "atomic-test"
        mock_instance.capabilities.return_value.capability_names = []
        desc_with_inst = ProviderDescriptor(
            id="atomic-test", publisher="jarvis-test", version="1.0.0",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="adapter.py",
            permissions=frozenset(),
            declared_capabilities=(),
            platforms=("windows",),
            fingerprint="abc123",
            manifest_path="/tmp/manifest.json",
            metadata={},
            instance=mock_instance,
        )
        result = TemporaryRegistry.commit(desc_with_inst)
        assert result is True

    def test_commit_unstaged_fails(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.registration import TemporaryRegistry
        TemporaryRegistry.clear()

        desc = ProviderDescriptor(
            id="never-staged", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="e.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
            instance=object(),
        )
        result = TemporaryRegistry.commit(desc)
        assert result is False

    def test_commit_no_instance_fails(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.registration import TemporaryRegistry
        TemporaryRegistry.clear()

        desc = ProviderDescriptor(
            id="no-instance", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="e.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
        )
        TemporaryRegistry.stage(desc)
        result = TemporaryRegistry.commit(desc)
        assert result is False

    def test_unstage_removes(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        from provider_sdk.registration import TemporaryRegistry
        TemporaryRegistry.clear()

        desc = ProviderDescriptor(
            id="to-unstage", publisher="p", version="1",
            sdk_version=2, api_version=1, transport="python",
            entrypoint="e.py", permissions=frozenset(),
            declared_capabilities=(), platforms=("windows",),
            fingerprint="x", manifest_path="x.json", metadata={},
        )
        TemporaryRegistry.stage(desc)
        assert "to-unstage" in TemporaryRegistry._staged
        TemporaryRegistry.unstage("to-unstage")
        assert "to-unstage" not in TemporaryRegistry._staged

    def test_no_partial_registration_on_failure(self):
        from provider_sdk.lifecycle import lifecycle_manager
        from provider_sdk.registration import TemporaryRegistry
        TemporaryRegistry.clear()

        staged_before = len(TemporaryRegistry._staged)
        record = lifecycle_manager.run_pipeline("/nonexistent/manifest.json")
        assert record.state == "REJECTED"
        staged_after = len(TemporaryRegistry._staged)
        assert staged_after >= staged_before
