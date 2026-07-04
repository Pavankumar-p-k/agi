from __future__ import annotations

import os


def read_tail(path: str | os.PathLike, n_lines: int = 40) -> str:
    """Read the last n_lines from a file, efficiently."""
    path = os.fspath(path)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            # Seek near the end
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return "(empty)"
            # Read last 4KB per line desired, min 4KB
            read_size = min(max(n_lines * 200, 4096), size)
            f.seek(max(size - read_size, 0))
            text = f.read()
            lines = text.splitlines()
            return "\n".join(lines[-n_lines:])
    except FileNotFoundError:
        return "(log file not found)"
    except Exception as e:
        return f"(error reading log: {e})"
