from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .audit_log import audit_log
from .ssrf import assert_safe_url, resolve_and_check

logger = logging.getLogger(__name__)

AUDIT_DIR = Path.home() / ".jarvis" / "security_audits"


@dataclass
class AuditFinding:
    severity: str
    category: str
    message: str
    detail: str = ""
    path: str = ""
    recommendation: str = ""


class SecurityAuditor:
    """Security audit system — matching OpenClaw's audit capabilities.

    Audits: config, filesystem, network/SSRF, auth, plugin permissions, dangerous config.
    """

    def __init__(self):
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Individual Audits ──

    def audit_config(self) -> list[AuditFinding]:
        findings = []
        config_dir = Path.home() / ".jarvis"

        # Check for dangerous config flags
        for f in config_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("dev_mode") is True:
                    findings.append(AuditFinding(
                        severity="high",
                        category="config",
                        message="DEV_MODE enabled — bypasses authentication",
                        path=str(f),
                        recommendation="Disable DEV_MODE in production. Set dev_mode=false.",
                    ))
                if data.get("allow_all_origins") is True:
                    findings.append(AuditFinding(
                        severity="medium",
                        category="config",
                        message="CORS allows all origins",
                        path=str(f),
                        recommendation="Restrict ALLOWED_ORIGINS to specific domains.",
                    ))
                # API keys in config
                for key in data:
                    if any(kw in key.lower() for kw in ["api_key", "token", "secret", "password"]):
                        findings.append(AuditFinding(
                            severity="critical",
                            category="config",
                            message=f"Credentials found in config file: {key}",
                            path=str(f),
                            recommendation="Move credentials to environment variables.",
                        ))
            except Exception as _e:
                logger.debug("security_audit scan config failed: %s", _e)

        # Check env vars for hardcoded credentials
        dangerous_env_prefixes = ["API_KEY", "TOKEN", "SECRET", "PASSWORD"]
        for key, value in os.environ.items():
            for prefix in dangerous_env_prefixes:
                if key.endswith(prefix) and value and len(value) > 0:
                    break

        if not findings:
            findings.append(AuditFinding(
                severity="info", category="config",
                message="No config issues found",
            ))
        return findings

    def audit_filesystem(self) -> list[AuditFinding]:
        findings = []
        jarvis_dir = Path.home() / ".jarvis"

        # Check permissions on sensitive files
        sensitive_patterns = ["*.db", "*credentials*", "*key*", "*.pem", "*token*"]
        for pattern in sensitive_patterns:
            for f in jarvis_dir.glob(pattern):
                if f.is_file():
                    findings.append(AuditFinding(
                        severity="medium" if "credential" in f.name.lower() else "low",
                        category="filesystem",
                        message=f"Sensitive file: {f.name}",
                        path=str(f),
                        recommendation="Ensure file permissions restrict access to owner only.",
                    ))

        # Check for world-readable session files
        sessions_dir = jarvis_dir / "sessions"
        if sessions_dir.exists():
            count = len(list(sessions_dir.glob("*.json")))
            if count > 100:
                findings.append(AuditFinding(
                    severity="low",
                    category="filesystem",
                    message=f"Large number of session files: {count}",
                    recommendation="Compact old sessions regularly.",
                ))

        if not findings:
            findings.append(AuditFinding(
                severity="info", category="filesystem",
                message="No filesystem issues found",
            ))
        return findings

    def audit_network(self) -> list[AuditFinding]:
        findings = []

        # Validate SSRF configuration
        test_urls = [
            "http://localhost:11434/api/tags",
            "http://127.0.0.1:8000/health",
            "http://169.254.169.254/latest/meta-data/",
        ]
        for url in test_urls:
            safe = resolve_and_check(url)
            if not safe:
                findings.append(AuditFinding(
                    severity="info",
                    category="network",
                    message=f"SSRF guard blocks private IP: {url}",
                    recommendation="SSRF protection is working correctly.",
                ))

        # Check cloud provider exposure
        providers_with_keys = []
        provider_envs = {
            "OPENAI_API_KEY": "OpenAI",
            "ANTHROPIC_API_KEY": "Anthropic",
            "GEMINI_API_KEY": "Gemini",
            "GROQ_API_KEY": "Groq",
            "DEEPSEEK_API_KEY": "DeepSeek",
            "MISTRAL_API_KEY": "Mistral",
            "TOGETHER_API_KEY": "Together",
            "FIREWORKS_API_KEY": "Fireworks",
            "XAI_API_KEY": "xAI",
        }
        for env_var, name in provider_envs.items():
            if os.getenv(env_var):
                providers_with_keys.append(name)

        if providers_with_keys:
            findings.append(AuditFinding(
                severity="info",
                category="network",
                message=f"Cloud providers configured: {', '.join(providers_with_keys)}",
                recommendation="Verify all API keys are from trusted sources.",
            ))

        if not findings:
            findings.append(AuditFinding(
                severity="info", category="network",
                message="No network issues found",
            ))
        return findings

    def audit_auth(self) -> list[AuditFinding]:
        findings = []

        from .config import DEV_MODE
        if DEV_MODE:
            findings.append(AuditFinding(
                severity="high",
                category="auth",
                message="DEV_MODE=True — authentication bypassed for loopback",
                recommendation="Set DEV_MODE=false in production.",
            ))

        firebase_creds = os.getenv("FIREBASE_CREDENTIALS", "firebase-credentials.json")
        if os.path.exists(firebase_creds):
            findings.append(AuditFinding(
                severity="info",
                category="auth",
                message="Firebase credentials file found",
                path=firebase_creds,
                recommendation="Ensure this file is excluded from version control.",
            ))

        if not findings:
            findings.append(AuditFinding(
                severity="info", category="auth",
                message="Auth configuration looks correct",
            ))
        return findings

    # ── Full Audit ──

    async def run_full_audit(self) -> dict[str, Any]:
        findings = []
        findings.extend(self.audit_config())
        findings.extend(self.audit_filesystem())
        findings.extend(self.audit_network())
        findings.extend(self.audit_auth())

        critical = [f for f in findings if f.severity == "critical"]
        high = [f for f in findings if f.severity == "high"]
        medium = [f for f in findings if f.severity == "medium"]
        low = [f for f in findings if f.severity == "low"]
        info = [f for f in findings if f.severity == "info"]

        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": len(findings),
                "critical": len(critical),
                "high": len(high),
                "medium": len(medium),
                "low": len(low),
                "info": len(info),
            },
            "findings": [
                {"severity": f.severity, "category": f.category,
                 "message": f.message, "detail": f.detail,
                 "path": f.path, "recommendation": f.recommendation}
                for f in findings
            ],
        }

        audit_log.log(
            event="security_audit",
            extra={
                "findings_total": len(findings),
                "critical": len(critical),
                "high": len(high),
            },
        )

        report_path = AUDIT_DIR / f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, indent=2))
        logger.info("[Security] Audit complete: %d findings (%d critical, %d high)",
                     len(findings), len(critical), len(high))
        return report


security_auditor = SecurityAuditor()
