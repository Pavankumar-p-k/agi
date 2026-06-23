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
import logging

import json
import os
from pathlib import Path
from prompt_toolkit.completion import Completer, Completion
logger = logging.getLogger(__name__)


class JarvisCompleter(Completer):
    COMMANDS = [
        "/session", "/sessions", "/session-new", "/session-switch",
        "/session-rename", "/session-export", "/session-fork", "/session-compact",
        "/model", "/undo", "/clear", "/agent", "/mode",
        "/history", "/timestamps", "/debug", "/debug-search", "/theme",
        "/stash", "/stash-list", "/stash-load",
        "/read", "/write", "/edit", "/ls", "/dir", "/tree", "/run", "/diff",
        "/status", "/boot", "/agents", "/design", "/frames", "/help", "/h", "/exit", "/quit",
        "/generate-ui", "/gui", "/opencode",
        "/plan", "/goal", "/develop", "/vision", "/feedback", "/tools",
        "/cmds", "/themes",
    ]

    def __init__(self, state_getter):
        self._state_getter = state_getter

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text:
            return
        first_space = text.find(" ")
        if first_space == -1:
            yield from self._complete_command(text)
            return
        cmd = text[:first_space].lower()
        arg = text[first_space + 1:]
        yield from self._complete_arg(cmd, arg)

    def _complete_command(self, prefix):
        for cmd in self.COMMANDS:
            if cmd.startswith(prefix):
                yield Completion(cmd, start_position=-len(prefix))

    def _complete_arg(self, cmd, prefix):
        if cmd in ("/read", "/write", "/edit", "/ls", "/dir", "/tree"):
            dir_part = os.path.dirname(prefix) or "."
            file_part = os.path.basename(prefix)
            try:
                dir_path = Path(dir_part)
                if dir_path.exists():
                    for entry in sorted(dir_path.iterdir()):
                        name = entry.name
                        if name.startswith(file_part):
                            display = name + ("/" if entry.is_dir() else "")
                            yield Completion(display, start_position=-len(file_part))
            except (PermissionError, OSError):
                pass
        elif cmd in ("/session-switch",):
            from core.session import list_sessions
            try:
                sessions = list_sessions()
                for s in sessions:
                    sid = s.get("session_id", "")
                    if sid.startswith(prefix):
                        yield Completion(sid, start_position=-len(prefix))
            except Exception as e:
                logger.warning("[cli_completer] complete_command failed: %s", e)
        elif cmd in ("/model",):
            yield from self._complete_model(prefix)
        elif cmd == "/stash-load":
            full_path = Path.home() / ".jarvis" / "stash"
            if full_path.exists():
                for f in sorted(full_path.glob("*.json")):
                    try:
                        idx = int(f.stem)
                        label = json.loads(f.read_text()).get("label", "") or str(idx)
                        if str(idx).startswith(prefix):
                            yield Completion(str(idx), start_position=-len(prefix), display_meta=f"#{idx} {label}")
                    except (ValueError, json.JSONDecodeError):
                        pass

    def _complete_model(self, prefix):
        models = ["gemma4:e4b", "qwen3:4b", "llama3.1:8b", "qwen2.5:7b",
                  "qwen2.5-coder:3b", "mistral:7b", "deepseek-r1:1.5b",
                  "tinyllama", "phi3:mini"]
        for m in models:
            if m.startswith(prefix):
                yield Completion(m, start_position=-len(prefix))
