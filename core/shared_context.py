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
"""core/shared_context.py
Project-level context file manager for SupervisorAgent.
Maintains a single SHARED_CONTEXT.md per project that all CLI agents can read.
Auto-summarizes when it grows beyond a threshold.
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("shared_context")

PROJECTS_DIR = Path.home() / ".jarvis" / "projects"
SUMMARY_THRESHOLD = 8000  # chars — summarize when above this

class SharedContext:
    def __init__(self, project_name: str):
        safe = re.sub(r'[^a-zA-Z0-9_-]+', '_', project_name).strip("_")[:60]
        self.project_dir = PROJECTS_DIR / safe
        self.context_file = self.project_dir / "SHARED_CONTEXT.md"
        self.goal_file = self.project_dir / "GOAL.md"
        self.state_file = self.project_dir / "state.json"
        self.project_dir.mkdir(parents=True, exist_ok=True)

    def write_goal(self, goal: str, plan: dict):
        self.goal_file.write_text(
            f"# Project Goal\n\n{goal}\n\n"
            f"## Plan\n```json\n{json.dumps(plan, indent=2)}\n```\n",
            encoding="utf-8"
        )

    def read_goal(self) -> str:
        if self.goal_file.exists():
            return self.goal_file.read_text(encoding="utf-8")
        return ""

    def append(self, section: str, content: str):
        text = self.context_file.read_text(encoding="utf-8") if self.context_file.exists() else ""
        entry = f"\n## {section} ({datetime.now().isoformat()})\n{content}\n"
        text += entry
        if len(text) > SUMMARY_THRESHOLD:
            text = self._summarize(text)
        self.context_file.write_text(text, encoding="utf-8")

    def read(self) -> str:
        if self.context_file.exists():
            return self.context_file.read_text(encoding="utf-8")
        return ""

    def set_state(self, key: str, value):
        state = {}
        if self.state_file.exists():
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        state[key] = value
        self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def get_state(self, key: str, default=None):
        if self.state_file.exists():
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
            return state.get(key, default)
        return default

    def mark_task_complete(self, task_id: str, result: str):
        completed = self.get_state("completed_tasks", [])
        completed.append({"task_id": task_id, "result": result[:200], "time": datetime.now().isoformat()})
        self.set_state("completed_tasks", completed)

    def get_progress(self) -> dict:
        return {
            "goal": self.read_goal(),
            "context_size": len(self.read()),
            "state": json.loads(self.state_file.read_text(encoding="utf-8")) if self.state_file.exists() else {},
            "files": list(self.project_dir.iterdir()) if self.project_dir.exists() else []
        }

    def _summarize(self, text: str) -> str:
        lines = text.strip().split("\n")
        if len(lines) <= 20:
            return text
        header = lines[0] if lines[0].startswith("#") else "# Project Context"
        recent = lines[-15:]
        summary = (
            f"{header}\n\n"
            f"_Auto-summarized at {datetime.now().isoformat()}_\n"
            f"_Original: {len(lines)} lines_\n\n"
            f"## Key Sections\n"
        )
        sections = set()
        for line in lines:
            if line.startswith("## "):
                sections.add(line.strip("# "))
        for s in sorted(sections):
            summary += f"- {s}\n"
        summary += "\n## Recent Activity\n" + "\n".join(recent) + "\n"
        return summary


def get_context(project_name: str) -> SharedContext:
    return SharedContext(project_name)
