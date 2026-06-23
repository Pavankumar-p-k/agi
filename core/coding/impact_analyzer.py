"""ImpactAnalyzer — what breaks when a file changes, risk scoring, test selection.

Given a changed file, finds all directly and transitively affected files,
scores the risk of the change, and suggests which tests to run.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.coding.architecture_map import ArchitectureMapper
from core.coding.dependency_graph import DependencyGraph
from core.coding.repository_indexer import RepositoryIndexer

logger = logging.getLogger(__name__)


@dataclass
class ImpactResult:
    file: str
    direct_affected: list[str] = field(default_factory=list)
    transitive_affected: list[str] = field(default_factory=list)
    total_affected: int = 0
    risk_score: float = 0.0
    risk_label: str = "low"
    suggested_tests: list[str] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "direct_affected": self.direct_affected,
            "transitive_affected": self.transitive_affected,
            "total_affected": self.total_affected,
            "risk_score": round(self.risk_score, 3),
            "risk_label": self.risk_label,
            "suggested_tests": self.suggested_tests,
            "breaking_changes": self.breaking_changes,
        }


class ImpactAnalyzer:
    """Analyze the impact of file changes on the repository.

    Factors into risk score:
      - fan_in: how many direct dependents (weight 0.3)
      - transitive_impact: how many transitive dependents (weight 0.25)
      - layer_risk: risk weight of the file's architectural layer (weight 0.2)
      - centrality: graph centrality of the file (weight 0.15)
      - test_coverage: whether the file has associated tests (weight -0.1)
    """

    def __init__(
        self,
        indexer: RepositoryIndexer,
        dep_graph: DependencyGraph,
        arch_mapper: ArchitectureMapper | None = None,
    ):
        self.indexer = indexer
        self.dep_graph = dep_graph
        self.arch_mapper = arch_mapper or ArchitectureMapper(indexer, dep_graph)
        self._file_to_tests: dict[str, list[str]] = {}
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self.dep_graph.build()
        self.arch_mapper.map_layers()
        self._build_test_map()
        self._initialized = True

    def _build_test_map(self) -> None:
        """Build reverse map: source file → test files that import it."""
        test_map: dict[str, list[str]] = {}
        entries = self.indexer.get_all_entries()

        test_entries = [e for e in entries if self._is_test_file(e.path)]
        for test_entry in test_entries:
            for imp in test_entry.imports:
                resolved = self.dep_graph._resolve_import(
                    imp, test_entry.path,
                    {e.path for e in entries},
                    entries,
                )
                if resolved:
                    test_map.setdefault(resolved, []).append(test_entry.path)

        self._file_to_tests = test_map

    @staticmethod
    def _is_test_file(filepath: str) -> bool:
        parts = Path(filepath).parts
        name = Path(filepath).name
        if "test" in str(parts).lower() or name.startswith("test_") or name.endswith("_test.py"):
            return True
        if name.endswith(".test.js") or name.endswith(".test.ts") or name.endswith(".spec.js") or name.endswith(".spec.ts"):
            return True
        return False

    # ── Public API ───────────────────────────────────────────────

    def analyze(self, filepath: str) -> ImpactResult:
        """Analyze impact of changing a single file."""
        self._ensure_initialized()
        normalized = filepath.replace("\\", "/")

        entry = self.indexer.get_entry(normalized)
        if entry is None:
            return ImpactResult(
                file=normalized,
                risk_score=0.0,
                risk_label="unknown",
                total_affected=0,
                breaking_changes=["File not found in index"],
            )

        direct = self.dep_graph.get_node(normalized)
        direct_affected = list(direct.imported_by) if direct else []
        transitive = list(self.dep_graph.reverse_dependencies(normalized, transitive=True))
        transitive_affected = sorted(set(transitive) - set(direct_affected))

        total = len(direct_affected) + len(transitive_affected)

        risk = self._compute_risk(normalized, direct_affected + transitive_affected, total)
        label = self._risk_label(risk)

        tests = self._find_tests_for(normalized, direct_affected + transitive_affected)
        breaking = self._find_breaking_changes(normalized)

        return ImpactResult(
            file=normalized,
            direct_affected=sorted(direct_affected),
            transitive_affected=transitive_affected,
            total_affected=total,
            risk_score=risk,
            risk_label=label,
            suggested_tests=tests,
            breaking_changes=breaking,
        )

    def analyze_batch(self, filepaths: list[str]) -> list[ImpactResult]:
        """Analyze impact of changing multiple files."""
        return [self.analyze(f) for f in filepaths]

    def analyze_feature(self, files: list[str], feature_name: str = "") -> dict:
        """Analyze the combined impact of a feature change (multiple files)."""
        self._ensure_initialized()
        results = self.analyze_batch(files)
        all_affected: set[str] = set()
        suggested_tests: set[str] = set()
        breaking: list[str] = []
        for r in results:
            all_affected.update(r.direct_affected)
            all_affected.update(r.transitive_affected)
            suggested_tests.update(r.suggested_tests)
            breaking.extend(r.breaking_changes)

        avg_risk = sum(r.risk_score for r in results) / max(len(results), 1)
        return {
            "feature": feature_name,
            "files_changed": files,
            "files_affected": sorted(all_affected),
            "total_affected": len(all_affected),
            "average_risk": round(avg_risk, 3),
            "max_risk": max((r.risk_score for r in results), default=0),
            "risk_label": self._risk_label(avg_risk),
            "suggested_tests": sorted(suggested_tests),
            "breaking_changes": breaking,
            "individual_analyses": [r.to_dict() for r in results],
        }

    # ── Risk computation ─────────────────────────────────────────

    def _compute_risk(
        self, filepath: str, affected: list[str], total: int,
    ) -> float:
        if not self._initialized:
            return 0.0

        node = self.dep_graph.get_node(filepath)
        if node is None:
            return 0.0

        # Normalize factors to 0-1 range
        max_fan_in = max((n.fan_in for n in self.dep_graph._nodes.values()), default=1)
        fan_in_score = node.fan_in / max(max_fan_in, 1)

        total_files = max(len(self.dep_graph._nodes), 1)
        transitive_score = min(total / total_files, 1.0)

        centrality = node.centrality

        layer = ""
        if self.arch_mapper:
            arch = self.arch_mapper.map_layers()
            layer = arch.file_to_layer.get(filepath, "other")
        layer_risk = {
            "controllers": 0.6,
            "services": 0.7,
            "models": 0.8,
            "repositories": 0.6,
            "config": 0.9,
            "middleware": 0.5,
            "utils": 0.3,
            "tests": 0.1,
            "types": 0.4,
            "other": 0.5,
        }.get(layer, 0.5)

        # Does this file have tests?
        test_coverage_bonus = 0.0
        if filepath in self._file_to_tests and self._file_to_tests[filepath]:
            test_coverage_bonus = -0.1

        risk = (
            fan_in_score * 0.30
            + transitive_score * 0.25
            + centrality * 0.15
            + layer_risk * 0.20
            + test_coverage_bonus
        )

        return max(0.0, min(1.0, risk))

    @staticmethod
    def _risk_label(risk: float) -> str:
        if risk >= 0.8:
            return "critical"
        if risk >= 0.5:
            return "high"
        if risk >= 0.25:
            return "medium"
        return "low"

    # ── Test selection ───────────────────────────────────────────

    def _find_tests_for(self, filepath: str, affected: list[str]) -> list[str]:
        tests: set[str] = set()

        # Tests that directly test this file
        for f in [filepath] + affected:
            if f in self._file_to_tests:
                tests.update(self._file_to_tests[f])

        # Tests that ARE the affected files (test files themselves)
        for f in [filepath] + affected:
            if self._is_test_file(f):
                tests.add(f)

        return sorted(tests)

    # ── Breaking changes ─────────────────────────────────────────

    def _find_breaking_changes(self, filepath: str) -> list[str]:
        """Identify potential breaking changes based on exports."""
        breaking: list[str] = []
        entry = self.indexer.get_entry(filepath)
        if entry is None:
            return breaking

        node = self.dep_graph.get_node(filepath)
        if node is None:
            return breaking

        # Breaking: files that import classes/functions we export
        if entry.class_names:
            for dep in node.imported_by:
                dep_entry = self.indexer.get_entry(dep)
                if dep_entry:
                    for cls_name in entry.class_names:
                        for dep_imp in dep_entry.imports:
                            if cls_name in dep_imp:
                                breaking.append(
                                    f"{dep} imports {cls_name} from {Path(filepath).name}"
                                )
                                break

        return breaking
