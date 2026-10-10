# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""cli_utils.py — shared helpers for the JARVIS CLI.

Canonical root-level implementation (kept in sync with jarvis-export/cli).
"""
from __future__ import annotations

import itertools
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

IDE_PRESETS: dict[str, dict[str, Any]] = {
    "vscode": {"cmd": ["code"], "args": ["-r"]},
    "cursor": {"cmd": ["cursor"], "args": ["-r"]},
    "webstorm": {"cmd": ["webstorm"], "args": []},
    "pycharm": {"cmd": ["charm"], "args": []},
    "sublime": {"cmd": ["subl"], "args": []},
}


def get_git_root(cwd: str = "") -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd or None,
            capture_output=True, text=True, timeout=10, check=True,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


_THEME_DARK = {
    "bg": "#0d1117", "fg": "#c9d1d9", "accent": "#58a6ff",
    "ok": "#3fb950", "warn": "#d29922", "err": "#f85149",
}
_THEME_LIGHT = {
    "bg": "#ffffff", "fg": "#24292f", "accent": "#0969da",
    "ok": "#1a7f37", "warn": "#9a6700", "err": "#cf222e",
}


def style_theme(dark: bool = True) -> dict[str, str]:
    return _THEME_DARK if dark else _THEME_LIGHT


def syntax_highlight(text: str, filename: str | None = None) -> str:
    """Fallback highlighter — returns text unchanged without pygments."""
    try:
        from pygments import highlight
        from pygments.lexers import get_lexer_for_filename, TextLexer
        from pygments.formatters import Terminal256Formatter

        try:
            lexer = get_lexer_for_filename(filename or "x.txt")
        except Exception:
            lexer = TextLexer()
        return highlight(text, lexer, Terminal256Formatter(style="monokai")).rstrip("\n")
    except ImportError:
        return text


_COLORS = {"red": "31", "green": "32", "yellow": "33", "blue": "34",
           "magenta": "35", "cyan": "36", "white": "37", "gray": "90"}


def colorize(text: str, color: str) -> str:
    code = _COLORS.get(color, "0")
    return f"\033[{code}m{text}\033[0m"


def python_exe() -> str:
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        candidate = Path(venv) / "Scripts" / "python.exe"
        if candidate.exists():
            return str(candidate)
        candidate = Path(venv) / "bin" / "python"
        if candidate.exists():
            return str(candidate)
    return sys.executable or "python"


def common_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def run_command(cmd: list[str], cwd: Path | None = None, env: dict | None = None,
                dry_run: bool = False) -> int:
    if dry_run:
        print(" ".join(cmd))
        return 0
    return subprocess.call(cmd, cwd=str(cwd) if cwd else None, env=env)


def spawn_background(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    log_path: Path | None = None,
) -> subprocess.Popen:
    handle = open(log_path, "ab") if log_path else subprocess.DEVNULL
    return subprocess.Popen(
        cmd, cwd=str(cwd) if cwd else None, env=env,
        stdout=handle, stderr=subprocess.STDOUT,
    )


def prepare_command(cmd: list[str]) -> list[str]:
    return [str(part) for part in cmd]


class _SPIN_FRAMES:
    pass


_SPINNER_FRAMES = itertools.cycle(["|", "/", "-", "\\"])


class ProgressSpinner:
    """Minimal no-tty spinner used by long-running CLI tasks."""

    def __init__(self, label: str = "") -> None:
        self.label = label
        self._frames = itertools.cycle(["|", "/", "-", "\\"])

    def tick(self) -> str:
        return f"{next(self._frames)} {self.label}"

    def done(self, message: str = "") -> str:
        return f"{message or self.label} done".strip()


__all__ = [
    "ROOT", "IDE_PRESETS", "ProgressSpinner",
    "get_git_root", "style_theme", "syntax_highlight", "colorize",
    "python_exe", "common_env", "run_command", "spawn_background",
    "prepare_command",
]
