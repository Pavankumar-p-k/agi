"""TestAgent — handles test-running sub-goals."""
from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.agents.base import AgentResult, BaseAgent


@dataclass
class TestSnapshot:
    project_dir: str = ""
    test_files: int = 0
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"project_dir": self.project_dir, "test_files": self.test_files,
                "timestamp": self.timestamp}


class TestAgent(BaseAgent):
    """Runs project tests (pytest preferred, unittest fallback)."""

    agent_id = "test"
    keywords = ["test", "unittest", "pytest", "run tests", "coverage"]
    priority = 10
    description = "Run project test suites"

    def analyze(self, project_dir: str = ".") -> TestSnapshot:
        p = Path(project_dir)
        count = 0
        if p.is_dir():
            count = sum(1 for f in p.rglob("test_*.py"))
            count += sum(1 for f in p.rglob("*_test.py"))
        return TestSnapshot(project_dir=str(p.resolve()), test_files=count,
                            timestamp=datetime.now().isoformat())

    async def _execute_impl(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> AgentResult:
        project_dir = "."
        variables = getattr(context, "variables", None) or {}
        if isinstance(variables, dict):
            project_dir = str(variables.get("project_dir", "."))
        return await self.run_tests(project_dir)

    async def run_tests(self, project_dir: str = ".", pytest_args: Optional[list[str]] = None) -> AgentResult:
        cmd = [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider"]
        if pytest_args:
            cmd += pytest_args
        try:
            proc = await asyncio.to_thread(
                subprocess.run, cmd, cwd=project_dir, capture_output=True,
                text=True, timeout=900,
            )
            output = ((proc.stdout or "") + (proc.stderr or ""))[-4000:]
            return AgentResult(success=proc.returncode == 0, output=output,
                               agent_id=self.agent_id, exit_code=proc.returncode)
        except subprocess.TimeoutExpired:
            return AgentResult(success=False, output="", agent_id=self.agent_id,
                               error="test run timed out after 900s")
        except FileNotFoundError as exc:
            return AgentResult(success=False, output="", agent_id=self.agent_id,
                               error=f"pytest not found: {exc}")
