"""RepositoryAnalyzer — dependency graphs, module graphs, entry point analysis.

Provides explain_repository, find_auth, find_db, find_api_routes, find_tests,
and build_pipeline analysis by combining workspace metadata with code scanning.
"""
from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


class RepositoryAnalyzer:
    """Analyzes repository structure: dependency graph, imports, entry points, dead code."""

    def __init__(self, workspace: WorkspaceManager | None = None, path: str | Path | None = None):
        if workspace:
            self.ws = workspace
        else:
            self.ws = WorkspaceManager(path)
        self._import_graph: dict[str, list[str]] = {}
        self._module_graph: dict[str, list[str]] = {}

    def set_path(self, path: str | Path) -> None:
        self.ws.set_path(path)

    def build_import_graph(self) -> dict[str, list[str]]:
        """Build import dependency graph for the project."""
        pm = self.ws.get_project_map()
        graph: dict[str, list[str]] = {}
        lang = pm.language
        source_exts = self._source_extensions(lang)
        import_triggers = {
            "python": ("import ", "from "),
            "javascript": ("import ", "require("),
            "typescript": ("import ", "require("),
            "java": ("import ",),
            "kotlin": ("import ",),
        }
        trigger_strings = import_triggers.get(lang, ("import ",))

        for filepath in pm.files:
            if os.path.splitext(filepath)[1] not in source_exts:
                continue
            full_path = Path(pm.root) / filepath
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if not any(trig in content for trig in trigger_strings):
                continue
            if lang == "python":
                imports = _parse_python_imports(content)
            elif lang in ("javascript", "typescript"):
                imports = _parse_js_imports(content)
            elif lang in ("java", "kotlin"):
                imports = _parse_java_imports(content)
            else:
                imports = []
            if imports:
                graph[filepath] = imports

        self._import_graph = graph
        return graph

    def build_module_graph(self) -> dict[str, list[str]]:
        """Group files into module-level dependency graph."""
        pm = self.ws.get_project_map()
        module_groups: dict[str, list[str]] = defaultdict(list)
        for filepath in pm.files:
            parts = Path(filepath).parts
            if len(parts) > 1:
                module_groups[parts[0]].append(filepath)
            else:
                module_groups["root"].append(filepath)
        self._module_graph = dict(module_groups)
        return self._module_graph

    def find_entry_points(self) -> list[dict]:
        """Identify and describe entry points with their type."""
        pm = self.ws.get_project_map()
        results = []
        for ep in pm.entry_points:
            fp = Path(pm.root) / ep
            if fp.exists():
                try:
                    lines = fp.read_text(encoding="utf-8", errors="replace").split("\n")
                    results.append({
                        "file": ep,
                        "type": _classify_entry_point(ep, pm.language),
                        "line_count": len(lines),
                    })
                except Exception:
                    results.append({"file": ep, "type": "unknown", "line_count": 0})
        return results

    def find_dead_code(self) -> list[dict]:
        """Identify potentially unused files based on import graph."""
        pm = self.ws.get_project_map()
        if not self._import_graph:
            self.build_import_graph()
        all_imported = set()
        for filepath, imports in self._import_graph.items():
            for imp in imports:
                all_imported.add(imp)
        candidates = []
        for filepath in pm.files:
            stem = Path(filepath).stem
            if filepath in self._import_graph and stem not in all_imported:
                candidates.append({
                    "file": filepath,
                    "suspected_dead": True,
                    "imported_by": [],
                })
        return candidates

    def _source_extensions(self, lang: str) -> set[str]:
        return {
            "python": {".py"},
            "typescript": {".ts", ".tsx", ".js", ".jsx"},
            "javascript": {".ts", ".tsx", ".js", ".jsx"},
            "java": {".java"},
            "kotlin": {".kt", ".kts"},
            "rust": {".rs"},
            "go": {".go"},
        }.get(lang, {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".kt", ".rs", ".go", ".rb", ".php", ".cs", ".cpp", ".c", ".swift"})

    def _find_keyword_matches(self, content: str, keywords: list[str], max_snippets: int = 5) -> list[dict]:
        """Fast keyword scan: single pass, lowercased content."""
        content_lower = content.lower()
        if not any(kw in content_lower for kw in keywords):
            return []
        matches = []
        for i, line in enumerate(content.split("\n"), 1):
            line_lower = line.lower()
            for keyword in keywords:
                if keyword in line_lower:
                    matches.append({"line": i, "text": line.strip()[:120]})
                    if len(matches) >= max_snippets:
                        return matches
                    break
        return matches

    def find_auth_code(self) -> list[dict]:
        """Find authentication-related files and code sections."""
        pm = self.ws.get_project_map()
        results = []
        keywords = ["login", "auth", "oauth", "jwt", "token", "session", "password",
                    "authenticate", "authorize", "signin", "signup", "register"]
        source_exts = self._source_extensions(pm.language)
        for filepath in pm.files:
            if os.path.splitext(filepath)[1] not in source_exts:
                continue
            full_path = Path(pm.root) / filepath
            if not full_path.is_file():
                continue
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            snippets = self._find_keyword_matches(content, keywords)
            if snippets:
                results.append({"file": filepath, "matches": len(snippets), "snippets": snippets})
        return sorted(results, key=lambda x: x["matches"], reverse=True)

    def find_database_layer(self) -> list[dict]:
        """Find database-related files and models."""
        pm = self.ws.get_project_map()
        results = []
        keywords = ["database", "db_", "select", "insert", "update", "delete",
                    "from", "sql", "query", "model", "schema", "migration",
                    "repository", "entity", "orm", "prisma", "sqlalchemy"]
        source_exts = self._source_extensions(pm.language)
        for filepath in pm.files:
            if os.path.splitext(filepath)[1] not in source_exts:
                continue
            full_path = Path(pm.root) / filepath
            if not full_path.is_file():
                continue
            if not any(kw in filepath.lower() for kw in ["model", "migration", "db", "schema"]):
                continue
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            snippets = self._find_keyword_matches(content, keywords)
            if snippets:
                results.append({"file": filepath, "matches": len(snippets), "snippets": snippets})
        return sorted(results, key=lambda x: x["matches"], reverse=True)

    def find_api_routes(self) -> list[dict]:
        """Find API route definitions."""
        pm = self.ws.get_project_map()
        results = []
        lang = pm.language
        source_exts = self._source_extensions(lang)
        if lang == "python":
            pattern = re.compile(r'@(?:app|router)\.(?:get|post|put|delete|patch|options)\s*\(\s*["\']([^"\']+)')
            for filepath in pm.files:
                if os.path.splitext(filepath)[1] not in source_exts:
                    continue
                full_path = Path(pm.root) / filepath
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                if "router." not in content and "app." not in content:
                    continue
                routes = pattern.findall(content)
                if routes:
                    results.append({"file": filepath, "routes": routes})
        elif lang in ("javascript", "typescript"):
            pattern = re.compile(r'(?:router|app)\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)')
            for filepath in pm.files:
                if os.path.splitext(filepath)[1] not in source_exts:
                    continue
                full_path = Path(pm.root) / filepath
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                if "router." not in content and "app." not in content:
                    continue
                routes = pattern.findall(content)
                if routes:
                    results.append({"file": filepath, "routes": routes})
        elif lang in ("java", "kotlin"):
            pattern = re.compile(r'@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\s*\(\s*["\']([^"\']+)')
            for filepath in pm.files:
                if os.path.splitext(filepath)[1] not in source_exts:
                    continue
                full_path = Path(pm.root) / filepath
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                if "Mapping" not in content:
                    continue
                routes = pattern.findall(content)
                if routes:
                    results.append({"file": filepath, "routes": routes})
        return results

    def find_tests(self) -> list[dict]:
        """Find and describe test files."""
        pm = self.ws.get_project_map()
        results = []
        for ts in pm.test_suites:
            full_path = Path(pm.root) / ts
            if full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    test_functions = _extract_test_names(content, pm.language)
                    results.append({
                        "file": ts,
                        "type": "file",
                        "test_count": len(test_functions),
                        "tests": test_functions[:20],
                    })
                except Exception:
                    results.append({"file": ts, "type": "file", "test_count": 0})
            elif full_path.is_dir():
                count = len(list(full_path.rglob("*"))) if pm.language == "python" else len(list(full_path.rglob("*.java"))) + len(list(full_path.rglob("*.kt")))
                results.append({"file": ts, "type": "directory", "test_files": count})
        return results

    def find_build_pipeline(self) -> dict:
        """Describe the build pipeline configuration."""
        pm = self.ws.get_project_map()
        pipeline = {
            "build_system": pm.build_system,
            "ci_config": pm.ci_config,
            "docker": pm.docker,
            "build_command": pm.build_command,
            "test_command": pm.test_command,
            "run_command": pm.run_command,
        }
        ci_paths = []
        github_actions = Path(pm.root) / ".github" / "workflows"
        if github_actions.exists():
            for f in github_actions.iterdir():
                if f.suffix in (".yml", ".yaml"):
                    ci_paths.append(str(f))
        if ci_paths:
            pipeline["ci_files"] = ci_paths
        return pipeline

    def explain(self) -> dict:
        """Generate comprehensive repository explanation."""
        pm = self.ws.get_project_map()
        entry_points = self.find_entry_points()
        api_routes = self.find_api_routes()
        tests = self.find_tests()
        pipeline = self.find_build_pipeline()

        explanation = {
            "project": pm.root,
            "language": pm.language,
            "framework": pm.framework,
            "build_system": pm.build_system,
            "package_manager": pm.package_manager,
            "active_branch": pm.active_branch,
            "file_count": len(pm.files),
            "folder_count": len(pm.folders),
            "entry_points": entry_points,
            "api_routes": len(api_routes),
            "api_route_files": api_routes,
            "test_files": tests,
            "build_pipeline": pipeline,
            "dependencies": {k: len(v) for k, v in pm.dependencies.items()},
            "docker": pm.docker,
            "ci": pm.ci_config,
        }
        return explanation


