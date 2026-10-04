"""Feature registry — the source of truth for what JARVIS can do.

Rebuilt in STEP 4. The previous file was a 72-line DynamicStub: ``FEATURES``
was the *string* ``"FEATURES"``, and ``get_feature_report()`` returned a stub
object whose attributes were further stubs. ``jarvis doctor`` caught the
resulting AttributeError and printed ``Feature audit failed: ...`` — one of
the red errors on the doctor gate.

Pinned specs
------------
* ``tests/cli/test_commands.py::TestDoctor`` patches
  ``core.feature_registry.get_feature_report`` — the name must exist at import.
* ``jarvis-export/cli/cli_commands.py`` (the real CLI) requires:

  ============  =========================================================
  symbol        shape
  ============  =========================================================
  FEATURES      mapping ``slug -> Feature`` (supports ``.get`` and ``in``)
  Feature       ``name, slug, category, description, status,
                enabled_by_default, config_key, docs_path, dependencies,
                health_check_fn``
  FeatureStatus enum with ``.value`` (lowercase) + ``.STABLE``/``.BROKEN``
  get_status    ``slug -> FeatureStatus``
  is_enabled    ``slug -> bool``
  set_status    ``(slug, FeatureStatus) -> None``
  get_all_features  ``-> list[Feature]``
  get_feature_report ``-> dict`` with ``features, total, enabled, disabled,
                  stable, beta, broken, planned``
  ============  =========================================================

Report semantics: a feature is ``enabled`` only when its toggle says so *and*
its dependencies import cleanly; the ``status`` counts are computed from the
live registry, not hardcoded.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

__all__ = [
    "Feature", "FeatureStatus", "FEATURES",
    "get_status", "set_status", "is_enabled",
    "get_all_features", "get_feature_report",
]


class FeatureStatus(str, Enum):
    """Maturity of a feature. ``.value`` is the lowercase wire format."""

    STABLE = "stable"
    BETA = "beta"
    EXPERIMENTAL = "experimental"
    BROKEN = "broken"
    PLANNED = "planned"

    @classmethod
    def coerce(cls, value: Any) -> "FeatureStatus":
        if isinstance(value, FeatureStatus):
            return value
        try:
            return cls(str(value).lower())
        except ValueError:
            return cls.PLANNED


@dataclass
class Feature:
    name: str
    slug: str
    category: str = "core"
    description: str = ""
    status: FeatureStatus = FeatureStatus.PLANNED
    enabled_by_default: bool = True
    config_key: str = ""
    docs_path: str = ""
    dependencies: List[str] = field(default_factory=list)
    health_check_fn: str = ""

    @property
    def default_enabled(self) -> bool:  # alias used by some callers
        return self.enabled_by_default


def _f(slug: str, name: str, category: str, description: str,
       status: FeatureStatus, deps: Optional[List[str]] = None,
       enabled_default: bool = True, health: str = "",
       config_key: str = "", docs: str = "") -> Feature:
    return Feature(
        name=name, slug=slug, category=category, description=description,
        status=status, enabled_by_default=enabled_default,
        config_key=config_key or f"feature.{slug}.enabled",
        docs_path=docs, dependencies=list(deps or []),
        health_check_fn=health,
    )


#: The feature table.  ``deps`` are import paths whose absence downgrades the
#: feature to BROKEN at report time (so the doctor table reflects reality).
FEATURES: Dict[str, Feature] = {
    f.slug: f for f in [
        _f("chat", "Chat", "core",
           "Streaming chat with the local/remote model router.",
           FeatureStatus.STABLE, ["core.llm_router"]),
        _f("agents", "Agent Registry", "core",
           "15 registered agents (6 tool + 9 LLM specialists) with keyword routing.",
           FeatureStatus.STABLE, ["core.agents.registry", "core.agents.router"]),
        _f("pipeline", "Message Pipeline", "core",
           "Canonical 19-stage request path (ADR-006/007/009).",
           FeatureStatus.STABLE, ["core.pipeline.pipeline"]),
        _f("desktop_control", "Desktop Control", "automation",
           "Windows UI Automation, windows, processes, clipboard, risk tiers.",
           FeatureStatus.STABLE, ["core.desktop.user_actions"]),
        _f("browser", "Browser Automation", "automation",
           "Playwright sessions: navigate, snapshot, screenshot, verify/recover.",
           FeatureStatus.STABLE, ["core.browser_manager", "core.tools.browser_tools"]),
        _f("memory", "Long-term Memory", "memory",
           "mem0-backed cross-session user memory with verification on write.",
           FeatureStatus.BETA, ["memory.mem0_adapter"]),
        _f("belief", "Belief Engine", "memory",
           "Confidence-tracked belief store with contradiction handling.",
           FeatureStatus.BETA, ["core.belief"]),
        _f("strategy", "Strategy Layer", "core",
           "Planning and strategy selection across sessions.",
           FeatureStatus.BETA, ["core.strategy"]),
        _f("providers", "Model Providers", "core",
           "Ollama/OpenAI/Anthropic/Gemini/Groq provider adapters.",
           FeatureStatus.BETA, ["core.llm_router"]),
        _f("mcp", "MCP Servers", "integrations",
           "Model Context Protocol servers for memory, RAG and tools.",
           FeatureStatus.BETA, ["jarvis_mcp"]),
        _f("skills", "Skills", "integrations",
           "Skill library with loader and shared helpers.",
           FeatureStatus.BETA, ["skills"]),
        _f("tui", "Terminal UI", "interface",
           "Textual-based TUI screens, widgets and services.",
           FeatureStatus.STABLE, ["jarvis_tui"]),
        _f("voice", "Voice Pipeline", "interface",
           "Wake word, STT and TTS. Requires the assistant package.",
           FeatureStatus.PLANNED, ["assistant"], enabled_default=False),
        _f("web", "Web UI", "interface",
           "FastAPI server backing the browser interface.",
           FeatureStatus.BETA, ["core.main"]),
        _f("scheduler", "Scheduler", "automation",
           "Timed and autonomous task scheduling.",
           FeatureStatus.PLANNED, [], enabled_default=False),
        _f("benchmark", "Benchmark", "quality",
           "Device-task evaluation harness.",
           FeatureStatus.PLANNED, [], enabled_default=False),
        _f("governance", "Governance", "quality",
           "Approval gates, policy audit and consent records.",
           FeatureStatus.PLANNED, ["core.authz"], enabled_default=False),
        _f("vision", "Screen Vision", "automation",
           "Screen capture + vision model for UI grounding.",
           FeatureStatus.BETA, ["core.vision_agent"], enabled_default=False),
    ]
}

# slug -> status override (runtime toggles persisted per process)
_STATUS_OVERRIDES: Dict[str, FeatureStatus] = {}
# slug -> explicit enable/disable; falls back to enabled_by_default
_ENABLED_OVERRIDES: Dict[str, bool] = {}


def _deps_ok(feature: Feature) -> bool:
    for dep in feature.dependencies:
        try:
            importlib.import_module(dep)
        except Exception:  # noqa: BLE001 — any import failure disqualifies
            return False
    return True


def get_all_features() -> List[Feature]:
    return list(FEATURES.values())


def get_status(slug: str) -> FeatureStatus:
    if slug in _STATUS_OVERRIDES:
        return _STATUS_OVERRIDES[slug]
    feature = FEATURES.get(slug)
    return feature.status if feature else FeatureStatus.PLANNED


def set_status(slug: str, status: Any) -> None:
    _STATUS_OVERRIDES[slug] = FeatureStatus.coerce(status)


def is_enabled(slug: str) -> bool:
    feature = FEATURES.get(slug)
    if feature is None:
        return False
    if slug in _ENABLED_OVERRIDES:
        want = _ENABLED_OVERRIDES[slug]
    else:
        want = feature.enabled_by_default
    return bool(want) and _deps_ok(feature)


def set_enabled(slug: str, enabled: bool) -> None:
    if slug in FEATURES:
        _ENABLED_OVERRIDES[slug] = bool(enabled)


def get_feature_report() -> Dict[str, Any]:
    """Report with counts derived from the live registry (never hardcoded)."""
    rows: List[Dict[str, Any]] = []
    counts = {s.value: 0 for s in FeatureStatus}
    enabled_n = disabled_n = 0

    for feature in FEATURES.values():
        status = get_status(feature.slug)
        enabled = is_enabled(feature.slug)
        if not _deps_ok(feature) and status not in (FeatureStatus.PLANNED,):
            status = FeatureStatus.BROKEN
            _STATUS_OVERRIDES.setdefault(feature.slug, status)
        counts[status.value] += 1
        enabled_n += 1 if enabled else 0
        disabled_n += 0 if enabled else 1
        rows.append({
            "name": feature.name,
            "slug": feature.slug,
            "category": feature.category,
            "description": feature.description,
            "status": status.value,
            "enabled": enabled,
            "config_key": feature.config_key,
            "dependencies": list(feature.dependencies),
        })

    return {
        "features": rows,
        "total": len(rows),
        "enabled": enabled_n,
        "disabled": disabled_n,
        "stable": counts["stable"],
        "beta": counts["beta"],
        "experimental": counts["experimental"],
        "broken": counts["broken"],
        "planned": counts["planned"],
    }
