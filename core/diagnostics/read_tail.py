"""Tail-reading helper for diagnostics logs."""
from __future__ import annotations

from pathlib import Path


def read_tail(path: Path | str, n_lines: int = 40) -> str:
    try:
        target = Path(path)
        if not target.exists():
            return ""
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max(1, n_lines):])
    except Exception:
        return ""


__all__ = ["read_tail"]
