"""RepositoryIndexer — persistent SQLite-backed file index with imports/exports extraction.

Builds on WorkspaceManager scanning to produce a queryable index
of every source file: imports, exports, class/function names, line counts.
Cache lives in data/repo_index.db for fast incremental re-indexing.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)

_DEFAULT_DB = str(Path("data") / "repo_index.db")


@dataclass
class FileEntry:
    path: str
    language: str
    line_count: int
    size_bytes: int
    last_modified: float
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)
    function_names: list[str] = field(default_factory=list)
    tokens: dict[str, list[str]] = field(default_factory=dict)


_SOURCE_EXTS: dict[str, set[str]] = {
    "python": {".py"},
    "typescript": {".ts", ".tsx"},
    "javascript": {".js", ".jsx"},
    "java": {".java"},
    "kotlin": {".kt", ".kts"},
    "rust": {".rs"},
    "go": {".go"},
    "ruby": {".rb"},
    "php": {".php"},
    "swift": {".swift"},
    "csharp": {".cs"},
    "cpp": {".cpp", ".cc", ".cxx", ".hpp", ".hxx"},
    "c": {".c", ".h"},
}


def _detect_language(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    for lang, exts in _SOURCE_EXTS.items():
        if ext in exts:
            return lang
    return "unknown"


# ── Import parsers ──────────────────────────────────────────────

_PY_IMPORT_RE = re.compile(
    r'^(?:from\s+([a-zA-Z0-9_.]+)\s+import|import\s+(?:[a-zA-Z0-9_.]+(?:\s+as\s+\w+)?(?:\s*,\s*[a-zA-Z0-9_.]+(?:\s+as\s+\w+)?)*))',
    re.MULTILINE,
)


def _parse_py_imports(content: str) -> list[str]:
    imports: list[str] = []
    for m in _PY_IMPORT_RE.finditer(content):
        if m.group(1):
            imports.append(m.group(1))
        else:
            rest = m.group(0)[7:]
            for part in rest.split(","):
                imports.append(part.strip().split(" ")[0])
    return imports


_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:\{[^}]*\}|\*\s+as\s+\w+|\w+(?:,\s*\w+)?)\s+from\s+['"]([^'"]+)|require\s*\(\s*['"]([^'"]+)['"])""",
)


def _parse_js_imports(content: str) -> list[str]:
    imports: list[str] = []
    for m in _JS_IMPORT_RE.finditer(content):
        imp = m.group(1) or m.group(2)
        if imp.startswith(".") or imp.startswith("/"):
            imports.append(imp)
        else:
            imports.append(imp.split("/")[0])
    return imports


_JAVA_IMPORT_RE = re.compile(r'^import\s+([a-zA-Z0-9_.]+)\s*;', re.MULTILINE)


def _parse_java_imports(content: str) -> list[str]:
    return [m.group(1).split(".")[0] for m in _JAVA_IMPORT_RE.finditer(content)]


def _parse_rust_imports(content: str) -> list[str]:
    imports: list[str] = []
    for line in content.split("\n"):
        s = line.strip()
        if s.startswith("use ") and ";" in s:
            imp = s[4:].split(";")[0].split("::")[0]
            imports.append(imp)
        elif s.startswith("extern crate") and ";" in s:
            imp = s[13:].strip().strip(";").split(" ")[0]
            imports.append(imp)
    return imports


def _parse_go_imports(content: str) -> list[str]:
    imports: list[str] = []
    for m in re.finditer(r'["]([a-zA-Z0-9_./-]+)["]', content):
        imp = m.group(1)
        parts = imp.split("/")
        if len(parts) >= 2:
            imports.append(parts[0] + "/" + parts[1])
        else:
            imports.append(imp)
    return imports


_IMPORT_PARSERS: dict[str, callable] = {
    "python": _parse_py_imports,
    "javascript": _parse_js_imports,
    "typescript": _parse_js_imports,
    "java": _parse_java_imports,
    "kotlin": _parse_java_imports,
    "rust": _parse_rust_imports,
    "go": _parse_go_imports,
}


def _parse_imports(content: str, language: str) -> list[str]:
    parser = _IMPORT_PARSERS.get(language)
    if parser:
        return parser(content)
    return []


