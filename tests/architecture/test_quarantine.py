from __future__ import annotations

import json
import time

import pytest


class TestQuarantineStore:
    def test_quarantine_record_persists(self):
        from provider_sdk.quarantine import QuarantineRecord, quarantine_store
        quarantine_store.clear()
        rec = QuarantineRecord(
            provider_id="quar-test", publisher="jarvis-test",
            version="1.0.0", fingerprint="abc123",
            last_healthy_fingerprint="",
            failing_stage="PROVIDER_LOAD",
            exception="ModuleNotFoundError",
            traceback="", timestamp=time.time(),
            retry_count=0,
            pipeline_version=1, manifest_version=2,
        )
        quarantine_store.quarantine(rec)
        loaded = quarantine_store.get("quar-test")
        assert loaded is not None
        assert loaded.failing_stage == "PROVIDER_LOAD"
        assert loaded.exception == "ModuleNotFoundError"

    def test_quarantine_increments_retry(self):
        from provider_sdk.quarantine import QuarantineRecord, quarantine_store
        quarantine_store.clear()
        rec = QuarantineRecord(
            provider_id="retry-test", publisher="p",
            version="1.0.0", fingerprint="x",
            last_healthy_fingerprint="",
            failing_stage="LOAD", exception="E",
            traceback="", timestamp=time.time(),
            retry_count=0, pipeline_version=1, manifest_version=2,
        )
        quarantine_store.quarantine(rec)
        assert quarantine_store.get("retry-test").retry_count == 0
        quarantine_store.quarantine(rec)
        assert quarantine_store.get("retry-test").retry_count == 1

    def test_remove_from_quarantine(self):
        from provider_sdk.quarantine import QuarantineRecord, quarantine_store
        quarantine_store.clear()
        rec = QuarantineRecord(
            provider_id="remove-me", publisher="p",
            version="1.0.0", fingerprint="x",
            last_healthy_fingerprint="",
            failing_stage="LOAD", exception="E",
            traceback="", timestamp=time.time(),
            retry_count=0, pipeline_version=1, manifest_version=2,
        )
        quarantine_store.quarantine(rec)
        assert quarantine_store.get("remove-me") is not None
        quarantine_store.remove("remove-me")
        assert quarantine_store.get("remove-me") is None

    def test_list_quarantined(self):
        from provider_sdk.quarantine import QuarantineRecord, quarantine_store
        quarantine_store.clear()
        for i in range(3):
            rec = QuarantineRecord(
                provider_id=f"list-{i}", publisher="p",
                version="1.0.0", fingerprint=f"fp-{i}",
                last_healthy_fingerprint="",
                failing_stage="STAGE", exception=f"E{i}",
                traceback="", timestamp=time.time(),
                retry_count=0, pipeline_version=1, manifest_version=2,
            )
            quarantine_store.quarantine(rec)
        items = quarantine_store.list_quarantined()
        assert len(items) == 3

    def test_record_roundtrip(self):
        from provider_sdk.quarantine import QuarantineRecord
        rec = QuarantineRecord(
            provider_id="rt", publisher="p",
            version="1.0.0", fingerprint="fp",
            last_healthy_fingerprint="old-fp",
            failing_stage="TEST", exception="X",
            traceback="trace...", timestamp=123.456,
            retry_count=2, pipeline_version=1, manifest_version=2,
        )
        d = rec.to_dict()
        rec2 = QuarantineRecord.from_dict(d)
        assert rec2.provider_id == "rt"
        assert rec2.last_healthy_fingerprint == "old-fp"
        assert rec2.retry_count == 2
        assert rec2.pipeline_version == 1

    def test_pipeline_quarantines_on_failure(self, tmp_path):
        from provider_sdk.lifecycle import lifecycle_manager
        from provider_sdk.quarantine import quarantine_store
        quarantine_store.clear()

        data = {"id": "will-quarantine", "publisher": "p", "version": "1",
                "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3",
                "transport": "python", "entrypoint": "/nonexistent/adapter.py",
                "permissions": [], "platforms": ["windows"],
                "capabilities": []}
        manifest_path = tmp_path / "will-quarantine.json"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        record = lifecycle_manager.run_pipeline(str(manifest_path))
        assert record.state == "QUARANTINED" or record.state == "REJECTED"
        qrec = quarantine_store.get("will-quarantine")
        if record.state == "QUARANTINED":
            assert qrec is not None

    def test_quarantine_early_rejection_same_fingerprint(self, tmp_path):
        from provider_sdk.lifecycle import lifecycle_manager
        from provider_sdk.quarantine import quarantine_store
        quarantine_store.clear()

        data = {"id": "early-reject", "publisher": "p", "version": "1",
                "sdk_version": 2, "api_version": 1, "minimum_jarvis": "3",
                "transport": "python", "entrypoint": "/nonexistent/e.py",
                "permissions": [], "platforms": ["windows"],
                "capabilities": []}
        path = tmp_path / "early-reject.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        record1 = lifecycle_manager.run_pipeline(str(path))
        assert record1.state in ("QUARANTINED", "REJECTED")
        record2 = lifecycle_manager.run_pipeline(str(path))
        assert record2.state == "REJECTED"
