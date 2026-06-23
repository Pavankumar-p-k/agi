"""Central capability registry — single source of truth for agent routing."""

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
