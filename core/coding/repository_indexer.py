"""Repository indexing for the Coding AI specialist."""
from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


_DEFAULT_EXCLUDES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
}

_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".md": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".css": "css",
    ".html": "html",
}


@dataclass
class FileEntry:
    path: str
    language: str = "unknown"
    size_bytes: int = 0
    line_count: int = 0
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)
    function_names: list[str] = field(default_factory=list)
    sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RepositoryIndexer:
    """Indexes source files and extracts lightweight symbols/imports."""

    def __init__(
        self,
        path: str | os.PathLike[str] = ".",
        db_path: str | os.PathLike[str] | None = None,
        excludes: set[str] | None = None,
    ):
        self.root = Path(path).resolve()
        self.db_path = Path(db_path) if db_path else self.root / ".jarvis_coding_index.db"
        self.excludes = set(_DEFAULT_EXCLUDES)
        if excludes:
            self.excludes.update(excludes)
        self.entries: dict[str, FileEntry] = {}
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def _should_skip(self, path: Path) -> bool:
        parts = set(path.parts)
        if parts & self.excludes:
            return True
        return any(fnmatch.fnmatch(path.name, pattern) for pattern in ("*.pyc", "*.pyo", "*.db", "*.sqlite", "*.log"))

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _iter_files(self) -> list[Path]:
        files: list[Path] = []
        for current, dirs, names in os.walk(self.root):
            current_path = Path(current)
            dirs[:] = [d for d in dirs if d not in self.excludes]
            for name in names:
                path = current_path / name
                if self._should_skip(path):
                    continue
                if path.suffix.lower() in _LANGUAGES:
                    files.append(path)
        return sorted(files)

    def _hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _extract_python(self, text: str) -> tuple[list[str], list[str], list[str], list[str]]:
        imports: list[str] = []
        exports: list[str] = []
        classes: list[str] = []
        functions: list[str] = []
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return imports, exports, classes, functions
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
                exports.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
                exports.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        exports.append(target.id)
        return sorted(set(imports)), sorted(set(exports)), sorted(set(classes)), sorted(set(functions))

    def _entry_for(self, path: Path) -> FileEntry:
        data = path.read_bytes()
        text = data.decode("utf-8", errors="ignore")
        language = _LANGUAGES.get(path.suffix.lower(), "unknown")
        imports: list[str] = []
        exports: list[str] = []
        classes: list[str] = []
        functions: list[str] = []
        if language == "python":
            imports, exports, classes, functions = self._extract_python(text)
        return FileEntry(
            path=self._rel(path),
            language=language,
            size_bytes=len(data),
            line_count=0 if not text else text.count("\n") + (0 if text.endswith("\n") else 1),
            imports=imports,
            exports=exports,
            class_names=classes,
            function_names=functions,
            sha256=self._hash(data),
        )

    def _store(self, entry: FileEntry) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO files(path, sha256, payload) VALUES (?, ?, ?)",
                (entry.path, entry.sha256, json.dumps(entry.to_dict())),
            )

    def _get_cached(self, path: str) -> FileEntry | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT payload FROM files WHERE path = ?", (path,)).fetchone()
        if not row:
            return None
        return FileEntry(**json.loads(row[0]))

    def index(self, force: bool = False) -> dict[str, FileEntry]:
        self.entries = {}
        for file_path in self._iter_files():
            rel = self._rel(file_path)
            entry = None if force else self._get_cached(rel)
            if entry is None:
                entry = self._entry_for(file_path)
                self._store(entry)
            self.entries[rel] = entry
        return self.entries

    def incremental_index(self) -> dict[str, FileEntry]:
        return self.index(force=False)

    def get_entry(self, path: str) -> FileEntry | None:
        normalized = path.replace("\\", "/")
        if not self.entries:
            self.incremental_index()
        return self.entries.get(normalized) or self._get_cached(normalized)

    def all_entries(self) -> list[FileEntry]:
        if not self.entries:
            self.incremental_index()
        return list(self.entries.values())

    def search_by_export(self, name: str) -> list[FileEntry]:
        return [entry for entry in self.all_entries() if name in entry.exports or name in entry.class_names or name in entry.function_names]

    def search(self, query: str) -> list[FileEntry]:
        q = query.casefold()
        return [
            entry for entry in self.all_entries()
            if q in entry.path.casefold()
            or any(q in symbol.casefold() for symbol in entry.exports + entry.imports)
        ]

    def summary(self) -> dict[str, Any]:
        entries = self.all_entries()
        languages: dict[str, int] = {}
        for entry in entries:
            languages[entry.language] = languages.get(entry.language, 0) + 1
        return {
            "root": str(self.root),
            "files": len(entries),
            "languages": languages,
            "total_lines": sum(entry.line_count for entry in entries),
        }
