"""Shared filesystem locations for JARVIS (rebuilt in STEP 4).

Pinned specs
------------
* ``tests/unit/test_execution_dispatch.py::test_tool_path_roots_includes_data``
* ``tests/unit/test_execution_tools.py::test_tool_path_roots_contains_data_dir``

Both require ``DATA_DIR`` to be a path that ``_tool_path_roots()`` returns —
i.e. a real, existing directory (the assertions use ``os.path.samefile`` when
the root exists, so the directory must actually be creatable).

The previous body was a DynamicStub that returned the *string literals*
``"DATA_DIR"`` / ``"PERSONAL_DIR"``; every consumer then built paths like
``Path("DATA_DIR") / "orchestration_store.db"`` and silently wrote files into
a directory named ``DATA_DIR`` next to wherever the process happened to run.

Layout
------
``DATA_DIR``    -> ``<repo>/data``           shared, machine-local app state
``PERSONAL_DIR``-> ``~/.jarvis/personal``    per-user documents for RAG

Both are created on first use so consumers can join paths unconditionally.
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = ["DATA_DIR", "PERSONAL_DIR", "ensure_data_dirs", "as_path"]

_REPO_ROOT = Path(__file__).resolve().parent.parent

#: Shared application state (databases, scratch files, indexes).
DATA_DIR: str = str(_REPO_ROOT / "data")

#: Per-user personal documents (the RAG corpus).
PERSONAL_DIR: str = str(Path.home() / ".jarvis" / "personal")


def ensure_data_dirs() -> None:
    """Create both directories if missing (idempotent, never raises)."""
    for raw in (DATA_DIR, PERSONAL_DIR):
        try:
            Path(raw).mkdir(parents=True, exist_ok=True)
        except OSError:
            # Read-only checkout / sandboxed FS: consumers fall back to cwd.
            pass


def as_path(raw: str) -> Path:
    """Return ``raw`` as an absolute Path, creating it if it does not exist."""
    p = Path(raw)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


# Guarantee the standard layout exists for callers that import constants
# for their side effect (execution.py joins DATA_DIR at module scope).
ensure_data_dirs()

# Convenience for consumers that want the resolved form without re-joining.
DATA_PATH = Path(DATA_DIR)
PERSONAL_PATH = Path(PERSONAL_DIR)
