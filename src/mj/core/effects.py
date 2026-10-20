"""Declared effects: what a capability's code actually touches.

The word-matching power rule (web/browser/shell in id/type/scopes) only
catches honest naming — a capability called "helper" that shells out passes
any name check. Manifests therefore *declare* effects, and this module is the
enforcement side (docs/09 §3):

  * vocabulary + power→effect cross-check + sensitive-effect risk floor are
    enforced by registry.validate_manifest at registration,
  * the runner denies sensitive effects from every trust level but the local
    terminal at runtime (defense in depth: a legacy or compromised row that
    skipped registration still cannot act),
  * scan_source finds the same effects by AST inspection without executing
    anything, so the lint test fails if code imports subprocess or a network
    library without declaring the effect.

Declared but unused effects are allowed (conservative declarations cost
nothing); used-but-undeclared effects are the violation that matters.
"""

from __future__ import annotations

import ast

# Vocabulary: what a capability may declare itself to touch.
EFFECTS = (
    "filesystem.read",  # reads files/directories it is given or its own area
    "filesystem.write",  # moves, creates or deletes files
    "network",  # opens network connections (HTTP, sockets, ...)
    "process",  # executes other processes (subprocess, os.system, ...)
    "secrets",  # reads credentials, tokens, keychains
)

# Sensitive effects: risk floor at registration, local-terminal-only at runtime.
SENSITIVE_EFFECTS = frozenset({"network", "process", "secrets"})

# A sensitive power implies a corresponding effect; validate_manifest rejects
# a manifest that declares the power but not the effect.
POWER_EFFECTS = {"shell": "process", "web": "network", "browser": "network"}

# Sensitive effects can never be a silent R0 read: minimum risk class.
MIN_RISK_FOR_EFFECT = {"network": "R1", "process": "R1", "secrets": "R3"}

# Imports that imply an effect (top-level module name -> effect).
IMPORT_EFFECTS: dict[str, str | None] = {
    "subprocess": "process",
    "multiprocessing": "process",
    "socket": "network",
    "ssl": "network",
    "urllib": "network",
    "http": "network",
    "ftplib": "network",
    "smtplib": "network",
    "poplib": "network",
    "imaplib": "network",
    "telnetlib": "network",
    "requests": "network",
    "httpx": "network",
    "aiohttp": "network",
    "keyring": "secrets",
}

# os module functions that execute other processes (os.replace etc. do not).
_OS_PROCESS_CALLS = {
    "system", "popen",
    "spawnl", "spawnle", "spawnlp", "spawnlpe",
    "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "execl", "execle", "execlp", "execlpe",
    "execv", "execve", "execvp", "execvpe",
}


def scan_source(source: str) -> set[str]:
    """Effects detectable in Python source by AST inspection (never executed)."""
    found: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                effect = IMPORT_EFFECTS.get(alias.name.split(".")[0])
                if effect:
                    found.add(effect)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                effect = IMPORT_EFFECTS.get(node.module.split(".")[0])
                if effect:
                    found.add(effect)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr in _OS_PROCESS_CALLS
        ):
            found.add("process")
    return found


def lint_module(module_name: str, declared_effects: set[str]) -> list[str]:
    """Human-readable violations: effects the module's code uses but the
    manifest does not declare. Importing a module here executes its top level
    (as pytest does anyway); the scan itself never runs the offending code."""
    import importlib
    import inspect

    module = importlib.import_module(module_name)
    source = inspect.getsource(module)
    undeclared = scan_source(source) - set(declared_effects)
    return sorted(
        f"{module_name} uses effect {effect!r} but the manifest does not declare it"
        for effect in undeclared
    )
