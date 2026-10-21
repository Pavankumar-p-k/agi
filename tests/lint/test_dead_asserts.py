"""Lint: an assertion that can never fail must not exist.

``assert X or True`` is unconditionally true — a test that cannot fail. The
second review found two of them (tests/unit/test_world.py and
tests/adversarial/test_adversarial.py) and asked for a lint so the pattern
cannot come back. This is that lint: any ``or True`` anywhere under ``tests/``,
``src/`` or ``tools/`` fails the suite.

The check is AST-based, not text-based: a *string* containing "or True"
(e.g. the detection fixtures below) is data, not an expression, so the lint
itself can prove both that it catches the pattern and that it stays quiet
on legitimate ``or`` usage.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root (tests/lint/ -> root)
SCAN_DIRS = ("tests", "src", "tools")


def violations(source: str, filename: str = "<source>") -> list[str]:
    """Return every `... or True` occurrence in `source` as file:line strings."""
    out: list[str] = []
    tree = ast.parse(source, filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            if any(isinstance(v, ast.Constant) and v.value is True for v in node.values):
                out.append(
                    f"{filename}:{node.lineno}: `or True` makes this expression "
                    "unconditionally true — a check that can never fail"
                )
    return out


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for name in SCAN_DIRS:
        files.extend(sorted((ROOT / name).rglob("*.py")))
    return files


def test_repository_contains_no_or_true():
    """The real scan: the whole repo must be clean of the pattern."""
    hits: list[str] = []
    for path in _scanned_files():
        rel = path.relative_to(ROOT).as_posix()
        hits.extend(violations(path.read_text(encoding="utf-8"), rel))
    assert hits == [], "\n" + "\n".join(hits)


def test_lint_detects_the_pattern_and_ignores_legit_or():
    """Self-test: the rule must be able to fail (catch the bad, spare the good)."""
    bad_assert = "assert any(x) or True\n"
    assert violations(bad_assert)

    bad_bool = "ready = flag or True\n"
    assert violations(bad_bool)

    leading_form = "assert True or expensive_check()\n"
    assert violations(leading_form)

    good = (
        "assert any(x) or any(y)\n"
        "assert flag or default\n"
        "if ready or maybe:\n"
        "    pass\n"
        "assert 'or True' not in text  # data, not an expression\n"
    )
    assert violations(good) == []
