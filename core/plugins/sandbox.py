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
from __future__ import annotations

import logging

from core.plugins.base import Plugin

logger = logging.getLogger(__name__)

# Safe stdlib modules that plugins are always allowed to use
STDLIB_ALLOWED: set[str] = {
    "json", "logging", "re", "datetime", "typing", "uuid", "math", "random",
    "collections", "itertools", "functools", "enum", "dataclasses", "pathlib",
    "threading", "time", "abc", "decimal", "hashlib", "copy", "textwrap",
    "asyncio",
}

# Project package prefixes that first-party plugins may import
PROJECT_PREFIXES: set[str] = {
    "core.", "assistant.", "pc_agent.", "governance.", "memory.", "tools.",
    "brain.", "channels.", "plugins.", "jarvis.",
}

# Combined for the runtime check (top-level packages only)
DEFAULT_ALLOWED_MODULES: set[str] = STDLIB_ALLOWED | {
    p.rstrip(".") for p in PROJECT_PREFIXES
}


def _is_allowed_module(module: str) -> bool:
    """Check if a fully-qualified module name is allowed."""
    if module in ("__future__",):
        return True
    top = module.split(".")[0]
    if top in STDLIB_ALLOWED:
        return True
    for prefix in PROJECT_PREFIXES:
        if module.startswith(prefix):
            return True
    return False


def check_plugin_imports(plugin: Plugin, allowed: set[str] | None = None) -> list[str]:
    """Check that a plugin's global imports are in the allowed set.

    Returns a list of disallowed module names (empty = all clean).
    Does NOT raise — the caller decides what to do (warn / reject).
    """
    if allowed is None:
        allowed = DEFAULT_ALLOWED_MODULES

    disallowed: list[str] = []
    for attr_name in dir(plugin):
        if attr_name.startswith("_"):
            continue
        obj = getattr(plugin, attr_name, None)
        if obj is None:
            continue
        mod = getattr(obj, "__module__", None) or ""
        if not mod:
            continue
        top = mod.split(".")[0]
        if top in allowed:
            continue
        if _is_allowed_module(mod):
            continue
        disallowed.append(mod)
    return sorted(set(disallowed))


def validate_manifest_imports(manifest_path: str) -> list[str]:
    """Read a plugin source file and check all imports against allowed list.

    Lightweight static check — does NOT execute the plugin.
    Walks the entire AST including inside function bodies.

    Detects:
      - ``import X`` / ``from X import Y``
      - ``__import__('X')``
      - ``importlib.import_module('X')``
    """
    import ast

    try:
        with open(manifest_path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except SyntaxError as e:
        logger.warning("[Sandbox] Syntax error in %s: %s", manifest_path, e)
        return []

    disallowed: list[str] = []

    def _check_name(name: str):
        if not _is_allowed_module(name):
            disallowed.append(name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_name(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                _check_name(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            # __import__('os')
            if isinstance(func, ast.Name) and func.id == "__import__":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        _check_name(arg.value)
            # importlib.import_module('os')
            if (isinstance(func, ast.Attribute)
                    and func.attr == "import_module"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "importlib"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        _check_name(arg.value)
    return sorted(set(disallowed))
