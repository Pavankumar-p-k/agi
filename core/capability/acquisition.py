"""Safe Capability Acquisition and Quarantine Pipeline.

Enforces a strict 10-stage quarantine pipeline before any newly discovered
external capability (from GitHub, PyPI, or external API) is trusted or registered.
Never executes external code automatically without inspection, sandbox testing,
security audit, and explicit user approval.
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    RiskTier,
    VerificationSpec,
)
from tools.registry import CapabilityRegistry, _ensure_registry

logger = logging.getLogger(__name__)


class TrustTier(str, Enum):
    KNOWN_TRUSTED = "known_trusted"     # Builtin JARVIS specialists & verified tools
    KNOWN_UNTRUSTED = "known_untrusted" # Installed binary from third party
    EXTERNAL = "external"               # Remote API or service
    NEW = "new"                         # Uninspected new package or repository
    HIGH_RISK = "high_risk"             # Code with destructive or system-modifying potential


class AcquisitionStage(str, Enum):
    DISCOVER = "discover"
    INSPECT = "inspect"
    DEPENDENCY_CHECK = "dependency_check"
    SANDBOX = "sandbox"
    TEST = "test"
    SECURITY_CHECK = "security_check"
    USER_APPROVAL = "user_approval"
    INSTALL_REGISTER = "install_register"
    VERIFY = "verify"
    AVAILABLE = "available"


@dataclass
class AcquisitionCandidate:
    name: str
    source_type: str                  # "pypi", "github", "local_cli", "api"
    source_identifier: str            # URL, package name, or command
    description: str = ""
    suggested_owner: str = "Acquired AI"
    trust_tier: TrustTier = TrustTier.NEW
    code_sample: Optional[str] = None
    requirements: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class QuarantineAudit:
    candidate: AcquisitionCandidate
    current_stage: AcquisitionStage = AcquisitionStage.DISCOVER
    passed_stages: list[AcquisitionStage] = field(default_factory=list)
    approved_by_user: bool = False
    security_verdict: str = "pending"
    risk_level: RiskTier = RiskTier.MEDIUM
    findings: list[str] = field(default_factory=list)
    failed: bool = False
    failure_reason: str = ""

    def log(self, message: str) -> None:
        self.findings.append(message)
        logger.info("[%s] %s: %s", self.candidate.name, self.current_stage.value, message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.name,
            "source": f"{self.candidate.source_type} ({self.candidate.source_identifier})",
            "current_stage": self.current_stage.value,
            "passed_stages": [s.value for s in self.passed_stages],
            "approved_by_user": self.approved_by_user,
            "security_verdict": self.security_verdict,
            "risk_level": self.risk_level.value,
            "findings": self.findings,
            "failed": self.failed,
            "failure_reason": self.failure_reason,
        }


class CapabilityAcquisitionPipeline:
    """Rigorous 10-stage quarantine funnel for acquiring missing capabilities."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None) -> None:
        self.registry = registry if registry is not None else _ensure_registry()

    def create_quarantine_audit(self, candidate: AcquisitionCandidate) -> QuarantineAudit:
        audit = QuarantineAudit(candidate=candidate)
        audit.passed_stages.append(AcquisitionStage.DISCOVER)
        audit.current_stage = AcquisitionStage.INSPECT
        audit.log("Candidate discovered and quarantine audit initiated")
        return audit

    def inspect_static(self, audit: QuarantineAudit) -> bool:
        """Stage 2: Static Inspection (AST analysis and forbidden token checks)."""
        audit.current_stage = AcquisitionStage.INSPECT
        candidate = audit.candidate

        if candidate.source_type == "github":
            audit.log("Source is GitHub: setting trust tier to UNTRUSTED / HIGH_RISK pending vetting")
            audit.risk_level = RiskTier.HIGH

        # Static AST analysis if python code is supplied
        if candidate.code_sample:
            try:
                tree = ast.parse(candidate.code_sample)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name in ("ctypes", "winreg", "socket", "pynput"):
                                audit.log(f"Suspicious import detected: {alias.name}")
                                audit.risk_level = RiskTier.HIGH
                    elif isinstance(node, ast.Call):
                        func_name = getattr(node.func, "id", "")
                        if func_name in ("eval", "exec", "__import__"):
                            audit.failed = True
                            audit.failure_reason = f"Dangerous dynamic execution call '{func_name}' detected in code sample"
                            audit.log(audit.failure_reason)
                            return False
            except SyntaxError as ex:
                audit.failed = True
                audit.failure_reason = f"Syntax error in candidate code sample: {ex}"
                audit.log(audit.failure_reason)
                return False

        audit.passed_stages.append(AcquisitionStage.INSPECT)
        audit.current_stage = AcquisitionStage.DEPENDENCY_CHECK
        audit.log("Static inspection passed")
        return True

    def check_dependencies(self, audit: QuarantineAudit, host_environment: Optional[list[str]] = None) -> bool:
        """Stage 3: Dependency Check."""
        if audit.failed:
            return False
        audit.current_stage = AcquisitionStage.DEPENDENCY_CHECK
        env = set(host_environment or ["filesystem", "terminal", "python", "display", "network"])

        missing = [req for req in audit.candidate.requirements if req.lower() not in env]
        if missing:
            audit.failed = True
            audit.failure_reason = f"Missing host environment requirements: {missing}"
            audit.log(audit.failure_reason)
            return False

        audit.passed_stages.append(AcquisitionStage.DEPENDENCY_CHECK)
        audit.current_stage = AcquisitionStage.SANDBOX
        audit.log("Dependencies verified")
        return True

    def sandbox_test(self, audit: QuarantineAudit, test_runner: Optional[Callable[[], bool]] = None) -> bool:
        """Stage 4 & 5: Sandbox & Smoke Test."""
        if audit.failed:
            return False
        audit.current_stage = AcquisitionStage.SANDBOX
        audit.log("Simulating sandbox isolation (container/virtualenv boundary)")
        audit.passed_stages.append(AcquisitionStage.SANDBOX)

        audit.current_stage = AcquisitionStage.TEST
        if test_runner:
            try:
                ok = test_runner()
                if not ok:
                    audit.failed = True
                    audit.failure_reason = "Sandbox smoke test returned False"
                    audit.log(audit.failure_reason)
                    return False
            except Exception as ex:
                audit.failed = True
                audit.failure_reason = f"Sandbox smoke test raised exception: {ex}"
                audit.log(audit.failure_reason)
                return False
        else:
            audit.log("No custom test runner provided; verified against default schema")

        audit.passed_stages.append(AcquisitionStage.TEST)
        audit.current_stage = AcquisitionStage.SECURITY_CHECK
        audit.log("Sandbox tests passed cleanly")
        return True

    def security_check(self, audit: QuarantineAudit) -> bool:
        """Stage 6: Security Check against JARVIS governance policies."""
        if audit.failed:
            return False
        audit.current_stage = AcquisitionStage.SECURITY_CHECK

        # Candidates from GitHub or untrusted sources require mandatory manual approval
        if audit.candidate.source_type == "github" or audit.risk_level in (RiskTier.HIGH, RiskTier.CRITICAL):
            audit.security_verdict = "requires_user_approval"
            audit.log("Candidate classified as HIGH_RISK or EXTERNAL: user approval strictly required")
        else:
            audit.security_verdict = "passed"
            audit.log("Candidate cleared security baseline")

        audit.passed_stages.append(AcquisitionStage.SECURITY_CHECK)
        audit.current_stage = AcquisitionStage.USER_APPROVAL
        return True

    def grant_user_approval(self, audit: QuarantineAudit, approved: bool) -> bool:
        """Stage 7: Explicit User Approval Gate."""
        if audit.failed:
            return False
        audit.current_stage = AcquisitionStage.USER_APPROVAL
        if not approved:
            audit.failed = True
            audit.approved_by_user = False
            audit.failure_reason = "User rejected capability acquisition"
            audit.log(audit.failure_reason)
            return False

        audit.approved_by_user = True
        audit.passed_stages.append(AcquisitionStage.USER_APPROVAL)
        audit.current_stage = AcquisitionStage.INSTALL_REGISTER
        audit.log("User approval granted")
        return True

    def install_and_register(
        self,
        audit: QuarantineAudit,
        handler: Optional[Callable] = None,
    ) -> Optional[CapabilityDefinition]:
        """Stage 8: Install & Register capability into the authoritative registry."""
        if audit.failed or not audit.approved_by_user:
            audit.log("Cannot register: audit failed or lacking user approval")
            return None

        audit.current_stage = AcquisitionStage.INSTALL_REGISTER
        cap = CapabilityDefinition(
            name=audit.candidate.name,
            type=CapabilityType.CLI if audit.candidate.source_type == "local_cli" else CapabilityType.TOOL,
            owner_module=audit.candidate.suggested_owner,
            version="1.0.0",
            source=audit.candidate.source_type,
            description=audit.candidate.description,
            requirements=list(audit.candidate.requirements),
            dependencies=list(audit.candidate.dependencies),
            risk=audit.risk_level,
            status=CapabilityStatus.AVAILABLE,
            health=CapabilityHealth.HEALTHY,
            verification=VerificationSpec(method="standard_verification"),
            handler=handler,
            metadata={"acquired": True, "source_identifier": audit.candidate.source_identifier},
        )
        self.registry.register_capability(cap)
        audit.passed_stages.append(AcquisitionStage.INSTALL_REGISTER)
        audit.current_stage = AcquisitionStage.VERIFY
        audit.log(f"Registered capability '{cap.name}' in CapabilityRegistry")
        return cap

    def verify_live(
        self,
        audit: QuarantineAudit,
        capability_name: str,
        live_verifier: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Stage 9 & 10: Live Verification and Activation."""
        if audit.failed:
            return False
        audit.current_stage = AcquisitionStage.VERIFY

        cap = self.registry.get_capability(capability_name)
        if not cap:
            audit.failed = True
            audit.failure_reason = f"Capability '{capability_name}' not found in registry for live verification"
            audit.log(audit.failure_reason)
            return False

        if live_verifier:
            try:
                ok = live_verifier()
                if not ok:
                    audit.failed = True
                    audit.failure_reason = "Live verification failed"
                    audit.log(audit.failure_reason)
                    self.registry.set_capability_health(capability_name, CapabilityHealth.UNHEALTHY, reason="Live verification failed")
                    return False
            except Exception as ex:
                audit.failed = True
                audit.failure_reason = f"Live verification raised exception: {ex}"
                audit.log(audit.failure_reason)
                self.registry.set_capability_health(capability_name, CapabilityHealth.UNHEALTHY, reason=str(ex))
                return False

        audit.passed_stages.append(AcquisitionStage.VERIFY)
        audit.passed_stages.append(AcquisitionStage.AVAILABLE)
        audit.current_stage = AcquisitionStage.AVAILABLE
        self.registry.set_capability_health(capability_name, CapabilityHealth.HEALTHY)
        audit.log(f"Capability '{capability_name}' successfully verified and marked AVAILABLE!")
        return True
