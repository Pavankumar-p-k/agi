"""WorkspaceManager — project root detection, build system identification, ProjectMap.

Reuses existing codebase_indexer.py for vector indexing and adds structured
project intelligence (build system, package manager, language, framework).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProjectMap:
    root: str = ""
    git_root: str = ""
    active_branch: str = ""
    build_system: str = ""
    package_manager: str = ""
    language: str = ""
    framework: str = ""
    files: list[str] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    entry_points: list[str] = field(default_factory=list)
    test_suites: list[str] = field(default_factory=list)
    build_command: str = ""
    test_command: str = ""
    run_command: str = ""
    docker: bool = False
    ci_config: str = ""

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "git_root": self.git_root,
            "active_branch": self.active_branch,
            "build_system": self.build_system,
            "package_manager": self.package_manager,
            "language": self.language,
            "framework": self.framework,
            "entry_points": self.entry_points,
            "test_suites": self.test_suites,
            "build_command": self.build_command,
            "test_command": self.test_command,
            "run_command": self.run_command,
            "docker": self.docker,
            "ci_config": self.ci_config,
            "file_count": len(self.files),
            "folder_count": len(self.folders),
        }


class WorkspaceManager:
    """Detects project structure, build systems, languages, and package managers."""

    def __init__(self, path: str | Path | None = None):
        self._path = Path(path).resolve() if path else Path.cwd().resolve()
        self._project_map: ProjectMap | None = None

    @property
    def root(self) -> str:
        return str(self._path)

    def set_path(self, path: str | Path) -> None:
        self._path = Path(path).resolve()
        self._project_map = None

    def scan(self) -> ProjectMap:
        """Scan workspace and return a ProjectMap with all detected metadata."""
        pm = ProjectMap(root=str(self._path))
        pm.git_root = self._detect_git_root()
        pm.active_branch = self._detect_active_branch()
        pm.build_system = self._detect_build_system()
        pm.package_manager = self._detect_package_manager()

        # Single walk: collect files, folders, extension counts
        pm.files, pm.folders, ext_counts = self._walk_project()

        pm.language = self._detect_language_from_extensions(ext_counts)
        pm.framework = self._detect_framework(pm.language)
        pm.docker = self._detect_docker()
        pm.ci_config = self._detect_ci_config()
        pm.build_command = self._get_build_command(pm.build_system)
        pm.test_command = self._get_test_command(pm.build_system, pm.package_manager)
        pm.run_command = self._get_run_command(pm.language, pm.build_system)
        pm.entry_points = self._find_entry_points(pm.language, pm.build_system)
        pm.test_suites = self._find_test_suites(pm.language, pm.build_system, pm.package_manager)
        pm.dependencies = self._read_dependencies(pm.language, pm.package_manager)
        self._project_map = pm
        return pm

    def get_project_map(self) -> ProjectMap:
        if self._project_map is None:
            return self.scan()
        return self._project_map

    def _detect_git_root(self) -> str:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5,
                cwd=str(self._path),
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
        return ""

    def _detect_active_branch(self) -> str:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=str(self._path),
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
        return ""

    def _detect_build_system(self) -> str:
        files = {f.name for f in self._path.iterdir() if f.is_file()}
        if "build.gradle" in files or "build.gradle.kts" in files:
            return "gradle"
        if "pom.xml" in files:
            return "maven"
        if "Makefile" in files or "makefile" in files:
            return "make"
        if "CMakeLists.txt" in files:
            return "cmake"
        if "Cargo.toml" in files:
            return "cargo"
        if "pyproject.toml" in files:
            return "python-pyproject"
        if "setup.py" in files or "setup.cfg" in files:
            return "python-setuptools"
        if "package.json" in files:
            return "npm"
        if "go.mod" in files:
            return "go"
        if "mix.exs" in files:
            return "elixir-mix"
        if "Project.toml" in files or "Project.toml" in files:
            return "julia"
        return "unknown"

    def _detect_package_manager(self) -> str:
        files = {f.name for f in self._path.iterdir() if f.is_file()}
        if "Cargo.toml" in files:
            return "cargo"
        if "package.json" in files:
            if (self._path / "yarn.lock").exists():
                return "yarn"
            if (self._path / "pnpm-lock.yaml").exists():
                return "pnpm"
            if (self._path / "bun.lockb").exists():
                return "bun"
            return "npm"
        if "pyproject.toml" in files:
            return "pip" if not (self._path / "poetry.lock").exists() else "poetry"
        if "requirements.txt" in files:
            return "pip"
        if "go.mod" in files:
            return "go-mod"
        if "Gemfile" in files:
            return "bundler"
        if "mix.exs" in files:
            return "hex"
        return "unknown"

    def _detect_language(self) -> str:
        counts: dict[str, int] = {}
        try:
            for root, dirs, filenames in os.walk(self._path, topdown=True):
                dirs[:] = [d for d in dirs if d not in {
                    ".git", "__pycache__", "node_modules", ".venv", ".venv_prod", "venv",
                    ".idea", ".vscode", "build", "dist", "target", ".gradle", ".m2",
                    ".ruff_cache", ".pytest_cache", ".hypothesis", ".deepeval",
                    ".egg-info", "site-packages", ".opencode",
                } and not d.startswith('.')]
                for f in filenames:
                    _, ext = os.path.splitext(f)
                    if ext:
                        counts[ext] = counts.get(ext, 0) + 1
        except Exception:
            pass
        if ".py" in counts:
            return "python"
        if ".java" in counts:
            return "java"
        if ".kt" in counts or ".kts" in counts:
            return "kotlin"
        if ".rs" in counts:
            return "rust"
        if ".go" in counts:
            return "go"
        if ".ts" in counts or ".tsx" in counts:
            return "typescript"
        if ".js" in counts or ".jsx" in counts:
            return "javascript"
        if ".cs" in counts:
            return "csharp"
        if ".cpp" in counts or ".cc" in counts or ".cxx" in counts:
            return "cpp"
        if ".c" in counts:
            return "c"
        if ".rb" in counts:
            return "ruby"
        if ".php" in counts:
            return "php"
        if ".swift" in counts:
            return "swift"
        if ".ex" in counts or ".exs" in counts:
            return "elixir"
        return "unknown"

    def _detect_framework(self, language: str) -> str:
        root_files = {f.name for f in self._path.iterdir() if f.is_file()}
        if language == "python":
            if "pyproject.toml" in root_files:
                try:
                    content = (self._path / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
                    if "django" in content:
                        return "django"
                    if "flask" in content:
                        return "flask"
                    if "fastapi" in content:
                        return "fastapi"
                except Exception:
                    pass
        if language == "javascript" or language == "typescript":
            pkg_file = self._path / "package.json"
            if pkg_file.exists():
                try:
                    pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "react" in deps:
                        return "react"
                    if "vue" in deps:
                        return "vue"
                    if "next" in deps:
                        return "next.js"
                    if "@angular/core" in deps:
                        return "angular"
                    if "express" in deps:
                        return "express"
                except Exception:
                    pass
        if language == "java" or language == "kotlin":
            gradle_file = self._path / "build.gradle"
            if gradle_file.exists():
                try:
                    content = gradle_file.read_text(encoding="utf-8", errors="replace")
                    if "android" in content.lower():
                        return "android"
                    if "spring" in content.lower():
                        return "spring-boot"
                except Exception:
                    pass
            pom_file = self._path / "pom.xml"
            if pom_file.exists():
                try:
                    content = pom_file.read_text(encoding="utf-8", errors="replace")
                    if "spring-boot" in content:
                        return "spring-boot"
                    if "android" in content.lower():
                        return "android"
                except Exception:
                    pass
        if language == "go":
            return "go-mod"
        if language == "rust":
            return "cargo"
        return ""

    def _detect_docker(self) -> bool:
        files = {f.name for f in self._path.iterdir() if f.is_file()}
        return "Dockerfile" in files or "docker-compose.yml" in files

    def _detect_ci_config(self) -> str:
        ci_dir = self._path / ".github" / "workflows"
        if ci_dir.exists():
            yamls = list(ci_dir.glob("*.yml")) + list(ci_dir.glob("*.yaml"))
            if yamls:
                return "github-actions"
        if (self._path / ".gitlab-ci.yml").exists():
            return "gitlab-ci"
        if (self._path / "Jenkinsfile").exists():
            return "jenkins"
        if (self._path / ".circleci" / "config.yml").exists():
            return "circleci"
        return ""

    def _get_build_command(self, build_system: str) -> str:
        commands = {
            "gradle": "./gradlew build" if (self._path / "gradlew").exists() else "gradle build",
            "maven": "mvn compile",
            "make": "make",
            "cmake": "cmake --build .",
            "cargo": "cargo build",
            "python-pyproject": "pip install -e .",
            "python-setuptools": "python setup.py build",
            "npm": "npm run build" if (self._path / "package.json").exists() and self._has_script("build") else "npm install",
            "go": "go build ./...",
        }
        return commands.get(build_system, "")

    def _get_test_command(self, build_system: str, package_manager: str) -> str:
        commands = {
            "gradle": "./gradlew test" if (self._path / "gradlew").exists() else "gradle test",
            "maven": "mvn test",
            "make": "make test",
            "cargo": "cargo test",
            "python-pyproject": "pytest",
            "python-setuptools": "pytest",
            "npm": "npm test",
            "go": "go test ./...",
        }
        return commands.get(build_system, "")

    def _get_run_command(self, language: str, build_system: str) -> str:
        if language == "python":
            main_files = list(self._path.rglob("main.py")) + list(self._path.rglob("app.py"))
            if main_files:
                rel = os.path.relpath(main_files[0], self._path)
                return f"python {rel}"
        if language == "java" or language == "kotlin":
            if build_system == "gradle":
                return "./gradlew run" if (self._path / "gradlew").exists() else "gradle run"
            if build_system == "maven":
                return "mvn exec:java"
        if language == "typescript" or language == "javascript":
            if (self._path / "package.json").exists():
                try:
                    pkg = json.loads((self._path / "package.json").read_text(encoding="utf-8"))
                    scripts = pkg.get("scripts", {})
                    if "start" in scripts:
                        return "npm start"
                    if "dev" in scripts:
                        return "npm run dev"
                except Exception:
                    pass
            return "npm start"
        if build_system == "cargo":
            return "cargo run"
        if build_system == "go":
            return "go run ."
        return ""

    def _has_script(self, name: str) -> bool:
        try:
            pkg = json.loads((self._path / "package.json").read_text(encoding="utf-8"))
            return name in pkg.get("scripts", {})
        except Exception:
            return False

    def _walk_project(self):
        """Single walk: returns (files, folders, extension_counts)."""
        files = []
        folders = []
        ext_counts = {}
        skip_extensions = {".pyc", ".pyo", ".so", ".dll", ".dylib", ".class", ".png", ".jpg", ".jpeg",
                           ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot"}
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", ".venv_prod", "venv",
            ".idea", ".vscode", "build", "dist", "target", ".gradle", ".m2",
            ".ruff_cache", ".pytest_cache", ".hypothesis", ".deepeval",
            ".egg-info", "site-packages", ".opencode",
            "AppData", "Application Data", "Local Settings",
            "Microsoft", "Windows", "WinSxS", "assembly",
            "System32", "SysWOW64", "Program Files", "Program Files (x86)",
            "ProgramData", "All Users", "Common Files",
            "ServiceState", "help", "PerfLogs", "Recovery",
        }
        try:
            for root, dirs, filenames in os.walk(self._path, topdown=True):
                dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
                rel_root = os.path.relpath(root, self._path)
                if rel_root != ".":
                    folders.append(rel_root)
                for f in filenames:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in skip_extensions:
                        continue
                    full = os.path.join(rel_root, f) if rel_root != "." else f
                    files.append(full)
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
        except Exception:
            pass
        return files, folders, ext_counts

    def _detect_language_from_extensions(self, ext_counts: dict[str, int]) -> str:
        lang_map: list[tuple[set[str], str]] = [
            ({".py"}, "python"),
            ({".java"}, "java"),
            ({".kt", ".kts"}, "kotlin"),
            ({".rs"}, "rust"),
            ({".go"}, "go"),
            ({".ts", ".tsx"}, "typescript"),
            ({".js", ".jsx"}, "javascript"),
            ({".cs"}, "csharp"),
            ({".cpp", ".cc", ".cxx"}, "cpp"),
            ({".c"}, "c"),
            ({".rb"}, "ruby"),
            ({".php"}, "php"),
            ({".swift"}, "swift"),
            ({".ex", ".exs"}, "elixir"),
        ]
        best_lang = "unknown"
        best_count = 0
        for exts, lang in lang_map:
            count = sum(ext_counts.get(e, 0) for e in exts)
            if count > best_count:
                best_count = count
                best_lang = lang
        return best_lang

    def _is_skip_dir(self, path: Path) -> bool:
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", ".venv_prod", "venv",
                     ".idea", ".vscode", "build", "dist", "target", ".gradle", ".m2",
                     ".ruff_cache", ".pytest_cache", ".hypothesis", ".deepeval",
                     ".egg-info", "site-packages", ".opencode",
                     "AppData", "Application Data", "Local Settings",
                     "Microsoft", "Windows", "WinSxS", "assembly",
                     "System32", "SysWOW64", "Program Files", "Program Files (x86)",
                     "ProgramData", "All Users", "Common Files",
                     "ServiceState", "help", "PerfLogs", "Recovery"}
        return any(p in skip_dirs for p in path.parts) or any(p.startswith(".") and p not in (".", "..", ".github") for p in path.parts)

    def _walk_source(self):
        """Generator that walks source directories, yielding (root, dirs, files) with skip dirs filtered."""
        skip = {".git", "__pycache__", "node_modules", ".venv", ".venv_prod", "venv",
                ".idea", ".vscode", "build", "dist", "target", ".gradle", ".m2",
                ".ruff_cache", ".pytest_cache", ".hypothesis", ".deepeval",
                ".egg-info", "site-packages", ".opencode",
                "AppData", "Application Data", "Local Settings",
                "Microsoft", "Windows", "WinSxS", "assembly",
                "System32", "SysWOW64", "Program Files", "Program Files (x86)",
                "ProgramData", "All Users", "Common Files",
                "ServiceState", "help", "PerfLogs", "Recovery"}
        for root, dirs, filenames in os.walk(self._path, topdown=True):
            rel = os.path.relpath(root, self._path)
            dirs[:] = [d for d in dirs if d not in skip and not d.startswith('.')]
            yield root, dirs, filenames

    def _find_entry_points(self, language: str, build_system: str) -> list[str]:
        entry_points = []
        if language == "python":
            targets = {"main.py", "app.py", "cli.py", "run.py", "__main__.py"}
            for root, dirs, filenames in self._walk_source():
                for f in filenames:
                    if f in targets:
                        entry_points.append(os.path.relpath(os.path.join(root, f), self._path))
                        break
        if language in ("java", "kotlin"):
            for root, dirs, filenames in self._walk_source():
                for f in filenames:
                    if ("Application" in f or f.startswith("Main.")) and (f.endswith(".java") or f.endswith(".kt")):
                        entry_points.append(os.path.relpath(os.path.join(root, f), self._path))
                        break
        if language in ("javascript", "typescript"):
            targets = {"index.js", "index.ts", "app.js", "app.ts", "main.js", "main.tsx", "main.ts"}
            for root, dirs, filenames in self._walk_source():
                for f in filenames:
                    if f in targets:
                        entry_points.append(os.path.relpath(os.path.join(root, f), self._path))
                        break
        if build_system == "cargo":
            src_main = os.path.join(self._path, "src", "main.rs")
            if os.path.isfile(src_main):
                entry_points.append("src/main.rs")
        if build_system == "go":
            for root, dirs, filenames in self._walk_source():
                for f in filenames:
                    if f == "main.go":
                        entry_points.append(os.path.relpath(os.path.join(root, f), self._path))
                        break
        return entry_points

    def _find_test_suites(self, language: str, build_system: str, package_manager: str) -> list[str]:
        suites = []
        seen_files = set()
        if language == "python":
            for root, dirs, filenames in self._walk_source():
                for f in filenames:
                    if f.startswith("test_") and f.endswith(".py"):
                        rel = os.path.relpath(os.path.join(root, f), self._path)
                        suites.append(rel)
                    elif f.endswith("_test.py"):
                        rel = os.path.relpath(os.path.join(root, f), self._path)
                        suites.append(rel)
                if os.path.basename(root) == "tests" and not suites:
                    suites.append(os.path.relpath(root, self._path) + "/")
        if language in ("javascript", "typescript"):
            for root, dirs, filenames in self._walk_source():
                for f in filenames:
                    if f.endswith(".test.js") or f.endswith(".test.ts") or f.endswith(".spec.js") or f.endswith(".spec.ts"):
                        rel = os.path.relpath(os.path.join(root, f), self._path)
                        suites.append(rel)
                if os.path.basename(root) == "__tests__" and not suites:
                    suites.append(os.path.relpath(root, self._path) + "/")
        if language in ("java", "kotlin"):
            for d in ("src/test", "src/test/java", "src/test/kotlin"):
                p = os.path.join(self._path, d)
                if os.path.isdir(p):
                    suites.append(d + "/")
        if build_system == "rust":
            p = os.path.join(self._path, "tests")
            if os.path.isdir(p):
                suites.append("tests/")
        return suites

    def _list_project_files(self) -> list[str]:
        """List project source files efficiently (single walk)."""
        files = []
        skip_extensions = {".pyc", ".pyo", ".so", ".dll", ".dylib", ".class", ".png", ".jpg", ".jpeg",
                           ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot"}
        try:
            for root, dirs, filenames in os.walk(self._path, topdown=True):
                rel_root = os.path.relpath(root, self._path)
                # Filter skip dirs in-place to prevent os.walk from descending
                _skip_dirs = {
                    ".git", "__pycache__", "node_modules", ".venv", ".venv_prod", "venv",
                    ".idea", ".vscode", "build", "dist", "target", ".gradle", ".m2",
                    ".ruff_cache", ".pytest_cache", ".hypothesis", ".deepeval",
                    ".egg-info", "site-packages", "__pycache__", ".opencode", ".github",
                    "AppData", "Application Data", "Local Settings",
                    "Microsoft", "Windows", "WinSxS", "assembly",
                    "System32", "SysWOW64", "Program Files", "Program Files (x86)",
                    "ProgramData", "All Users", "Common Files",
                    "ServiceState", "help", "PerfLogs", "Recovery",
                }
                dirs[:] = [d for d in dirs if d not in _skip_dirs and not d.startswith('.')]
                for f in filenames:
                    if os.path.splitext(f)[1].lower() in skip_extensions:
                        continue
                    full = os.path.join(rel_root, f) if rel_root != "." else f
                    files.append(full)
        except Exception:
            pass
        return files

    def _list_project_folders(self) -> list[str]:
        """List project source folders efficiently (single walk)."""
        folders = []
        try:
            for root, dirs, _ in os.walk(self._path, topdown=True):
                rel_root = os.path.relpath(root, self._path)
                _skip_dirs = {
                    ".git", "__pycache__", "node_modules", ".venv", ".venv_prod", "venv",
                    ".idea", ".vscode", "build", "dist", "target", ".gradle", ".m2",
                    ".ruff_cache", ".pytest_cache", ".hypothesis", ".deepeval",
                    ".egg-info", "site-packages", "__pycache__", ".opencode", ".github",
                    "AppData", "Application Data", "Local Settings",
                    "Microsoft", "Windows", "WinSxS", "assembly",
                    "System32", "SysWOW64", "Program Files", "Program Files (x86)",
                    "ProgramData", "All Users", "Common Files",
                    "ServiceState", "help", "PerfLogs", "Recovery",
                }
                dirs[:] = [d for d in dirs if d not in _skip_dirs and not d.startswith('.')]
                if rel_root != ".":
                    folders.append(rel_root)
        except Exception:
            pass
        return folders

    def _read_dependencies(self, language: str, package_manager: str) -> dict[str, list[str]]:
        deps: dict[str, list[str]] = {}
        try:
            if package_manager in ("npm", "yarn", "pnpm"):
                pkg_file = self._path / "package.json"
                if pkg_file.exists():
                    pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
                    deps["dependencies"] = list(pkg.get("dependencies", {}).keys())
                    deps["devDependencies"] = list(pkg.get("devDependencies", {}).keys())
            if package_manager == "pip":
                req_file = self._path / "requirements.txt"
                if req_file.exists():
                    lines = [l.strip() for l in req_file.read_text(encoding="utf-8").split("\n") if l.strip() and not l.startswith("#")]
                    deps["requirements"] = lines
            if package_manager in ("pip", "poetry"):
                pyproject = self._path / "pyproject.toml"
                if pyproject.exists():
                    txt = pyproject.read_text(encoding="utf-8")
                    import re
                    m = re.findall(r'^\s*"?([a-zA-Z0-9_-]+)"?\s*[=~><]', txt, re.MULTILINE)
                    if m:
                        deps["pyproject"] = m
            if package_manager == "cargo":
                cargo_file = self._path / "Cargo.toml"
                if cargo_file.exists():
                    txt = cargo_file.read_text(encoding="utf-8")
                    import re
                    m = re.findall(r'^([a-zA-Z0-9_-]+)\s*=', txt, re.MULTILINE)
                    if m:
                        deps["cargo"] = m
            if build_system := self._detect_build_system() in ("gradle",):
                gradle_file = self._path / "build.gradle"
                if not gradle_file.exists():
                    gradle_file = self._path / "build.gradle.kts"
                if gradle_file.exists():
                    txt = gradle_file.read_text(encoding="utf-8")
                    import re
                    m = re.findall(r"implementation\s+['\"]([^'\"]+)['\"]", txt)
                    if m:
                        deps["gradle"] = m
        except Exception as e:
            logger.debug("dependency parsing failed: %s", e)
        return deps

    def summary(self) -> dict:
        pm = self.get_project_map()
        return {
            "project": pm.root,
            "language": pm.language,
            "framework": pm.framework,
            "build_system": pm.build_system,
            "package_manager": pm.package_manager,
            "files": len(pm.files),
            "folders": len(pm.folders),
            "entry_points": pm.entry_points,
            "test_suites": len(pm.test_suites),
            "docker": pm.docker,
            "ci": pm.ci_config,
            "git_branch": pm.active_branch,
        }

    def show_structure(self, max_depth: int = 3) -> list[str]:
        lines: list[str] = []
        root_name = self._path.name
        lines.append(f"{root_name}/")
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", ".venv_prod", "venv", ".idea", ".vscode", "build", "dist", "target", ".gradle", ".m2", ".ruff_cache", ".pytest_cache", "AppData", "Microsoft", "Windows", "Program Files", "Program Files (x86)", "ProgramData"}
        skip_extensions = {".pyc", ".pyo"}

        def _walk(dir_path: Path, depth: int):
            if depth > max_depth:
                return
            try:
                entries = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError:
                return
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                if entry.name in skip_dirs:
                    continue
                if entry.is_dir():
                    indent = "  " * depth
                    lines.append(f"{indent}{entry.name}/")
                    _walk(entry, depth + 1)
                elif entry.suffix not in skip_extensions:
                    indent = "  " * depth
                    lines.append(f"{indent}{entry.name}")

        _walk(self._path, 1)
        return lines
