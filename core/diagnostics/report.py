from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DiagnosticIssue:
    severity: str  # critical | high | medium | low
    category: str  # e.g. import, config, dependency, port
    path: str
    message: str


@dataclass
class DiagnosticReport:
    status: str  # ok | warning | critical
    issues: list[DiagnosticIssue] = field(default_factory=list)
    capability_gaps: list[str] = field(default_factory=list)


def build_diagnostic_report() -> DiagnosticReport:
    """Run a series of checks and return a diagnostic report."""
    issues: list[DiagnosticIssue] = []
    gaps: list[str] = []
    status = "ok"
    root = Path(__file__).resolve().parents[2]

    # ── Check 1: ROOT exists ───────────────────────────────────────────
    if not root.is_dir():
        issues.append(DiagnosticIssue(
            severity="critical", category="config", path=str(root),
            message=f"Project root does not exist: {root}",
        ))

    # ── Check 2: Can import core.main ───────────────────────────────────
    try:
        import core.main  # noqa: F401
    except Exception as e:
        issues.append(DiagnosticIssue(
            severity="critical", category="import", path="core/main.py",
            message=f"Cannot import core.main: {e}",
        ))
        status = "critical"

    # ── Check 3: Configuration files exist ──────────────────────────────
    env_path = root / ".env"
    if not env_path.exists():
        issues.append(DiagnosticIssue(
            severity="medium", category="config", path=str(env_path),
            message="No .env file — using defaults",
        ))

    # ── Check 4: Port 8000 availability ─────────────────────────────────
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        result = s.connect_ex(("127.0.0.1", 8000))
        s.close()
        if result == 0:
            issues.append(DiagnosticIssue(
                severity="low", category="port", path="127.0.0.1:8000",
                message="Port 8000 is already in use (another instance running?)",
            ))
    except Exception as e:
        issues.append(DiagnosticIssue(
            severity="low", category="port", path="127.0.0.1:8000",
            message=f"Port check failed: {e}",
        ))

    # ── Check 5: Server health endpoint ─────────────────────────────────
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8000/health", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status >= 500:
                issues.append(DiagnosticIssue(
                    severity="high", category="server", path="/health",
                    message=f"Server returned {resp.status}",
                ))
    except Exception as e:
        issues.append(DiagnosticIssue(
            severity="low", category="server", path="/health",
            message=f"Server not reachable (not running?): {e}",
        ))

    # ── Check 6: Log directory writable ─────────────────────────────────
    log_dir = root / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        test_file = log_dir / ".diag_test"
        test_file.write_text("ok")
        test_file.unlink()
    except Exception as e:
        issues.append(DiagnosticIssue(
            severity="high", category="config", path=str(log_dir),
            message=f"Log directory not writable: {e}",
        ))

    # ── Check 7: Missing dependencies ───────────────────────────────────
    critical_deps = ["fastapi", "uvicorn", "sqlalchemy", "pydantic", "alembic"]
    for dep in critical_deps:
        try:
            __import__(dep)
        except ImportError:
            issues.append(DiagnosticIssue(
                severity="critical", category="dependency", path=dep,
                message=f"Missing critical dependency: {dep}. Run: pip install {dep}",
            ))
            status = "critical"

    # ── Overall status ──────────────────────────────────────────────────
    high_or_critical = [i for i in issues if i.severity in ("critical", "high")]
    if high_or_critical:
        status = "critical"
    elif issues:
        status = "warning"

    return DiagnosticReport(status=status, issues=issues, capability_gaps=gaps)
