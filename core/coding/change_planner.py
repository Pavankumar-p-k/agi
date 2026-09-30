"""Change planning for the coding engine (ChangeType, FileChange, ChangePlan).

The planner turns a list of FileChange requests into an ordered,
risk-scored ChangePlan with execution groups, breaking-change and
warning detection, impact analysis and suggested tests, using the
repository indexer, dependency graph, architecture map and impact
analyzer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional


class ChangeType(str, Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"
    MOVE = "move"


@dataclass
class FileChange:
    change_type: ChangeType
    path: str
    description: str = ""
    new_file: str = ""

    @property
    def file(self) -> str:
        """Alias for path (historical contract)."""
        return self.path


@dataclass
class ChangeStep:
    id: str = ""
    order: int = 0
    description: str = ""
    file_change: Optional[FileChange] = None
    group: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "order": self.order,
            "description": self.description,
            "group": self.group,
            "file": self.file_change.path if self.file_change else "",
        }


@dataclass
class ChangePlan:
    request: str = ""
    goal: str = ""
    steps: list[ChangeStep] = field(default_factory=list)
    changes: list[FileChange] = field(default_factory=list)
    risk: str = "low"
    overall_risk: float = 0.0
    warnings: list[str] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)
    total_affected_files: list[str] = field(default_factory=list)
    execution_groups: list[list[str]] = field(default_factory=list)
    all_suggested_tests: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "goal": self.goal,
            "risk": self.risk,
            "overall_risk": self.overall_risk,
            "step_count": len(self.steps),
            "steps": [step.to_dict() for step in self.steps],
            "warnings": list(self.warnings),
            "breaking_changes": list(self.breaking_changes),
            "total_affected_files": list(self.total_affected_files),
            "execution_groups": [list(group) for group in self.execution_groups],
            "all_suggested_tests": list(self.all_suggested_tests),
        }


_RISK_LABELS = ((0.8, "critical"), (0.55, "high"), (0.25, "medium"))


def _risk_label(score: float) -> str:
    for threshold, label in _RISK_LABELS:
        if score >= threshold:
            return label
    return "low"


class ChangePlanner:
    """Plans ordered, risk-scored change sets against a repository."""

    def __init__(self, indexer, dependency_graph, architecture,
                 impact_analyzer) -> None:
        self.indexer = indexer
        self.dependency_graph = dependency_graph
        self.architecture = architecture
        self.impact_analyzer = impact_analyzer

    # ── planning ─────────────────────────────────────────────────────
    def plan(self, request: str, changes: Iterable[FileChange]) -> ChangePlan:
        change_list = list(changes)
        plan = ChangePlan(request=request, goal=request, changes=change_list)

        if not change_list:
            return plan

        arch = self.architecture.architecture or self.architecture.map_layers()
        if not self.dependency_graph.nodes:
            self.dependency_graph.build()

        affected: set[str] = set()
        breaking: list[str] = []
        warnings: list[str] = []
        tests: set[str] = set()
        risk_scores: list[float] = []
        steps: list[ChangeStep] = []

        for index, change in enumerate(change_list):
            path = change.path.replace("\\", "/")
            entry = self.indexer.get_entry(path)

            # Impact for this file (real analysis, tolerate unknown files).
            impact = self.impact_analyzer.analyze(path)
            affected.update(impact.direct_affected)
            affected.update(impact.transitive_affected)
            tests.update(impact.suggested_tests)
            risk_scores.append(impact.risk_score)

            # Breaking changes / warnings per action.
            if change.change_type == ChangeType.DELETE:
                for dependent in self.dependency_graph.impact_set([path]):
                    breaking.append(
                        f"deleting {path} breaks {dependent}")
                if entry is None:
                    warnings.append(f"{path} does not exist")
            elif change.change_type in (ChangeType.RENAME, ChangeType.MOVE):
                if entry is None:
                    warnings.append(f"{path} does not exist")
                if change.new_file:
                    for dependent in self.dependency_graph.impact_set([path]):
                        breaking.append(
                            f"renaming {path} to {change.new_file} requires "
                            f"import updates in {dependent}")
            elif change.change_type == ChangeType.CREATE and entry is not None:
                warnings.append(f"{path} already exists")
            elif change.change_type == ChangeType.MODIFY and entry is None:
                warnings.append(f"{path} does not exist")

            # Central/shared files raise risk.
            layer = arch.file_to_layer.get(path, "")
            if layer in ("config", "settings") or "settings" in path or "config" in path:
                risk_scores.append(0.6)
                warnings.append(f"{path} is a central configuration file")        # Execution ordering: models/repos first, then services, then
        # controllers/routes, then tests (dependency-safe order).
            group = self._group_for(path, arch)
            description = self._describe(change)
            steps.append(ChangeStep(
                id=f"change_{index + 1}_{change.change_type.value}",
                order=index + 1,
                description=description,
                file_change=change,
                group=group,
            ))

        # Repository understanding always comes first (pinned contract).
        steps.insert(0, ChangeStep(
            id="understand_repository",
            order=0,
            description="Build repository, dependency and architecture context",
            group=0,
        ))

        overall = max(risk_scores) if risk_scores else 0.0
        plan.overall_risk = round(min(1.0, overall), 3)
        plan.risk = _risk_label(plan.overall_risk)
        plan.warnings = warnings
        plan.breaking_changes = breaking
        plan.total_affected_files = sorted(affected | {c.path.replace("\\", "/")
                                                       for c in change_list})
        plan.all_suggested_tests = sorted(tests)

        # Group steps into execution waves.
        groups: dict[int, list[str]] = {}
        for step in sorted(steps, key=lambda s: (s.group, s.order)):
            groups.setdefault(step.group, []).append(step.description)
        plan.execution_groups = [groups[key] for key in sorted(groups)]
        plan.steps = sorted(steps, key=lambda s: (s.group, s.order))
        for order, step in enumerate(plan.steps, start=1):
            step.order = order
        return plan

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _group_for(path: str, arch) -> int:
        layer = arch.file_to_layer.get(path, "")
        order = {"models": 0, "repositories": 1, "config": 1, "settings": 1,
                 "services": 2, "utils": 2, "controllers": 3, "routes": 3,
                 "api": 3, "tests": 4}
        return order.get(layer, 2)

    @staticmethod
    def _describe(change: FileChange) -> str:
        action = change.change_type.value
        if change.change_type == ChangeType.CREATE:
            return f"Scaffold {change.path}: {change.description or 'create file'}".strip()
        if change.change_type == ChangeType.DELETE:
            return f"Delete {change.path}: {change.description or 'remove file'}".strip()
        if change.change_type in (ChangeType.RENAME, ChangeType.MOVE):
            target = change.new_file or "?"
            return f"Rename {change.path} -> {target}: {change.description}".strip()
        return f"Modify {change.path}: {change.description or 'edit file'}".strip()
