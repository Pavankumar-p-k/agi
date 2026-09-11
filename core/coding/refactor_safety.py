"""Pre-edit risk assessment for refactoring operations."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.coding.architecture_map import ArchitectureMapper
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.repository_indexer import RepositoryIndexer


@dataclass
class SafetyWarning:
    message: str
    severity: str = "warning"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SafetyAssessment:
    file: str
    action: str
    safe: bool = True
    risk_label: str = "low"
    risk_score: float = 0.0
    warnings: list[SafetyWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["warnings"] = [warning.to_dict() for warning in self.warnings]
        return data


class RefactorSafetyEngine:
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

    def evaluate_change(self, file: str, action: str) -> SafetyAssessment:
        normalized = file.replace("\\", "/")
        action = action.lower()
        entry = self.indexer.get_entry(normalized)
        impact = self.impact_analyzer.analyze(normalized)
        warnings: list[SafetyWarning] = []
        safe = True
        risk = impact.risk_score
        if action == "create" and entry is not None:
            warnings.append(SafetyWarning(f"{normalized} already exists", "warning"))
            safe = False
            risk = max(risk, 0.4)
        if action in {"modify", "delete", "rename", "move"} and entry is None:
            warnings.append(SafetyWarning(f"{normalized} does not exist", "warning"))
            safe = False
            risk = max(risk, 0.3)
        if action in {"delete", "rename"} and impact.total_affected:
            warnings.append(SafetyWarning(f"{action} may break {impact.total_affected} dependent files", "error"))
            risk = max(risk, 0.65)
        if any(token in normalized for token in ("auth", "security", "database", "migration", "config", "settings")):
            warnings.append(SafetyWarning(f"{normalized} is a sensitive project file", "warning"))
            risk = max(risk, 0.55)
        label = impact.risk_label if risk <= impact.risk_score else ("high" if risk >= 0.55 else "medium")
        return SafetyAssessment(normalized, action, safe=safe, risk_label=label, risk_score=round(min(1.0, risk), 3), warnings=warnings)

    def evaluate_plan(self, changes: list[tuple[str, str]]) -> list[SafetyAssessment]:
        return [self.evaluate_change(file, action) for file, action in changes]
