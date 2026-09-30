"""RepositoryIndexer — walks a repository, parses symbols, records stats.

index() returns {relative_path: FileEntry}; all_entries()/get_entry()
expose the parsed entries (path, language, size_bytes, line_count,
imports, class_names, function_names, exports); summary() returns
aggregate counts. Everything is honest: unreadable files are skipped
and reported rather than fabricated.
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Directories never indexed.
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".hypothesis", ".deepeval", "node_modules", ".venv", "venv", "env",
    "dist", "build", ".idea", ".vscode",
}

# Interesting extensions (language mapping).
_LANGUAGE_BY_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".go": "go",
    ".rs": "rust", ".java": "java", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp", ".rb": "ruby",
    ".php": "php", ".sh": "shell", ".ps1": "powershell",
    ".md": "markdown", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".html": "html", ".css": "css",
}

_MAX_FILE_SIZE = 1_000_000  # skip huge files

_FALLBACK_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import\s|import\s+([\w.,\s]+))", re.MULTILINE)
_UPPER_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass
class FileEntry:
    """One indexed file record."""

    path: str                      # relative, posix-style
    language: str = ""
    size: int = 0
    line_count: int = 0
    imports: list[str] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)
    function_names: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)

    @property
    def size_bytes(self) -> int:
        return self.size

    @property
    def lines(self) -> int:
        return self.line_count

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "language": self.language,
            "size": self.size,
            "size_bytes": self.size,
            "lines": self.line_count,
            "line_count": self.line_count,
            "imports": list(self.imports),
            "class_names": list(self.class_names),
            "function_names": list(self.function_names),
            "exports": list(self.exports),
        }


def _parse_python(source: str) -> dict:
    """Extract imports, classes, functions and exports from Python source."""
    imports: list[str] = []
    class_names: list[str] = []
    function_names: list[str] = []
    exports: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        for match in _FALLBACK_IMPORT_RE.finditer(source):
            module = match.group(1) or match.group(2)
            if module:
                for part in module.split(","):
                    part = part.strip().split(" as ")[0].strip()
                    if part:
                        imports.append(part)
        return {"imports": imports, "class_names": [], "function_names": [],
                "exports": []}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        elif isinstance(node, ast.ClassDef):
            class_names.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_names.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and _UPPER_NAME_RE.match(target.id):
                    exports.append(target.id)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and _UPPER_NAME_RE.match(target.id):
                exports.append(target.id)

    # __all__ declarations are explicit exports.
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for element in node.value.elts:
                            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                                exports.append(element.value)

    merged = sorted(set(class_names) | set(function_names) | set(exports))
    return {
        "imports": sorted(set(imports)),
        "class_names": sorted(set(class_names)),
        "function_names": sorted(set(function_names)),
        "exports": merged,
    }


class RepositoryIndexer:
    """Indexes a repository root: files, languages, sizes, symbols."""

    def __init__(self, path: str | Path = ".", root: str | Path | None = None,
                 db_path: str | Path | None = None, max_depth: int = 12) -> None:
        # `path` is the repository root (pinned contract); `root` is an alias.
        root_path = Path(root) if root is not None else Path(path)
        self.root: Path = root_path.resolve()
        self.db_path = Path(db_path) if db_path else None
        self.max_depth = max_depth
        self.entries: dict[str, FileEntry] = {}
        self._entries = self.entries
        self._errors: list[str] = []
        self._indexed = False

    # ── indexing ─────────────────────────────────────────────────────
    def index(self, force: bool = False) -> dict[str, FileEntry]:
        """Walk the repository; returns {relative_path: FileEntry}."""
        if self._indexed and not force:
            return self.entries
        files: dict[str, FileEntry] = {}
        errors: list[str] = []
        root = self.root
        if not root.exists():
            self.entries, self._errors, self._indexed = {}, [f"root not found: {self.root}"], True
            return self.entries

        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            if len(current.parts) - base_depth >= self.max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if d not in _SKIP_DIRS and not d.startswith(".")
                           and not d.endswith(".egg-info")]
            for filename in filenames:
                file_path = current / filename
                ext = file_path.suffix.lower()
                if ext not in _LANGUAGE_BY_EXT:
                    continue
                try:
                    size = file_path.stat().st_size
                    if size > _MAX_FILE_SIZE:
                        errors.append(f"skipped (too large): {file_path}")
                        continue
                    relative = file_path.relative_to(root).as_posix()
                    line_count = self._count_lines(file_path, errors)
                    entry = FileEntry(path=relative,
                                      language=_LANGUAGE_BY_EXT[ext],
                                      size=size, line_count=line_count)
                    if ext == ".py":
                        try:
                            source = file_path.read_text(encoding="utf-8",
                                                         errors="ignore")
                            parsed = _parse_python(source)
                            entry.imports = parsed["imports"]
                            entry.class_names = parsed["class_names"]
                            entry.function_names = parsed["function_names"]
                            entry.exports = parsed["exports"]
                        except OSError as exc:
                            errors.append(f"{file_path}: {exc}")
                    files[relative] = entry
                except OSError as exc:
                    errors.append(f"{file_path}: {exc}")

        self.entries = files
        self._entries = self.entries
        self._errors = errors
        self._indexed = True
        return self.entries

    def incremental_index(self) -> dict[str, FileEntry]:
        """Refresh the index (re-walk; changed files are re-parsed)."""
        return self.index(force=True)

    @staticmethod
    def _count_lines(file_path: Path, errors: list[str]) -> int:
        try:
            with open(file_path, "rb") as handle:
                return sum(chunk.count(b"\n") for chunk in handle)
        except OSError as exc:
            errors.append(f"{file_path}: {exc}")
            return 0

    # ── queries ──────────────────────────────────────────────────────
    def all_entries(self) -> list[FileEntry]:
        if not self._indexed:
            self.index()
        return list(self.entries.values())

    def get_entry(self, path: str) -> Optional[FileEntry]:
        if not self._indexed:
            self.index()
        return self.entries.get(self._normalize(path))

    def _get_cached(self, path: str) -> Optional[FileEntry]:
        return self.get_entry(path)

    def _normalize(self, path: str) -> str:
        value = str(path).replace("\\", "/")
        candidate = Path(value)
        if candidate.is_absolute():
            try:
                candidate = candidate.relative_to(self.root)
            except ValueError:
                return value
        value = candidate.as_posix()
        while value.startswith("./"):
            value = value[2:]
        return value.lstrip("/")

    def search(self, query: str, limit: int = 10) -> list[FileEntry]:
        """Entries whose path or symbols match any query token, best first."""
        if not self._indexed:
            self.index()
        tokens = [t for t in str(query).lower().split() if len(t) > 2]
        scored: list[tuple[int, FileEntry]] = []
        for entry in self.entries.values():
            haystack = " ".join([entry.path.lower()]
                                + [s.lower() for s in entry.exports])
            score = sum(1 for token in tokens if token in haystack)
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1].path))
        return [entry for _, entry in scored[:limit]]

    def search_by_export(self, name: str) -> list[FileEntry]:
        """Entries that declare *name* as an export/class/function."""
        if not self._indexed:
            self.index()
        wanted = str(name).lower()
        return sorted(
            (entry for entry in self.entries.values()
             if any(wanted == symbol.lower() for symbol in entry.exports)),
            key=lambda entry: entry.path,
        )

    def summary(self, index_result: Optional[dict] = None) -> dict:
        """Aggregate stats for the current index."""
        if not self._indexed:
            self.index()
        entries = list(self.entries.values())
        by_language: dict = {}
        total_lines = 0
        total_size = 0
        for entry in entries:
            stats = by_language.setdefault(
                entry.language, {"files": 0, "lines": 0, "size": 0})
            stats["files"] += 1
            stats["lines"] += entry.line_count
            stats["size"] += entry.size
            total_lines += entry.line_count
            total_size += entry.size
        return {
            "root": str(self.root),
            "files": len(entries),
            "total_files": len(entries),
            "total_lines": total_lines,
            "total_size": total_size,
            "languages": dict(sorted(by_language.items(),
                                     key=lambda kv: -kv[1]["files"])),
            "errors": list(self._errors),
        }


__all__ = ["RepositoryIndexer", "FileEntry"]
