"""Independent verification for Coding AI work."""
from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    command: str
    status: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""

    @property
    def success(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    status: str
    checks: list[CheckResult] = field(default_factory=list)
    git_diff: str = ""
    files_changed: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
            "git_diff": self.git_diff,
            "files_changed": self.files_changed,
            "evidence": self.evidence,
        }


class CodingVerifier:
    """Runs checks and inspects Git state without claiming success from code generation alone."""

    def __init__(self, repository: str | Path):
        self.repository = Path(repository).resolve()

    def _run(self, command: str, timeout: int = 120) -> CheckResult:
        try:
            completed = subprocess.run(
                command,
                cwd=self.repository,
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
            status = "success" if completed.returncode == 0 else "failed"
            return CheckResult(command, status, completed.returncode, completed.stdout[-4000:], completed.stderr[-4000:])
        except subprocess.TimeoutExpired as exc:
            return CheckResult(command, "failed", None, exc.stdout or "", f"timeout after {timeout}s")
        except Exception as exc:
            return CheckResult(command, "failed", None, "", str(exc))

    def git_changed_files(self) -> list[str]:
        result = self._run("git status --porcelain", timeout=30)
        if not result.success:
            return []
        files = []
        for line in result.stdout.splitlines():
            if len(line) > 3:
                files.append(line[3:].strip())
        return files

    def git_diff(self) -> str:
        result = self._run("git diff --stat", timeout=30)
        return result.stdout.strip() if result.success else ""

    def verify(self, commands: list[str] | None = None) -> VerificationResult:
        checks = [self._run(command) for command in (commands or [])]
        changed = self.git_changed_files()
        diff = self.git_diff()
        if checks and all(check.success for check in checks):
            status = "success"
        elif checks:
            status = "failed"
        else:
            status = "unknown"
        return VerificationResult(
            status=status,
            checks=checks,
            git_diff=diff,
            files_changed=changed,
            evidence={"checks_run": len(checks), "git_diff_inspected": bool(diff or changed)},
        )
