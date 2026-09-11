"""Predictive simulation for change plans."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.coding.change_planner import ChangePlan, ChangeType


@dataclass
class PredictedBreakage:
    file: str
    reason: str
    risk: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChangeConflict:
    file: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationResult:
    plan_summary: str
    breakages: list[PredictedBreakage] = field(default_factory=list)
    conflicts: list[ChangeConflict] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    unchanged_affected: list[str] = field(default_factory=list)

    @property
    def free_of_issues(self) -> bool:
        return not self.breakages and not self.conflicts

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_summary": self.plan_summary,
            "breakages": [item.to_dict() for item in self.breakages],
            "conflicts": [item.to_dict() for item in self.conflicts],
            "breakage_count": len(self.breakages),
            "conflict_count": len(self.conflicts),
            "affected_files": self.affected_files,
            "unchanged_affected": self.unchanged_affected,
            "free_of_issues": self.free_of_issues,
        }


class ChangeSimulation:
    def __init__(self, indexer, dependency_graph, architecture, impact_analyzer):
        self.indexer = indexer
        self.dependency_graph = dependency_graph
        self.architecture = architecture
        self.impact_analyzer = impact_analyzer

    def simulate(self, plan: ChangePlan) -> SimulationResult:
        touched = [change.file for change in plan.changes]
        affected = sorted(set(plan.total_affected_files))
        breakages: list[PredictedBreakage] = []
        conflicts: list[ChangeConflict] = []
        by_file: dict[str, set[str]] = {}
        for change in plan.changes:
            by_file.setdefault(change.file, set()).add(change.change_type.value)
            if change.change_type == ChangeType.DELETE:
                for file in self.dependency_graph.impact_set([change.file]):
                    breakages.append(PredictedBreakage(file, f"Delete of {change.file} may remove imported code", "high"))
            elif change.change_type == ChangeType.RENAME:
                for file in self.dependency_graph.impact_set([change.file]):
                    breakages.append(PredictedBreakage(file, f"Rename of {change.file} requires import updates", "medium"))
            elif change.change_type == ChangeType.MODIFY and self.indexer.get_entry(change.file) is None:
                breakages.append(PredictedBreakage(change.file, "Cannot modify a file that does not exist", "high"))
        for file, actions in by_file.items():
            if len(actions) > 1:
                conflicts.append(ChangeConflict(file, f"Conflicting actions requested: {', '.join(sorted(actions))}"))
        unchanged = sorted(set(affected) - set(touched))
        return SimulationResult(plan.request, breakages, conflicts, affected, unchanged)

    def predict_test_failures(self, plan: ChangePlan) -> list[dict[str, Any]]:
        result = self.simulate(plan)
        failures = []
        for test in plan.all_suggested_tests:
            failures.append({"test": test, "risk": "high" if result.breakages else "medium", "reason": "affected by planned changes"})
        return failures
