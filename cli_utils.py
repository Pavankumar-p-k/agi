from __future__ import annotations

import itertools
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from prompt_toolkit.styles import Style

ROOT = Path(__file__).resolve().parent


def style_theme(dark=True):
    return Style.from_dict({
        "prompt": "fg:#00ff00 bold" if dark else "fg:#005500 bold",
        "jarvis": "fg:#00afff bold" if dark else "fg:#0055ff bold",
        "user": "fg:#ffffff" if dark else "fg:#000000",
        "info": "fg:#888888 italic",
        "error": "fg:#ff0000 bold",
        "success": "fg:#00ff00" if dark else "fg:#005500",
        "warning": "fg:#ffaa00",
        "timestamp": "fg:#666666",
        "header": "fg:#00afff bold",
    })


def syntax_highlight(text, filename=None):
    try:
        from pygments import highlight
        from pygments.lexers import guess_lexer_for_filename, PythonLexer
        from pygments.formatters import TerminalFormatter
        lexer = guess_lexer_for_filename(filename or "_.py", text) if filename else PythonLexer()
        return highlight(text, lexer, TerminalFormatter())
    except Exception:
        return text


def colorize(text, color):
    colors = {
        "green": "\033[92m", "cyan": "\033[96m", "red": "\033[91m",
        "yellow": "\033[93m", "blue": "\033[94m", "magenta": "\033[95m",
        "bold": "\033[1m", "dim": "\033[2m", "reset": "\033[0m",
    }
    c = colors.get(color, colors["reset"])
    return f"{c}{text}{colors['reset']}"


IDE_PRESETS = {
    "codex": "CLI-first workflow similar to Codex. Use JARVIS through terminal and HTTP APIs.",
    "vscode": "VS Code and forks can call JARVIS through local tasks, terminal profiles, and HTTP tools.",
    "cursor": "Cursor can reuse the same local CLI and HTTP endpoints as VS Code.",
    "windsurf": "Windsurf can connect through terminal tasks and local JARVIS APIs.",
    "zed": "Zed can use shell commands and OpenAPI/HTTP integrations against the JARVIS server.",
    "jetbrains": "JetBrains IDEs can use external tools and HTTP clients against the JARVIS server.",
}


def python_exe() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv311" / "Scripts" / "python.exe",
        ROOT / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def common_env() -> dict:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    env.setdefault("JARVIS_SERVER", "http://127.0.0.1:8000")
    env.setdefault("OLLAMA_URL", "http://127.0.0.1:11434")
    env.setdefault("JARVIS_AUTO_MODELS", "single")
    return env


def run_command(cmd: list[str], cwd: Path | None = None, env: dict | None = None, dry_run: bool = False) -> int:
    cmd = prepare_command(cmd)
    if dry_run:
        print("DRY RUN:", " ".join(cmd))
        if cwd:
            print("CWD:", cwd)
        return 0
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env).returncode


def spawn_background(
    title: str,
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    dry_run: bool = False,
) -> int:
    cmd = prepare_command(cmd)
    if dry_run:
        print(f"DRY RUN [{title}]:", " ".join(cmd))
        if cwd:
            print("CWD:", cwd)
        return 0
    popen_kwargs = {
        "cwd": str(cwd) if cwd else None,
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(cmd, **popen_kwargs)
    return 0


def prepare_command(cmd: list[str]) -> list[str]:
    if not cmd:
        raise ValueError("Command cannot be empty")
    if os.name != "nt":
        return cmd
    executable = shutil.which(cmd[0]) or cmd[0]
    if Path(executable).suffix.lower() in {".bat", ".cmd"}:
        return ["cmd.exe", "/c", executable, *cmd[1:]]
    return [executable, *cmd[1:]]


class ProgressSpinner:
    def __init__(self, label: str = ""):
        self._label = label
        self._chars = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])

    def tick(self) -> str:
        return f"{next(self._chars)} {self._label}"

    def done(self, message: str = "") -> str:
        return f"✓ {message}" if message else "✓"
