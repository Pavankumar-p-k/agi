"""Architecture boundary enforcement.

These tests fail if someone reintroduces a duplicate canonical component
or bypasses the canonical API. Run as part of CI.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# ── Files / dirs that are exempt from various rules ──────────────────────────
EXEMPT_DEPRECATED_IMPORT = {
    # Shim files themselves
    "core/intent_router.py",
    "core/config_schema.py",
    "core/config.py",
    "core/governance/resource_monitor.py",
    "core/environment_monitor.py",
    "core/memory.py",
    "core/memory_vector.py",
    "core/memory_driven_decisions.py",
    # Test files
    "tests/",
    # Benchmarks
    "benchmarks/",
    # Demo
    "demo/",
}

EXEMPT_OS_GETENV = {
    # Infrastructure — these ARE the config backend
    "core/configuration/service.py",
    "core/settings/store.py",
    "core/config_schema.py",
    "core/config_registry.py",
    # Deprecated shims
    "core/config.py",
    "core/environment_monitor.py",
    # Bootstrap
    "core/config_init.py",
    # SDK / plugin host — need env access at import time
    "jarvis_plugin_sdk/",
    "plugins/",
    "tools/",
    "assistant/providers/",
}

EXEMPT_INTENT_ROUTER_IMPORT = EXEMPT_DEPRECATED_IMPORT | {
    # Test files that specifically test the shim
    "tests/integration/test_channels_e2e.py",
}

EXEMPT_CONFIG_SCHEMA_IMPORT = EXEMPT_DEPRECATED_IMPORT | {
    # Tests exercise the shim
    "tests/",
    "demo/quick_demo.py",
}

# ── Helpers ──────────────────────────────────────────────────────────────────


def _walk_py_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _walk_source_py_files() -> list[Path]:
    """Walk the source directories that should be checked (skip node_modules, .venv, etc.)."""
    results: list[Path] = []
    for subdir in ("core", "channels", "api", "routers", "brain", "memory", "assistant",
                   "monitors", "tools", "mcp", "notifications", "vision", "automation",
                   "integrations", "daemon", "network", "models"):
        d = ROOT / subdir
        if d.exists():
            results.extend(d.rglob("*.py"))
    return sorted(set(results))


def _is_exempt(path: Path, exemptions: set[str]) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    for e in exemptions:
        if rel.startswith(e) or rel == e:
            return True
    return False


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  Single canonical owner for each subsystem
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_safe(src: str) -> ast.Module | None:
    try:
        return ast.parse(src)
    except (SyntaxError, IndentationError):
        return None


def test_single_config_service():
    """Only core.configuration.ConfigurationService is a config service."""
    violations: list[str] = []
    for path in _walk_py_files(ROOT / "core"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ("core/configuration/service.py",):
            continue
        src = _read_source(path)
        tree = _parse_safe(src)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Config" in node.name:
                body_src = src[node.lineno:node.end_lineno] if hasattr(node, "end_lineno") else ""
                if any(kw in body_src for kw in (".get(", ".set(", "_load_yaml", "_load_settings", "_scan_env")):
                    violations.append(f"{rel}:{node.lineno} — {node.name}")
    assert not violations, "Non-canonical config classes found:\n" + "\n".join(violations)


def test_single_event_bus():
    """Only core.event_bus defines the event bus."""
    violations: list[str] = []
    for path in _walk_py_files(ROOT / "core"):
        rel = path.relative_to(ROOT).as_posix()
        if rel == "core/event_bus.py":
            continue
        src = _read_source(path)
        if "class EventBus" in src:
            violations.append(rel)
    assert not violations, "EventBus defined outside core/event_bus.py:\n" + "\n".join(violations)


def test_single_intent_classifier():
    """Only core.routing.request_classifier.classify_request is the intent classifier."""
    violations: list[str] = []
    for path in _walk_py_files(ROOT / "core"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ("core/routing/request_classifier.py", "core/intent_router.py"):
            continue
        src = _read_source(path)
        tree = _parse_safe(src)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in ("classify_request", "_keyword_classify", "_llm_router_classify", "_match_trigger"):
                violations.append(f"{rel}:{node.lineno} — {node.name}")
    assert not violations, "Intent classifier functions defined outside canonical module:\n" + "\n".join(violations)


def test_single_agent_registry():
    """Only core/agents/ package provides the agent registry."""
    violations: list[str] = []
    for path in _walk_py_files(ROOT / "core"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("core/agents/") or rel == "core/agent_registry.py":
            continue
        if rel.startswith("core/agents_") or rel.startswith("core/agents_"):
            continue
        src = _read_source(path)
        if "def get_agent(" in src or "class AgentRegistry" in src:
            violations.append(rel)
    assert not violations, "Agent registry functions defined outside canonical package:\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  Direct `os.getenv()` for registered ConfigEntry env vars
# ═══════════════════════════════════════════════════════════════════════════════

_REGISTERED_ENV_VARS: set[str] = set()
try:
    from core.config_registry import _REGISTRY
    _REGISTERED_ENV_VARS = {e.env_var for e in _REGISTRY if e.env_var}
except ImportError:
    pass


def test_no_direct_getenv_for_registered_keys():
    """Production code must use configuration.get() for registered config keys."""
    if not _REGISTERED_ENV_VARS:
        pytest.skip("Cannot resolve ConfigEntry registry")
    registered = sorted(_REGISTERED_ENV_VARS)
    violations: list[str] = []
    for path in _walk_source_py_files():
        rel = path.relative_to(ROOT).as_posix()
        if _is_exempt(path, EXEMPT_OS_GETENV):
            continue
        src = _read_source(path)
        # Fast pre-filter: check if any os.getenv call exists at all
        if "os.getenv" not in src and "os.environ.get" not in src:
            continue
        for env_var in registered:
            if f'os.getenv("{env_var}")' in src or f"os.getenv('{env_var}')" in src:
                violations.append(f"{rel} — os.getenv(\"{env_var}\")")
            elif f'os.environ.get("{env_var}")' in src or f"os.environ.get('{env_var}')" in src:
                violations.append(f"{rel} — os.environ.get(\"{env_var}\")")
    seen = {v.split(" — ")[0] for v in violations}
    new_violations = seen - _KNOWN_DIRECT_GETENV
    assert not new_violations, (
        "Direct os.getenv() for registered config keys (use configuration.get() instead):\n"
        + "\n".join(sorted(new_violations))
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  No deprecated imports in production code
# ═══════════════════════════════════════════════════════════════════════════════


# Known deprecated imports (grandfathered — must not grow)
_KNOWN_CONFIG_SCHEMA_IMPORTS: set[str] = {
    "core/llm_failover.py",
    "core/llm_router.py",
    "core/lifespan.py",
    "core/routes/infrastructure.py",
    "core/sandbox/sandbox_manager.py",
    "core/spawning/manager.py",
    "core/spawning/orphan.py",
    "core/tools/execution.py",
    "core/debugger.py",
}

_KNOWN_INTENT_ROUTER_IMPORTS: set[str] = {
    "channels/processor.py",
    "core/routes/websocket.py",
    "network/websocket_server.py",
}

_KNOWN_DIRECT_GETENV: set[str] = {
    # These are known usages of os.getenv() for registered config keys.
    # Each should be migrated to configuration.get().
    "assistant/providers/faster_whisper.py",
    "assistant/tts.py",
    "core/constants.py",
    "core/diagnostics/report.py",
    "core/embeddings.py",
    "core/llm_router.py",
    "core/routes/chat.py",
    "core/routes/operations.py",
    "core/routes/websocket.py",
    "memory/embedding_memory.py",
    "routers/screen.py",
    "routers/setup.py",
    "tools/image_gen.py",
}


def test_no_deprecated_config_schema_import():
    """Production code must not import from core.config_schema directly.

    Known grandfather violations are tracked in _KNOWN_CONFIG_SCHEMA_IMPORTS.
    Any NEW import will fail this test.
    """
    violations: set[str] = set()
    for path in _walk_source_py_files():
        rel = path.relative_to(ROOT).as_posix()
        if _is_exempt(path, EXEMPT_CONFIG_SCHEMA_IMPORT):
            continue
        src = _read_source(path)
        if "from core.config_schema import" in src or "import core.config_schema" in src:
            violations.add(rel)
    new_violations = violations - _KNOWN_CONFIG_SCHEMA_IMPORTS
    assert not new_violations, (
        "NEW imports from deprecated core.config_schema (use configuration.get() instead):\n"
        + "\n".join(sorted(new_violations))
    )


def test_no_deprecated_intent_router_import():
    """Production code must not import from core.intent_router.

    Known grandfather violations are tracked in _KNOWN_INTENT_ROUTER_IMPORTS.
    Any NEW import will fail this test.
    """
    violations: set[str] = set()
    for path in _walk_source_py_files():
        rel = path.relative_to(ROOT).as_posix()
        if _is_exempt(path, EXEMPT_INTENT_ROUTER_IMPORT):
            continue
        src = _read_source(path)
        if "from core.intent_router import" in src or "import core.intent_router" in src:
            violations.add(rel)
    new_violations = violations - _KNOWN_INTENT_ROUTER_IMPORTS
    assert not new_violations, (
        "NEW imports from deprecated core.intent_router (use classify_request() instead):\n"
        + "\n".join(sorted(new_violations))
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  Dependency direction: core/ must not import from channels/, brain/, api/
# ═══════════════════════════════════════════════════════════════════════════════

_FORBIDDEN_IMPORTS_IN_CORE: dict[str, set[str]] = {
    "channels": {"channels.", "channels"},
    "api": {"api.", "api"},
    "routers": {"routers.", "routers"},
    "daemon": {"daemon.", "daemon"},
    "network": {"network.", "network"},
}

_EXEMPT_CORE_IMPORTS: set[str] = {
    "core/config.py",
    "core/config_schema.py",
    "core/environment_monitor.py",
    "core/memory.py",
    "core/memory_vector.py",
    "core/memory_driven_decisions.py",
}


# Known dependencies from core/ to higher layers (grandfathered, must not grow)
_KNOWN_CORE_UPSTREAM_IMPORTS: set[str] = {
    "core/auth.py — api/",
    "core/integration_manager.py — channels/",
    "core/main.py — api/",
    "core/main.py — channels/",
    "core/main.py — routers/",
    "core/providers/adapters/messaging_provider.py — channels/",
    "core/routes/chat.py — routers/",
    "core/routes/websocket.py — network/",
}


def test_core_does_not_import_higher_layers():
    """core/ must not import from channels/, api/, routers/, daemon/, network/.

    Known grandfather violations are tracked in _KNOWN_CORE_UPSTREAM_IMPORTS.
    Any NEW violation will fail this test.
    """
    _exempt = _EXEMPT_CORE_IMPORTS | {
        "core/lifespan.py",
        "core/build_routes.py",
    }
    violations: set[str] = set()
    for path in sorted((ROOT / "core").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if _is_exempt(path, _exempt):
            continue
        src = _read_source(path)
        for layer, patterns in _FORBIDDEN_IMPORTS_IN_CORE.items():
            for pat in patterns:
                if f"from {pat}" in src or f"import {pat}" in src:
                    if "TYPE_CHECKING" in src:
                        continue
                    violations.add(f"{rel} — {layer}/")
                    break
    new_violations = violations - _KNOWN_CORE_UPSTREAM_IMPORTS
    assert not new_violations, (
        "NEW dependency violations from core/ to higher layers:\n"
        + "\n".join(sorted(new_violations))
        + "\n\nKnown (grandfathered):\n"
        + "\n".join(sorted(_KNOWN_CORE_UPSTREAM_IMPORTS))
    )
