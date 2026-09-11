from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar
import json
import os
import shutil

PROJECTS_DIR = Path(os.path.expanduser("~/.jarvis/projects"))


@dataclass
class ProjectState:
    project_name: str
    goal: str = ""
    status: str = "pending"
    interpreted_goal: dict[str, Any] = field(default_factory=dict)
    template_name: str = ""
    retries: int = 0
    quality_score: dict[str, Any] | None = None
    current_step: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    _KNOWN_FIELDS: ClassVar[set[str]] = {item.name for item in fields(__class__)} if False else set()

    @property
    def project_dir(self) -> Path:
        return PROJECTS_DIR / self.project_name

    @property
    def state_path(self) -> Path:
        return self.project_dir / "state.json"

    def save(self) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        payload = {item.name: getattr(self, item.name) for item in fields(self)}
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        os.replace(temporary, self.state_path)

    @classmethod
    def load(cls, project_name: str) -> "ProjectState | None":
        path = PROJECTS_DIR / project_name / "state.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        allowed = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in allowed})


def list_projects() -> list[ProjectState]:
    if not PROJECTS_DIR.exists():
        return []
    projects: list[ProjectState] = []
    for child in PROJECTS_DIR.iterdir():
        if child.is_dir():
            state = ProjectState.load(child.name)
            if state is not None:
                projects.append(state)
    return projects


def delete_project(project_name: str) -> None:
    shutil.rmtree(PROJECTS_DIR / project_name, ignore_errors=True)
