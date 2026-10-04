"""First-run setup detector.

Rebuilt in STEP 4: the previous body was ``return False`` — a constant that
made the first-run banner unreachable forever.  Real rule now:

    first run  ==  no wizard state AND no completed config

Both files are checked because a user may have a config from an older JARVIS
build without ever having run this wizard, and vice versa (interrupted setup).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

JARVIS_DIR = Path.home() / ".jarvis"
SETUP_STATE_PATH = JARVIS_DIR / "setup_state.json"
CONFIG_PATH = JARVIS_DIR / "config.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, ValueError):
        pass
    return {}


def is_first_run() -> bool:
    """True when no setup has been recorded and no config exists yet."""
    state = _load_json(SETUP_STATE_PATH)
    if state.get("phase") in ("complete", "in_progress", "failed"):
        return False
    config = _load_json(CONFIG_PATH)
    if config.get("setup_completed") or config.get("default_model"):
        return False
    return True


__all__ = ["is_first_run"]
