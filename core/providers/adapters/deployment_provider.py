from __future__ import annotations

import logging
import time
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class DeploymentProvider(ExecutionProvider):
    provider_id = "deployment"
    name = "Application Deployment"
    version = "1.0.0"
    priority = 10
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=[
                "deployment",
                "deploy",
                "publish",
                "rollback",
                "health_check",
                "docker",
                "git",
            ],
            features=[
                "docker",
                "git",
                "vercel",
                "railway",
                "netlify",
            ],
        )

    async def health(self) -> ProviderHealth:
        import shutil

        has_docker = shutil.which("docker") is not None
        has_git = shutil.which("git") is not None
        has_vercel = shutil.which("vercel") is not None

        if has_docker or has_git:
            return ProviderHealth(
                status=ProviderHealthStatus.HEALTHY,
                latency_ms=0.0,
                last_checked=time.time(),
            )
        return ProviderHealth(
            status=ProviderHealthStatus.DEGRADED,
            error="No deployment tools (docker/git) found",
            last_checked=time.time(),
        )

    async def execute(
        self, task: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ExecutionResult:
        start = time.monotonic()
        action = task.get("action", task.get("capability", ""))
        project_dir = task.get("project_dir", task.get("directory", ""))
        target = task.get("target", task.get("platform", ""))

        try:
            if "docker" in action:
                return await self._run_docker(task, project_dir, start)
            if "git" in action:
                return await self._run_git(task, project_dir, start)
            if "vercel" in action or target == "vercel":
                return await self._run_vercel(task, project_dir, start)
            if "railway" in action or target == "railway":
                return await self._run_railway(task, project_dir, start)
            if "netlify" in action or target == "netlify":
                return await self._run_netlify(task, project_dir, start)
            # Default: try docker
            return await self._run_docker(task, project_dir, start)
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[DeploymentProvider] Execution failed: %s", e)
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                duration_ms=elapsed,
                metadata={"provider": "deployment"},
            )

    async def _run_docker(
        self, task: dict[str, Any], project_dir: str, start: float
    ) -> ExecutionResult:
        from core.sandbox.docker_sandbox import docker_sandbox

        command = task.get("command", "build")
        dockerfile = task.get("dockerfile", ".")
        tag = task.get("tag", "latest")

        if command == "build":
            cmd = f"docker build -t {tag} -f {dockerfile} {project_dir or '.'}"
        elif command == "push":
            registry = task.get("registry", "")
            cmd = f"docker push {registry}/{tag}" if registry else f"docker push {tag}"
        elif command == "run":
            cmd = f"docker run {tag} {task.get('entrypoint', '')}"
        elif command == "stop":
            container = task.get("container", "")
            cmd = f"docker stop {container}" if container else "docker ps -q | xargs docker stop"
        else:
            cmd = command

        result = await docker_sandbox.exec_bash(cmd)
        elapsed = (time.monotonic() - start) * 1000
        success = result.get("exit_code", 1) == 0
        return ExecutionResult(
            success=success,
            output=result.get("output", ""),
            error=result.get("error", ""),
            exit_code=result.get("exit_code", 1),
            duration_ms=elapsed,
            artifacts={},
            metadata={
                "provider": "deployment",
                "platform": "docker",
                "command": command,
            },
        )

    async def _run_git(
        self, task: dict[str, Any], project_dir: str, start: float
    ) -> ExecutionResult:
        import asyncio

        command = task.get("command", "status")
        remote = task.get("remote", "origin")
        branch = task.get("branch", "main")
        message = task.get("message", "")

        if command == "status":
            cmd = "git status"
        elif command == "push":
            cmd = f"git push {remote} {branch}"
        elif command == "pull":
            cmd = f"git pull {remote} {branch}"
        elif command == "commit":
            cmd = f'git commit -m "{message}"' if message else "git commit"
        elif command == "clone":
            repo = task.get("repository", "")
            cmd = f"git clone {repo} {project_dir or '.'}"
        else:
            cmd = command

        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=project_dir or None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        elapsed = (time.monotonic() - start) * 1000
        success = proc.returncode == 0
        return ExecutionResult(
            success=success,
            output=stdout.decode("utf-8", errors="replace"),
            error=stderr.decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
            duration_ms=elapsed,
            metadata={
                "provider": "deployment",
                "platform": "git",
                "command": command,
            },
        )

    async def _run_vercel(
        self, task: dict[str, Any], project_dir: str, start: float
    ) -> ExecutionResult:
        import asyncio

        command = task.get("command", "deploy")
        prod = task.get("production", True)

        if command == "deploy":
            cmd = f"vercel --prod" if prod else "vercel"
        elif command == "list":
            cmd = "vercel list"
        elif command == "logs":
            cmd = "vercel logs"
        else:
            cmd = command

        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=project_dir or None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        elapsed = (time.monotonic() - start) * 1000
        success = proc.returncode == 0
        return ExecutionResult(
            success=success,
            output=stdout.decode("utf-8", errors="replace"),
            error=stderr.decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
            duration_ms=elapsed,
            metadata={
                "provider": "deployment",
                "platform": "vercel",
                "command": command,
            },
        )

    async def _run_railway(
        self, task: dict[str, Any], project_dir: str, start: float
    ) -> ExecutionResult:
        import asyncio

        command = task.get("command", "up")
        environment = task.get("environment", "production")

        if command == "up":
            cmd = "railway up"
        elif command == "down":
            cmd = "railway down"
        elif command == "status":
            cmd = "railway status"
        elif command == "logs":
            cmd = f"railway logs -e {environment}"
        else:
            cmd = command

        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=project_dir or None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        elapsed = (time.monotonic() - start) * 1000
        success = proc.returncode == 0
        return ExecutionResult(
            success=success,
            output=stdout.decode("utf-8", errors="replace"),
            error=stderr.decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
            duration_ms=elapsed,
            metadata={
                "provider": "deployment",
                "platform": "railway",
                "command": command,
            },
        )

    async def _run_netlify(
        self, task: dict[str, Any], project_dir: str, start: float
    ) -> ExecutionResult:
        import asyncio

        command = task.get("command", "deploy")

        if command == "deploy":
            prod = task.get("production", False)
            site = task.get("site", "")
            cmd = f"netlify deploy {'--prod' if prod else ''} --dir={project_dir or '.'}"
            if site:
                cmd += f" --site={site}"
        elif command == "status":
            cmd = "netlify status"
        elif command == "open":
            cmd = "netlify open"
        else:
            cmd = command

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        elapsed = (time.monotonic() - start) * 1000
        success = proc.returncode == 0
        return ExecutionResult(
            success=success,
            output=stdout.decode("utf-8", errors="replace"),
            error=stderr.decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
            duration_ms=elapsed,
            metadata={
                "provider": "deployment",
                "platform": "netlify",
                "command": command,
            },
        )

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        action = task.get("action", task.get("capability", ""))
        if "docker" in action:
            return 0.02
        if "vercel" in action:
            return 0.01
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        action = task.get("action", task.get("capability", ""))
        if "docker" in action:
            return 30000.0
        if "deploy" in action:
            return 60000.0
        return 5000.0
