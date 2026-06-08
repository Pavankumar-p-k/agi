"""Track recently accessed files to provide live context to the model.

Every read_file, write_file, edit_file, and batch_edit_file call updates
a per-session LRU of "hot files". The system prompt can include these as
context so the model knows what files the user/agent is currently working on.
"""

import time
from collections import OrderedDict
from typing import Optional

_HOT_FILES: dict[str, OrderedDict] = {}  # session_id -> OrderedDict[path, timestamp]
_MAX_HOT_FILES = 10


def _get_store(session_id: str) -> OrderedDict:
    if session_id not in _HOT_FILES:
        _HOT_FILES[session_id] = OrderedDict()
    return _HOT_FILES[session_id]


def touch_file(path: str, session_id: str = "default") -> None:
    """Record that a file was accessed."""
    store = _get_store(session_id)
    store[path] = time.time()
    store.move_to_end(path)
    while len(store) > _MAX_HOT_FILES:
        store.popitem(last=False)


def get_hot_files(session_id: str = "default", max_age: float = 300.0) -> list[dict]:
    """Return recently accessed files with timestamps."""
    store = _get_store(session_id)
    now = time.time()
    result = []
    for path, ts in reversed(list(store.items())):
        if now - ts > max_age:
            continue
        result.append({"path": path, "accessed_seconds_ago": int(now - ts)})
    return result


def format_hot_files(session_id: str = "default") -> str:
    """Format hot files as a context string for the system prompt."""
    files = get_hot_files(session_id)
    if not files:
        return ""
    lines = ["\n## Recently active files"]
    for f in files:
        ago = f["accessed_seconds_ago"]
        label = "just now" if ago < 5 else f"{ago}s ago" if ago < 60 else f"{ago // 60}m ago"
        lines.append(f"- `{f['path']}` ({label})")
    return "\n".join(lines)


def format_file_changes(session_id: str = "default") -> str:
    """Format recently changed files for the system prompt."""
    files = get_hot_files(session_id, max_age=60.0)
    if not files:
        return ""
    lines = ["\n## Files recently changed"]
    for f in files:
        ago = f["accessed_seconds_ago"]
        label = "just now" if ago < 5 else f"{ago}s ago"
        lines.append(f"- `{f['path']}` ({label})")
    return "\n".join(lines)
