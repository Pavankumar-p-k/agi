"""DependencyGraph — transitive dependencies, reverse deps, circular detection, centrality.

Builds on RepositoryIndexer to produce a queryable dependency graph.
Each file becomes a node with fan-in (how many import it), fan-out (how many it imports),
and centrality (fraction of nodes it can reach via transitive reverse traversal).
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.coding.repository_indexer import FileEntry, RepositoryIndexer

logger = logging.getLogger(__name__)


@dataclass
class DependencyNode:
    file: str
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)
    fan_in: int = 0
    fan_out: int = 0
    centrality: float = 0.0

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "fan_in": self.fan_in,
            "fan_out": self.fan_out,
            "centrality": self.centrality,
            "imports": sorted(self.imports),
            "imported_by": sorted(self.imported_by),
        }


class DependencyGraph:
    """Build and query a dependency graph from a RepositoryIndexer.

    The graph resolves relative imports to their indexed absolute paths,
    builds forward and reverse edges, and computes graph metrics.
    """

    def __init__(self, indexer: RepositoryIndexer):
        self.indexer = indexer
        self._nodes: dict[str, DependencyNode] = {}
        self._built = False

    def build(self) -> dict[str, DependencyNode]:
        """Build the dependency graph from the indexer's entries."""
        entries = self.indexer.get_all_entries()
        all_paths = {e.path for e in entries}

        nodes: dict[str, DependencyNode] = {}
        for entry in entries:
            nodes[entry.path] = DependencyNode(
                file=entry.path,
                imports=list(entry.imports),
            )

        # Resolve imports to indexed files
        path_to_module: dict[str, str] = {}
        for entry in entries:
            stem = Path(entry.path).stem
            path_to_module[stem] = entry.path
            path_to_module[entry.path] = entry.path

        file_to_entry = {e.path: e for e in entries}

        for node in nodes.values():
            entry = file_to_entry.get(node.file)
            if not entry:
                continue
            resolved: list[str] = []
            for imp in entry.imports:
                resolved_path = self._resolve_import(imp, node.file, all_paths, entries)
                if resolved_path and resolved_path in nodes and resolved_path != node.file:
                    resolved.append(resolved_path)
            node.imports = sorted(set(resolved))

        # Build reverse deps
        for node in nodes.values():
            node.imported_by = []
        for node in nodes.values():
            for dep in node.imports:
                if dep in nodes:
                    nodes[dep].imported_by.append(node.file)

        # Deduplicate
        for node in nodes.values():
            node.imported_by = sorted(set(node.imported_by))

        # Compute metrics
        for node in nodes.values():
            node.fan_out = len(node.imports)
            node.fan_in = len(node.imported_by)
            node.centrality = self._compute_centrality(node.file, nodes)

        self._nodes = nodes
        self._built = True
        return nodes

    @staticmethod
    def _resolve_import(
        imp: str,
        filepath: str,
        all_paths: set[str],
        entries: list[FileEntry],
    ) -> str | None:
        """Resolve an import string to an indexed file path."""
        if imp.startswith(".") or imp.startswith("/"):
            dir_part = str(Path(filepath).parent).replace("\\", "/")
            imp_norm = imp.replace("\\", "/")
            candidates = [
                str(Path(dir_part) / imp_norm).replace("\\", "/"),
                str(Path(dir_part) / imp_norm / "__init__").replace("\\", "/"),
            ]
            for candidate in candidates:
                for ep in all_paths:
                    if ep == candidate or ep.startswith(candidate) or candidate.startswith(ep):
                        return ep
            return None

        # Dotted module path (e.g. src.services.user_service -> src/services/user_service)
        dotted_path = imp.replace(".", "/")
        for ep in all_paths:
            norm_ep = ep.replace("\\", "/")
            mod_stem = os.path.splitext(norm_ep)[0]
            if mod_stem == dotted_path:
                return ep
            if norm_ep.endswith("/__init__.py") and norm_ep.startswith(dotted_path):
                return ep

        # Direct module name match
        for entry in entries:
            stem = Path(entry.path).stem
            if stem == imp or entry.path == imp:
                return entry.path
        return None

    @staticmethod
    def _compute_centrality(file: str, nodes: dict[str, DependencyNode]) -> float:
        """Centrality = fraction of nodes reachable via reverse traversal."""
        if not nodes:
            return 0.0
        visited: set[str] = set()
        queue = deque([file])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            node = nodes.get(current)
            if node:
                for up in node.imported_by:
                    if up not in visited:
                        queue.append(up)
        return (len(visited) - 1) / max(len(nodes) - 1, 1)

    # ── Queries ──────────────────────────────────────────────────

    def get_node(self, filepath: str) -> DependencyNode | None:
        if not self._built:
            self.build()
        return self._nodes.get(filepath.replace("\\", "/"))

    def reverse_dependencies(self, filepath: str, transitive: bool = True) -> list[str]:
        """Files that depend on this file, directly or transitively."""
        if not self._built:
            self.build()
        normalized = filepath.replace("\\", "/")
        visited: set[str] = set()
        queue = deque([normalized])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            node = self._nodes.get(current)
            if node and transitive:
                for up in node.imported_by:
                    if up not in visited:
                        queue.append(up)
        result = sorted(visited - {normalized})
        return result

    def impact_set(self, files: list[str]) -> set[str]:
        """All files affected by changes to the given file list."""
        if not self._built:
            self.build()
        affected: set[str] = set()
        for f in files:
            affected.update(self.reverse_dependencies(f, transitive=True))
        return affected

    def find_circular_dependencies(self) -> list[list[str]]:
        """DFS-based cycle detection. Returns list of cycles (each is file chains)."""
        if not self._built:
            self.build()
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {n: WHITE for n in self._nodes}
        parent: dict[str, str | None] = {}
        cycles: list[list[str]] = []

        def dfs(u: str) -> None:
            color[u] = GRAY
            node = self._nodes.get(u)
            if node:
                for v in node.imports:
                    if v not in color:
                        continue
                    if color[v] == GRAY:
                        cycle = []
                        cur = u
                        while cur is not None and cur != v:
                            cycle.append(cur)
                            cur = parent.get(cur)
                        cycle.append(v)
                        cycle.append(u)
                        cycles.append(list(reversed(cycle)))
                    elif color[v] == WHITE:
                        parent[v] = u
                        dfs(v)
            color[u] = BLACK

        for n in list(self._nodes.keys()):
            if color.get(n) == WHITE:
                parent[n] = None
                dfs(n)

        return cycles

    def high_impact_files(self, top_n: int = 10) -> list[dict]:
        """Files with highest centrality (most depended upon, transitively)."""
        if not self._built:
            self.build()
        scored = []
        for node in self._nodes.values():
            scored.append(node.to_dict())
        scored.sort(key=lambda x: x["centrality"], reverse=True)
        return scored[:top_n]

    def to_dot(self) -> str:
        """Export Graphviz DOT format."""
        if not self._built:
            self.build()
        lines = ["digraph G {"]
        for node in self._nodes.values():
            file_label = Path(node.file).name
            lines.append(f'  "{node.file}" [label="{file_label}"];')
        for node in self._nodes.values():
            for dep in node.imports:
                if dep in self._nodes:
                    lines.append(f'  "{node.file}" -> "{dep}";')
        lines.append("}")
        return "\n".join(lines)

    def summary(self) -> dict:
        if not self._built:
            self.build()
        total = len(self._nodes)
        if total == 0:
            return {"files": 0}

        edges = sum(len(n.imports) for n in self._nodes.values())
        max_fan_in = max((n.fan_in for n in self._nodes.values()), default=0)
        max_fan_out = max((n.fan_out for n in self._nodes.values()), default=0)
        avg_centrality = sum(n.centrality for n in self._nodes.values()) / total
        isolated = sum(1 for n in self._nodes.values() if n.fan_in == 0 and n.fan_out == 0)
        top = ", ".join(
            Path(n.file).name for n in sorted(
                self._nodes.values(), key=lambda x: x.centrality, reverse=True,
            )[:5]
        )

        return {
            "files": total,
            "edges": edges,
            "max_fan_in": max_fan_in,
            "max_fan_out": max_fan_out,
            "avg_centrality": round(avg_centrality, 4),
            "isolated_files": isolated,
            "top_5_central": top,
        }
