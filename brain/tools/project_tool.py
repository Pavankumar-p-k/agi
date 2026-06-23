from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from brain.executor.executor import ActionResult, executor

logger = logging.getLogger(__name__)


class ProjectTool:
    """High-level project operations: scaffold, build, test, compile.

    These are the "real" actions an autonomous AI needs to complete
    software projects without human supervision.
    """

    def __init__(self):
        self._running_processes: dict[str, subprocess.Popen] = {}
        self.root_dir: str = "."

    def _resolve(self, path: str) -> str:
        """Resolve a path relative to root_dir."""
        if os.path.isabs(path):
            return path
        return os.path.join(self.root_dir, path)

    async def create_directory(self, path: str = ".", **kwargs) -> ActionResult:
        """Create directory structure. Returns ActionResult."""
        try:
            full = self._resolve(path)
            os.makedirs(full, exist_ok=True)
            return ActionResult(
                success=True,
                output=f"Created directory: {full}",
                evidence=f"Directory exists: {os.path.isdir(full)}",
                confidence=1.0,
            )
        except OSError as e:
            return ActionResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    async def write_file(self, path: str = "", content: str = "", **kwargs) -> ActionResult:
        """Write content to a file, creating parent directories as needed."""
        try:
            if not path:
                return ActionResult(
                    success=False,
                    error="No path specified",
                    confidence=0.0,
                )
            full = self._resolve(path)
            os.makedirs(os.path.dirname(os.path.abspath(full)), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            return ActionResult(
                success=True,
                output=f"Wrote {len(content)} bytes to {full}",
                evidence=f"File exists: {os.path.exists(full)}",
                confidence=1.0,
            )
        except OSError as e:
            return ActionResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    async def read_file(self, path: str = "", max_bytes: int = 1_000_000, **kwargs) -> ActionResult:
        """Read file content."""
        try:
            full = self._resolve(path)
            if not os.path.exists(full):
                return ActionResult(
                    success=False,
                    error=f"File not found: {full}",
                    confidence=0.0,
                )
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_bytes)
            return ActionResult(
                success=True,
                output=content,
                evidence=f"Read {len(content)} bytes from {full}",
                confidence=1.0,
            )
        except OSError as e:
            return ActionResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    async def edit_file(self, path: str = "", old_string: str = "",
                        new_string: str = "", **kwargs) -> ActionResult:
        """Find and replace text in a file."""
        try:
            full = self._resolve(path)
            if not os.path.exists(full):
                return ActionResult(
                    success=False,
                    error=f"File not found: {full}",
                    confidence=0.0,
                )
            with open(full, "r", encoding="utf-8") as f:
                content = f.read()

            if old_string not in content:
                return ActionResult(
                    success=False,
                    error=f"old_string not found in {path}",
                    confidence=0.0,
                )

            new_content = content.replace(old_string, new_string, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ActionResult(
                success=True,
                output=f"Replaced in {path}",
                evidence=f"Replaced {len(old_string)} chars with {len(new_string)} chars",
                confidence=1.0,
            )
        except OSError as e:
            return ActionResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    async def delete_file(self, path: str = "", **kwargs) -> ActionResult:
        try:
            full = self._resolve(path)
            if not os.path.exists(full):
                return ActionResult(success=False, error=f"Not found: {full}")
            os.remove(full)
            return ActionResult(
                success=True,
                output=f"Deleted: {full}",
                confidence=1.0,
            )
        except OSError as e:
            return ActionResult(success=False, error=str(e))

    async def list_directory(self, path: str = ".", **kwargs) -> ActionResult:
        try:
            full = self._resolve(path)
            entries = os.listdir(full)
            return ActionResult(
                success=True,
                output="\n".join(sorted(entries)),
                evidence=f"{len(entries)} entries in {full}",
                confidence=1.0,
            )
        except OSError as e:
            return ActionResult(success=False, error=str(e))

    async def run_command(self, command: str = "", cwd: str | None = None,
                          timeout: float = 120.0,
                          env: dict | None = None, **kwargs) -> ActionResult:
        """Run a shell command safely. Returns stdout + stderr."""
        start = time.time()
        try:
            if not command:
                return ActionResult(
                    success=False,
                    error="No command specified",
                    confidence=0.0,
                )
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._resolve(cwd) if cwd else self.root_dir,
                env={**os.environ, **(env or {})},
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                elapsed = (time.time() - start) * 1000
                return ActionResult(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                    output=f"Partial output: {(await proc.stdout.read()).decode(errors='replace')[:1000]}" if proc.stdout else "",
                    duration_ms=elapsed,
                )

            elapsed = (time.time() - start) * 1000
            out = stdout.decode(errors="replace").strip()
            err = stderr.decode(errors="replace").strip()
            success = proc.returncode == 0

            return ActionResult(
                success=success,
                output=out or err,
                evidence=out[:500] if out else err[:500],
                error=err if not success else "",
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=elapsed,
            )

    async def compile_java(self, project_dir: str = "", source_path: str = "",
                           **kwargs) -> ActionResult:
        """Compile a Java file."""
        return await self.run_command(
            f"javac \"{source_path}\"",
            cwd=self._resolve(project_dir),
            timeout=60.0,
        )

    async def run_tests(self, project_dir: str = "", test_command: str = "",
                        **kwargs) -> ActionResult:
        """Run tests in a project directory."""
        resolved = self._resolve(project_dir)
        cmd = test_command or self._detect_test_command(resolved)
        if not cmd:
            return ActionResult(
                success=False,
                error="No test framework detected",
                confidence=0.0,
            )
        return await self.run_command(cmd, cwd=resolved, timeout=300.0)

    async def build_project(self, project_dir: str = "", build_command: str = "",
                            **kwargs) -> ActionResult:
        """Build a project."""
        resolved = self._resolve(project_dir)
        cmd = build_command or self._detect_build_command(resolved)
        if not cmd:
            return ActionResult(
                success=False,
                error="No build system detected",
                confidence=0.0,
            )
        return await self.run_command(cmd, cwd=resolved, timeout=300.0)

    def _detect_test_command(self, project_dir: str) -> str | None:
        """Auto-detect the test framework from project files."""
        if os.path.exists(os.path.join(project_dir, "pom.xml")):
            return "mvn test"
        if os.path.exists(os.path.join(project_dir, "build.gradle")):
            if os.path.exists(os.path.join(project_dir, "gradlew.bat")):
                return "gradlew.bat test"
            if os.path.exists(os.path.join(project_dir, "gradlew")):
                return "./gradlew test"
            return "gradle test"
        if os.path.exists(os.path.join(project_dir, "Cargo.toml")):
            return "cargo test"
        if os.path.exists(os.path.join(project_dir, "package.json")):
            return "npm test"
        if os.path.exists(os.path.join(project_dir, "Makefile")):
            return "make test"
        return None

    def _detect_build_command(self, project_dir: str) -> str | None:
        if os.path.exists(os.path.join(project_dir, "pom.xml")):
            return "mvn compile"
        if os.path.exists(os.path.join(project_dir, "build.gradle")):
            if os.path.exists(os.path.join(project_dir, "gradlew.bat")):
                return "gradlew.bat assembleDebug"
            if os.path.exists(os.path.join(project_dir, "gradlew")):
                return "./gradlew assembleDebug"
            return "gradle build"
        if os.path.exists(os.path.join(project_dir, "Cargo.toml")):
            return "cargo build"
        if os.path.exists(os.path.join(project_dir, "package.json")):
            return "npm run build"
        if os.path.exists(os.path.join(project_dir, "Makefile")):
            return "make"
        return None

    def _detect_project_type(self, project_dir: str) -> str:
        if os.path.exists(os.path.join(project_dir, "pom.xml")):
            return "maven"
        if os.path.exists(os.path.join(project_dir, "build.gradle")):
            return "gradle"
        if os.path.exists(os.path.join(project_dir, "Cargo.toml")):
            return "rust"
        if os.path.exists(os.path.join(project_dir, "package.json")):
            return "node"
        if os.path.exists(os.path.join(project_dir, "Makefile")):
            return "make"
        if os.path.exists(os.path.join(project_dir, "setup.py")) or \
           os.path.exists(os.path.join(project_dir, "pyproject.toml")):
            return "python"
        return "unknown"


project_tool = ProjectTool()
