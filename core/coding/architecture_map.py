"""Architecture mapping for Coding AI repository intelligence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.coding.dependency_graph import DependencyGraph
from core.coding.repository_indexer import RepositoryIndexer


_LAYER_HINTS = ["controllers", "routes", "api", "services", "repositories", "models", "utils", "config", "tests"]


@dataclass
class LayerInfo:
    name: str
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CrossLayerEdge:
    source: str
    target: str
    source_layer: str
    target_layer: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ArchitectureMap:
    pattern: str = "unknown"
    layers: dict[str, LayerInfo] = field(default_factory=dict)
    file_to_layer: dict[str, str] = field(default_factory=dict)
    cross_layer_edges: list[CrossLayerEdge] = field(default_factory=list)
    modules: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "layers": {name: layer.to_dict() for name, layer in self.layers.items()},
            "file_to_layer": dict(self.file_to_layer),
            "cross_layer_edges": [edge.to_dict() for edge in self.cross_layer_edges],
            "modules": dict(self.modules),
        }


class ArchitectureMapper:
    def __init__(self, indexer: RepositoryIndexer, dependency_graph: DependencyGraph):
        self.indexer = indexer
        self.dependency_graph = dependency_graph
        self.architecture: ArchitectureMap | None = None

    def _detect_layer(self, path: str) -> str:
        parts = path.split("/")
        for hint in _LAYER_HINTS:
            if hint in parts:
                return hint
        if "test" in path or "tests" in path:
            return "tests"
        return parts[0] if parts else "root"

    def _detect_pattern(self, layers: dict[str, LayerInfo]) -> str:
        names = set(layers)
        if {"controllers", "services", "models"} <= names:
            return "layered"
        if {"models", "views", "controllers"} <= names:
            return "mvc"
        return "modular" if len(names) > 2 else "simple"

    def map_layers(self) -> ArchitectureMap:
        entries = self.indexer.all_entries()
        layers: dict[str, LayerInfo] = {}
        file_to_layer: dict[str, str] = {}
        modules: dict[str, list[str]] = {}
        for entry in entries:
            layer_name = self._detect_layer(entry.path)
            layers.setdefault(layer_name, LayerInfo(layer_name)).files.append(entry.path)
            file_to_layer[entry.path] = layer_name
            top = entry.path.split("/", 1)[0]
            modules.setdefault(top, []).append(entry.path)

        edges: list[CrossLayerEdge] = []
        if not self.dependency_graph.nodes:
            self.dependency_graph.build()
        for node in self.dependency_graph.nodes.values():
            source_layer = file_to_layer.get(node.path, "unknown")
            for dep in node.dependencies:
                target_layer = file_to_layer.get(dep, "unknown")
                if source_layer != target_layer:
                    edges.append(CrossLayerEdge(node.path, dep, source_layer, target_layer))

        self.architecture = ArchitectureMap(
            pattern=self._detect_pattern(layers),
            layers=layers,
            file_to_layer=file_to_layer,
            cross_layer_edges=edges,
            modules={key: sorted(value) for key, value in modules.items()},
        )
        return self.architecture

    def report(self) -> dict[str, Any]:
        arch = self.architecture or self.map_layers()
        data = arch.to_dict()
        data["layer_count"] = len(arch.layers)
        data["cross_layer_edge_count"] = len(arch.cross_layer_edges)
        return data
