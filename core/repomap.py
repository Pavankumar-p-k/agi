"""Build a compact structural map of the codebase for injection into agent prompts.

Aider's key differentiator: the model gets a bird's-eye view of every file,
its symbols, and dependencies — without reading full file contents.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_RE_CLS = re.compile(r"^\s*(?:export\s+)?(?:abstract\s+|sealed\s+)?(?:class|struct|interface|trait|type)\s+(\w+)", re.MULTILINE)
_RE_FN = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:fn|function|def|func)\s+(\w+)", re.MULTILINE)
_RE_CONST = re.compile(r"^\s*(?:export\s+)?(?:const|let|var|val)\s+(\w+)", re.MULTILINE)
_RE_IMPORT = re.compile(r"^\s*(?:import|from|use|require|include)\s+[\"']?([a-zA-Z0-9_.-/]+)", re.MULTILINE)


IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".tox", ".eggs", "dist", "build", ".ruff_cache", ".mypy_cache",
    ".pytest_cache", "__pycache__", ".opencode", ".cursor", ".vscode",
}

SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java",
                     ".rb", ".php", ".swift", ".kt", ".scala", ".c", ".h",
                     ".cpp", ".hpp", ".cs", ".m", ".mm"}


def _parse_py_file(text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    classes = []
    functions = []
    constants = []
    imports = []
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id.isupper():
                        constants.append(t.id)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
    except SyntaxError:
        pass
    return classes, functions, constants, imports


def _parse_generic_file(text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    classes = list(set(_RE_CLS.findall(text)))
    functions = list(set(_RE_FN.findall(text)))
    constants = list(set(_RE_CONST.findall(text)))
    imports = list(set(_RE_IMPORT.findall(text)))
    return classes, functions, constants, imports


def _parse_file(text: str, ext: str) -> tuple[list[str], list[str], list[str], list[str]]:
    if ext == ".py":
        return _parse_py_file(text)
    return _parse_generic_file(text)


def build_repomap(workspace_root: str | Path, max_files: int = 80) -> str:
    import os
    root = Path(workspace_root).resolve()
    lines = []
    file_count = 0

    files_to_map = []
    try:
        for dirpath, dirnames, filenames in os.walk(str(root)):
            # Prune ignored dirs in-place so os.walk skips them
            dirnames[:] = [
                d for d in dirnames
                if d not in IGNORE_DIRS and not d.startswith(".")
            ]
            for fname in sorted(filenames):
                if fname.startswith("."):
                    continue
                fpath = os.path.join(dirpath, fname)
                ext = os.path.splitext(fname)[1]
                if ext not in SOURCE_EXTENSIONS:
                    continue
                if len(files_to_map) >= max_files:
                    break
                files_to_map.append(fpath)
            if len(files_to_map) >= max_files:
                break
    except Exception as e:
        logger.warning("repomap walk failed: %s", e)

    for fpath in files_to_map:
        if file_count >= max_files:
            break
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as _fh:
                text = _fh.read()
        except Exception:
            continue
        rel = os.path.relpath(fpath, str(root))
        ext = os.path.splitext(fpath)[1]
        classes, functions, constants, imports = _parse_file(text, ext)
        symbols = []
        if classes:
            symbols.append(f"cls:{','.join(classes)}")
        if functions:
            symbols.append(f"fn:{','.join(functions)}")
        if constants:
            symbols.append(f"const:{','.join(constants)}")
        imp_str = ""
        if imports:
            imp_str = f" imports:{','.join(imports[:8])}"
        line_count = len(text.split("\n"))
        symbol_str = " ".join(symbols) if symbols else "no symbols"
        lines.append(f"{rel} ({line_count}L) [{symbol_str}]{imp_str}")
        file_count += 1

    if not lines:
        return ""

    header = f"## Repomap ({file_count} files in {root.name}/)"
    return header + "\n" + "\n".join(lines)
