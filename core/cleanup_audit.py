"""Import-aware cleanup audit for JARVIS.

The goal is not to delete files automatically. It produces a conservative map
of active modules, orphan candidates, duplicate names, and root-level clutter so
cleanup can happen with evidence.
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "jarvis_launcher.egg-info",
    "archive",
    "data",
    "devtools",
    "reports",
    "apps",
}
ENTRYPOINT_MODULES = {
    "jarvis",
    "core.main",
    "core.lifespan",
    "api.ai_os_routes",
    "api.hybrid_integration",
    "api.os_routes",
    "api.vision_routes",
    "automation.routes",
    "routers.chat",
    "routers.whatsapp",
}
ROOT_SCRIPT_ALLOWLIST = {
    "jarvis.py",
    "comprehensive_audit.py",
    "quick_audit.py",
}


@dataclass
class CleanupAudit:
    root: str
    totals: dict[str, int] = field(default_factory=dict)
    entrypoints: list[str] = field(default_factory=list)
    active_modules: list[str] = field(default_factory=list)
    orphan_candidates: list[str] = field(default_factory=list)
    root_clutter: list[str] = field(default_factory=list)
    duplicate_basenames: dict[str, list[str]] = field(default_factory=dict)
    broken_imports: dict[str, list[str]] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _iter_python_files(root: Path = ROOT) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        rel_parts = set(path.relative_to(root).parts)
        if rel_parts & IGNORED_DIRS:
            continue
        yield path


def _module_for(path: Path, root: Path = ROOT) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _path_for_module(module: str, module_to_path: dict[str, Path]) -> Path | None:
    if module in module_to_path:
        return module_to_path[module]
    parts = module.split(".")
    while len(parts) > 1:
        parts.pop()
        parent = ".".join(parts)
        if parent in module_to_path:
            return module_to_path[parent]
    return None


def _resolve_relative_import(current: str, level: int, module: str | None) -> str:
    parts = current.split(".")
    if parts and parts[-1] != "__init__":
        parts = parts[:-1]
    if level:
        parts = parts[: max(0, len(parts) - level + 1)]
    if module:
        parts.extend(module.split("."))
    return ".".join(p for p in parts if p)


def _imports_for(path: Path, module: str) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        tree = ast.parse(text, filename=str(path))
    except (OSError, SyntaxError):
        return set()

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                imports.add(_resolve_relative_import(module, node.level, node.module))
            elif node.module:
                imports.add(node.module)
    return imports


def build_cleanup_audit(root: Path = ROOT) -> CleanupAudit:
    files = sorted(_iter_python_files(root))
    module_to_path = {_module_for(path, root): path for path in files}
    path_to_module = {path: module for module, path in module_to_path.items()}
    graph: dict[str, set[str]] = {}
    broken: dict[str, list[str]] = {}

    for path in files:
        module = path_to_module[path]
        graph[module] = set()
        for imported in _imports_for(path, module):
            target = _path_for_module(imported, module_to_path)
            if target is not None:
                graph[module].add(path_to_module[target])
            elif imported.split(".")[0] in {"core", "api", "ai_os", "assistant", "tools", "memory", "brain", "routers", "automation", "pc_agent", "governance", "channels"}:
                broken.setdefault(module, []).append(imported)

    entrypoints = sorted(m for m in ENTRYPOINT_MODULES if m in module_to_path)
    active: set[str] = set(entrypoints)
    queue = deque(entrypoints)
    while queue:
        current = queue.popleft()
        for target in graph.get(current, set()):
            if target not in active:
                active.add(target)
                queue.append(target)

    orphan_candidates = []
    for module, path in module_to_path.items():
        rel = path.relative_to(root).as_posix()
        if module in active:
            continue
        if rel.startswith("tests/") or path.name == "__init__.py":
            continue
        if path.parent == root and path.name in ROOT_SCRIPT_ALLOWLIST:
            continue
        orphan_candidates.append(rel)

    root_clutter = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.suffix in {".py", ".txt", ".log", ".err", ".html", ".json"}:
            if path.name not in ROOT_SCRIPT_ALLOWLIST and path.name not in {"README.md", "pyproject.toml", "requirements.txt", "uv.lock"}:
                root_clutter.append(path.name)

    basenames: dict[str, list[str]] = defaultdict(list)
    for path in files:
        if path.name == "__init__.py":
            continue
        basenames[path.stem].append(path.relative_to(root).as_posix())
    duplicates = {name: sorted(paths) for name, paths in basenames.items() if len(paths) > 1}

    audit = CleanupAudit(root=str(root))
    audit.totals = {
        "python_files": len(files),
        "active_modules": len(active),
        "orphan_candidates": len(orphan_candidates),
        "root_clutter": len(root_clutter),
        "duplicate_basenames": len(duplicates),
        "broken_local_import_sources": len(broken),
    }
    audit.entrypoints = entrypoints
    audit.active_modules = sorted(active)
    audit.orphan_candidates = sorted(orphan_candidates)
    audit.root_clutter = root_clutter
    audit.duplicate_basenames = duplicates
    audit.broken_imports = {k: sorted(v) for k, v in sorted(broken.items())}
    audit.recommendations = [
        "Move root-level one-off audit/output files into devtools/ or archive/ after reviewing them.",
        "Do not delete orphan candidates automatically; first grep for dynamic imports, route registration, and mobile/CLI references.",
        "Collapse duplicate module names only when their APIs overlap and tests prove the migration.",
        "Keep FastAPI route functions even if no direct Python caller exists; decorators are runtime entrypoints.",
    ]
    return audit
