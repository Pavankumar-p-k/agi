"""ChangePlanner — structured change plan generation with risk assessment and execution ordering.

Builds on Phase 8.1 components (ImpactAnalyzer, DependencyGraph, ArchitectureMapper)
to produce validated, ordered change plans from a set of file modifications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from core.coding.architecture_map import ArchitectureMapper
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.repository_indexer import RepositoryIndexer

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"


@dataclass
class FileChange:
    action: ChangeType
    file: str
    description: str = ""
    new_file: str = ""

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "action": self.action.value,
            "file": self.file,
            "description": self.description,
        }
        if self.new_file:
            d["new_file"] = self.new_file
        return d


@dataclass
class ChangeStep:
    description: str
    file_changes: list[FileChange] = field(default_factory=list)
    risk_score: float = 0.0
    risk_label: str = "low"
    suggested_tests: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "file_changes": [fc.to_dict() for fc in self.file_changes],
            "risk_score": round(self.risk_score, 3),
            "risk_label": self.risk_label,
            "suggested_tests": self.suggested_tests,
            "affected_files": self.affected_files,
        }


@dataclass
class ChangePlan:
    request: str
    steps: list[ChangeStep] = field(default_factory=list)
    overall_risk: float = 0.0
    risk_label: str = "low"
    total_affected_files: list[str] = field(default_factory=list)
    all_suggested_tests: list[str] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)
    execution_groups: list[list[int]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "request": self.request,
            "step_count": len(self.steps),
            "overall_risk": round(self.overall_risk, 3),
            "risk_label": self.risk_label,
            "total_affected_files": len(self.total_affected_files),
            "affected_files": sorted(self.total_affected_files)[:50],
            "suggested_tests": self.all_suggested_tests[:30],
            "breaking_changes": self.breaking_changes,
            "execution_groups": self.execution_groups,
            "warnings": self.warnings,
            "steps": [s.to_dict() for s in self.steps],
        }


class ChangePlanner:
    """Plan and validate code changes from file-level decisions.

    Takes a user request and a set of file changes (from the agent),
    validates them against the repository index and dependency graph,
    computes risk, orders execution, and selects relevant tests.
    """

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
        self._initialized = False

    def _ensure(self) -> None:
        if self._initialized:
            return
        self.dep_graph.build()
        self.arch_mapper.map_layers()
        self._initialized = True

    def plan(
        self,
        request: str,
        file_changes: list[FileChange],
    ) -> ChangePlan:
        """Produce a validated ChangePlan from a list of file changes."""
        self._ensure()
        all_files = [fc.file for fc in file_changes]
        all_affected: set[str] = set(all_files)

        # Compute individual risks per file
        risk_scores: dict[str, float] = {}
        for fc in file_changes:
            result = self.impact_analyzer.analyze(fc.file)
            risk_scores[fc.file] = result.risk_score
            all_affected.update(result.direct_affected)
            all_affected.update(result.transitive_affected)

        # Group into ordered execution steps
        steps = self._build_steps(file_changes, risk_scores)

        # Compute overall risk
        if steps:
            overall = sum(s.risk_score for s in steps) / len(steps)
        else:
            overall = 0.0
        label = self._risk_label(overall)

        # Collect all tests
        all_tests: set[str] = set()
        for fc in file_changes:
            result = self.impact_analyzer.analyze(fc.file)
            all_tests.update(result.suggested_tests)

        # Collect breaking changes
        breaking: list[str] = []
        for fc in file_changes:
            if fc.action == ChangeType.DELETE:
                node = self.dep_graph.get_node(fc.file)
                if node and node.imported_by:
                    for dep in node.imported_by:
                        breaking.append(f"Deleting {fc.file} breaks {dep}")
            elif fc.action == ChangeType.MODIFY:
                result = self.impact_analyzer.analyze(fc.file)
                breaking.extend(result.breaking_changes)

        # Execution groups (parallelizable steps)
        groups = self._build_execution_groups(steps)

        # Warnings
        warnings = self._build_warnings(file_changes)

        return ChangePlan(
            request=request,
            steps=steps,
            overall_risk=overall,
            risk_label=label,
            total_affected_files=sorted(all_affected),
            all_suggested_tests=sorted(all_tests),
            breaking_changes=breaking,
            execution_groups=groups,
            warnings=warnings,
        )

    # ── Step building ────────────────────────────────────────────

    def _build_steps(
        self,
        file_changes: list[FileChange],
        risk_scores: dict[str, float],
    ) -> list[ChangeStep]:
        """Group file changes into ordered execution steps."""
        if not file_changes:
            return []

        # Phase 1: CREATE new files (no dependencies, safe)
        # Phase 2: MODIFY files that nothing depends on
        # Phase 3: MODIFY files with dependents
        # Phase 4: DELETE files
        # Phase 5: RENAME files

        phases: dict[str, list[FileChange]] = {
            "scaffold": [],
            "low_impact_modify": [],
            "high_impact_modify": [],
            "delete": [],
            "rename": [],
        }

        for fc in file_changes:
            if fc.action == ChangeType.CREATE:
                phases["scaffold"].append(fc)
            elif fc.action == ChangeType.MODIFY:
                node = self.dep_graph.get_node(fc.file)
                if node and node.fan_in > 2:
                    phases["high_impact_modify"].append(fc)
                else:
                    phases["low_impact_modify"].append(fc)
            elif fc.action == ChangeType.DELETE:
                phases["delete"].append(fc)
            elif fc.action == ChangeType.RENAME:
                phases["rename"].append(fc)

        steps: list[ChangeStep] = []
        phase_order = ["scaffold", "low_impact_modify", "high_impact_modify", "delete", "rename"]

        for phase_name in phase_order:
            changes = phases[phase_name]
            if not changes:
                continue

            labels = {
                "scaffold": "Create new files (scaffold)",
                "low_impact_modify": "Modify low-impact files",
                "high_impact_modify": "Modify high-impact files",
                "delete": "Delete files",
                "rename": "Rename files",
            }
            all_affected: set[str] = set()
            all_tests: set[str] = set()
            phase_risks: list[float] = []
            for fc in changes:
                all_affected.update([fc.file])
                if fc.new_file:
                    all_affected.add(fc.new_file)
                result = self.impact_analyzer.analyze(fc.file)
                all_affected.update(result.direct_affected)
                all_affected.update(result.transitive_affected)
                all_tests.update(result.suggested_tests)
                phase_risks.append(result.risk_score)

            avg_risk = sum(phase_risks) / max(len(phase_risks), 1)

            step = ChangeStep(
                description=labels.get(phase_name, phase_name),
                file_changes=list(changes),
                risk_score=avg_risk,
                risk_label=self._risk_label(avg_risk),
                suggested_tests=sorted(all_tests),
                affected_files=sorted(all_affected),
            )
            steps.append(step)

        return steps

    def _build_execution_groups(self, steps: list[ChangeStep]) -> list[list[int]]:
        """Build parallelizable execution groups from steps."""
        groups: list[list[int]] = []
        for i, step in enumerate(steps):
            groups.append([i])
        return groups

    def _build_warnings(self, file_changes: list[FileChange]) -> list[str]:
        warnings: list[str] = []
        for fc in file_changes:
            if fc.action in (ChangeType.MODIFY, ChangeType.DELETE):
                entry = self.indexer.get_entry(fc.file)
                if entry is None:
                    warnings.append(f"{fc.file} not found in repository index")
                    continue
                node = self.dep_graph.get_node(fc.file)
                if node and node.centrality > 0.5:
                    warnings.append(
                        f"{fc.file} has high centrality ({node.centrality:.2f}) — changes may have widespread impact"
                    )
                arch = self.arch_mapper.map_layers()
                layer = arch.file_to_layer.get(fc.file, "other")
                layer_risks = {"config": 0.9, "models": 0.8, "services": 0.7}
                if layer in layer_risks and layer_risks[layer] >= 0.7:
                    warnings.append(
                        f"{fc.file} is in '{layer}' layer (risk weight {layer_risks[layer]}) — changes may be high impact"
                    )
        return warnings

    @staticmethod
    def _risk_label(risk: float) -> str:
        if risk >= 0.8:
            return "critical"
        if risk >= 0.5:
            return "high"
        if risk >= 0.25:
            return "medium"
        return "low"
