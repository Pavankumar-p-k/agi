from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from provider_sdk.manifest_v2 import (
    PIPELINE_VERSION,
    ProviderDescriptor,
    StageResult,
    build_descriptor,
    detect_manifest_version,
    load_raw_manifest,
    parse_and_validate,
    validate_v2_schema,
    v1_to_v2,
)
from provider_sdk.permissions import permission_manager, validate_permissions

logger = logging.getLogger(__name__)

_STAGE_ORDER: list[str] = [
    "DISCOVERY",
    "MANIFEST_VALIDATION",
    "COMPATIBILITY",
    "PERMISSION_DECLARATION",
    "PROVIDER_LOAD",
    "SELF_VERIFICATION",
    "CAPABILITY_DISCOVERY",
    "RUNTIME_PERMISSION_REGISTRATION",
    "ATOMIC_REGISTRATION",
]


def _fail(stage: str, reason: str, detail: str = "") -> StageResult:
    diag = f"[{stage}] {reason}"
    if detail:
        diag += f": {detail}"
    return StageResult(
        success=False,
        next_state="REJECTED",
        diagnostics=(diag,),
        metadata={"stage": stage, "reason": reason},
    )


def _ok(stage: str, next_state: str = "VALIDATED", **metadata: Any) -> StageResult:
    return StageResult(
        success=True,
        next_state=next_state,
        diagnostics=(f"[{stage}] Passed",),
        metadata={"stage": stage, **metadata},
    )


# ── Stage 1: DISCOVERY ────────────────────────────────────────────────────


class DiscoveryStage:
    def run(self, manifest_path: str) -> StageResult:
        try:
            raw = load_raw_manifest(manifest_path)
            version = detect_manifest_version(raw)
            return _ok(
                "DISCOVERY",
                raw_data=raw,
                manifest_version=version,
                path=manifest_path,
            )
        except Exception as e:
            return _fail("DISCOVERY", f"Cannot load manifest", str(e))


# ── Stage 2: MANIFEST VALIDATION ──────────────────────────────────────────


class ManifestValidationStage:
    def run(self, raw_data: dict, manifest_path: str) -> tuple[StageResult, ProviderDescriptor | None]:
        version = detect_manifest_version(raw_data)
        try:
            if version == 1:
                normalized = v1_to_v2(raw_data, manifest_path)
                desc = build_descriptor(normalized, manifest_path)
                return _ok("MANIFEST_VALIDATION", manifest_version=1), desc
            else:
                errors = validate_v2_schema(raw_data)
                if errors:
                    return _fail("MANIFEST_VALIDATION", "Schema validation failed", "; ".join(errors)), None
                descriptor = build_descriptor(raw_data, manifest_path)
                return _ok("MANIFEST_VALIDATION", manifest_version=2), descriptor
        except Exception as e:
            return _fail("MANIFEST_VALIDATION", "Unexpected error", str(e)), None


# ── Stage 3: COMPATIBILITY ────────────────────────────────────────────────


class CompatibilityStage:
    def run(self, descriptor: ProviderDescriptor) -> StageResult:
        errors: list[str] = []
        if descriptor.sdk_version > PIPELINE_VERSION:
            errors.append(f"sdk_version {descriptor.sdk_version} > pipeline version {PIPELINE_VERSION}")
        if descriptor.sdk_version < 1:
            errors.append(f"sdk_version {descriptor.sdk_version} < 1")
        if descriptor.api_version < 1:
            errors.append(f"api_version {descriptor.api_version} < 1")
        if descriptor.transport not in ("python", "mcp", "http", "grpc", "cli"):
            errors.append(f"Unsupported transport: {descriptor.transport}")
        if not descriptor.entrypoint:
            errors.append("No entrypoint specified")
        if errors:
            return _fail("COMPATIBILITY", "Compatibility check failed", "; ".join(errors))
        return _ok("COMPATIBILITY")


# ── Stage 4: PERMISSION DECLARATION ───────────────────────────────────────


class PermissionDeclarationStage:
    def run(self, descriptor: ProviderDescriptor) -> StageResult:
        perm_list = list(descriptor.permissions)
        errors = validate_permissions(perm_list)
        if errors:
            return _fail("PERMISSION_DECLARATION", "Permission validation failed", "; ".join(errors))
        if not perm_list:
            logger.warning(
                "[PermissionDeclaration] Provider %s declares no permissions — will be restricted",
                descriptor.id,
            )
        return _ok("PERMISSION_DECLARATION", permissions=perm_list)


# ── Stage 5: PROVIDER LOAD ────────────────────────────────────────────────


