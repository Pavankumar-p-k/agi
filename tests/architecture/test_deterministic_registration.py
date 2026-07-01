from __future__ import annotations

import json


class TestDeterministicRegistration:
    def test_same_manifest_produces_same_fingerprint(self, tmp_path):
        from provider_sdk.manifest_v2 import parse_and_validate
        data = {
            "id": "det-provider", "publisher": "jarvis-test",
            "version": "1.0.0",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "det_adapter.py",
            "permissions": ["filesystem.read"],
            "platforms": ["windows"],
            "capabilities": [{"id": "det-cap", "version": 1}],
        }
        (tmp_path / "det_adapter.py").write_text("class Provider: pass", encoding="utf-8")
        first = tmp_path / "first.json"
        first.write_text(json.dumps(data), encoding="utf-8")
        second = tmp_path / "second.json"
        second.write_text(json.dumps(data), encoding="utf-8")

        d1 = parse_and_validate(str(first))
        d2 = parse_and_validate(str(second))
        assert d1.fingerprint == d2.fingerprint

    def test_different_adapter_different_fingerprint(self, tmp_path):
        from provider_sdk.manifest_v2 import parse_and_validate
        data = {
            "id": "fp-diff", "publisher": "jarvis-test",
            "version": "1.0.0",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "fp_adapter.py",
            "permissions": [],
            "platforms": ["windows"],
            "capabilities": [],
        }
        m1 = tmp_path / "m1.json"
        m1.write_text(json.dumps(data), encoding="utf-8")
        (tmp_path / "fp_adapter.py").write_text(
            "class Provider: pass", encoding="utf-8",
        )
        d1 = parse_and_validate(str(m1))

        m2 = tmp_path / "m2.json"
        m2.write_text(json.dumps(data), encoding="utf-8")
        (tmp_path / "fp_adapter.py").write_text(
            "class Provider: pass\n# different content",
            encoding="utf-8",
        )
        d2 = parse_and_validate(str(m2))

        assert d1.fingerprint != d2.fingerprint

    def test_same_fingerprint_idempotent_registration(self, tmp_path):
        from provider_sdk.manifest_v2 import parse_and_validate
        data = {
            "id": "idempotent", "publisher": "jarvis-test",
            "version": "1.0.0",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "idem_adapter.py",
            "permissions": [],
            "platforms": ["windows"],
            "capabilities": [],
        }
        path = tmp_path / "idem.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        (tmp_path / "idem_adapter.py").write_text("class Provider: pass", encoding="utf-8")

        d1 = parse_and_validate(str(path))
        d2 = parse_and_validate(str(path))
        assert d1.fingerprint == d2.fingerprint
        assert d1.id == d2.id
        assert d1.version == d2.version

    def test_pipeline_idempotent(self, tmp_path):
        from provider_sdk.lifecycle import lifecycle_manager
        from provider_sdk.registration import TemporaryRegistry
        from provider_sdk.quarantine import quarantine_store
        TemporaryRegistry.clear()
        quarantine_store.clear()

        data = {
            "id": "idem-pipeline", "publisher": "jarvis-test",
            "version": "1.0.0",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "idem_adapter.py",
            "permissions": [],
            "platforms": ["windows"],
            "capabilities": [],
        }
        (tmp_path / "idem_adapter.py").write_text(
            "from __future__ import annotations\n"
            "from core.providers.base import ExecutionProvider, ProviderCapabilities, ProviderHealth, ProviderHealthStatus, ExecutionResult\n"
            "class Provider(ExecutionProvider):\n"
            "    provider_id = 'idem-pipeline'\n"
            "    name = 'Idempotent'\n"
            "    def capabilities(self):\n"
            "        return ProviderCapabilities(capability_names=[])\n"
            "    async def health(self):\n"
            "        return ProviderHealth(status=ProviderHealthStatus.HEALTHY)\n"
            "    async def execute(self, task, context=None):\n"
            "        return ExecutionResult(success=True, output='ok', exit_code=0)\n",
            encoding="utf-8",
        )
        manifest_path = tmp_path / "idem-pipeline.json"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        r1 = lifecycle_manager.run_pipeline(str(manifest_path))
        quarantine_store._records.clear()
        r2 = lifecycle_manager.run_pipeline(str(manifest_path))
        assert r1.state == r2.state

    def test_build_descriptor_deterministic(self, tmp_path):
        from provider_sdk.manifest_v2 import build_descriptor
        import json
        data = {
            "id": "det-build", "publisher": "p",
            "version": "1.0.0",
            "sdk_version": 2, "api_version": 1,
            "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "det/adapter.py",
            "permissions": ["filesystem.read"],
            "platforms": ["windows"],
            "capabilities": [{"id": "c1", "version": 1}],
        }
        (tmp_path / "det").mkdir(parents=True, exist_ok=True)
        (tmp_path / "det" / "adapter.py").write_text("class Provider: pass", encoding="utf-8")
        m1 = tmp_path / "m1.json"
        m1.write_text(json.dumps(data), encoding="utf-8")
        m2 = tmp_path / "m2.json"
        m2.write_text(json.dumps(data), encoding="utf-8")
        d1 = build_descriptor(data, str(m1))
        d2 = build_descriptor(data, str(m2))
        assert d1.fingerprint == d2.fingerprint