# ── Export / definition parsers ─────────────────────────────────

_PY_EXPORT_RE = re.compile(
    r'^[ \t]*(?:class\s+(\w+)|(?:async\s+)?def\s+(\w+)|([A-Z_][A-Z0-9_]*)\s*=)',
    re.MULTILINE,
)


def _parse_py_exports(content: str) -> tuple[list[str], list[str], list[str]]:
    classes: list[str] = []
    functions: list[str] = []
    constants: list[str] = []
    for m in _PY_EXPORT_RE.finditer(content):
        if m.group(1):
            classes.append(m.group(1))
        elif m.group(2):
            functions.append(m.group(2))
        elif m.group(3):
            constants.append(m.group(3))
    return classes, functions, constants


_JS_EXPORT_RE = re.compile(
    r'(?:export\s+(?:default\s+)?)?(?:class\s+(\w+)|function\s+(\w+)|const\s+(\w+))',
)


def _parse_js_exports(content: str) -> tuple[list[str], list[str], list[str]]:
    classes: list[str] = []
    functions: list[str] = []
    constants: list[str] = []
    for m in _JS_EXPORT_RE.finditer(content):
        if m.group(1):
            classes.append(m.group(1))
        elif m.group(2):
            functions.append(m.group(2))
        elif m.group(3):
            constants.append(m.group(3))
    return classes, functions, constants


_JAVA_EXPORT_RE = re.compile(
    r'(?:public\s+|private\s+|protected\s+)?(?:static\s+)?(?:class|interface|enum|record)\s+(\w+)',
)


def _parse_java_exports(content: str) -> tuple[list[str], list[str], list[str]]:
    classes = [m.group(1) for m in _JAVA_EXPORT_RE.finditer(content)]
    return classes, [], []


_EXPORT_PARSERS: dict[str, callable] = {
    "python": _parse_py_exports,
    "javascript": _parse_js_exports,
    "typescript": _parse_js_exports,
    "java": _parse_java_exports,
    "kotlin": _parse_java_exports,
}


def _parse_exports(content: str, language: str) -> tuple[list[str], list[str], list[str]]:
    parser = _EXPORT_PARSERS.get(language)
    if parser:
        return parser(content)
    return [], [], []


def _resolve_import_path(imp: str, filepath: str) -> str:
    """Resolve a relative import to an absolute file path (no extension)."""
    if imp.startswith(".") or imp.startswith("/"):
        dir_part = os.path.dirname(filepath)
        candidate = os.path.normpath(os.path.join(dir_part, imp))
        return candidate
    return imp


# ── RepositoryIndexer ───────────────────────────────────────────