def _parse_python_imports(content: str) -> list[str]:
    imports = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("import "):
            parts = line[7:].split(" as ")[0].split(",")
            for p in parts:
                imports.append(p.strip().split(".")[0])
        elif line.startswith("from "):
            parts = line[5:].split(" import ")[0].strip()
            imports.append(parts.split(".")[0])
    return imports


def _parse_js_imports(content: str) -> list[str]:
    imports = []
    patterns = [
        r"""import\s+(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+['"]([^'"]+)""",
        r"""require\s*\(\s*['"]([^'"]+)['"]""",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, content):
            imp = m.group(1)
            if imp.startswith(".") or imp.startswith("/"):
                imports.append(imp)
            else:
                imports.append(imp.split("/")[0] if "/" in imp else imp)
    return imports


def _parse_java_imports(content: str) -> list[str]:
    imports = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("import "):
            imp = line[7:].rstrip(";")
            parts = imp.split(".")
            imports.append(parts[0] if parts else imp)
    return imports


def _classify_entry_point(filepath: str, language: str) -> str:
    name = Path(filepath).name.lower()
    if name in ("main.py", "main.rs", "main.go", "main.java"):
        return "application_entry"
    if name == "app.py" or name == "app.js":
        return "application_entry"
    if name in ("__init__.py", "__main__.py"):
        return "package_init"
    if "application" in name:
        return "application_entry"
    if "cli" in name:
        return "cli_entry"
    return "module"


def _extract_test_names(content: str, language: str) -> list[str]:
    test_names = []
    if language == "python":
        for m in re.finditer(r"^(?:async\s+)?def\s+(test_\w+)", content, re.MULTILINE):
            test_names.append(m.group(1))
    elif language in ("javascript", "typescript"):
        for m in re.finditer(r"(?:it|test)\s*\(\s*['\"]([^'\"]+)", content):
            test_names.append(m.group(1))
        for m in re.finditer(r"describe\s*\(\s*['\"]([^'\"]+)", content):
            test_names.append(f"describe: {m.group(1)}")
    elif language in ("java", "kotlin"):
        for m in re.finditer(r"@Test\s*\n\s*(?:public\s+)?void\s+(\w+)", content):
            test_names.append(m.group(1))
        for m in re.finditer(r"fun\s+(\w+test\w*|test\w+)", content, re.IGNORECASE):
            test_names.append(m.group(1))
    return test_names
