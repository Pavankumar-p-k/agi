from __future__ import annotations

import json


class TestBootResilience:
    def test_bad_provider_does_not_crash(self, tmp_path):
        from provider_sdk.lifecycle import lifecycle_manager

        data = {
            "id": "broken-1", "publisher": "test",
            "version": "1.0.0",
            "sdk_version": 999, "api_version": 1, "minimum_jarvis": "99.0",
            "transport": "telepathy", "entrypoint": "/nonexistent/foo.py",
            "permissions": ["all"], "platforms": ["windows", "mars"],
            "capabilities": [],
        }
        path = tmp_path / "broken-1.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        record = lifecycle_manager.run_pipeline(str(path))
        assert record.state in ("REJECTED", "QUARANTINED")

    def test_bad_provider_does_not_block_good_provider(self, tmp_path):
        from provider_sdk.lifecycle import lifecycle_manager
        from provider_sdk.registration import TemporaryRegistry
        from provider_sdk.quarantine import quarantine_store

        TemporaryRegistry.clear()
        quarantine_store.clear()

        bad_data = {
            "id": "broken-2", "publisher": "test",
            "version": "1.0.0",
            "sdk_version": 999, "api_version": 1, "minimum_jarvis": "99.0",
            "transport": "telepathy", "entrypoint": "/nonexistent/foo.py",
            "permissions": ["all"], "platforms": ["windows", "mars"],
            "capabilities": [],
        }
        bad_path = tmp_path / "broken-2.json"
        bad_path.write_text(json.dumps(bad_data), encoding="utf-8")

        good_data = {
            "id": "resilient-good", "publisher": "jarvis-test",
            "version": "1.0.0",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "good_adapter.py",
            "permissions": ["filesystem.read"],
            "platforms": ["windows"],
            "capabilities": [{"id": "good-cap", "version": 1}],
        }
        good_path = tmp_path / "resilient-good.json"
        good_path.write_text(json.dumps(good_data), encoding="utf-8")
        (tmp_path / "good_adapter.py").write_text(
            "from __future__ import annotations\n"
            "from core.providers.base import ExecutionProvider, ProviderCapabilities, ProviderHealth, ProviderHealthStatus, ExecutionResult\n"
            "class Provider(ExecutionProvider):\n"
            "    provider_id = 'resilient-good'\n"
            "    name = 'Resilient Good'\n"
            "    def capabilities(self):\n"
            "        return ProviderCapabilities(capability_names=['good-cap'])\n"
            "    async def health(self):\n"
            "        return ProviderHealth(status=ProviderHealthStatus.HEALTHY)\n"
            "    async def execute(self, task, context=None):\n"
            "        return ExecutionResult(success=True, output='ok', exit_code=0)\n",
            encoding="utf-8",
        )

        bad_record = lifecycle_manager.run_pipeline(str(bad_path))
        assert bad_record.state in ("REJECTED", "QUARANTINED")

        quarantine_store._records.clear()

        good_record = lifecycle_manager.run_pipeline(str(good_path))
        assert good_record.state == "ACTIVE", f"Expected ACTIVE, got {good_record.state}: {good_record.diagnostics}"

    def test_duplicate_registration_safe(self, tmp_path):
        from provider_sdk.lifecycle import lifecycle_manager
        from provider_sdk.registration import TemporaryRegistry
        from provider_sdk.quarantine import quarantine_store

        TemporaryRegistry.clear()
        quarantine_store.clear()

        data = {
            "id": "dup-safe", "publisher": "jarvis-test",
            "version": "1.0.0",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "dup_adapter.py",
            "permissions": [],
            "platforms": ["windows"],
            "capabilities": [],
        }
        (tmp_path / "dup_adapter.py").write_text(
            "from __future__ import annotations\n"
            "from core.providers.base import ExecutionProvider, ProviderCapabilities, ProviderHealth, ProviderHealthStatus, ExecutionResult\n"
            "class Provider(ExecutionProvider):\n"
            "    provider_id = 'dup-safe'\n"
            "    name = 'Dup Safe'\n"
            "    def capabilities(self):\n"
            "        return ProviderCapabilities(capability_names=[])\n"
            "    async def health(self):\n"
            "        return ProviderHealth(status=ProviderHealthStatus.HEALTHY)\n"
            "    async def execute(self, task, context=None):\n"
            "        return ExecutionResult(success=True, output='ok', exit_code=0)\n",
            encoding="utf-8",
        )
        path = tmp_path / "dup-safe.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        r1 = lifecycle_manager.run_pipeline(str(path))
        assert r1.state == "ACTIVE"

        quarantine_store.clear()
        r2 = lifecycle_manager.run_pipeline(str(path))
        assert r2.state == "ACTIVE"

    def test_missing_manifest_no_crash(self):
        from provider_sdk.lifecycle import lifecycle_manager
        record = lifecycle_manager.run_pipeline("C:/nonexistent/manifest.json")
        assert record is not None
        assert record.state == "REJECTED"
