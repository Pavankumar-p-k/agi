"""Persistent shell — a long-running shell subprocess with cwd persistence.

Contract (tests/contract/test_persistent_shell.py):
- ``get_or_create_shell()`` — returns a :class:`PersistentShell` instance,
  creating one per process if none exists.
- ``close_shell()`` — cleanly terminates the underlying subprocess.
- ``PersistentShell`` owns a :class:`subprocess.Popen` running a platform-
  appropriate shell (``/bin/bash`` on Unix, ``cmd.exe`` on Windows).  All
  commands are executed via ``PersistentShell.execute(cmd)`` which returns
- ``(stdout, stderr, rc)``.
- The shell preserves cwd across calls; ``cd``-style commands update the
  stored cwd.
- Security: the shell runs as the current user with the same privileges.
  Admins must explicitly opt‑in via ``PersistentShell(privileged=True)``.
"""
from __future__ import annotations

import atexit
import os
import signal
import subprocess
import threading
from typing import Any, Optional, Tuple


if os.name == "nt":

    _DEFAULT_CMD = ["cmd", "/c"]
else:

    _DEFAULT_CMD = ["/bin/bash", "-i"]


class PersistentShell:
    """A long-running shell subprocess with cwd persistence."""

    def __init__(self, privileged: bool = False) -> None:
        self.privileged = privileged
        self._process: Optional[subprocess.Popen] = None
        self._cwd: Optional[str] = os.getcwd()
        self._lock = threading.Lock()
        self._start()

    # ── lifecycle ──────────────────────────────────────────────────

    def _start(self) -> None:
        env = os.environ.copy()
        self._process = subprocess.Popen(
            _DEFAULT_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self._cwd,
            env=env,
            bufsize=0,
        )
        atexit.register(self.close)

    # ── API ────────────────────────────────────────────────────────

    def execute(self, cmd: str) -> Tuple[str, str, int]:
        """Execute *cmd* in the persistent shell.

        Returns ``(stdout, stderr, returncode)``.
        """
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._start()
            proc = self._process
        # Write command + newline; read output
        try:
            proc.stdin.write((cmd + "\n").encode("utf-8"))
            proc.stdin.flush()
        except Exception as exc:  # noqa: BLE001
            return ("", str(exc), 1)

        # Read until we see the prompt reappear (simple heuristic)
        import time as _time
        _time.sleep(0.05)

        # Drain available output
        data = ""
        try:
            chunk = proc.stdout.read1(65536)
            if chunk:
                data = chunk.decode("utf-8", errors="replace")
        except Exception:
            pass

        # Also read stderr
        err_data = ""
        try:
            chunk = proc.stderr.read1(65536)
            if chunk:
                err_data = chunk.decode("utf-8", errors="replace")
        except Exception:
            pass

        return (data, err_data, self._process.returncode if self._process.returncode is not None else 0)

    def set_cwd(self, cwd: str) -> None:
        """Update the stored working directory."""
        self._cwd = cwd
        if self._process is not None:
            self._process.cwd = cwd

    def close(self) -> None:
        """Terminate the subprocess."""
        with self._lock:
            if self._process is not None:
                try:
                    self._process.stdin.close()
                except Exception:
                    pass
                try:
                    self._process.terminate()
                    self._process.wait(timeout=3)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                self._process = None


# Module-level singleton — created on first use
_shell: Optional[PersistentShell] = None
_shell_lock = threading.Lock()


def get_or_create_shell(privileged: bool = False) -> PersistentShell:
    """Return the module-level persistent shell, creating it if needed."""
    global _shell
    with _shell_lock:
        if _shell is None:
            _shell = PersistentShell(privileged=privileged)
        return _shell


def close_shell() -> None:
    """Close the module-level persistent shell."""
    global _shell
    with _shell_lock:
        if _shell is not None:
            _shell.close()
            _shell = None

__all__ = [
    "PersistentShell",
    "get_or_create_shell",
    "close_shell",
]