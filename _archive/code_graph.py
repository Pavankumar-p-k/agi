"""
code_graph.py — AST-based code understanding and dependency graph.

Provides:
- Symbol index: functions, classes, imports per file
- Call graph: which function calls which
- Dependency graph: which file imports which
- Relevance ranking: PageRank-like scoring of files given a query
"""

from __future__ import annotations

import ast
import logging
import re
import os
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SOURCE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
    ".rb", ".php", ".swift", ".kt", ".cs", ".cpp", ".h", ".hpp",
    ".c", ".cc", ".m", ".mm",
}
_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", ".eggs", "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache"})


class SymbolIndex:
    """Per-file symbol information."""

    def __init__(self):
        self.functions: list[str] = []
        self.classes: list[str] = []
        self.imports: list[str] = []
        self.calls: list[str] = []
        self.size: int = 0
        self.lines: int = 0


class CodeGraph:
    """Code graph for a workspace: symbols, imports, call graph, ranking."""

    def __init__(self, workspace_root: str | Path):
        self.root = Path(workspace_root).resolve()
        self._files: dict[str, SymbolIndex] = {}
        self._import_graph: dict[str, set[str]] = defaultdict(set)  # file → files it imports
        self._reverse_imports: dict[str, set[str]] = defaultdict(set)  # file → files that import it
        self._call_graph: dict[str, set[str]] = defaultdict(set)  # function → functions it calls
        self._dirty = True

    def build(self) -> None:
        """Scan workspace and build the full graph."""
        self._files = {}
        self._import_graph.clear()
        self._reverse_imports.clear()
        self._call_graph.clear()

        for dirpath, dirnames, filenames in os.walk(str(self.root)):
            # Prune skip dirs
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for fname in sorted(filenames):
                if fname.startswith("."):
                    continue
                ext = os.path.splitext(fname)[1]
                if ext not in _SOURCE_EXTS:
                    continue
                fpath = os.path.join(dirpath, fname)
                rel = os.path.relpath(fpath, str(self.root))
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except Exception:
                    continue
                si = self._parse_file(text, ext, rel)
                if si is not None:
                    self._files[rel] = si

        self._build_import_edges()
        self._dirty = False

    def search_symbols(self, query: str, top_n: int = 10) -> list[tuple[str, str, str]]:
        """Search for files containing a symbol matching ``query``.

        Returns [(file_path, symbol_type, symbol_name), ...]
        """
        q = query.lower()
        results: list[tuple[str, str, str]] = []
        for rel, si in self._files.items():
            for fn in si.functions:
                if q in fn.lower():
                    results.append((rel, "function", fn))
            for cls in si.classes:
                if q in cls.lower():
                    results.append((rel, "class", cls))
        results.sort(key=lambda x: (len(x[0]), x[0]))
        return results[:top_n]

    def find_relevant_files(self, query: str, top_n: int = 8) -> list[str]:
        """Find files relevant to ``query`` using symbol match + dependency ranking."""
        q = query.lower()
        # Score each file by symbol relevance
        scores: dict[str, float] = defaultdict(float)
        for rel, si in self._files.items():
            for fn in si.functions:
                if q in fn.lower():
                    scores[rel] += 3.0
            for cls in si.classes:
                if q in cls.lower():
                    scores[rel] += 3.0
            for imp in si.imports:
                if q in imp.lower():
                    scores[rel] += 1.0

        # Boost files with many incoming imports (centrality)
        centrality = self._compute_centrality()
        for rel, score in centrality.items():
            if rel in scores:
                scores[rel] += score * 2.0

        if not scores:
            return list(self._files.keys())[:top_n] if self._files else []

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [r[0] for r in ranked[:top_n]]

    def get_dependencies(self, file_path: str) -> list[str]:
        """Return files that ``file_path`` imports."""
        return sorted(self._import_graph.get(file_path, set()))

    def get_dependents(self, file_path: str) -> list[str]:
        """Return files that import ``file_path``."""
        return sorted(self._reverse_imports.get(file_path, set()))

    def format_for_prompt(self, query: str, top_n: int = 8) -> str:
        """Build a compact text block for prompt injection: relevant files + symbols + deps."""
        relevant = self.find_relevant_files(query, top_n=top_n)
        if not relevant:
            return ""
        parts = ["## Relevant code context"]
        for rel in relevant:
            si = self._files.get(rel)
            if si is None:
                continue
            line = f"**{rel}** ({si.lines}L)"
            if si.classes:
                line += f" cls:{','.join(si.classes[:5])}"
            if si.functions:
                line += f" fn:{','.join(si.functions[:8])}"
            deps = self.get_dependencies(rel)
            if deps:
                line += f" imports:{','.join(deps[:5])}"
            parts.append(line)
        return "\n".join(parts)

    def _parse_file(self, text: str, ext: str, rel: str) -> Optional[SymbolIndex]:
        """Parse a source file and extract symbols."""
        si = SymbolIndex()
        si.size = len(text)
        si.lines = text.count("\n") + 1

        if ext == ".py":
            return self._parse_python(text, si)
        else:
            return self._parse_generic(text, ext, si)

    def _parse_python(self, text: str, si: SymbolIndex) -> Optional[SymbolIndex]:
        """Parse Python file with AST."""
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                si.functions.append(node.name)
                # Collect calls within this function
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        si.calls.append(child.func.id)
                    elif isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                        si.calls.append(child.func.attr)
            elif isinstance(node, ast.ClassDef):
                si.classes.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    si.imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    si.imports.append(node.module.split(".")[0])
        return si

    def _parse_generic(self, text: str, ext: str, si: SymbolIndex) -> Optional[SymbolIndex]:
        """Parse non-Python files with regex."""
        # Function/class definitions
        patterns = [
            (r"(?:export\s+)?(?:function|async function|const\s+\w+\s*=\s*(?:async\s+)?function)\s+(\w+)", "fn"),
            (r"(?:class|struct|trait|interface|enum)\s+(\w+)", "cls"),
            (r"(?:def|fn|func|fun|sub)\s+(\w+)", "fn"),
            (r"(?:func|fn)\s+(\w+)", "fn"),
            (r"(?:public|private|protected)?\s*(?:static\s+)?(?:function|def)\s+(\w+)", "fn"),
        ]
        for pat, kind in patterns:
            for m in re.finditer(pat, text):
                name = m.group(1)
                if kind == "fn":
                    si.functions.append(name)
                else:
                    si.classes.append(name)

        # Import statements
        imp_pats = [
            r'(?:import|from)\s+["\']?([a-zA-Z_][\w.]*)["\']?',
            r'use\s+(?:.*?\bfrom\s+)?["\']([a-zA-Z_][\w./]*)["\']',
            r'require\(["\']([a-zA-Z_][\w./]*)["\']\)',
        ]
        for pat in imp_pats:
            for m in re.finditer(pat, text):
                si.imports.append(m.group(1).split("/")[0].split(".")[0])
        return si

    def _build_import_edges(self) -> None:
        """Build import dependency graph between workspace files."""
        module_to_file: dict[str, str] = {}
        for rel in self._files:
            stem = Path(rel).stem
            module_to_file[stem] = rel
            # Also map directory-based imports (e.g., "core.tools" → core/tools/__init__.py)
            dir_path = Path(rel).parent / "__init__" if Path(rel).name == "__init__.py" else None

        for rel, si in self._files.items():
            for imp in si.imports:
                # Check if the imported module is another file in the workspace
                target = module_to_file.get(imp)
                if target and target != rel:
                    self._import_graph[rel].add(target)
                    self._reverse_imports[target].add(rel)

    def _compute_centrality(self, iterations: int = 5) -> dict[str, float]:
        """Simple PageRank-like centrality over import graph."""
        if not self._files:
            return {}
        scores: dict[str, float] = {f: 1.0 for f in self._files}
        damping = 0.85
        for _ in range(iterations):
            new_scores: dict[str, float] = {}
            for f in self._files:
                incoming = self._reverse_imports.get(f, set())
                rank_sum = 0.0
                for src in incoming:
                    out_degree = max(len(self._import_graph.get(src, set())), 1)
                    rank_sum += scores.get(src, 0.0) / out_degree
                new_scores[f] = (1 - damping) + damping * rank_sum
            scores = new_scores
        # Normalize
        max_score = max(scores.values()) if scores else 1.0
        return {f: s / max_score for f, s in scores.items()}


# Workspace-level cache
_graph_cache: dict[str, CodeGraph] = {}
_graph_root: Optional[str] = None


def get_code_graph(workspace_root: Optional[str | Path] = None) -> Optional[CodeGraph]:
    """Get or create a CodeGraph for the workspace (cached)."""
    global _graph_root
    root = str(Path(workspace_root or Path.cwd()).resolve()) if workspace_root else _graph_root
    if root is None:
        try:
            root = str(Path.cwd().resolve())
        except Exception:
            return None

    if root in _graph_cache:
        return _graph_cache[root]

    cg = CodeGraph(root)
    try:
        cg.build()
        _graph_cache[root] = cg
        _graph_root = root
        logger.info("[code_graph] built for %s (%d files)", root, len(cg._files))
    except Exception as e:
        logger.warning("[code_graph] build failed: %s", e)
        return None
    return cg
