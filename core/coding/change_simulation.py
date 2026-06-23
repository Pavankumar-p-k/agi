"""ChangeSimulation — predict breakages, detect conflicts, select tests before editing.

Simulates the effect of planned changes on the repository's dependency graph
and test suite without touching any files. Answers "what breaks if I do this?"
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from core.coding.architecture_map import ArchitectureMapper
from core.coding.change_planner import ChangePlan, ChangeType, FileChange
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.repository_indexer import RepositoryIndexer

logger = logging.getLogger(__name__)


@dataclass
class PredictedBreakage:
    file: str
    reason: str
    severity: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "reason": self.reason,
            "severity": self.severity,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class ChangeConflict:
    step_a_index: int
    step_b_index: int
    file: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "step_a": self.step_a_index,
            "step_b": self.step_b_index,
            "file": self.file,
            "reason": self.reason,
        }


@dataclass
class SimulationResult:
    plan_summary: str
    breakages: list[PredictedBreakage] = field(default_factory=list)
    conflicts: list[ChangeConflict] = field(default_factory=list)
    recommended_tests: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    unchanged_affected: list[str] = field(default_factory=list)
    free_of_issues: bool = False

    def to_dict(self) -> dict:
        return {
            "plan_summary": self.plan_summary,
            "breakages": sorted(
                [b.to_dict() for b in self.breakages],
                key=lambda x: x["severity"],
            ),
            "conflicts": [c.to_dict() for c in self.conflicts],
            "recommended_tests": self.recommended_tests[:30],
            "affected_files": self.affected_files[:50],
            "unchanged_affected": self.unchanged_affected[:50],
            "free_of_issues": self.free_of_issues,
            "breakage_count": len(self.breakages),
            "conflict_count": len(self.conflicts),
        }


class ChangeSimulation:
    """Simulate the impact of a ChangePlan before any file is modified."""

    def __init__(
        self,
        indexer: RepositoryIndexer,
        dep_graph: DependencyGraph,
        arch_mapper: ArchitectureMapper,
        impact_analyzer: ImpactAnalyzer,
    ):
        self.indexer = indexer
        self.dep_graph = dep_graph
        self.arch_mapper = arch_mapper
        self.impact_analyzer = impact_analyzer

    def simulate(self, plan: ChangePlan) -> SimulationResult:
        breakages: list[PredictedBreakage] = []
        conflicts: list[ChangeConflict] = []
        recommended_tests: set[str] = set()
        affected_files: set[str] = set()
        changed_files = {fc.file for step in plan.steps for fc in step.file_changes}

        for step in plan.steps:
            for fc in step.file_changes:
                self._simulate_file_change(
                    fc, changed_files, breakages,
                    recommended_tests, affected_files,
                )

        conflicts = self._detect_conflicts(plan)
        unaffected = [f for f in sorted(affected_files) if f not in changed_files]

        return SimulationResult(
            plan_summary=plan.request,
            breakages=sorted(breakages, key=lambda b: (b.severity, b.file)),
            conflicts=conflicts,
            recommended_tests=sorted(recommended_tests),
            affected_files=sorted(affected_files),
            unchanged_affected=unaffected,
            free_of_issues=len(breakages) == 0 and len(conflicts) == 0,
        )

    def _simulate_file_change(
        self,
        fc: FileChange,
        changed_files: set[str],
        breakages: list[PredictedBreakage],
        recommended_tests: set[str],
        affected_files: set[str],
    ) -> None:
        normalized = fc.file.replace("\\", "/")
        affected_files.add(normalized)

        if fc.action == ChangeType.DELETE:
            node = self.dep_graph.get_node(normalized)
            if node and node.imported_by:
                for dep in node.imported_by:
                    if dep not in changed_files:
                        breakages.append(PredictedBreakage(
                            file=dep,
                            reason=f"{normalized} deleted — {dep} imports it",
                            severity="break" if node.fan_in > 1 else "warning",
                            confidence=0.9,
                        ))
                        affected_files.add(dep)
                breakages.append(PredictedBreakage(
                    file=normalized,
                    reason=f"Deleted — {len(node.imported_by)} dependents affected",
                    severity="break" if node.fan_in > 0 else "info",
                    confidence=0.95,
                ))

        elif fc.action == ChangeType.MODIFY:
            node = self.dep_graph.get_node(normalized)
            if node is None:
                breakages.append(PredictedBreakage(
                    file=normalized,
                    reason="Not in dependency graph — may be new or unindexed",
                    severity="warning",
                    confidence=0.3,
                ))
                return

            entry = self.indexer.get_entry(normalized)
            if entry and entry.exports and node.imported_by:
                for dep in node.imported_by:
                    ex = ", ".join(entry.exports[:3])
                    breakages.append(PredictedBreakage(
                        file=dep,
                        reason=f"Modifying {normalized} (exports {ex}) — may break {dep}",
                        severity="warning",
                        confidence=0.5,
                    ))
                    affected_files.add(dep)

            for t in self.dep_graph.reverse_dependencies(normalized, transitive=True):
                affected_files.add(t)

        elif fc.action == ChangeType.CREATE:
            node = self.dep_graph.get_node(normalized)
            if node is not None:
                breakages.append(PredictedBreakage(
                    file=normalized,
                    reason="File exists — create may overwrite",
                    severity="warning" if node.imported_by else "info",
                    confidence=0.7,
                ))

        elif fc.action == ChangeType.RENAME:
            node = self.dep_graph.get_node(normalized)
            if node and node.imported_by:
                for dep in node.imported_by:
                    breakages.append(PredictedBreakage(
                        file=dep,
                        reason=f"Renaming {normalized} breaks import in {dep}",
                        severity="break",
                        confidence=0.9,
                    ))
                    affected_files.add(dep)
                breakages.append(PredictedBreakage(
                    file=normalized,
                    reason=f"Renamed — {len(node.imported_by)} imports need updating",
                    severity="break" if node.fan_in > 1 else "warning",
                    confidence=0.9,
                ))

        result = self.impact_analyzer.analyze(normalized)
        for t in result.suggested_tests:
            recommended_tests.add(t)
        for af in result.direct_affected:
            affected_files.add(af)

    def _detect_conflicts(self, plan: ChangePlan) -> list[ChangeConflict]:
        file_to_steps: dict[str, list[int]] = defaultdict(list)
        for i, step in enumerate(plan.steps):
            for fc in step.file_changes:
                file_to_steps[fc.file].append(i)
                if fc.new_file:
                    file_to_steps[fc.new_file].append(i)

        conflicts: list[ChangeConflict] = []
        for file, step_indices in file_to_steps.items():
            if len(step_indices) > 1:
                for a in range(len(step_indices)):
                    for b in range(a + 1, len(step_indices)):
                        conflicts.append(ChangeConflict(
                            step_a_index=step_indices[a],
                            step_b_index=step_indices[b],
                            file=file,
                            reason=f"Both steps modify {file}",
                        ))
        return conflicts

    def predict_test_failures(self, plan: ChangePlan) -> list[dict]:
        result = self.simulate(plan)
        test_failures: list[dict] = []
        for test in result.recommended_tests:
            test_entry = self.indexer.get_entry(test)
            if test_entry:
                risk = "likely" if test in {b.file for b in result.breakages} else "possible"
                test_failures.append({
                    "test": test,
                    "function_count": len(test_entry.function_names),
                    "risk": risk,
                })
        return test_failures
