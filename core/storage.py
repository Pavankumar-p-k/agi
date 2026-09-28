"""System database locations for JARVIS.

All persistent stores live under the data/ directory. Individual modules
derive their own table schemas; this module only owns the file paths so
there is a single source of truth for storage locations.
"""
from __future__ import annotations

import os
from pathlib import Path

_DATA_DIR = Path(os.getenv("JARVIS_DATA_DIR", "data"))
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Canonical system database (SQLite) shared by memory/learning modules.
SYSTEM_DB = str(_DATA_DIR / "system.db")

# Per-feature database paths derived from the same root.
MEMORY_DB = str(_DATA_DIR / "memory.db")
TASKS_DB = str(_DATA_DIR / "tasks.db")
DECISIONS_DB = str(_DATA_DIR / "decisions.db")
