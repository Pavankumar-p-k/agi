from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from provider_sdk.manifest_v2 import (
    PIPELINE_VERSION,
    ProviderDescriptor,
    StageResult,
    parse_and_validate,
)
from provider_sdk.stages import (
    DiscoveryStage,
    ManifestValidationStage,
    CompatibilityStage,
    PermissionDeclarationStage,
    ProviderLoadStage,
    SelfVerificationStage,
    CapabilityDiscoveryStage,
    RuntimePermissionRegistrationStage,
    AtomicRegistrationStage,
)
from provider_sdk.quarantine import QuarantineRecord, quarantine_store
from provider_sdk.registration import TemporaryRegistry

logger = logging.getLogger(__name__)


class ProviderLifecycleError(Exception):
    pass


@dataclass
class ProviderLifecycleRecord:
    provider_id: str
    publisher: str
    version: str
    state: str
    fingerprint: str
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "publisher": self.publisher,
            "version": self.version,
            "state": self.state,
            "fingerprint": self.fingerprint,
            "diagnostics": self.diagnostics,
        }


class ProviderLifecycleManager:
    def __init__(self) -> None:
        self._records: dict[str, ProviderLifecycleRecord] = {}

    @property
    def pipeline_version(self) -> int:
        return PIPELINE_VERSION

    def run_pipeline(self, manifest_path: str) -> ProviderLifecycleRecord:
        path = Path(manifest_path)

        # Check quarantine — if quarantined and fingerprint unchanged, reject early
        qrec = quarantine_store.get(path.stem)
        if qrec:
            try:
                descriptor = parse_and_validate(str(path))
                if descriptor.fingerprint == qrec.fingerprint:
                    return self._reject(
                        descriptor.id, descriptor.publisher, descriptor.version,
                        descriptor.fingerprint,
                        f"Provider is quarantined (fingerprint unchanged)",
                    )
            except Exception:
                pass

        # Stage 1: DISCOVERY
        discovery = DiscoveryStage()
        r1 = discovery.run(str(path))
        if not r1.success:
            return self._reject(path.stem, "", "", "", r1.diagnostics[0])

        raw_data = r1.metadata.get("raw_data", {})

        # Stage 2: MANIFEST VALIDATION
        validation = ManifestValidationStage()
        r2, descriptor = validation.run(raw_data, str(path))
        if not r2.success or descriptor is None:
            return self._reject(path.stem, "", "", "", r2.diagnostics[0])

        # Stage 3: COMPATIBILITY
        compat = CompatibilityStage()
        r3 = compat.run(descriptor)
        if not r3.success:
            return self._reject(descriptor.id, descriptor.publisher, descriptor.version,
                                descriptor.fingerprint, r3.diagnostics[0])

        # Stage 4: PERMISSION DECLARATION
        perm_decl = PermissionDeclarationStage()
        r4 = perm_decl.run(descriptor)
        if not r4.success:
            return self._reject(descriptor.id, descriptor.publisher, descriptor.version,
                                descriptor.fingerprint, r4.diagnostics[0])

        # Stage 5: PROVIDER LOAD
        loader = ProviderLoadStage()
        r5, descriptor = loader.run(descriptor)
        if not r5.success:
            return self._quarantine_or_reject(descriptor, r5)
        if descriptor.instance is None:
            return self._reject(descriptor.id, descriptor.publisher, descriptor.version,
                                descriptor.fingerprint, "Provider instance is None after load")

        # Stage 6: SELF VERIFICATION
        verifier = SelfVerificationStage()
        r6 = verifier.run(descriptor)
        if not r6.success:
            return self._quarantine_or_reject(descriptor, r6)

        # Stage 7: CAPABILITY DISCOVERY
        cap_discovery = CapabilityDiscoveryStage()
        r7 = cap_discovery.run(descriptor)
        if not r7.success:
            return self._quarantine_or_reject(descriptor, r7)

        # Stage 8: RUNTIME PERMISSION REGISTRATION
        runtime_perm = RuntimePermissionRegistrationStage()
        r8 = runtime_perm.run(descriptor)
        if not r8.success:
            return self._quarantine_or_reject(descriptor, r8)

        # Stage 9: ATOMIC REGISTRATION
        atomic_reg = AtomicRegistrationStage()
        TemporaryRegistry.stage(descriptor)
        r9 = atomic_reg.run(descriptor)
        if not r9.success:
            TemporaryRegistry.unstage(descriptor.id)
            return self._quarantine_or_reject(descriptor, r9)

        record = ProviderLifecycleRecord(
            provider_id=descriptor.id,
            publisher=descriptor.publisher,
            version=descriptor.version,
            state="ACTIVE",
            fingerprint=descriptor.fingerprint,
            diagnostics=[r.diagnostics[0] for r in [r1, r2, r3, r4, r5, r6, r7, r8, r9]],
        )
        self._records[descriptor.id] = record
        quarantine_store.remove(descriptor.id, descriptor.publisher)
        logger.info(
            "[Lifecycle] Provider %s/%s v%s → ACTIVE (fingerprint=%s)",
            descriptor.publisher, descriptor.id, descriptor.version,
            descriptor.fingerprint[:12],
        )
        return record

    def _quarantine_or_reject(self, descriptor: ProviderDescriptor, result: StageResult) -> ProviderLifecycleRecord:
        import traceback
        import time
        qrec = quarantine_store.get(descriptor.id, descriptor.publisher)
        last_healthy = qrec.last_healthy_fingerprint if qrec else ""
        record = QuarantineRecord(
            provider_id=descriptor.id,
            publisher=descriptor.publisher,
            version=descriptor.version,
            fingerprint=descriptor.fingerprint,
            last_healthy_fingerprint=last_healthy,
            failing_stage=result.metadata.get("stage", "UNKNOWN"),
            exception=result.metadata.get("reason", ""),
            traceback="",
            timestamp=time.time(),
            retry_count=qrec.retry_count if qrec else 0,
            pipeline_version=PIPELINE_VERSION,
            manifest_version=descriptor.sdk_version,
        )
        quarantine_store.quarantine(record)
        lr = ProviderLifecycleRecord(
            provider_id=descriptor.id,
            publisher=descriptor.publisher,
            version=descriptor.version,
            state="QUARANTINED",
            fingerprint=descriptor.fingerprint,
            diagnostics=[result.diagnostics[0]],
        )
        self._records[descriptor.id] = lr
        logger.warning(
            "[Lifecycle] Provider %s/%s → QUARANTINED (stage=%s, reason=%s)",
            descriptor.publisher, descriptor.id,
            record.failing_stage, record.exception,
        )
        return lr

    def _reject(self, pid: str, publisher: str, version: str, fingerprint: str, reason: str) -> ProviderLifecycleRecord:
        lr = ProviderLifecycleRecord(
            provider_id=pid,
            publisher=publisher or "unknown",
            version=version or "0.0.0",
            state="REJECTED",
            fingerprint=fingerprint or "unknown",
            diagnostics=[reason],
        )
        self._records[pid] = lr
        logger.warning("[Lifecycle] Provider %s → REJECTED: %s", pid, reason)
        return lr

    def get_records(self) -> list[ProviderLifecycleRecord]:
        return list(self._records.values())

    def get_active_ids(self) -> list[str]:
        return [r.provider_id for r in self._records.values() if r.state == "ACTIVE"]

    def clear(self) -> None:
        self._records.clear()

    def get_state_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._records.values():
            counts[r.state] = counts.get(r.state, 0) + 1
        return counts

    def get_state_list(self, state: str) -> list[ProviderLifecycleRecord]:
        return [r for r in self._records.values() if r.state == state]


lifecycle_manager = ProviderLifecycleManager()
