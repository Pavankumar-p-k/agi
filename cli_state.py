"""cli_state.py — Shared state and constants for the JARVIS CLI."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT
APPS = ROOT / "apps" / "jarvis_app"
AUTONOMY_CLI = ROOT / "autonomy" / "cli" / "jarvis_cli.py"
STUDENT_MAIN = ROOT / "learning" / "student_agi" / "student_agi_main.py"

MODEL_PORTS = [
    ("tinyllama", 11434),
    ("deepseek-r1:1.5b", 11435),
    ("qwen2.5-coder:3b", 11436),
    ("qwen3:4b", 11437),
    ("qwen2.5:7b", 11438),
    ("mistral:7b", 11439),
    ("llama3.1:8b", 11440),
    ("phi3:mini", 11441),
    ("moondream", 11442),
]

from cli_config import JarvisConfig, JARVIS_DIR, CONFIG_PATH, HISTORY_PATH


@dataclass
class CliState:
    session: 'ConversationManager' = None
    config: 'JarvisConfig' = None
    mode: str = "chat"
    debug: bool = False
    debug_search: bool = False
    show_timestamps: bool = False
    stream: bool = True
    current_model: str = "gemma4:e4b"
    base_url: str = "http://127.0.0.1:8000"
    goal: str = ""
    progress: int = 0
    todos: list = None
    _pending_text: str = ""
