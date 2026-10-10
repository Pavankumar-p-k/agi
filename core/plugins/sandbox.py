# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""core.plugins.sandbox — static import validation for plugin entry points."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# Safe stdlib modules a plugin may import.
STDLIB_ALLOWED: set[str] = {
    "__future__", "abc", "argparse", "asyncio", "base64", "binascii",
    "bisect", "calendar", "collections", "contextlib", "contextvars",
    "copy", "csv", "dataclasses", "datetime", "decimal", "difflib",
    "enum", "functools", "gc", "gettext", "glob", "graphlib", "hashlib",
    "heapq", "html", "http", "importlib", "inspect", "io", "ipaddress",
    "itertools", "json", "keyword", "linecache", "locale", "logging",
    "math", "mimetypes", "numbers", "operator", "pathlib", "pickle",
    "platform", "pprint", "queue", "random", "re", "reprlib", "secrets",
    "select", "shlex", "shutil", "site", "string", "stringprep", "struct",
    "statistics", "sys", "tempfile", "textwrap", "threading", "time",
    "timeit", "token", "tokenize", "trace", "traceback", "tracemalloc",
    "types", "typing", "unicodedata", "unittest", "urllib", "uuid",
    "warnings", "weakref", "webbrowser", "xml", "zipfile", "zipimport",
    "zlib",
}

# Internal projects packages plugins are allowed to import.
_PROJECT_ALLOWED: set[str] = {
    "core.plugins.base", "core.privacy_classifier", "assistant.wake_word",
    "pc_agent.computer_agent", "governance.GovernanceValidator",
    "memory.embedding_memory", "tools.search_tool",
}

# Modules that are always denied regardless of stdlib status.
_ALWAYS_DENIED: dict[str, str | None] = {
    "os": None, "subprocess": None, "socket": None, "requests": None,
    "httpx": None, "ctypes": None, "multiprocessing": None,
}


def _top_level(module: str) -> str:
    return module.split(".")[0]


def _collect_imports(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _dynamic_import_names(tree: ast.AST) -> set[str]:
    """Catch `__import__("x")` and `importlib.import_module("x")` literal calls."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            target: str | None = None
            if isinstance(func, ast.Name) and func.id == "__import__":
                target = "dot"
            elif isinstance(func, ast.Attribute) and func.attr == "import_module":
                if isinstance(func.value, ast.Name) and func.value.id == "importlib":
                    target = "dot"
            if target and isinstance(node.args[0].value, str):
                names.add(node.args[0].value)
    return names


def validate_manifest_imports(path: str | Path) -> list[str]:
    """Return a sorted list of disallowed top-level module names imported by *path*."""
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return []

    disallowed: set[str] = set()
    project_roots: set[str] = {"core", "channels", "assistant", "memory", "tools",
                               "governance", "pc_agent", "monitors", "brain", "plugins",
                               "api", "routers", "notifications", "vision", "network"}
    for module in _collect_imports(tree) | _dynamic_import_names(tree):
        top = _top_level(module)
        if top in disallowed:
            continue
        if module in _PROJECT_ALLOWED or top in project_roots:
            continue
        if top in _ALWAYS_DENIED:
            disallowed.add(top)  # dynamic import of denied module
        elif top in STDLIB_ALLOWED:
            # `importlib` alone is safe; dynamic use is caught separately above.
            continue
        elif top in sys.stdlib_module_names:
            # allowlist is the strict sandbox; anything else in stdlib is denied
            disallowed.add(top)
        else:
            # Not stdlib and not in the approved project set -> third-party, denied
            disallowed.add(top)
    return sorted(disallowed)


def check_plugin_imports(path: str | Path) -> tuple[bool, list[str]]:
    disallowed = validate_manifest_imports(path)
    return (not disallowed, disallowed)


__all__ = ["STDLIB_ALLOWED", "validate_manifest_imports", "check_plugin_imports"]
