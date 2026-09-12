"""Project path constants.

De-poisoned: this module previously fabricated a DynamicStub for any name
(``core.constants.Anything`` "worked") and defined ``DATA_DIR`` as the literal
string ``"DATA_DIR"`` — so every derived path (data stores, RAG indexes,
tool-path safety roots) pointed at a nonexistent relative directory.

Resolution:
- ``DATA_DIR``      — project-local mutable data (default: <repo>/data)
- ``PERSONAL_DIR``  — user-private documents (default: <repo>/personal)

Both honour env-var overrides (``JARVIS_DATA_DIR`` / ``JARVIS_PERSONAL_DIR``)
and are created on first import (best effort — a read-only checkout must not
crash the import).
"""
from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _prepare(path: Path) -> str:
    resolved = Path(os.path.expanduser(str(path))).resolve()
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # read-only checkout: paths still resolve, creation happens later
    return str(resolved)


DATA_DIR = _prepare(Path(os.environ.get("JARVIS_DATA_DIR", _PROJECT_ROOT / "data")))
PERSONAL_DIR = _prepare(Path(os.environ.get("JARVIS_PERSONAL_DIR", _PROJECT_ROOT / "personal")))

__all__ = ["DATA_DIR", "PERSONAL_DIR"]
