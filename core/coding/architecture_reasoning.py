"""Architecture reasoning utilities for Coding AI."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.coding.change_planner import ChangePlanner, FileChange


@dataclass
class ArchitectureScore:
    coupling: float = 1.0
    cohesion: float = 1.0
    maintainability: float = 1.0
    stability: float = 1.0
    layer_discipline: float = 1.0

    def overall(self) -> float:
        return round((self.coupling + self.cohesion + self.maintainability + self.stability + self.layer_discipline) / 5, 3)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["overall"] = self.overall()
        return data


@dataclass
class DesignWeakness:
    category: str
    file: str
    severity: str
    message: str
    metric_value: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DesignReport:
    pattern: str
    score: ArchitectureScore
    weaknesses: list[DesignWeakness] = field(default_factory=list)
    migration_suggestions: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "score": self.score.to_dict(),
            "weaknesses": [weakness.to_dict() for weakness in self.weaknesses],
            "migration_suggestions": self.migration_suggestions,
            "summary": self.summary,
        }


class ArchitectureScorer:
    def __init__(self, indexer, dependency_graph, architecture):
        self.indexer = indexer
        self.dependency_graph = dependency_graph
        self.architecture = architecture

    def score(self) -> ArchitectureScore:
        if not self.dependency_graph.nodes:
            self.dependency_graph.build()
        arch = self.architecture.architecture or self.architecture.map_layers()
        files = max(1, len(self.dependency_graph.nodes))
        edges = sum(len(node.dependencies) for node in self.dependency_graph.nodes.values())
        coupling = max(0.0, 1.0 - min(1.0, edges / (files * 3)))
        cohesion = min(1.0, len(arch.layers) / 6) if arch.layers else 0.5
        layer_discipline = max(0.0, 1.0 - min(1.0, len(arch.cross_layer_edges) / max(1, edges)))
        stability = max(0.0, 1.0 - min(1.0, len(self.dependency_graph.high_impact_files(3)) / files))
        maintainability = round((coupling + cohesion + layer_discipline + stability) / 4, 3)
        return ArchitectureScore(round(coupling, 3), round(cohesion, 3), maintainability, round(stability, 3), round(layer_discipline, 3))


class DesignAnalyzer:
    def __init__(self, indexer, dependency_graph, architecture, scorer: ArchitectureScorer):
        self.indexer = indexer
        self.dependency_graph = dependency_graph
        self.architecture = architecture
        self.scorer = scorer

    def analyze(self) -> DesignReport:
        arch = self.architecture.architecture or self.architecture.map_layers()
        score = self.scorer.score()
        weaknesses: list[DesignWeakness] = []
        for entry in self.indexer.all_entries():
            if entry.line_count > 500:
                weaknesses.append(DesignWeakness("god_file", entry.path, "high", "Large file may need decomposition", entry.line_count))
        if score.layer_discipline < 0.5:
            weaknesses.append(DesignWeakness("layering", "", "medium", "Cross-layer dependencies are dense", score.layer_discipline))
        suggestions = ["Keep Coding AI changes dependency-aware", "Run targeted tests for impacted layers"]
        if arch.pattern != "layered":
            suggestions.append("Consider explicit module boundaries")
        return DesignReport(arch.pattern, score, weaknesses, suggestions, f"{arch.pattern} architecture with {len(arch.layers)} detected layers")


@dataclass
class TradeoffComparison:
    current: str
    alternatives: dict[str, float]
    recommended: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TradeoffEngine:
    PATTERN_PROFILES = {
        "layered": 0.82,
        "mvc": 0.72,
        "modular_monolith": 0.86,
        "monolith": 0.55,
        "microservices": 0.68,
    }

    def compare(self, current_pattern: str) -> TradeoffComparison:
        alternatives = dict(self.PATTERN_PROFILES)
        recommended = max(alternatives, key=alternatives.get)
        return TradeoffComparison(current_pattern, alternatives, recommended, f"{recommended} balances maintainability and operational complexity best for most local codebases")


class MigrationPlanner:
    def __init__(self, indexer, dependency_graph, architecture, impact_analyzer, planner: ChangePlanner):
        self.indexer = indexer
        self.dependency_graph = dependency_graph
        self.architecture = architecture
        self.impact_analyzer = impact_analyzer
        self.planner = planner

    def plan_migration(self, target_pattern: str):
        changes: list[FileChange] = []
        request = f"Migrate architecture toward {target_pattern}"
        return self.planner.plan(request, changes)
