"""Impact analysis for proposed coding changes."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.coding.architecture_map import ArchitectureMapper
from core.coding.dependency_graph import DependencyGraph
from core.coding.repository_indexer import RepositoryIndexer


@dataclass
class ImpactResult:
    file: str
    direct_affected: list[str] = field(default_factory=list)
    transitive_affected: list[str] = field(default_factory=list)
    suggested_tests: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    risk_label: str = "low"

    @property
    def total_affected(self) -> int:
        return len(set(self.direct_affected) | set(self.transitive_affected))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_affected"] = self.total_affected
        return data


class ImpactAnalyzer:
    def __init__(self, indexer: RepositoryIndexer, dependency_graph: DependencyGraph, architecture: ArchitectureMapper):
        self.indexer = indexer
        self.dependency_graph = dependency_graph
        self.architecture = architecture

    def _label(self, score: float) -> str:
        if score >= 0.8:
            return "critical"
        if score >= 0.55:
            return "high"
        if score >= 0.25:
            return "medium"
        return "low"

    def _suggest_tests(self, file: str, affected: set[str]) -> list[str]:
        candidates = []
        tokens = {part for path in affected | {file} for part in path.replace(".py", "").split("/") if part and part not in {"src", "core"}}
        for entry in self.indexer.all_entries():
            lower = entry.path.lower()
            if "test" not in lower:
                continue
            if any(token.lower() in lower for token in tokens):
                candidates.append(entry.path)
        return sorted(set(candidates))

    def analyze(self, file: str) -> ImpactResult:
        path = file.replace("\\", "/")
        entry = self.indexer.get_entry(path)
        if entry is None:
            return ImpactResult(file=path, risk_label="unknown")
        if not self.dependency_graph.nodes:
            self.dependency_graph.build()
        direct = set(self.dependency_graph.reverse_dependencies(path))
        transitive = self.dependency_graph.impact_set([path])
        node = self.dependency_graph.get_node(path)
        arch = self.architecture.architecture or self.architecture.map_layers()
        layer = arch.file_to_layer.get(path, "")
        base = min(1.0, (len(transitive) + (node.centrality if node else 0.0)) / max(3.0, len(self.dependency_graph.nodes) / 2))
        if any(part in path for part in ("config", "settings", "auth", "security", "database", "migration")):
            base = max(base, 0.55)
        if layer in {"models", "repositories"}:
            base = max(base, 0.35)
        score = round(min(1.0, base), 3)
        return ImpactResult(
            file=path,
            direct_affected=sorted(direct),
            transitive_affected=sorted(transitive),
            suggested_tests=self._suggest_tests(path, transitive),
            risk_score=score,
            risk_label=self._label(score),
        )

    def analyze_batch(self, files: list[str]) -> list[ImpactResult]:
        return [self.analyze(file) for file in files]

    def analyze_feature(self, files: list[str], feature_name: str = "") -> dict[str, Any]:
        results = self.analyze_batch(files)
        affected = set()
        tests = set()
        for result in results:
            affected.update(result.direct_affected)
            affected.update(result.transitive_affected)
            tests.update(result.suggested_tests)
        return {
            "feature": feature_name,
            "files_changed": files,
            "total_affected": len(affected),
            "affected_files": sorted(affected),
            "suggested_tests": sorted(tests),
            "risk_score": max((r.risk_score for r in results), default=0.0),
        }
