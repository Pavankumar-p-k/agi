"""RepositoryIndexer — walks a repository and reports real structure stats.

index() returns file records; summary() returns aggregate counts and
language breakdown. Both are honest: unreadable files are skipped and
counted as errors rather than fabricated.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Directories never indexed.
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    "node_modules", ".venv", "venv", "env", "dist", "build",
    ".idea", ".vscode", "data/tmp_pytest",
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


class FileEntry:
    """One indexed file record."""

    def __init__(self, path: str, language: str, size: int,
                 lines: int) -> None:
        self.path = path
        self.language = language
        self.size = size
        self.lines = lines

    def to_dict(self) -> dict:
        return {"path": self.path, "language": self.language,
                "size": self.size, "lines": self.lines}


class RepositoryIndexer:
    """Indexes a repository root: files, languages, sizes, line counts."""

    def __init__(self, root: str = ".", max_depth: int = 12) -> None:
        self.root = str(Path(root).resolve())
        self.max_depth = max_depth

    def index(self, force: bool = False) -> dict:
        """Walk the repository; returns {'files': [...], 'errors': [...]}."""
        files: list = []
        errors: list = []
        root = Path(self.root)
        if not root.exists():
            return {"files": [], "errors": [f"root not found: {self.root}"]}

        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            if len(current.parts) - base_depth >= self.max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if d not in _SKIP_DIRS and not d.startswith(".")]
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
                    lines = 0
                    with open(file_path, "rb") as handle:
                        for chunk in handle:
                            lines += chunk.count(b"\n")
                    files.append(FileEntry(
                        path=str(file_path),
                        language=_LANGUAGE_BY_EXT[ext],
                        size=size,
                        lines=lines,
                    ))
                except OSError as exc:
                    errors.append(f"{file_path}: {exc}")
        return {"files": files, "errors": errors}

    def summary(self, index_result: Optional[dict] = None) -> dict:
        """Aggregate stats for an index() result (or a fresh index)."""
        result = index_result if index_result is not None else self.index()
        files = result.get("files", [])
        by_language: dict = {}
        total_lines = 0
        total_size = 0
        for entry in files:
            record = entry.to_dict() if isinstance(entry, FileEntry) else dict(entry)
            lang = record.get("language", "unknown")
            stats = by_language.setdefault(
                lang, {"files": 0, "lines": 0, "size": 0})
            stats["files"] += 1
            stats["lines"] += int(record.get("lines", 0))
            stats["size"] += int(record.get("size", 0))
            total_lines += int(record.get("lines", 0))
            total_size += int(record.get("size", 0))
        return {
            "root": self.root,
            "total_files": len(files),
            "total_lines": total_lines,
            "total_size": total_size,
            "languages": dict(sorted(by_language.items(),
                                     key=lambda kv: -kv[1]["files"])),
            "errors": list(result.get("errors", [])),
        }


__all__ = ["RepositoryIndexer", "FileEntry"]
