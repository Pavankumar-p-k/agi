"""ArchitectureReasoning — design analysis, pattern advisory, tradeoff comparison, migration planning.

Phase 8.4 adds design-level reasoning on top of the 8.1-8.3 pipeline:
  - ArchitectureScorer: quantify coupling, cohesion, maintainability
  - DesignAnalyzer: detect weaknesses (god files, unstable deps, hub modules)
  - PatternAdvisor: match/compare architectural patterns
  - TradeoffEngine: compare alternative architectures
  - MigrationPlanner: multi-step migration between patterns
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.coding.architecture_map import ArchitectureMapper
from core.coding.change_planner import ChangePlan, ChangePlanner, ChangeStep, ChangeType, FileChange
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.repository_indexer import FileEntry, RepositoryIndexer

logger = logging.getLogger(__name__)


# ── Scoring models ──────────────────────────────────────────────


@dataclass
class ArchitectureScore:
    """Quantitative assessment of architecture quality.

    All metrics are 0.0 (worst) to 1.0 (best) for consistency.
    """
    coupling: float = 0.0
    cohesion: float = 0.0
    maintainability: float = 0.0
    stability: float = 0.0
    layer_discipline: float = 0.0

    def to_dict(self) -> dict:
        return {
            "coupling": round(self.coupling, 3),
            "cohesion": round(self.cohesion, 3),
            "maintainability": round(self.maintainability, 3),
            "stability": round(self.stability, 3),
            "layer_discipline": round(self.layer_discipline, 3),
            "overall": round(self.overall(), 3),
        }

    def overall(self) -> float:
        return (self.coupling + self.cohesion + self.maintainability
                + self.stability + self.layer_discipline) / 5.0


@dataclass
class DesignWeakness:
    category: str
    file: str
    severity: str  # low, medium, high, critical
    message: str
    metric_value: float = 0.0

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "file": self.file,
            "severity": self.severity,
            "message": self.message,
            "metric_value": round(self.metric_value, 3),
        }


@dataclass
class DesignReport:
    score: ArchitectureScore = field(default_factory=ArchitectureScore)
    weaknesses: list[DesignWeakness] = field(default_factory=list)
    pattern: str = ""
    alternative_patterns: list[dict] = field(default_factory=list)
    migration_suggestions: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "score": self.score.to_dict(),
            "weaknesses": sorted(
                [w.to_dict() for w in self.weaknesses],
                key=lambda x: x["severity"],
                reverse=True,
            ),
            "pattern": self.pattern,
            "alternative_patterns": self.alternative_patterns,
            "migration_suggestions": self.migration_suggestions,
            "summary": self.summary,
            "weakness_count": len(self.weaknesses),
        }


# ── ArchitectureScorer ──────────────────────────────────────────


class ArchitectureScorer:
    """Quantify architecture quality using coupling, cohesion, stability, and layer metrics."""

    def __init__(
        self,
        indexer: RepositoryIndexer,
        dep_graph: DependencyGraph,
        arch_mapper: ArchitectureMapper,
    ):
        self.indexer = indexer
        self.dep_graph = dep_graph
        self.arch_mapper = arch_mapper

    def score(self) -> ArchitectureScore:
        """Compute full architecture score."""
        nodes = self.dep_graph.build()
        arch = self.arch_mapper.map_layers()
        if not nodes:
            return ArchitectureScore()

        coupling = self._score_coupling(nodes)
        cohesion = self._score_cohesion(nodes)
        stability = self._score_stability(nodes)
        layer_disc = self._score_layer_discipline(arch)
        maintainability = (coupling + cohesion + stability + layer_disc) / 4.0

        return ArchitectureScore(
            coupling=coupling,
            cohesion=cohesion,
            maintainability=maintainability,
            stability=stability,
            layer_discipline=layer_disc,
        )

    @staticmethod
    def _score_coupling(nodes: dict) -> float:
        """Coupling: lower average fan-out is better."""
        if not nodes:
            return 0.0
        fan_outs = [len(n.imports) for n in nodes.values()]
        avg = sum(fan_outs) / len(fan_outs)
        max_reasonable = max(len(nodes) * 0.2, 1)
        return max(0.0, 1.0 - (avg / max_reasonable))

    @staticmethod
    def _score_cohesion(nodes: dict) -> float:
        """Cohesion: files with both class and function exports suggest focus."""
        # Simplification: files with 0 exports have no cohesion signal (neutral)
        # Files with 1-5 exports in a single category = good cohesion
        # Files with 6+ exports across categories = lower cohesion
        scored = 0
        total = 0
        for node in nodes.values():
            total += 1
            # We approximate cohesion from the source itself via tokens
            # This is a placeholder for a deeper metric
            if len(node.imported_by) + len(node.imports) <= 5:
                scored += 1
        return scored / max(total, 1)

    @staticmethod
    def _score_stability(nodes: dict) -> float:
        """Stability: files with many dependents should depend on little (stable abstraction)."""
        if not nodes:
            return 0.0
        scores: list[float] = []
        for node in nodes.values():
            fan_in = node.fan_in
            fan_out = node.fan_out
            total = fan_in + fan_out
            if total == 0:
                scores.append(0.5)
            else:
                instability = fan_out / total
                scores.append(1.0 - instability)
        return sum(scores) / len(scores)

    @staticmethod
    def _score_layer_discipline(arch) -> float:
        """Layer discipline: few violations = high score."""
        if not arch.cross_layer_edges:
            return 1.0
        total_edges = len(arch.cross_layer_edges)
        violations = len(ArchitectureMapper._find_violations(arch))
        if total_edges == 0:
            return 1.0
        return max(0.0, 1.0 - (violations / total_edges))


# ── DesignAnalyzer ──────────────────────────────────────────────


class DesignAnalyzer:
    """Detect architectural weaknesses: god files, hub modules, fragile dependencies."""

    def __init__(
        self,
        indexer: RepositoryIndexer,
        dep_graph: DependencyGraph,
        arch_mapper: ArchitectureMapper,
        scorer: ArchitectureScorer,
    ):
        self.indexer = indexer
        self.dep_graph = dep_graph
        self.arch_mapper = arch_mapper
        self.scorer = scorer

    def analyze(self) -> DesignReport:
        """Run full design analysis and return a report."""
        nodes = self.dep_graph.build()
        arch = self.arch_mapper.map_layers()
        score = self.scorer.score()
        weaknesses: list[DesignWeakness] = []

        weaknesses.extend(self._find_god_files(nodes))
        weaknesses.extend(self._find_hub_modules(nodes))
        weaknesses.extend(self._find_fragile_files(nodes))
        weaknesses.extend(self._find_circular_weaknesses())
        weaknesses.extend(self._find_layer_violations(arch))

        pattern = arch.pattern
        alternatives = self._suggest_patterns(arch, score)
        migrations = self._suggest_migrations(arch, weaknesses)

        summary = self._generate_summary(score, weaknesses, pattern)

        return DesignReport(
            score=score,
            weaknesses=weaknesses,
            pattern=pattern,
            alternative_patterns=alternatives,
            migration_suggestions=migrations,
            summary=summary,
        )

    # ── Weakness detectors ──────────────────────────────────────

    def _find_god_files(self, nodes: dict) -> list[DesignWeakness]:
        """Find files with high export counts AND high fan-in."""
        weaknesses: list[DesignWeakness] = []
        for node in nodes.values():
            entry = self.indexer.get_entry(node.file)
            if entry is None:
                continue
            export_count = len(entry.exports)
            if export_count >= 5 and node.fan_in >= 5:
                weaknesses.append(DesignWeakness(
                    category="god_file",
                    file=node.file,
                    severity="critical" if (export_count >= 10 and node.fan_in >= 10) else "high",
                    message=f"God file: {export_count} exports, {node.fan_in} dependents",
                    metric_value=export_count + node.fan_in,
                ))
            elif export_count >= 3 and node.fan_in >= 3:
                weaknesses.append(DesignWeakness(
                    category="god_file",
                    file=node.file,
                    severity="medium",
                    message=f"Growing file: {export_count} exports, {node.fan_in} dependents",
                    metric_value=export_count + node.fan_in,
                ))
        return weaknesses

    def _find_hub_modules(self, nodes: dict) -> list[DesignWeakness]:
        """Find modules with very high fan-in (central hubs)."""
        weaknesses: list[DesignWeakness] = []
        if not nodes:
            return weaknesses
        max_fan_in = max((n.fan_in for n in nodes.values()), default=0)
        if max_fan_in == 0:
            return weaknesses
        threshold = max(max_fan_in * 0.7, 3)
        for node in nodes.values():
            if node.fan_in >= threshold and node.fan_in >= 3:
                weaknesses.append(DesignWeakness(
                    category="hub_module",
                    file=node.file,
                    severity="high" if node.fan_in >= 10 else "medium",
                    message=f"Hub module: {node.fan_in} dependents, centrality {node.centrality:.2f}",
                    metric_value=node.fan_in,
                ))
        return weaknesses

    def _find_fragile_files(self, nodes: dict) -> list[DesignWeakness]:
        """Find files with high fan-out (fragile — break if deps change)."""
        weaknesses: list[DesignWeakness] = []
        for node in nodes.values():
            if node.fan_out >= 10:
                weaknesses.append(DesignWeakness(
                    category="fragile_dependency",
                    file=node.file,
                    severity="high",
                    message=f"Fragile: depends on {node.fan_out} other files",
                    metric_value=node.fan_out,
                ))
            elif node.fan_out >= 5:
                weaknesses.append(DesignWeakness(
                    category="fragile_dependency",
                    file=node.file,
                    severity="medium",
                    message=f"Moderate coupling: depends on {node.fan_out} other files",
                    metric_value=node.fan_out,
                ))
        return weaknesses

    def _find_circular_weaknesses(self) -> list[DesignWeakness]:
        """Report circular dependencies as weaknesses."""
        cycles = self.dep_graph.find_circular_dependencies()
        weaknesses: list[DesignWeakness] = []
        for cycle in cycles:
            file_label = cycle[0] if cycle else "unknown"
            weaknesses.append(DesignWeakness(
                category="circular_dependency",
                file=file_label,
                severity="high",
                message=f"Circular dependency: {' → '.join(cycle[:4])}{'...' if len(cycle) > 4 else ''}",
                metric_value=len(cycle),
            ))
        return weaknesses

    @staticmethod
    def _find_layer_violations(arch) -> list[DesignWeakness]:
        """Report architecture layer violations."""
        violations = ArchitectureMapper._find_violations(arch)
        weaknesses: list[DesignWeakness] = []
        for v in violations:
            weaknesses.append(DesignWeakness(
                category="layer_violation",
                file=v["source"],
                severity="medium" if v["risk"] < 0.5 else "high",
                message=f"Layer violation: {v['type']}",
                metric_value=v["risk"],
            ))
        return weaknesses

    # ── Pattern advisory ─────────────────────────────────────────

    def _suggest_patterns(self, arch, score: ArchitectureScore) -> list[dict]:
        """Suggest alternative architectural patterns."""
        suggestions: list[dict] = []
        current = arch.pattern

        if current == "layered":
            if score.coupling < 0.4:
                suggestions.append({
                    "pattern": "hexagonal",
                    "rationale": "High coupling suggests ports/adapters could help isolate core logic",
                    "difficulty": "high",
                })
            suggestions.append({
                "pattern": "modular_monolith",
                "rationale": "If layer boundaries are clear, formalizing modules improves discipline",
                "difficulty": "medium",
            })

        elif current == "mvc":
            suggestions.append({
                "pattern": "layered",
                "rationale": "Adding service and repository layers separates business logic from controllers",
                "difficulty": "medium",
            })
            suggestions.append({
                "pattern": "mvvm",
                "rationale": "Better separation of view state from controller logic",
                "difficulty": "low",
            })

        elif current == "microservices":
            suggestions.append({
                "pattern": "modular_monolith",
                "rationale": "If services are tightly coupled, a monolith reduces deployment complexity",
                "difficulty": "high",
            })

        elif current == "monolith":
            suggestions.append({
                "pattern": "layered",
                "rationale": "Adding layers improves separation of concerns",
                "difficulty": "low",
            })

        if not suggestions:
            suggestions.append({
                "pattern": current,
                "rationale": "Current pattern is reasonable for the observed architecture",
                "difficulty": "none",
            })

        return suggestions

    def _suggest_migrations(self, arch, weaknesses: list[DesignWeakness]) -> list[str]:
        """Generate migration suggestions based on weaknesses."""
        suggestions: list[str] = []
        god_files = [w for w in weaknesses if w.category == "god_file"]
        hubs = [w for w in weaknesses if w.category == "hub_module"]
        circular = [w for w in weaknesses if w.category == "circular_dependency"]
        violations = [w for w in weaknesses if w.category == "layer_violation"]
        fragile = [w for w in weaknesses if w.category == "fragile_dependency"]

        if god_files:
            suggestions.append(
                f"Extract {len(god_files)} god file(s) into focused modules"
            )
        if hubs:
            suggestions.append(
                f"Introduce interface abstractions for {len(hubs)} hub module(s) to reduce coupling"
            )
        if circular:
            suggestions.append(
                f"Resolve {len(circular)} circular dependency chain(s) by extracting shared interfaces"
            )
        if violations:
            suggestions.append(
                f"Fix {len(violations)} layer violation(s) by redirecting dependencies through service layer"
            )
        if fragile:
            suggestions.append(
                f"Reduce coupling in {len(fragile)} fragile file(s) with dependency injection"
            )

        if not suggestions:
            suggestions.append("Architecture is healthy — no migrations needed")

        return suggestions

    def _generate_summary(
        self, score: ArchitectureScore,
        weaknesses: list[DesignWeakness],
        pattern: str,
    ) -> str:
        parts = [
            f"Pattern: {pattern}",
            f"Overall score: {score.overall():.2f}/1.0",
        ]
        if weaknesses:
            by_severity = defaultdict(list)
            for w in weaknesses:
                by_severity[w.severity].append(w)
            if by_severity.get("critical"):
                parts.append(f"Critical: {len(by_severity['critical'])} issue(s)")
            if by_severity.get("high"):
                parts.append(f"High: {len(by_severity['high'])} issue(s)")
            if by_severity.get("medium"):
                parts.append(f"Medium: {len(by_severity['medium'])} issue(s)")
        else:
            parts.append("No significant weaknesses detected")
        return ". ".join(parts)


# ── TradeoffEngine ──────────────────────────────────────────────


@dataclass
class TradeoffComparison:
    """Comparison of two or more architecture alternatives."""

    alternatives: list[dict] = field(default_factory=list)
    recommended: str = ""
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "alternatives": self.alternatives,
            "recommended": self.recommended,
            "rationale": self.rationale,
        }


class TradeoffEngine:
    """Compare architectural alternatives using scoring dimensions."""

    PATTERN_PROFILES: dict[str, dict[str, float]] = {
        "layered": {
            "coupling": 0.7, "cohesion": 0.7, "maintainability": 0.7,
            "stability": 0.6, "scalability": 0.5, "complexity": 0.6,
        },
        "mvc": {
            "coupling": 0.5, "cohesion": 0.6, "maintainability": 0.5,
            "stability": 0.5, "scalability": 0.4, "complexity": 0.7,
        },
        "hexagonal": {
            "coupling": 0.8, "cohesion": 0.8, "maintainability": 0.8,
            "stability": 0.7, "scalability": 0.6, "complexity": 0.4,
        },
        "microservices": {
            "coupling": 0.9, "cohesion": 0.9, "maintainability": 0.7,
            "stability": 0.5, "scalability": 0.9, "complexity": 0.2,
        },
        "modular_monolith": {
            "coupling": 0.7, "cohesion": 0.8, "maintainability": 0.8,
            "stability": 0.7, "scalability": 0.5, "complexity": 0.6,
        },
        "monolith": {
            "coupling": 0.3, "cohesion": 0.4, "maintainability": 0.3,
            "stability": 0.4, "scalability": 0.2, "complexity": 0.8,
        },
    }

    DIMENSION_WEIGHTS: dict[str, float] = {
        "maintainability": 0.25,
        "coupling": 0.20,
        "cohesion": 0.20,
        "complexity": 0.15,
        "stability": 0.10,
        "scalability": 0.10,
    }

    def compare(
        self,
        current_pattern: str,
        alternatives: list[str] | None = None,
    ) -> TradeoffComparison:
        """Compare the current pattern against alternatives."""
        if alternatives is None:
            alternatives = [p for p in self.PATTERN_PROFILES if p != current_pattern]

        current_profile = self.PATTERN_PROFILES.get(current_pattern, {})
        scored: list[dict] = []

        for alt_name in alternatives:
            alt_profile = self.PATTERN_PROFILES.get(alt_name)
            if alt_profile is None:
                continue

            dimensions: dict[str, float] = {}
            total_weighted = 0.0
            for dim, weight in self.DIMENSION_WEIGHTS.items():
                alt_score = alt_profile.get(dim, 0.5)
                dimensions[dim] = alt_score
                total_weighted += alt_score * weight

            migration_risk = self._estimate_migration_risk(current_pattern, alt_name)

            scored.append({
                "pattern": alt_name,
                "score": round(total_weighted, 3),
                "dimensions": dimensions,
                "migration_risk": migration_risk,
                "advantage_over_current": round(
                    total_weighted - sum(
                        current_profile.get(d, 0.5) * w
                        for d, w in self.DIMENSION_WEIGHTS.items()
                    ), 3,
                ),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        best = scored[0] if scored else {}
        current_score = sum(
            current_profile.get(d, 0.5) * w
            for d, w in self.DIMENSION_WEIGHTS.items()
        )

        # Sanity: only recommend if it's meaningfully better
        recommended = best.get("pattern", current_pattern) if best.get("advantage_over_current", 0) > 0.05 else current_pattern
        rationale = self._rationalize(recommended, current_pattern, best)

        return TradeoffComparison(
            alternatives=scored,
            recommended=recommended,
            rationale=rationale,
        )

    @staticmethod
    def _estimate_migration_risk(source: str, target: str) -> str:
        high = {"hexagonal", "microservices"}
        if target in high:
            return "high"
        if source == "monolith" and target not in ("layered", "mvc"):
            return "high"
        if target == "modular_monolith":
            return "medium"
        return "low"

    @staticmethod
    def _rationalize(recommended: str, current: str, best: dict) -> str:
        if recommended == current:
            return f"Staying with {current} is reasonable — alternatives offer marginal improvement"
        adv = best.get("advantage_over_current", 0)
        return (
            f"{recommended} scores {adv:.2f} higher than {current} on weighted dimensions. "
            f"Primary advantages: {recommended} separates concerns more cleanly."
        )


# ── MigrationPlanner ────────────────────────────────────────────


class MigrationPlanner:
    """Generate multi-step migration plans between architecture patterns."""

    def __init__(
        self,
        indexer: RepositoryIndexer,
        dep_graph: DependencyGraph,
        arch_mapper: ArchitectureMapper,
        impact_analyzer: ImpactAnalyzer,
        planner: ChangePlanner,
    ):
        self.indexer = indexer
        self.dep_graph = dep_graph
        self.arch_mapper = arch_mapper
        self.impact_analyzer = impact_analyzer
        self.planner = planner

    def plan_migration(
        self,
        target_pattern: str,
    ) -> ChangePlan:
        """Generate a change plan for migrating toward a target pattern."""
        arch = self.arch_mapper.map_layers()
        current = arch.pattern
        changes: list[FileChange] = []
        steps: list[ChangeStep] = []

        if current == "mvc" and target_pattern in ("layered", "modular_monolith"):
            steps.extend(self._mvc_to_layered(arch))

        elif current == "layered" and target_pattern == "modular_monolith":
            steps.extend(self._layered_to_modular(arch))

        elif current == "monolith" and target_pattern in ("layered", "mvc"):
            steps.extend(self._monolith_to_layered(arch))

        return self.planner.plan(
            f"Migrate from {current} to {target_pattern}",
            changes,
        )

    @staticmethod
    def _mvc_to_layered(arch) -> list[ChangeStep]:
        steps: list[ChangeStep] = []
        steps.append(StepSuggestion(
            "Create service layer", "Extract business logic from controllers into services/",
            0.3, "medium",
        ))
        steps.append(StepSuggestion(
            "Create repository layer", "Extract data access from models into repositories/",
            0.4, "medium",
        ))
        steps.append(StepSuggestion(
            "Add dependency injection", "Wire layers together through interfaces",
            0.2, "high",
        ))
        return steps

    @staticmethod
    def _layered_to_modular(arch) -> list[ChangeStep]:
        steps: list[ChangeStep] = []
        steps.append(StepSuggestion(
            "Identify bounded contexts", "Group related services/models into modules",
            0.5, "high",
        ))
        steps.append(StepSuggestion(
            "Enforce module boundaries", "Prevent cross-module direct dependencies",
            0.4, "high",
        ))
        return steps

    @staticmethod
    def _monolith_to_layered(arch) -> list[ChangeStep]:
        steps: list[ChangeStep] = []
        steps.append(StepSuggestion(
            "Separate business logic", "Extract models/domain logic from controllers",
            0.3, "medium",
        ))
        steps.append(StepSuggestion(
            "Add data access layer", "Extract queries into repositories",
            0.4, "medium",
        ))
        return steps


@dataclass
class StepSuggestion:
    title: str
    description: str
    risk_score: float
    risk_label: str
