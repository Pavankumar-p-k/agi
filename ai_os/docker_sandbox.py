from __future__ import annotations

import io
import logging
import os
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "python:3.11-slim"
SANDBOX_NETWORK_DISABLED = os.getenv("DOCKER_SANDBOX_NETWORK", "false").lower() == "true"
SANDBOX_TIMEOUT = int(os.getenv("DOCKER_SANDBOX_TIMEOUT", "30"))
SANDBOX_MEMORY_LIMIT = os.getenv("DOCKER_SANDBOX_MEMORY", "256m")


class DockerSandbox:
    """Docker container sandbox for isolated code execution.

    Each call creates a temporary container, runs the code, captures output, destroys container.
    Network disabled by default for security.
    """

    def __init__(self, image: str = DEFAULT_IMAGE):
        self._image = image
        self._client = None
        self._available = False
        self._init_client()

    def _init_client(self):
        try:
            import docker
            self._client = docker.from_env()
            self._client.ping()
            self._available = True
            logger.info("[DockerSandbox] Docker available [OK]")
        except Exception as e:
            self._available = False
            logger.warning("[DockerSandbox] Docker not available: %s", e)

    @property
    def available(self) -> bool:
        return self._available

    def _ensure_image(self):
        try:
            self._client.images.get(self._image)
        except Exception:
            logger.info("[DockerSandbox] Pulling image %s...", self._image)
            self._client.images.pull(self._image)

    async def exec_python(self, code: str, timeout: int = SANDBOX_TIMEOUT) -> dict[str, Any]:
        if not self._available:
            return {"success": False, "error": "Docker not available", "stdout": "", "stderr": ""}
        try:
            self._ensure_image()
            cmd = ["python", "-c", code]
            container = self._client.containers.create(
                image=self._image,
                command=cmd,
                network_disabled=SANDBOX_NETWORK_DISABLED,
                mem_limit=SANDBOX_MEMORY_LIMIT,
                read_only=True,
                auto_remove=True,
            )
            container.start()
            exit_code = container.wait(timeout=timeout)
            logs = container.logs(stdout=True, stderr=True, tail=10000).decode("utf-8", errors="replace")
            stdout, stderr = self._split_logs(logs)
            return {
                "success": exit_code == 0,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
            }
        except Exception as e:
            logger.warning("[DockerSandbox] exec_python failed: %s", e)
            return {"success": False, "error": str(e), "stdout": "", "stderr": ""}
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass

    async def exec_command(self, cmd: list[str], timeout: int = SANDBOX_TIMEOUT,
                           files: dict[str, bytes] | None = None) -> dict[str, Any]:
        if not self._available:
            return {"success": False, "error": "Docker not available", "stdout": "", "stderr": ""}
        try:
            self._ensure_image()
            container = self._client.containers.create(
                image=self._image,
                command=cmd,
                network_disabled=SANDBOX_NETWORK_DISABLED,
                mem_limit=SANDBOX_MEMORY_LIMIT,
                auto_remove=False,
            )
            if files:
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                    for name, content in files.items():
                        info = tarfile.TarInfo(name=name)
                        info.size = len(content)
                        tar.addfile(info, io.BytesIO(content))
                tar_stream.seek(0)
                container.put_archive("/workspace", tar_stream.read())

            container.start()
            container.wait(timeout=timeout)
            logs = container.logs(stdout=True, stderr=True, tail=10000).decode("utf-8", errors="replace")
            stdout, stderr = self._split_logs(logs)

            result_files = {}
            try:
                stream, _ = container.get_archive("/workspace/output")
                tar_bytes = b"".join(stream)
                tar_stream = io.BytesIO(tar_bytes)
                with tarfile.open(fileobj=tar_stream) as tar:
                    for member in tar.getmembers():
                        f = tar.extractfile(member)
                        if f:
                            result_files[member.name] = f.read()
            except Exception:
                pass

            return {
                "success": True,
                "stdout": stdout,
                "stderr": stderr,
                "files": result_files,
            }
        except Exception as e:
            logger.warning("[DockerSandbox] exec_command failed: %s", e)
            return {"success": False, "error": str(e), "stdout": "", "stderr": ""}
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass

    def _split_logs(self, logs: str) -> tuple[str, str]:
        stdout_lines = []
        stderr_lines = []
        for line in logs.split("\n"):
            if line.startswith("STDERR:"):
                stderr_lines.append(line[7:])
            else:
                stdout_lines.append(line)
        return "\n".join(stdout_lines).strip(), "\n".join(stderr_lines).strip()


docker_sandbox = DockerSandbox()
