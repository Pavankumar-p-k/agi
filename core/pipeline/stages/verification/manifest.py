"""Plugin manifest integrity verification.

Migrated from core/plugins/verification.py (VRF-01).
"""
from __future__ import annotations

import hashlib
import json
import logging
from enum import StrEnum
from typing import Any

from core.pipeline.base import PipelineContext
from core.pipeline.stages.verification import Verifier, Verdict

logger = logging.getLogger("jarvis.plugins.verification")


class VerificationMode(StrEnum):
    STRICT = "strict"
    PERMISSIVE = "permissive"
    OFF = "off"


class ManifestVerifier(Verifier):
    """SHA-256 manifest verification with optional file checksum support.

    Can be used standalone or as a pipeline Verifier.
    """

    def __init__(self, mode: str = "permissive"):
        self._mode = VerificationMode(mode)

    @property
    def name(self) -> str:
        return "manifest_integrity"

    async def verify(self, context: PipelineContext) -> Verdict:
        manifest_path = context.metadata.get("manifest_path", "")
        if not manifest_path:
            return Verdict(
                verifier_name=self.name,
                outcome="PASS",
                message="No manifest to verify",
            )
        ok = self.verify_manifest_integrity(manifest_path)
        if ok:
            return Verdict(
                verifier_name=self.name,
                outcome="PASS",
                message=f"Manifest integrity verified: {manifest_path}",
            )
        return Verdict(
            verifier_name=self.name,
            outcome="FAIL",
            message=f"Manifest integrity check failed: {manifest_path}",
            blocking=True,
        )

    def verify_manifest_integrity(self, manifest_path: str) -> bool:
        """Verify that a plugin.json file has not been tampered with.

        Checks for an embedded ``checksum_sha256`` field. If present,
        computes SHA-256 of all other fields and compares.
        If absent in PERMISSIVE mode, accepts the manifest as-is.
        If absent in STRICT mode, rejects.
        If OFF, always returns True.
        """
        if self._mode == VerificationMode.OFF:
            return True

        try:
            with open(manifest_path, "rb") as f:
                raw = f.read()
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("[VERIFY] Cannot read manifest %s: %s", manifest_path, e)
            return False

        stored_checksum = data.pop("checksum_sha256", None)

        if stored_checksum is None:
            if self._mode == VerificationMode.STRICT:
                logger.error(
                    "[VERIFY] Manifest %s has no checksum_sha256 (strict mode)",
                    manifest_path,
                )
                return False
            logger.warning("[VERIFY] Manifest %s has no checksum — accepted (permissive)", manifest_path)
            return True

        manifest_bytes = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        computed = hashlib.sha256(manifest_bytes).hexdigest()

        if computed != stored_checksum:
            logger.error(
                "[VERIFY] Checksum mismatch for %s: expected=%s computed=%s",
                manifest_path, stored_checksum, computed,
            )
            return False

        logger.debug("[VERIFY] Manifest %s integrity verified", manifest_path)
        return True

    def verify_file_checksum(self, file_path: str, expected_sha256: str) -> bool:
        """Verify a downloaded file's SHA-256 checksum."""
        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            computed = h.hexdigest()
            if computed != expected_sha256:
                logger.error(
                    "[VERIFY] File checksum mismatch for %s: expected=%s computed=%s",
                    file_path, expected_sha256, computed,
                )
                return False
            return True
        except OSError as e:
            logger.error("[VERIFY] Cannot read file %s: %s", file_path, e)
            return False

    def compute_manifest_checksum(self, manifest_path: str) -> str:
        """Compute the SHA-256 checksum of a manifest file (all fields)."""
        with open(manifest_path, "rb") as f:
            raw = f.read()
        data = json.loads(raw)
        data.pop("checksum_sha256", None)
        manifest_bytes = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(manifest_bytes).hexdigest()

    def inject_checksum(self, manifest_path: str) -> str:
        """Compute and inject a ``checksum_sha256`` field into the manifest.

        Returns the computed checksum.
        """
        checksum = self.compute_manifest_checksum(manifest_path)
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        data["checksum_sha256"] = checksum
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("[VERIFY] Injected checksum into %s: %s", manifest_path, checksum)
        return checksum


manifest_verifier = ManifestVerifier()
