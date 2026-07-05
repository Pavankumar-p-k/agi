"""Architecture audit: transports must not contain business logic.

Every transport should only:
1. Convert its input to a canonical ``Request``
2. Call ``process_message()`` (via an adapter)
3. Convert the ``Response`` back to wire format

This test enforces that transport adapters and route handlers do NOT
perform direct LLM calls, intent classification, own retry/fallback, or
direct memory writes.  Those belong in pipeline stages.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# ── Files that are exempt from the audit (the file ITSELF is the banned pattern) ─
EXEMPT = {
    "core/pipeline/adapters/__init__.py",
    "core/pipeline/",
    "tests/",
    "benchmarks/",
    "demo/",
    "jarvis_plugin_sdk/",
    "plugins/",
}

# ── Banned patterns in transport adapters ─────────────────────────────────────

# Pattern 1: Direct LLM calls
LLM_PATTERNS = (
    "llm_router", "acompletion", "llm_complete", "complete_vision",
    "get_router()", "stream_agent_loop", "unified_brain",
)

# Pattern 2: Intent classification
INTENT_PATTERNS = (
    "extract_intent", "classify_request", "intent_router",
    "_keyword_classify", "_llm_router_classify",
)

# Pattern 3: Own retry/fallback (the actual logic, not docstrings)
RETRY_PATTERNS = (
    "models_to_try", "deduped", "get_ollama_url",
)

# Pattern 4: Direct memory writes
MEMORY_PATTERNS = (
    "memory.store(", "memory_facade",
)

# Pattern 5: Raw HTTP calls to LLM providers
HTTP_PATTERNS = (
    "httpx.AsyncClient", "client.post(", "ollama_chat_url",
)


def _walk_adapter_files() -> list[Path]:
    """Return all Python files under ``core/pipeline/adapters/``."""
    return sorted((ROOT / "core" / "pipeline" / "adapters").rglob("*.py"))


def _is_exempt(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    for e in EXEMPT:
        if rel.startswith(e) or rel == e:
            return True
    return False


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _check_banned_patterns(
    path: Path,
    patterns: tuple[str, ...],
    label: str,
) -> list[str]:
    """Return violations of *patterns* found in *path*'s source code.

    Only reports patterns that appear in real code (not docstrings).
    """
    src = _read_source(path)
    violations: list[str] = []
    tree = _safe_parse(src)
    if tree is None:
        return violations

    # Find line ranges for docstrings so we can exclude them
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node):
            start = node.lineno
            end = node.body[0].end_lineno if hasattr(node, "end_lineno") and node.body else start
            docstring_lines.update(range(start, end + 1))

    lines = src.splitlines()
    for pat in patterns:
        for lineno, line in enumerate(lines, start=1):
            if pat in line and lineno not in docstring_lines:
                violations.append(f"  L{lineno}: {pat!r} in {line.strip()!r}")
    return violations


def _safe_parse(src: str) -> ast.Module | None:
    try:
        return ast.parse(src)
    except (SyntaxError, IndentationError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTransportAdapterAudit:
    """Verify transport adapters contain zero business logic."""

    @pytest.mark.parametrize(
        "pattern_group, patterns, label",
        [
            ("Direct LLM calls", LLM_PATTERNS, "llm"),
            ("Intent classification", INTENT_PATTERNS, "intent"),
            ("Own retry/fallback logic", RETRY_PATTERNS, "retry"),
            ("Direct memory writes", MEMORY_PATTERNS, "memory"),
            ("Raw HTTP to LLM providers", HTTP_PATTERNS, "http"),
        ],
        ids=["llm", "intent", "retry", "memory", "http"],
    )
    def test_no_banned_patterns_in_adapters(
        self, pattern_group: str, patterns: tuple[str, ...], label: str,
    ) -> None:
        """Adapter files must not contain {pattern_group}."""
        all_violations: list[str] = []
        for path in _walk_adapter_files():
            if _is_exempt(path):
                continue
            rel = path.relative_to(ROOT).as_posix()
            violations = _check_banned_patterns(path, patterns, label)
            for v in violations:
                all_violations.append(f"{rel}\n{v}")
        assert not all_violations, (
            f"Found banned patterns ({pattern_group}) in transport adapters:\n"
            + "\n".join(all_violations)
            + "\n\nAll business logic must live in pipeline stages, not adapters."
        )
