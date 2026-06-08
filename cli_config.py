from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

JARVIS_DIR = Path.home() / ".jarvis"
CONFIG_PATH = JARVIS_DIR / "config.json"
HISTORY_PATH = JARVIS_DIR / "history"


@dataclass
class JarvisConfig:
    default_model: str = "gemma4:e4b"
    debug: bool = False
    debug_search: bool = False
    show_timestamps: bool = False
    mode: str = "chat"
    theme: str = "dark"
    aliases: dict | None = None

    def save(self):
        JARVIS_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2, default=str))

    @classmethod
    def load(cls):
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                valid_keys = cls.__dataclass_fields__
                filtered = {k: v for k, v in data.items() if k in valid_keys}
                return cls(**filtered)
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "[Config] Failed to load %s: %s", CONFIG_PATH, e
                )
        return cls()
