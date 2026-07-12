"""Central capability registry — single source of truth for agent routing.

All capabilities are registered with ``CapabilityRegistry`` at import time.
Direct access to ``CAPABILITIES`` is deprecated — use ``capability_registry``
from ``core.capability`` instead.
"""
import logging
import warnings

warnings.warn(
    "core.agents.capabilities.CAPABILITIES is deprecated — use core.capability.capability_registry instead",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)

CAPABILITIES: dict[str, list[str]] = {
    # ── Tool agents (priority 10) ──────────────────────────────────────────
    "research": ["research", "competitor", "market", "trend", "ui trend"],
    "build":    ["build", "compile", "create", "develop", "make", "apk", "package"],
    "test":     ["test", "testing", "qa", "validate", "verify", "check"],
    "browser":  ["browse", "navigate", "scrape", "login", "form", "click"],
    "memory":   ["memory", "remember", "learn", "pattern", "store", "recall"],
    "email":    ["email", "mail", "send", "deliver", "notify"],

    # ── LLM specialist adapters (priority 50) ─────────────────────────────
    # Each keyword is scoped to NOT overlap with tool agent keywords above.
    "forge":    ["codegen", "generate code", "implement", "refactor", "debug code"],
    "nexus":    ["deep research", "synthesize", "compare", "intelligence brief"],
    "oracle":   ["plan", "decompose", "strategy", "estimate", "prioritize"],
    "phantom":  ["scrape url", "extract page", "monitor page", "web content"],
    "cipher":   ["security audit", "threat model", "vulnerability", "secure review"],
    "herald":   ["draft message", "summarize", "smart reply", "compose"],
    "atlas":    ["data analysis", "sql query", "visualization", "pandas"],
    "scribe":   ["documentation", "readme", "changelog", "technical report"],
    "sentinel": ["system health", "diagnose", "optimize", "monitor metrics"],
}


def _register_with_capability_registry() -> None:
    """Register all capabilities with the canonical ``CapabilityRegistry``."""
    try:
        from core.capability import capability_registry
        from core.capability.models import Capability
        for agent_id, keywords in CAPABILITIES.items():
            cap = Capability(
                id=agent_id,
                description=f"Agent capability for {agent_id}",
                version=1,
                category="agent",
                permissions=[],
                inputs={},
                outputs={},
                tags=tuple(keywords),
            )
            capability_registry.register(cap)
    except Exception:
        logger.debug("CapabilityRegistry not available — skipping registration")


_register_with_capability_registry()