class ProviderLoadStage:
    def run(self, descriptor: ProviderDescriptor) -> tuple[StageResult, ProviderDescriptor]:
        if descriptor.transport != "python":
            return _fail("PROVIDER_LOAD", f"Non-python transports not yet supported: {descriptor.transport}"), descriptor
        adapter_path = descriptor.entrypoint
        if not Path(adapter_path).is_absolute():
            base = Path(descriptor.manifest_path).parent
            adapter_path = str(base / adapter_path)
        if not Path(adapter_path).exists():
            return _fail("PROVIDER_LOAD", f"Adapter not found", adapter_path), descriptor
        try:
            spec = importlib.util.spec_from_file_location(
                f"provider_{descriptor.id}", adapter_path,
            )
            if not spec or not spec.loader:
                return _fail("PROVIDER_LOAD", "Cannot load adapter spec"), descriptor
            mod = importlib.util.module_from_spec(spec)
            sys.modules[f"provider_{descriptor.id}"] = mod
            spec.loader.exec_module(mod)
            provider_class = getattr(mod, "Provider", None)
            if not provider_class:
                return _fail("PROVIDER_LOAD", "No Provider class found"), descriptor
            instance = provider_class()
            new_desc = replace(descriptor, instance=instance)
            return _ok("PROVIDER_LOAD", loaded=True, pclass=provider_class.__name__), new_desc
        except Exception as e:
            import traceback
            return _fail("PROVIDER_LOAD", f"Load failed", f"{type(e).__name__}: {e}"), descriptor


# ── Stage 6: SELF VERIFICATION ────────────────────────────────────────────


class SelfVerificationStage:
    def run(self, descriptor: ProviderDescriptor) -> StageResult:
        instance = descriptor.instance
        if instance is None:
            return _fail("SELF_VERIFICATION", "No provider instance loaded")
        errors: list[str] = []
        try:
            caps = instance.capabilities()
            runtime_ids = set(caps.capability_names)
        except Exception as e:
            return _fail("SELF_VERIFICATION", "capabilities() failed", str(e))
        declared_ids = {c["id"] for c in descriptor.declared_capabilities}
        extra_runtime = runtime_ids - declared_ids
        if extra_runtime:
            logger.warning(
                "[SelfVerification] Provider %s has undeclared capabilities: %s",
                descriptor.id, sorted(extra_runtime),
            )
        missing_runtime = declared_ids - runtime_ids
        if missing_runtime:
            logger.warning(
                "[SelfVerification] Provider %s declared but missing at runtime: %s",
                descriptor.id, sorted(missing_runtime),
            )
        try:
            health = instance.health()
            if asyncio.iscoroutine(health):
                health = asyncio.run(health)
        except Exception as e:
            return _fail("SELF_VERIFICATION", f"health() failed: {e}")
        try:
            ver = getattr(instance, "version", descriptor.version)
        except Exception:
            ver = descriptor.version
        if errors:
            return _fail("SELF_VERIFICATION", "; ".join(errors))
        return _ok(
            "SELF_VERIFICATION",
            runtime_capabilities=sorted(runtime_ids),
            extra_capabilities=sorted(extra_runtime),
            health_status=getattr(health, "status", "unknown"),
            version=ver,
        )


# ── Stage 7: CAPABILITY DISCOVERY ─────────────────────────────────────────


class CapabilityDiscoveryStage:
    def run(self, descriptor: ProviderDescriptor) -> StageResult:
        instance = descriptor.instance
        if instance is None:
            return _fail("CAPABILITY_DISCOVERY", "No provider instance loaded")
        try:
            caps = instance.capabilities()
            return _ok(
                "CAPABILITY_DISCOVERY",
                capability_names=list(caps.capability_names),
                features=list(caps.features),
                languages=list(caps.languages),
            )
        except Exception as e:
            return _fail("CAPABILITY_DISCOVERY", "capabilities() failed", str(e))


# ── Stage 8: RUNTIME PERMISSION REGISTRATION ──────────────────────────────


class RuntimePermissionRegistrationStage:
    def run(self, descriptor: ProviderDescriptor) -> StageResult:
        permission_manager.grant(descriptor.id, descriptor.permissions)
        return _ok(
            "RUNTIME_PERMISSION_REGISTRATION",
            granted_permissions=sorted(descriptor.permissions),
            high_risk=bool(descriptor.permissions & {
                "system.shell", "desktop.mouse.click", "desktop.keyboard.type",
            }),
        )


# ── Stage 9: ATOMIC REGISTRATION ──────────────────────────────────────────


class AtomicRegistrationStage:
    def run(self, descriptor: ProviderDescriptor) -> StageResult:
        from provider_sdk.registration import TemporaryRegistry
        ok = TemporaryRegistry.commit(descriptor)
        if not ok:
            return _fail("ATOMIC_REGISTRATION", "Commit failed", "Provider not staged or no instance")
        return _ok(
            "ATOMIC_REGISTRATION",
            next_state="ACTIVE",
            provider_id=descriptor.id,
            fingerprint=descriptor.fingerprint,
        )
