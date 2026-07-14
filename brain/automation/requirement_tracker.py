from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Requirement:
    name: str
    completed: bool = False


class RequirementTracker:
    """Parse goal into named requirements and measure completion percentage."""

    def __init__(self):
        self.requirements: list[Requirement] = []
        self._raw_goal: str = ""

    def parse_goal(self, goal: str):
        self._raw_goal = goal
        self.requirements = []
        lines = goal.split("\n")
        for line in lines:
            line = line.strip()
            m = re.match(r"^[-*\d+\.]\s+(.+)$", line)
            if m:
                self.requirements.append(Requirement(name=m.group(1).strip()))
        if not self.requirements:
            parts = re.split(r"\band\b|,", goal)
            for p in parts:
                p = p.strip()
                if p and len(p) > 3 and p.lower() not in ("with", "the", "for", "using", "that", "this"):
                    self.requirements.append(Requirement(name=p))
        if not self.requirements:
            self.requirements.append(Requirement(name=goal.strip()))

    def check_completion(self, proj_dir: str, plan: dict) -> float:
        proj_name = plan.get("project_name", "project")
        root = os.path.join(proj_dir, proj_name) if proj_dir else proj_name
        for req in self.requirements:
            req.completed = self._check_requirement(req.name, root)
        if not self.requirements:
            return 0.0
        done = sum(1 for r in self.requirements if r.completed)
        return (done / len(self.requirements)) * 100.0

    def _check_requirement(self, name: str, root: str) -> bool:
        lo = name.lower()
        keywords = [w for w in lo.split() if len(w) > 3]
        if not keywords:
            return False
        for r, _dirs, files in os.walk(root if root and os.path.isdir(root) else "."):
            for f in files:
                if f.endswith((".java", ".kt", ".py", ".ts", ".js", ".xml", ".rs", ".md")):
                    try:
                        with open(os.path.join(r, f), encoding="utf-8", errors="replace") as fh:
                            c = fh.read().lower()
                        found = sum(1 for w in keywords if w in c)
                        if found >= max(1, len(keywords) * 2 // 3):
                            return True
                    except Exception:
                        pass
        return False

    def summary(self) -> str:
        lines = []
        for r in self.requirements:
            lines.append(f"{'✓' if r.completed else '✗'} {r.name}")
        return "\n".join(lines)
