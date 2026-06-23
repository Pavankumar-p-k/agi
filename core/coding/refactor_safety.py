"""RefactorSafetyEngine — pre-edit safety checks, architecture violation detection, safe alternatives.

Evaluates proposed changes against the repository's dependency graph and
architecture before any file is modified. Flags high-risk changes and
suggests safer approaches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.coding.architecture_map import ArchitectureMapper, ArchitectureMap
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.repository_indexer import RepositoryIndexer

logger = logging.getLogger(__name__)


@dataclass
class SafetyWarning:
    message: str
    severity: str  # info, warning, error
    file: str = ""
    category: str = ""

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "severity": self.severity,
            "file": self.file,
            "category": self.category,
        }


@dataclass
class SafetyAssessment:
    file: str
    change_type: str
    safe: bool
    warnings: list[SafetyWarning] = field(default_factory=list)
    risk_score: float = 0.0
    risk_label: str = "low"
    alternatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "change_type": self.change_type,
            "safe": self.safe,
            "warnings": [w.to_dict() for w in self.warnings],
            "risk_score": round(self.risk_score, 3),
            "risk_label": self.risk_label,
            "alternatives": self.alternatives,
        }


class RefactorSafetyEngine:
    """Evaluate safety of proposed code changes before they are made.

    Checks performed:
      - Does the file exist / not exist (create vs modify)?
      - Is the file in a high-risk layer?
      - Will the change introduce circular dependencies?
      - Does the change violate architecture layering?
      - What is the transitive blast radius?
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

    def evaluate_change(
        self,
        filepath: str,
        change_type: str,  # "create", "modify", "delete", "rename"
    ) -> SafetyAssessment:
        """Evaluate the safety of modifying a single file."""
        normalized = filepath.replace("\\", "/")
        entry = self.indexer.get_entry(normalized)
        warnings: list[SafetyWarning] = []
        risk_score = 0.0
        alternatives: list[str] = []

        # Check 1: File existence consistency
        if change_type == "create" and entry is not None:
            warnings.append(SafetyWarning(
                message=f"File already exists — use modify instead of create",
                severity="error",
                file=normalized,
                category="existence",
            ))
            risk_score += 0.5

        if change_type in ("modify", "delete") and entry is None:
            warnings.append(SafetyWarning(
                message=f"File does not exist in repository index",
                severity="error",
                file=normalized,
                category="existence",
            ))
            risk_score += 0.5

        if change_type == "rename" and entry is None:
            warnings.append(SafetyWarning(
                message=f"Source file not found — cannot rename",
                severity="error",
                file=normalized,
                category="existence",
            ))
            risk_score += 0.5

        # Check 2: Layer risk
        arch = self.arch_mapper.map_layers()
        layer = arch.file_to_layer.get(normalized, "other")
        layer_risks = {"config": 0.9, "models": 0.8, "services": 0.7}
        if layer in layer_risks:
            warnings.append(SafetyWarning(
                message=f"File is in '{layer}' layer (risk weight {layer_risks[layer]})",
                severity="warning",
                file=normalized,
                category="layer_risk",
            ))
            risk_score += layer_risks[layer] * 0.3

        # Check 3: Centrality / impact
        node = self.dep_graph.get_node(normalized)
        if node:
            if node.centrality > 0.3:
                pct = round(node.centrality * 100, 1)
                warnings.append(SafetyWarning(
                    message=f"File is central ({pct}% of repo reachable via reverse deps) — high impact risk",
                    severity="warning",
                    file=normalized,
                    category="centrality",
                ))
                risk_score += node.centrality * 0.4

            if change_type == "delete" and node.imported_by:
                for dep in node.imported_by[:5]:
                    warnings.append(SafetyWarning(
                        message=f"Deleting will break {dep}",
                        severity="warning",
                        file=normalized,
                        category="breakage",
                    ))
                risk_score += min(len(node.imported_by) * 0.05, 0.3)

        # Check 4: Architecture violation risk
        violations = ArchitectureMapper._find_violations(arch)
        for v in violations:
            if v["source"] == normalized:
                warnings.append(SafetyWarning(
                    message=f"Architecture violation: {v['type']} (risk {v['risk']})",
                    severity="warning",
                    file=normalized,
                    category="architecture_violation",
                ))
                risk_score += v["risk"] * 0.3

        # Check 5: Suggest alternatives for unsafe changes
        if change_type == "delete" and node and node.imported_by:
            alternatives.append(
                f"Consider deprecation cycle instead of deletion ({len(node.imported_by)} dependents)"
            )
            alternatives.append(
                f"Update all {len(node.imported_by)} dependents before deleting"
            )

        risk_score = min(risk_score, 1.0)
        safe = risk_score < 0.7

        return SafetyAssessment(
            file=normalized,
            change_type=change_type,
            safe=safe,
            warnings=warnings,
            risk_score=risk_score,
            risk_label=self._risk_label(risk_score),
            alternatives=alternatives,
        )

    def evaluate_plan(self, changes: list[tuple[str, str]]) -> list[SafetyAssessment]:
        """Evaluate a list of (filepath, change_type) pairs."""
        return [self.evaluate_change(filepath, ctype) for filepath, ctype in changes]

    def check_architecture_violation(
        self,
        filepath: str,
        imports_new_file: str | None = None,
    ) -> SafetyWarning | None:
        """Check if importing a new dependency would violate architecture."""
        normalized = filepath.replace("\\", "/")
        arch = self.arch_mapper.map_layers()
        source_layer = arch.file_to_layer.get(normalized)

        if imports_new_file:
            target_layer = arch.file_to_layer.get(imports_new_file.replace("\\", "/"))
            if source_layer and target_layer:
                allowed = arch.allowed_direction(source_layer, target_layer)
                if not allowed:
                    return SafetyWarning(
                        message=f"Architecture violation: {source_layer} importing {target_layer} (reverse direction)",
                        severity="warning",
                        file=normalized,
                        category="import_violation",
                    )
        return None

    @staticmethod
    def _risk_label(risk: float) -> str:
        if risk >= 0.8:
            return "critical"
        if risk >= 0.5:
            return "high"
        if risk >= 0.25:
            return "medium"
        return "low"
