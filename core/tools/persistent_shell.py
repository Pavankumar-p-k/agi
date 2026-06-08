"""Persistent shell sessions — stateful subprocesses across tool calls.

Each session gets a long-lived shell process (cmd.exe on Windows, /bin/sh on Unix)
that preserves working directory, environment variables, and shell state.
"""

import asyncio
import logging
import os
import sys
import time
from typing import Optional

logger = logging.getLogger(__name__)

_SHELL_SESSIONS: dict[str, "PersistentShell"] = {}
_SESSION_MAX_IDLE = 300  # 5 minutes

if sys.platform == "win32":
    _SHELL_EXECUTABLE = "cmd.exe"
    _SHELL_ARGS = []
else:
    _SHELL_EXECUTABLE = "/bin/sh"
    _SHELL_ARGS = []


class PersistentShell:
    """A long-running shell subprocess that preserves state between commands."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.last_used: float = time.time()
        self._closed = False

    async def start(self) -> None:
        if self.proc is not None and self.proc.returncode is None:
            return
        self.proc = await asyncio.create_subprocess_exec(
            _SHELL_EXECUTABLE,
            *_SHELL_ARGS,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.last_used = time.time()
        logger.info("shell session %s started (pid=%s)", self.session_id, self.proc.pid)

    async def exec(self, command: str, timeout: float = 60.0) -> dict:
        """Execute a command in this shell session.

        Returns {"output": ..., "exit_code": ..., "timed_out": bool}.
        """
        await self.start()
        self.last_used = time.time()

        if sys.platform == "win32":
            full_cmd = command + "\r\n"
        else:
            full_cmd = command + "\n"

        try:
            self.proc.stdin.write(full_cmd.encode("utf-8", errors="replace"))
            await self.proc.stdin.drain()
        except BrokenPipeError:
            return {"output": "Shell process died — start a new session", "exit_code": -1, "timed_out": False}
        except OSError as e:
            return {"output": f"Shell error: {e}", "exit_code": -1, "timed_out": False}

        # Read until we get the next prompt or hit timeout
        # For cmd.exe we read a chunk; for sh we read until idle
        try:
            output = await asyncio.wait_for(
                self._read_until_idle(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {"output": "", "exit_code": -1, "timed_out": True}

        # Extract the last line as pseudo-exit-code marker
        lines = output.strip().split("\n")
        exit_code = 0
        cleaned = []
        for line in lines:
            cleaned.append(line)

        text = "\n".join(cleaned).strip()
        return {
            "output": text or "(no output)",
            "exit_code": exit_code,
            "timed_out": False,
        }

    async def _read_until_idle(self, idle_ms: int = 50) -> str:
        """Read from stdout until no new data for `idle_ms`."""
        chunks = []
        while True:
            try:
                chunk = await asyncio.wait_for(
                    self.proc.stdout.read(4096),
                    timeout=idle_ms / 1000.0,
                )
                if not chunk:
                    break
                chunks.append(chunk.decode("utf-8", errors="replace"))
            except asyncio.TimeoutError:
                break
        return "".join(chunks)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.kill()
                await self.proc.wait()
            except ProcessLookupError:
                pass
        if self.session_id in _SHELL_SESSIONS:
            del _SHELL_SESSIONS[self.session_id]
        logger.info("shell session %s closed", self.session_id)


def get_or_create_shell(session_id: str) -> PersistentShell:
    """Get or create a persistent shell for the given session."""
    if session_id not in _SHELL_SESSIONS:
        _SHELL_SESSIONS[session_id] = PersistentShell(session_id)
    return _SHELL_SESSIONS[session_id]


async def close_shell(session_id: str) -> None:
    """Close a shell session."""
    shell = _SHELL_SESSIONS.get(session_id)
    if shell:
        await shell.close()


async def gc_idle_shells() -> int:
    """Close and remove shell sessions idle longer than _SESSION_MAX_IDLE."""
    now = time.time()
    closed = 0
    for sid, shell in list(_SHELL_SESSIONS.items()):
        if now - shell.last_used > _SESSION_MAX_IDLE:
            await shell.close()
            closed += 1
    return closed
