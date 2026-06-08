"""core/project_state.py
Single source of truth for every JARVIS project.
All agents read/write this object. No exceptions.
"""
import os, re, json, logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger("project_state")

PROJECTS_DIR = Path.home() / ".jarvis" / "projects"


@dataclass
class ValidationResult:
    check: str
    passed: bool
    details: str = ""


@dataclass
class ProjectState:
    project_name: str
    created_at: str = ""
    goal: str = ""
    status: str = "created"

    interpreted_goal: Optional[dict] = None
    plan: list = field(default_factory=list)
    pages: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    validation_results: list = field(default_factory=list)
    issues: list = field(default_factory=list)

    retries: int = 0
    max_retries: int = 5
    current_task_id: str = ""

    template_name: str = ""
    template_path: str = ""

    quality_score: Optional[dict] = None
    partial_progress: Optional[dict] = None
    composed_plan: Optional[dict] = None

    ambiguous_goal_result: Optional[dict] = None

    agent_log: list = field(default_factory=list)
    events: list = field(default_factory=list)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self._sanitize_name()

    def _sanitize_name(self):
        self.project_name = re.sub(r'[^a-zA-Z0-9_-]+', '_', self.project_name).strip("_")[:60]

    @property
    def project_dir(self) -> Path:
        return PROJECTS_DIR / self.project_name

    @property
    def state_path(self) -> Path:
        return self.project_dir / "state.json"

    def save(self):
        self.project_dir.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["validation_results"] = [asdict(v) if isinstance(v, ValidationResult) else v for v in self.validation_results]
        self.state_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    @classmethod
    def load(cls, project_name: str) -> Optional["ProjectState"]:
        path = PROJECTS_DIR / re.sub(r'[^a-zA-Z0-9_-]+', '_', project_name).strip("_")[:60] / "state.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                vrs = data.pop("validation_results", [])
                # Filter to known fields only (resilient to schema drift)
                known = set(cls.__dataclass_fields__.keys())
                filtered = {k: v for k, v in data.items() if k in known}
                state = cls(**filtered)
                state.validation_results = [ValidationResult(**v) for v in vrs if isinstance(v, dict)]
                return state
            except Exception as e:
                logger.error(f"Failed to load state for {project_name}: {e}")
        return None

    def log_event(self, event: str, data: dict = None):
        entry = {"timestamp": datetime.now().isoformat(), "event": event, "data": data or {}}
        self.events.append(entry)
        self.save()

    def log_agent(self, agent: str, task_id: str, action: str, result: str = ""):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent, "task_id": task_id,
            "action": action, "result": result[:500],
        }
        self.agent_log.append(entry)
        self.save()


def list_projects() -> list[dict]:
    if not PROJECTS_DIR.exists():
        return []
    projects = []
    for d in sorted(PROJECTS_DIR.iterdir(), reverse=True):
        state_file = d / "state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                projects.append({
                    "name": d.name,
                    "status": data.get("status", "unknown"),
                    "goal": data.get("goal", "")[:80],
                    "retries": data.get("retries", 0),
                    "created_at": data.get("created_at", ""),
                    "issues": len(data.get("issues", [])),
                })
            except Exception as _e:
                logger.debug("project_state load projects failed: %s", _e)
    return projects


def delete_project(project_name: str) -> bool:
    safe = re.sub(r'[^a-zA-Z0-9_-]+', '_', project_name).strip("_")[:60]
    path = PROJECTS_DIR / safe
    if path.exists():
        import shutil
        shutil.rmtree(path)
        return True
    return False
