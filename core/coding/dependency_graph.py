"""Dependency graph over repository index entries."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any

from core.coding.repository_indexer import RepositoryIndexer


@dataclass
class DependencyNode:
    path: str
    imports: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    fan_in: int = 0
    fan_out: int = 0
    centrality: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DependencyGraph:
    def __init__(self, indexer: RepositoryIndexer):
        self.indexer = indexer
        self.nodes: dict[str, DependencyNode] = {}

    def _module_to_file(self, module: str) -> str | None:
        candidate = module.replace(".", "/") + ".py"
        if self.indexer.get_entry(candidate):
            return candidate
        init_candidate = module.replace(".", "/") + "/__init__.py"
        if self.indexer.get_entry(init_candidate):
            return init_candidate
        tail = PurePosixPath(candidate).name
        matches = [entry.path for entry in self.indexer.all_entries() if entry.path.endswith("/" + tail) or entry.path == tail]
        return matches[0] if len(matches) == 1 else None

    def build(self) -> dict[str, DependencyNode]:
        entries = self.indexer.all_entries()
        self.nodes = {
            entry.path: DependencyNode(path=entry.path, imports=list(entry.imports))
            for entry in entries
        }
        for entry in entries:
            node = self.nodes[entry.path]
            deps = []
            for imported in entry.imports:
                dep = self._module_to_file(imported)
                if dep and dep != entry.path:
                    deps.append(dep)
            node.dependencies = sorted(set(deps))
        for node in self.nodes.values():
            for dep in node.dependencies:
                if dep in self.nodes:
                    self.nodes[dep].dependents.append(node.path)
        total = max(1, len(self.nodes) - 1)
        for node in self.nodes.values():
            node.dependents = sorted(set(node.dependents))
            node.fan_in = len(node.dependents)
            node.fan_out = len(node.dependencies)
            node.centrality = min(1.0, (node.fan_in + node.fan_out) / total)
        return self.nodes

    def get_node(self, path: str) -> DependencyNode | None:
        if not self.nodes:
            self.build()
        return self.nodes.get(path.replace("\\", "/"))

    def reverse_dependencies(self, path: str) -> list[str]:
        node = self.get_node(path)
        return list(node.dependents) if node else []

    def transitive_dependencies(self, path: str) -> set[str]:
        if not self.nodes:
            self.build()
        seen: set[str] = set()
        stack = list(self.nodes.get(path, DependencyNode(path)).dependencies)
        while stack:
            item = stack.pop()
            if item in seen:
                continue
            seen.add(item)
            stack.extend(self.nodes.get(item, DependencyNode(item)).dependencies)
        return seen

    def impact_set(self, paths: list[str]) -> set[str]:
        if not self.nodes:
            self.build()
        seen: set[str] = set()
        stack = [p.replace("\\", "/") for p in paths]
        while stack:
            item = stack.pop()
            for dependent in self.nodes.get(item, DependencyNode(item)).dependents:
                if dependent not in seen:
                    seen.add(dependent)
                    stack.append(dependent)
        return seen

    def high_impact_files(self, top_n: int = 10) -> list[DependencyNode]:
        if not self.nodes:
            self.build()
        return sorted(self.nodes.values(), key=lambda n: (n.fan_in, n.centrality), reverse=True)[:top_n]

    def summary(self) -> dict[str, Any]:
        if not self.nodes:
            self.build()
        return {
            "files": len(self.nodes),
            "edges": sum(len(node.dependencies) for node in self.nodes.values()),
            "high_impact": [node.path for node in self.high_impact_files(5)],
        }
