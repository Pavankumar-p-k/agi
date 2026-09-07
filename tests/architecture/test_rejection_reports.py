from __future__ import annotations

import json


class TestRejectionReports:
    def test_rejected_record_has_diagnostics(self):
        from provider_sdk.lifecycle import lifecycle_manager
        record = lifecycle_manager.run_pipeline("/nonexistent/manifest.json")
        assert record.state == "REJECTED"
        assert len(record.diagnostics) > 0
        assert all(isinstance(d, str) for d in record.diagnostics)

    def test_rejected_has_state_metadata(self):
        from provider_sdk.lifecycle import lifecycle_manager
        record = lifecycle_manager.run_pipeline("/nonexistent/manifest.json")
        assert record.state
        assert record.provider_id
        assert record.fingerprint

    def test_quarantine_record_full_fields(self, tmp_path):
        from provider_sdk.lifecycle import lifecycle_manager
        from provider_sdk.quarantine import quarantine_store

        data = {
            "id": "full-fields-reject", "publisher": "jarvis-test",
            "version": "1.0.0",
            "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3.0.0",
            "transport": "python", "entrypoint": "/nonexistent/adapter.py",
            "permissions": [], "platforms": ["windows"],
            "capabilities": [],
        }
        path = tmp_path / "full-fields.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        record = lifecycle_manager.run_pipeline(str(path))
        assert record.state in ("QUARANTINED", "REJECTED")

        qrec = quarantine_store.get("full-fields-reject")
        if qrec:
            assert qrec.failing_stage
            assert qrec.exception
            from provider_sdk.manifest_v2 import PIPELINE_VERSION
            assert qrec.pipeline_version == PIPELINE_VERSION
            assert qrec.manifest_version >= 1
            assert qrec.timestamp > 0

    def test_provider_lifecycle_record_to_dict(self):
        from provider_sdk.lifecycle import ProviderLifecycleRecord
        record = ProviderLifecycleRecord(
            provider_id="test", publisher="p", version="1.0.0",
            state="REJECTED", fingerprint="abc123",
            diagnostics=["Stage failed"],
        )
        d = record.to_dict()
        assert d["provider_id"] == "test"
        assert d["publisher"] == "p"
        assert d["state"] == "REJECTED"
        assert d["fingerprint"] == "abc123"
        assert d["diagnostics"] == ["Stage failed"]

    def test_stage_result_failure_has_reason(self):
        from provider_sdk.manifest_v2 import StageResult
        result = StageResult(
            success=False, next_state="REJECTED",
            diagnostics=("[COMPATIBILITY] Unsupported transport: telepathy",),
            metadata={"stage": "COMPATIBILITY", "reason": "Unsupported transport"},
        )
        assert not result.success
        assert result.next_state == "REJECTED"
        assert "telepathy" in result.diagnostics[0]

    def test_stage_result_success_has_diagnostics(self):
        from provider_sdk.manifest_v2 import StageResult
        result = StageResult(
            success=True, next_state="VALIDATED",
            diagnostics=("[DISCOVERY] Passed",),
            metadata={"stage": "DISCOVERY"},
        )
        assert result.success
        assert result.next_state == "VALIDATED"
