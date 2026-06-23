from __future__ import annotations
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CodeIndex:
    symbols: dict[str, list[dict]] = field(default_factory=dict)
    files: dict[str, dict] = field(default_factory=dict)
    last_built: float = 0.0
    stale: bool = True

    def needs_refresh(self, cwd: str) -> bool:
        if self.stale:
            return True
        if time.time() - self.last_built > 300:
            return True
        return False

    def refresh(self, cwd: str):
        self.symbols.clear()
        self.files.clear()
        try:
            from core.repository_analyzer import RepositoryAnalyzer
            analyzer = RepositoryAnalyzer(cwd)
            analyzer.analyze()
            for path, info in analyzer.files.items():
                self.files[str(path)] = {
                    "path": str(path),
                    "lines": info.get("lines", 0),
                    "imports": info.get("imports", []),
                }
                for imp in info.get("imports", []):
                    self.symbols.setdefault(imp, []).append({"path": str(path), "type": "import"})
            for func, locations in analyzer.functions.items():
                for loc in locations:
                    self.symbols.setdefault(func, []).append({"path": loc.get("path", ""), "line": loc.get("line", 0), "type": "function"})
            self.last_built = time.time()
            self.stale = False
        except Exception as e:
            logger.warning("[CodeIndex] refresh failed: %s", e)
            self.last_built = time.time()


@dataclass
class SessionMemory:
    session_id: str
    cwd: str = ""
    last_commands: list[str] = field(default_factory=list)
    recent_files: list[str] = field(default_factory=list)
    current_task: str | None = None
    # Browser memory
    browser_last_url: str | None = None
    browser_last_title: str | None = None
    browser_last_action: str | None = None
    browser_history: list[str] = field(default_factory=list)


