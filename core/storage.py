"""Shared backend storage location compatibility constant."""
from __future__ import annotations

import os
from pathlib import Path

SYSTEM_DB = os.getenv("JARVIS_SYSTEM_DB", str(Path("data") / "system.db"))

__all__ = ["SYSTEM_DB"]
