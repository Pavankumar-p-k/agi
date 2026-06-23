"""ArchitectureMapper — layer detection, pattern recognition, module boundaries.

Given a RepositoryIndexer and DependencyGraph, maps every file to an architectural layer,
detects the overall pattern (MVC, layered, hexagonal, etc.), and identifies
cross-layer dependencies that may indicate architecture violations.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.coding.dependency_graph import DependencyGraph
from core.coding.repository_indexer import RepositoryIndexer

logger = logging.getLogger(__name__)


# Layer definitions — heuristic patterns for directory + naming conventions
_LAYER_PATTERNS: list[tuple[str, list[str], list[str]]] = [
    ("controllers", ["controller", "controllers", "routes", "views"], []),
    ("services", ["service", "services", "usecase", "use_cases", "logic"], []),
    ("models", ["model", "models", "entity", "entities", "domain"], []),
    ("repositories", ["repository", "repositories", "dao", "dal", "data_access"], []),
    ("config", ["config", "configuration", "settings"], []),
    ("middleware", ["middleware", "middlewares"], []),
    ("utils", ["utils", "util", "helpers", "helper", "common", "shared",
               "support", "infra", "infrastructure"], []),
    ("tests", ["tests", "test", "__tests__"], []),
    ("types", ["types", "interfaces", "contracts", "typedefs"], []),
]


def _classify_file_layer(filepath: str) -> str:
    """Assign a file to an architectural layer based on path conventions."""
    parts = Path(filepath).parts
    for layer, dir_patterns, _ in _LAYER_PATTERNS:
        for part in parts:
            part_lower = part.lower()
            for pattern in dir_patterns:
                if pattern == part_lower or part_lower.endswith(pattern) or part_lower.startswith(pattern):
                    return layer
    return "other"


_LAYER_RISK: dict[str, float] = {
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
}


@dataclass
class LayerInfo:
    name: str
    files: list[str] = field(default_factory=list)
    description: str = ""
    risk_weight: float = 0.5

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "files": sorted(self.files),
            "file_count": len(self.files),
            "description": self.description,
            "risk_weight": self.risk_weight,
        }


@dataclass
class CrossLayerEdge:
    source_file: str
    target_file: str
    source_layer: str
    target_layer: str

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "target_file": self.target_file,
            "source_layer": self.source_layer,
            "target_layer": self.target_layer,
        }


class ArchitectureMapper:
    """Map repository files to architectural layers and detect patterns."""

    def __init__(self, indexer: RepositoryIndexer, dep_graph: DependencyGraph):
        self.indexer = indexer
        self.dep_graph = dep_graph
        self._arch: ArchitectureMap | None = None

    def map_layers(self) -> ArchitectureMap:
        """Assign every file to a layer and build cross-layer edges."""
        entries = self.indexer.get_all_entries()
        dep_graph = self.dep_graph.build()

        layers: dict[str, LayerInfo] = {}
        file_to_layer: dict[str, str] = {}

        for entry in entries:
            layer_name = _classify_file_layer(entry.path)
            file_to_layer[entry.path] = layer_name
            if layer_name not in layers:
                lr = _LAYER_RISK.get(layer_name, 0.5)
                layers[layer_name] = LayerInfo(
                    name=layer_name,
                    description=_layer_description(layer_name),
                    risk_weight=lr,
                )
            layers[layer_name].files.append(entry.path)

        # Detect cross-layer dependency edges
        cross_edges: list[CrossLayerEdge] = []
        for node in dep_graph.values():
            src_layer = file_to_layer.get(node.file, "other")
            for dep in node.imports:
                tgt_layer = file_to_layer.get(dep, "unknown")
                if tgt_layer != "unknown" and src_layer != tgt_layer:
                    cross_edges.append(CrossLayerEdge(
                        source_file=node.file,
                        target_file=dep,
                        source_layer=src_layer,
                        target_layer=tgt_layer,
                    ))

        # Detect architectural pattern
        pattern = self._detect_pattern(layers, cross_edges)

        # Map modules (top-level directories)
        modules: dict[str, list[str]] = defaultdict(list)
        for entry in entries:
            parts = Path(entry.path).parts
            if len(parts) > 1:
                modules[parts[0]].append(entry.path)
            else:
                modules["root"].append(entry.path)

        self._arch = ArchitectureMap(
            layers=layers,
            pattern=pattern,
            entry_points=self.dep_graph.indexer.ws.get_project_map().entry_points,
            modules=dict(modules),
            file_to_layer=file_to_layer,
            cross_layer_edges=cross_edges,
        )
        return self._arch

    def _detect_pattern(
        self,
        layers: dict[str, LayerInfo],
        cross_edges: list[CrossLayerEdge],
    ) -> str:
        """Detect architectural pattern from layer composition."""
        layer_names = set(layers.keys())

        # Layered: controllers → services → repositories → models
        if "controllers" in layer_names and "services" in layer_names and "repositories" in layer_names:
            return "layered"

        # MVC: controllers + models + views/templates
        if "controllers" in layer_names and "models" in layer_names:
            return "mvc"

        # Hexagonal / ports-adapters
        if "ports" in layer_names or "adapters" in layer_names:
            return "hexagonal"

        # Microservices: multiple top-level service dirs
        pm = self.indexer.ws.get_project_map()
        top_dirs = {Path(f).parts[0] for f in pm.files if len(Path(f).parts) > 1}
        if len(top_dirs) >= 4 and "controllers" not in layer_names:
            return "microservices"

        # Monolith with utils
        if layer_names == {"utils", "other"}:
            return "monolith"

        # Default
        return "layered"

    def get_layer(self, name: str) -> LayerInfo | None:
        if self._arch is None:
            self.map_layers()
        if self._arch:
            return self._arch.layers.get(name)
        return None

    def report(self) -> dict:
        arch = self._arch or self.map_layers()
        return {
            "pattern": arch.pattern,
            "layers": {name: layer.to_dict() for name, layer in arch.layers.items()},
            "entry_points": arch.entry_points,
            "modules": {k: len(v) for k, v in arch.modules.items()},
            "cross_layer_edges": len(arch.cross_layer_edges),
            "violations": self._find_violations(arch),
        }

    @staticmethod
    def _find_violations(arch: ArchitectureMap) -> list[dict]:
        """Find architecture violations — e.g., models importing controllers."""
        violations: list[dict] = []
        for edge in arch.cross_layer_edges:
            risk = _LAYER_RISK.get(edge.source_layer, 0.5)
            if (
                edge.source_layer == "models"
                and edge.target_layer in ("controllers", "middleware")
            ):
                violations.append({
                    "type": "model_imports_controller",
                    "source": edge.source_file,
                    "target": edge.target_file,
                    "risk": round(risk * 0.8, 2),
                })
            elif (
                edge.source_layer == "repositories"
                and edge.target_layer == "controllers"
            ):
                violations.append({
                    "type": "repository_imports_controller",
                    "source": edge.source_file,
                    "target": edge.target_file,
                    "risk": round(risk * 0.7, 2),
                })
            elif (
                edge.source_layer == "utils"
                and edge.target_layer == "config"
            ):
                violations.append({
                    "type": "utils_imports_config",
                    "source": edge.source_file,
                    "target": edge.target_file,
                    "risk": round(risk * 0.3, 2),
                })
        return violations

    def allowed_direction(self, source_layer: str, target_layer: str) -> bool:
        """Check if dependency direction follows expected layering."""
        order = ["controllers", "services", "repositories", "models", "utils", "config"]
        if source_layer in order and target_layer in order:
            return order.index(source_layer) <= order.index(target_layer)
        return True


@dataclass
class ArchitectureMap:
    layers: dict[str, LayerInfo]
    pattern: str
    entry_points: list[str]
    modules: dict[str, list[str]]
    file_to_layer: dict[str, str]
    cross_layer_edges: list[CrossLayerEdge]


def _layer_description(name: str) -> str:
    descriptions = {
        "controllers": "Handles HTTP requests, input validation, response formatting",
        "services": "Business logic, orchestration, application rules",
        "models": "Data models, domain entities, business objects",
        "repositories": "Data access, database queries, persistence layer",
        "config": "Application configuration, environment settings",
        "middleware": "Request preprocessing, authentication, logging",
        "utils": "Shared utilities, helper functions, common infrastructure",
        "tests": "Test files and test infrastructure",
        "types": "Type definitions, interfaces, data contracts",
    }
    return descriptions.get(name, "Other files without clear layer assignment")
