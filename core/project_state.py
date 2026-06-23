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
"""core/project_state.py
Single source of truth for every JARVIS project.
All agents read/write this object. No exceptions.
"""
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("project_state")

PROJECTS_DIR = Path.home() / ".jarvis" / "projects"


class RequirementStatus(Enum):
    MET = "met"
    NOT_MET = "not_met"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass
class Requirement:
    id: str
    description: str
    category: str = "general"
    status: RequirementStatus = RequirementStatus.UNKNOWN
    evidence: str = ""


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

    interpreted_goal: dict | None = None
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

    quality_score: dict | None = None
    partial_progress: dict | None = None
    composed_plan: dict | None = None

    ambiguous_goal_result: dict | None = None

    agent_log: list = field(default_factory=list)
    events: list = field(default_factory=list)

    requirements: list = field(default_factory=list)
    completion_score: float = 0.0

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

    def extract_requirements(self):
        if not self.interpreted_goal:
            return

        goal = self.interpreted_goal
        pages = goal.get("pages", [])
        tech = goal.get("tech_stack", [])
        features = goal.get("features", [])
        brand = goal.get("brand_name", "")
        business = goal.get("business_type", "")
        original = goal.get("original_goal", "").lower()

        reqs = []
        req_id = 0
        for p in pages:
            req_id += 1
            reqs.append(Requirement(id=f"req_{req_id}", description=f"Page: {p}", category="pages"))

        for f in features:
            req_id += 1
            reqs.append(Requirement(id=f"req_{req_id}", description=f"Feature: {f}", category="features"))

        for t in tech:
            req_id += 1
            reqs.append(Requirement(id=f"req_{req_id}", description=f"Tech stack: {t}", category="tech"))

        if brand:
            req_id += 1
            reqs.append(Requirement(id=f"req_{req_id}", description=f"Brand name '{brand}' present", category="branding"))

        if business:
            req_id += 1
            reqs.append(Requirement(id=f"req_{req_id}", description=f"Business type: {business}", category="business"))

        for keyword, label in [("dark mode", "Dark Mode"), ("light mode", "Light Mode"),
                                ("responsive", "Responsive Design"), ("mobile", "Mobile Friendly"),
                                ("deploy", "Deployment"), ("auth", "Authentication"),
                                ("login", "Login"), ("contact", "Contact Form"),
                                ("animation", "Animations"), ("seo", "SEO")]:
            if keyword in original:
                req_id += 1
                reqs.append(Requirement(id=f"req_{req_id}", description=label, category="features"))

        self.requirements = [asdict(r) for r in reqs]

    def compute_completion(self):
        if not self.requirements:
            self.completion_score = 0.0
            return

        reqs = [Requirement(**r) if isinstance(r, dict) else r for r in self.requirements]
        if not reqs:
            self.completion_score = 0.0
            return

        met = sum(1 for r in reqs if r.status == RequirementStatus.MET)
        partial = sum(1 for r in reqs if r.status == RequirementStatus.PARTIAL)
        total = len(reqs)

        self.completion_score = (met + partial * 0.5) / total * 100.0 if total else 0.0

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
