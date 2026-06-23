"""Persistent shell sessions — stateful subprocesses across tool calls.

Each session gets a long-lived shell process (cmd.exe on Windows, /bin/sh on Unix)
that preserves working directory, environment variables, and shell state.
"""

import asyncio
import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

_SHELL_SESSIONS: dict[str, "PersistentShell"] = {}
_SESSION_MAX_IDLE = 300  # 5 minutes

if sys.platform == "win32":
    _SHELL_EXECUTABLE = "cmd.exe"
    _SHELL_ARGS = []
    _EXIT_CODE_CMD = "echo ExitCodeIs:%errorlevel%"
    _NEWLINE = "\r\n"
else:
    _SHELL_EXECUTABLE = "/bin/sh"
    _SHELL_ARGS = []
    _EXIT_CODE_CMD = "echo ExitCodeIs:$?"
    _NEWLINE = "\n"


class PersistentShell:
    """A long-running shell subprocess that preserves state between commands."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.proc: asyncio.subprocess.Process | None = None
        self.last_used: float = time.time()
        self._closed = False
        self._cwd: str = os.getcwd()

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

    async def exec(self, command: str, timeout: float = 60.0, cwd: str | None = None) -> dict:
        """Execute a command in this shell session.

        Returns {"output": ..., "exit_code": ..., "stderr": ..., "duration_ms": ..., "cwd": ..., "timed_out": bool}.
        """
        await self.start()
        self.last_used = time.time()

        start = time.monotonic()
        full_cmd = command + _NEWLINE + _EXIT_CODE_CMD + _NEWLINE

        try:
            self.proc.stdin.write(full_cmd.encode("utf-8", errors="replace"))
            await self.proc.stdin.drain()
        except BrokenPipeError:
            return {"output": "Shell process died — start a new session", "exit_code": -1, "stderr": "", "duration_ms": 0, "cwd": self._cwd, "timed_out": False}
        except OSError as e:
            return {"output": f"Shell error: {e}", "exit_code": -1, "stderr": "", "duration_ms": 0, "cwd": self._cwd, "timed_out": False}

        try:
            output = await asyncio.wait_for(
                self._read_until_idle(),
                timeout=timeout,
            )
        except TimeoutError:
            duration_ms = round((time.monotonic() - start) * 1000)
            return {"output": "", "exit_code": -1, "stderr": "", "duration_ms": duration_ms, "cwd": self._cwd, "timed_out": True}

        duration_ms = round((time.monotonic() - start) * 1000)

        # Parse exit code from the output
        exit_code = 0
        lines = output.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.rstrip("\r")
            if "ExitCodeIs:" in stripped:
                try:
                    exit_code = int(stripped.split("ExitCodeIs:", 1)[1].strip())
                except (ValueError, IndexError):
                    exit_code = 0
            elif stripped.startswith(command.rstrip()):
                continue
            elif stripped.strip():
                cleaned_lines.append(stripped)

        text = "\n".join(cleaned_lines).strip() if cleaned_lines else "(no output)"

        # Track cwd changes from cd commands
        if command.strip().startswith("cd "):
            new_dir = command.strip()[3:].strip()
            if new_dir:
                self._cwd = os.path.abspath(os.path.join(self._cwd, new_dir))

        return {
            "output": text,
            "exit_code": exit_code,
            "stderr": "",
            "duration_ms": duration_ms,
            "cwd": self._cwd,
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
            except TimeoutError:
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
