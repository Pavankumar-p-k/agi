from __future__ import annotations

from pathlib import Path

from ..contracts import ToolSpec
from ..utils import resolve_workspace_path


def register_file_tools(registry) -> None:
    registry.register(
        ToolSpec("read_file", "Read a file from disk.", ["path"], parameters={"path": {"type": "string", "required": True}}, category="filesystem", read_only=True, keywords=["read", "file", "open"]),
        lambda path, context=None, **_: _read_file(path, context=context),
    )
    registry.register(
        ToolSpec("write_file", "Write content to a file.", ["path", "content"], parameters={"path": {"type": "string", "required": True}, "content": {"type": "string", "required": False, "default": ""}}, category="filesystem", permission="elevated", keywords=["write", "save", "file"]),
        lambda path, content="", context=None, **_: _write_file(path, content, context=context),
    )
    registry.register(
        ToolSpec("create_file", "Create a file if it does not exist.", ["path", "content"], parameters={"path": {"type": "string", "required": True}, "content": {"type": "string", "required": False, "default": ""}}, category="filesystem", permission="elevated", keywords=["create", "new", "file"]),
        lambda path, content="", context=None, **_: _write_file(path, content, create_only=True, context=context),
    )
    registry.register(
        ToolSpec("delete_file", "Delete a file from disk.", ["path"], parameters={"path": {"type": "string", "required": True}}, category="filesystem", permission="elevated", keywords=["delete", "remove", "file"]),
        lambda path, context=None, **_: _delete_file(path, context=context),
    )
    registry.register(
        ToolSpec("list_directory", "List directory contents.", ["path"], parameters={"path": {"type": "string", "required": False, "default": "."}}, category="filesystem", read_only=True, keywords=["list", "directory", "folder"]),
        lambda path=".", context=None, **_: _list_directory(path, context=context),
    )
    registry.register(
        ToolSpec("search_files", "Search files by name pattern.", ["path", "pattern"], parameters={"path": {"type": "string", "required": False, "default": "."}, "pattern": {"type": "string", "required": False, "default": "*"}}, category="filesystem", read_only=True, keywords=["search", "find", "files"]),
        lambda path=".", pattern="*", context=None, **_: _search_files(path, pattern, context=context),
    )


def _resolve_path(path: str, context: dict | None = None) -> Path:
    return resolve_workspace_path(path, context=context)


def _read_file(path: str, context: dict | None = None) -> dict:
    target = _resolve_path(path, context=context)
    if not target.exists():
        return {"path": str(target), "content": "", "exists": False}
    return {"path": str(target), "content": target.read_text(encoding="utf-8"), "exists": True}


def _write_file(path: str, content: str, create_only: bool = False, context: dict | None = None) -> dict:
    target = _resolve_path(path, context=context)
    target.parent.mkdir(parents=True, exist_ok=True)
    if create_only and target.exists():
        return {"written": False, "path": str(target), "reason": "file already exists"}
    target.write_text(content, encoding="utf-8")
    return {"written": True, "path": str(target), "bytes": len(content.encode("utf-8"))}


def _delete_file(path: str, context: dict | None = None) -> dict:
    target = _resolve_path(path, context=context)
    if target.exists():
        target.unlink()
    return {"deleted": True, "path": str(target)}


def _list_directory(path: str, context: dict | None = None) -> dict:
    root = _resolve_path(path, context=context)
    if not root.exists():
        return {"path": str(root), "entries": [], "exists": False}
    return {
        "path": str(root),
        "exists": True,
        "entries": [{"name": item.name, "is_dir": item.is_dir()} for item in sorted(root.iterdir(), key=lambda value: value.name.lower())],
    }


def _search_files(path: str, pattern: str, context: dict | None = None) -> dict:
    root = _resolve_path(path, context=context)
    if not root.exists():
        return {"path": str(root), "pattern": pattern, "matches": [], "exists": False}
    matches = [str(item) for item in root.rglob(pattern)]
    return {"path": str(root), "pattern": pattern, "matches": matches[:200], "exists": True}
