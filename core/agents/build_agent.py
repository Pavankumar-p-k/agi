"""BuildAgent — handles build/compile/package sub-goals."""
from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.agents.base import AgentResult, BaseAgent


@dataclass
class BuildSnapshot:
    project_dir: str = ""
    build_files: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_dir": self.project_dir,
            "build_files": list(self.build_files),
            "timestamp": self.timestamp,
        }


class BuildAgent(BaseAgent):
    """Detects build tooling and runs builds in the project directory."""

    agent_id = "build"
    keywords = ["build", "compile", "apk", "package", "bundle", "artifact"]
    priority = 10
    description = "Build, compile and package projects"

    _BUILD_FILES = ("pyproject.toml", "setup.py", "Makefile", "package.json",
                    "build.gradle", "CMakeLists.txt", "Cargo.toml")

    def analyze(self, project_dir: str = ".") -> BuildSnapshot:
        """Read-only scan of build tooling in a project directory."""
        from datetime import datetime
        p = Path(project_dir)
        files = [f.name for f in p.iterdir() if f.name in self._BUILD_FILES] if p.is_dir() else []
        return BuildSnapshot(
            project_dir=str(p.resolve()),
            build_files=sorted(files),
            timestamp=datetime.now().isoformat(),
        )

    async def _execute_impl(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> AgentResult:
        project_dir = "."
        variables = getattr(context, "variables", None) or {}
        if isinstance(variables, dict):
            project_dir = str(variables.get("project_dir", "."))
        return await self.build(project_dir)

    async def build(self, project_dir: str = ".") -> AgentResult:
        """Run the best-matching build command for the project."""
        snapshot = self.analyze(project_dir)
        if not snapshot.build_files:
            return AgentResult(
                success=False,
                output="",
                agent_id=self.agent_id,
                error=f"No build files found in {project_dir}",
            )

        commands = {
            "pyproject.toml": [sys.executable, "-m", "pip", "install", "-e", "."],
            "setup.py": [sys.executable, "setup.py", "build"],
            "package.json": ["npm", "run", "build"],
            "Makefile": ["make"],
            "build.gradle": ["gradle", "build"],
            "CMakeLists.txt": ["cmake", "--build", "."],
            "Cargo.toml": ["cargo", "build"],
        }
        cmd = commands.get(snapshot.build_files[0])
        if cmd is None:
            return AgentResult(success=False, output="", agent_id=self.agent_id,
                               error=f"No build command for {snapshot.build_files[0]}")

        try:
            proc = await asyncio.to_thread(
                subprocess.run, cmd, cwd=project_dir, capture_output=True,
                text=True, timeout=600,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            return AgentResult(
                success=proc.returncode == 0,
                output=output[-4000:],
                agent_id=self.agent_id,
                exit_code=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return AgentResult(success=False, output="", agent_id=self.agent_id,
                               error="build timed out after 600s")
        except FileNotFoundError as exc:
            return AgentResult(success=False, output="", agent_id=self.agent_id,
                               error=f"build tool not found: {exc}")
