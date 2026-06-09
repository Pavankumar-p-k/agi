# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