class ProjectContext:
    def __init__(self, cwd: str):
        self.cwd = str(Path(cwd).resolve())
        self.git_root: str | None = None
        self.branch: str = ""
        self.last_scan: float = 0.0
        self.languages: list[str] = []
        self.build_system: list[str] = []
        self.project_type: str = ""
        self.entrypoints: list[str] = []
        self.important_files: list[str] = []
        self.top_files: list[str] = []
        self.code_index = CodeIndex()

    def refresh(self):
        root = Path(self.cwd)
        self.git_root = self._detect_git_root(root)
        self.branch = self._detect_branch()
        self.top_files = [p.name + ("/" if p.is_dir() else "") for p in root.iterdir() if not p.name.startswith(".")][:30]
        self.languages = self._detect_languages(root)
        self.build_system = self._detect_build_system(root)
        self.project_type = self._detect_project_type()
        self.entrypoints = self._detect_entrypoints(root)
        self.important_files = self._detect_important_files(root)
        self.last_scan = time.time()

    def needs_refresh(self) -> bool:
        if time.time() - self.last_scan > 300:
            return True
        current_branch = self._detect_branch()
        if current_branch != self.branch:
            return True
        return False

    def _detect_git_root(self, root: Path) -> str | None:
        for parent in [root] + list(root.parents):
            if (parent / ".git").exists():
                return str(parent)
        return None

    def _detect_branch(self) -> str:
        if not self.git_root:
            return ""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=self.git_root,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _detect_languages(self, root: Path) -> list[str]:
        exts: dict[str, int] = {}
        try:
            for f in root.iterdir():
                if f.is_file() and "." in f.name:
                    ext = f.name.rsplit(".", 1)[1].lower()
                    lang_map = {
                        "py": "python", "js": "javascript", "ts": "typescript",
                        "tsx": "typescript", "jsx": "javascript", "rs": "rust",
                        "go": "go", "java": "java", "kt": "kotlin",
                        "dart": "dart", "yaml": "yaml", "yml": "yaml",
                        "json": "json", "md": "markdown", "toml": "toml",
                        "html": "html", "css": "css", "scss": "scss",
                    }
                    lang = lang_map.get(ext)
                    if lang:
                        exts[lang] = exts.get(lang, 0) + 1
        except Exception:
            pass
        return sorted(exts, key=exts.get, reverse=True)[:5]

    def _detect_build_system(self, root: Path) -> list[str]:
        systems = []
        markers = {
            "pyproject.toml": "poetry",
            "requirements.txt": "pip",
            "package.json": "npm",
            "yarn.lock": "yarn",
            "pnpm-lock.yaml": "pnpm",
            "Cargo.toml": "cargo",
            "build.gradle": "gradle",
            "pom.xml": "maven",
            "pubspec.yaml": "pub",
            "go.mod": "go",
        }
        for fname, system in markers.items():
            if (root / fname).exists():
                systems.append(system)
        return systems

    def _detect_project_type(self) -> str:
        langs = self.languages
        builds = self.build_system
        parts = []
        if "python" in langs:
            if "poetry" in builds:
                parts.append("python")
            else:
                parts.append("python")
        if "typescript" in langs or "javascript" in langs:
            if any(b in builds for b in ("npm", "yarn", "pnpm")):
                parts.append("nextjs" if (Path(self.cwd) / "next.config.js").exists() or (Path(self.cwd) / "next.config.ts").exists() else "node")
        if "dart" in langs:
            parts.append("flutter")
        if "java" in langs or "kotlin" in langs:
            parts.append("android" if "gradle" in builds else "java")
        if "rust" in langs:
            parts.append("rust")
        return "_".join(parts) if parts else "unknown"

    def _detect_entrypoints(self, root: Path) -> list[str]:
        candidates = [
            "jarvis.py", "main.py", "app.py", "cli.py",
            "core/main.py", "src/main.py",
            "package.json", "pyproject.toml",
            "web/src/app/page.tsx", "web/src/pages/index.tsx",
            "index.ts", "index.js", "server.ts", "server.js",
            "lib/main.dart", "bin/main.dart",
        ]
        found = []
        for c in candidates:
            if (root / c).exists():
                found.append(c)
        return found

    def _detect_important_files(self, root: Path) -> list[str]:
        important = [
            "README.md", "CONTRIBUTING.md", "CHANGELOG.md",
            "pyproject.toml", "package.json", "Cargo.toml",
            "build.gradle", "pom.xml", "go.mod",
            "docker-compose.yml", "Dockerfile",
            ".env.example", "Makefile",
        ]
        return [f for f in important if (root / f).exists()]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cwd": self.cwd,
            "git_root": self.git_root,
            "branch": self.branch,
            "languages": self.languages,
            "build_system": self.build_system,
            "project_type": self.project_type,
            "entrypoints": self.entrypoints,
            "important_files": self.important_files,
            "files": self.top_files,
        }


class ContextManager:
    def __init__(self):
        self.sessions: dict[str, SessionMemory] = {}
        self.contexts: dict[str, ProjectContext] = {}
        self.browser_sessions: dict[str, Any] = {}

    def get_or_create_browser_session(self, session_id: str) -> Any:
        """Get or create a browser session for the given session_id.
        Returns the BrowserSession object from core.browser_manager.
        """
        if session_id in self.browser_sessions:
            return self.browser_sessions[session_id]
        from core.browser_manager import BrowserManager
        bm = BrowserManager.instance()
        session = bm.get_or_create_session(session_id)
        self.browser_sessions[session_id] = session
        return session

    def get_or_create_context(self, cwd: str) -> ProjectContext:
        resolved = str(Path(cwd).resolve())
        for ctx in self.contexts.values():
            if ctx.cwd == resolved:
                if ctx.needs_refresh():
                    ctx.refresh()
                return ctx
        ctx = ProjectContext(resolved)
        ctx.refresh()
        self.contexts[resolved] = ctx
        return ctx

    def get_session(self, session_id: str) -> SessionMemory:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionMemory(session_id=session_id)
        return self.sessions[session_id]

    def update_session_context(self, session_id: str, cwd: str):
        session = self.get_session(session_id)
        session.cwd = cwd

    def update_project_context(self, cwd: str):
        ctx = self.get_or_create_context(cwd)
        ctx.refresh()
        return ctx


# Singleton
_context_manager = None


def get_context_manager() -> ContextManager:
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager


def get_project_context(cwd: str) -> dict[str, Any]:
    cm = get_context_manager()
    ctx = cm.get_or_create_context(cwd)
    return ctx.to_dict()