class RepositoryIndexer:
    """Build and query a persistent index of repository source files.

    Walks source files, extracts imports/exports/class/function names,
    and stores them in a SQLite cache for fast re-indexing.
    """

    def __init__(
        self,
        workspace: WorkspaceManager | None = None,
        path: str | Path | None = None,
        db_path: str | None = None,
    ):
        self.ws = workspace or WorkspaceManager(path)
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()
        self._index: dict[str, FileEntry] = {}

    # ── Database ────────────────────────────────────────────────

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS repo_index (
                    path TEXT PRIMARY KEY,
                    language TEXT NOT NULL,
                    line_count INTEGER NOT NULL DEFAULT 0,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    last_modified REAL NOT NULL DEFAULT 0,
                    imports_json TEXT DEFAULT '[]',
                    exports_json TEXT DEFAULT '[]',
                    class_names_json TEXT DEFAULT '[]',
                    function_names_json TEXT DEFAULT '[]',
                    tokens_json TEXT DEFAULT '{}',
                    indexed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_repo_language
                    ON repo_index(language);
            """)

    def _clear_cache(self) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM repo_index")

    # ── Indexing ─────────────────────────────────────────────────

    def index(self, force: bool = False) -> dict[str, FileEntry]:
        """Full index of the repository. Returns path→FileEntry map."""
        pm = self.ws.get_project_map()
        skip_exts = {".pyc", ".pyo", ".class", ".png", ".jpg", ".jpeg",
                     ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot",
                     ".mp4", ".avi", ".mov", ".pdf", ".zip", ".tar", ".gz"}

        for filepath in pm.files:
            filepath = filepath.replace("\\", "/")
            _, ext = os.path.splitext(filepath)
            if ext.lower() in skip_exts:
                continue
            full = Path(pm.root) / filepath
            if not full.is_file():
                continue

            if not force:
                cached = self._get_cached(filepath)
                if cached is not None:
                    try:
                        stat = full.stat()
                        if stat.st_mtime <= cached.last_modified:
                            self._index[filepath] = cached
                            continue
                    except OSError:
                        pass

            try:
                stat = full.stat()
                content = full.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            language = _detect_language(filepath)
            imports = _parse_imports(content, language)
            classes, functions, constants = _parse_exports(content, language)
            exports = list(dict.fromkeys(classes + functions + constants))

            entry = FileEntry(
                path=filepath,
                language=language,
                line_count=len(content.split("\n")),
                size_bytes=stat.st_size,
                last_modified=stat.st_mtime,
                imports=imports,
                exports=exports,
                class_names=classes,
                function_names=functions,
                tokens={
                    "classes": classes,
                    "functions": functions,
                    "constants": constants,
                    "line_count": [str(len(content.split("\n")))],
                },
            )
            self._index[filepath] = entry
            self._cache_entry(entry)

        return self._index

    def incremental_index(self) -> dict[str, FileEntry]:
        """Incremental index: only re-index changed files."""
        return self.index(force=False)

    # ── Cache read/write ─────────────────────────────────────────

    def _get_cached(self, path: str) -> FileEntry | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT language, line_count, size_bytes, last_modified, "
                "imports_json, exports_json, class_names_json, function_names_json "
                "FROM repo_index WHERE path = ?",
                (path,),
            ).fetchone()
        if row is None:
            return None
        return FileEntry(
            path=path,
            language=row[0],
            line_count=row[1],
            size_bytes=row[2],
            last_modified=row[3],
            imports=json.loads(row[4]),
            exports=json.loads(row[5]),
            class_names=json.loads(row[6]),
            function_names=json.loads(row[7]),
        )

    def _cache_entry(self, entry: FileEntry) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO repo_index
                   (path, language, line_count, size_bytes, last_modified,
                    imports_json, exports_json, class_names_json,
                    function_names_json, tokens_json, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.path,
                    entry.language,
                    entry.line_count,
                    entry.size_bytes,
                    entry.last_modified,
                    json.dumps(entry.imports),
                    json.dumps(entry.exports),
                    json.dumps(entry.class_names),
                    json.dumps(entry.function_names),
                    json.dumps(entry.tokens),
                    now,
                ),
            )

    # ── Query ────────────────────────────────────────────────────

    def get_entry(self, filepath: str) -> FileEntry | None:
        normalized = filepath.replace("\\", "/")
        if normalized in self._index:
            return self._index[normalized]
        return self._get_cached(normalized)

    def search_by_export(self, name: str) -> list[FileEntry]:
        results: list[FileEntry] = []
        name_lower = name.lower()
        for entry in self._index.values():
            if any(name_lower == e.lower() for e in entry.exports):
                results.append(entry)
        return results

    def search_by_import(self, name: str) -> list[FileEntry]:
        results: list[FileEntry] = []
        name_lower = name.lower()
        for entry in self._index.values():
            if any(name_lower == i.lower() for i in entry.imports):
                results.append(entry)
        return results

    def files_by_language(self, language: str) -> list[FileEntry]:
        return [e for e in self._index.values() if e.language == language]

    def summary(self) -> dict:
        langs: dict[str, int] = {}
        total_lines = 0
        total_imports = 0
        total_exports = 0
        for entry in self._index.values():
            langs[entry.language] = langs.get(entry.language, 0) + 1
            total_lines += entry.line_count
            total_imports += len(entry.imports)
            total_exports += len(entry.exports)
        return {
            "files": len(self._index),
            "languages": langs,
            "total_lines": total_lines,
            "total_imports": total_imports,
            "total_exports": total_exports,
        }

    def get_all_entries(self) -> list[FileEntry]:
        return list(self._index.values())
