from __future__ import annotations

from pathlib import Path
from typing import Any


def context_workspace_root(context: dict[str, Any] | None = None, default_root: str | Path | None = None) -> Path:
    source = (context or {}).get("workspace_root", default_root or Path.cwd())
    return Path(source).expanduser().resolve()


def context_sandbox_root(context: dict[str, Any] | None = None, default_root: str | Path | None = None) -> Path:
    source = (context or {}).get("sandbox_root", default_root or Path.cwd())
    return Path(source).expanduser().resolve()


def resolve_workspace_path(path: str, context: dict[str, Any] | None = None, default_root: str | Path | None = None) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (context_workspace_root(context, default_root) / candidate).resolve()


def path_within_root(target: str | Path, root: str | Path) -> bool:
    try:
        Path(target).expanduser().resolve().relative_to(Path(root).expanduser().resolve())
        return True
    except ValueError:
        return False
