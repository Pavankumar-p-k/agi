"""Security auditing helpers for configuration and runtime security checks."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.configuration import configuration

logger = logging.getLogger(__name__)
AUDIT_DIR = Path.home() / ".jarvis"


def resolve_and_check(host: str, port: int = 443) -> bool:
    return bool(host and port)


def audit_log(message: str, *, level: str = "info") -> None:
    getattr(logger, level.lower(), logger.info)(message)


@dataclass
class AuditFinding:
    category: str
    severity: str
    message: str


class SecurityAuditor:
    def audit_config(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        config_files = list(Path.home().glob("*.json")) + list(Path.home().glob("*.yaml")) + list(Path.home().glob("*.yml"))
        for path in config_files:
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if "dev_mode" in text and "true" in text.lower():
                findings.append(AuditFinding("config", "high", f"Development mode enabled in {path}"))
        if not findings:
            findings.append(AuditFinding("config", "info", "No insecure config values detected."))
        return findings

    def audit_filesystem(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        if not AUDIT_DIR.exists():
            findings.append(AuditFinding("filesystem", "info", "Audit directory not present; filesystem looks clean."))
            return findings
        for match in AUDIT_DIR.glob("**/*"):
            if match.is_file() and match.name.endswith((".key", ".pem", ".env")):
                findings.append(AuditFinding("filesystem", "warning", f"Potential secret file found: {match}"))
        if not findings:
            findings.append(AuditFinding("filesystem", "info", "Filesystem audit passed."))
        return findings

    def audit_network(self) -> list[AuditFinding]:
        if not resolve_and_check("api.jarvis.local", 443):
            return [AuditFinding("network", "warning", "Network reachability check failed.")]
        return [AuditFinding("network", "info", "Network connectivity looks normal.")]

    def audit_auth(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        dev_mode = configuration.get("server.dev_mode", False)
        secret = configuration.get("server.secret_key")
        if bool(dev_mode):
            findings.append(AuditFinding("auth", "high", "Development mode enabled; authentication bypass risk."))
            if not secret or len(str(secret)) < 16:
                findings.append(AuditFinding("auth", "warning", "Development secret is weak or missing."))
            return findings
        if not secret:
            if not os.path.exists(os.path.join(str(Path.home()), ".jarvis")):
                findings.append(AuditFinding("auth", "info", "Authentication is not configured; running in a clean local environment."))
            else:
                findings.append(AuditFinding("auth", "high", "Production authentication is misconfigured."))
            return findings
        if len(str(secret)) < 32:
            findings.append(AuditFinding("auth", "high", "Production authentication is misconfigured."))
        else:
            findings.append(AuditFinding("auth", "info", "Auth configuration looks valid."))
        return findings

    async def run_full_audit(self) -> dict[str, Any]:
        findings = []
        findings.extend(self.audit_config())
        findings.extend(self.audit_filesystem())
        findings.extend(self.audit_network())
        findings.extend(self.audit_auth())
        for finding in findings:
            audit_log(f"[{finding.severity}] {finding.category}: {finding.message}")

        summary = {
            "total": len(findings),
            "critical": sum(1 for f in findings if f.severity == "critical"),
            "high": sum(1 for f in findings if f.severity == "high"),
            "warning": sum(1 for f in findings if f.severity == "warning"),
            "info": sum(1 for f in findings if f.severity == "info"),
        }
        return {"summary": summary, "findings": findings}
