"""Change planning for the Coding AI specialist."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from core.coding.architecture_map import ArchitectureMapper
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.repository_indexer import RepositoryIndexer


class ChangeType(str, Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"
    MOVE = "move"


@dataclass
class FileChange:
    change_type: ChangeType | str
    file: str
    description: str = ""
    new_file: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.change_type, ChangeType):
            self.change_type = ChangeType(str(self.change_type).lower())
        self.file = self.file.replace("\\", "/")
        if self.new_file:
            self.new_file = self.new_file.replace("\\", "/")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["change_type"] = self.change_type.value
        return data


@dataclass
class ChangeStep:
    id: str
    description: str
    files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChangePlan:
    request: str
    changes: list[FileChange] = field(default_factory=list)
    steps: list[ChangeStep] = field(default_factory=list)
    overall_risk: float = 0.0
    total_affected_files: list[str] = field(default_factory=list)
    all_suggested_tests: list[str] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    execution_groups: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "changes": [change.to_dict() for change in self.changes],
            "steps": [step.to_dict() for step in self.steps],
            "step_count": len(self.steps),
            "overall_risk": self.overall_risk,
            "total_affected_files": self.total_affected_files,
            "all_suggested_tests": self.all_suggested_tests,
            "breaking_changes": self.breaking_changes,
            "warnings": self.warnings,
            "execution_groups": self.execution_groups,
        }


class ChangePlanner:
    def __init__(
        self,
        indexer: RepositoryIndexer,
        dependency_graph: DependencyGraph,
        architecture: ArchitectureMapper,
        impact_analyzer: ImpactAnalyzer,
    ):
        self.indexer = indexer
        self.dependency_graph = dependency_graph
        self.architecture = architecture
        self.impact_analyzer = impact_analyzer

    def plan(self, request: str, changes: list[FileChange]) -> ChangePlan:
        if not changes:
            return ChangePlan(request=request)
        impacts = {change.file: self.impact_analyzer.analyze(change.file) for change in changes}
        affected = {change.file for change in changes}
        tests = set()
        breaking: list[str] = []
        warnings: list[str] = []
        for change in changes:
            impact = impacts[change.file]
            affected.update(impact.direct_affected)
            affected.update(impact.transitive_affected)
            tests.update(impact.suggested_tests)
            if change.change_type in {ChangeType.DELETE, ChangeType.RENAME}:
                for dependent in sorted(set(impact.direct_affected) | set(impact.transitive_affected)):
                    breaking.append(f"{change.change_type.value} of {change.file} may break {dependent}")
            if impact.risk_label in {"high", "critical"}:
                warnings.append(f"{change.file} is {impact.risk_label} risk")
            if change.change_type == ChangeType.CREATE and self.indexer.get_entry(change.file):
                warnings.append(f"{change.file} already exists")
            if change.change_type in {ChangeType.MODIFY, ChangeType.DELETE, ChangeType.RENAME} and not self.indexer.get_entry(change.file):
                warnings.append(f"{change.file} does not exist")

        steps: list[ChangeStep] = [
            ChangeStep("understand_repository", "Refresh repository, architecture, and dependency context", sorted(affected)),
            ChangeStep("inspect_targets", "Inspect target files and affected callers", sorted(affected), ["understand_repository"]),
        ]
        previous = "inspect_targets"
        for index, change in enumerate(changes, start=1):
            verb = {
                ChangeType.CREATE: "Create or scaffold",
                ChangeType.MODIFY: "Modify",
                ChangeType.DELETE: "Delete safely",
                ChangeType.RENAME: "Rename",
                ChangeType.MOVE: "Move",
            }[change.change_type]
            step_id = f"change_{index}"
            files = [change.file] + ([change.new_file] if change.new_file else [])
            steps.append(ChangeStep(step_id, f"{verb} {change.file}: {change.description}", files, [previous]))
            previous = step_id
        steps.extend([
            ChangeStep("run_targeted_tests", "Run targeted tests/checks for affected files", sorted(tests), [previous]),
            ChangeStep("inspect_diff", "Inspect Git diff and verify intended behavior", sorted(affected), ["run_targeted_tests"]),
        ])
        risk = max((impact.risk_score for impact in impacts.values()), default=0.0)
        if any(change.change_type == ChangeType.DELETE for change in changes):
            risk = max(risk, 0.6)
        execution_groups = [[step.id] for step in steps]
        return ChangePlan(
            request=request,
            changes=changes,
            steps=steps,
            overall_risk=round(min(1.0, risk), 3),
            total_affected_files=sorted(affected),
            all_suggested_tests=sorted(tests),
            breaking_changes=breaking,
            warnings=warnings,
            execution_groups=execution_groups,
        )
