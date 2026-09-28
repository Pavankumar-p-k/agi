"""CAPABILITIES — keyword routing table for all 15 agents.

Maps agent_id -> keywords used by core.agents.router to pick the right
specialist for a goal. Tool agents and adapter agents must not share
keywords (routing ambiguity), which tests enforce.
"""
from __future__ import annotations

# 6 tool agents (priority 10 — direct action on the local system)
TOOL_AGENT_KEYWORDS: dict[str, list[str]] = {
    "build": ["build", "compile", "apk", "package", "bundle", "artifact"],
    "test": ["test", "unittest", "pytest", "run tests", "coverage"],
    "email": ["email", "send mail", "inbox", "smtp", "mail"],
    "research": ["research", "investigate", "explore topic", "search for information"],
    "memory": ["remember", "recall", "memorize", "memory", "forget"],
    "browser": ["browse", "open chrome", "screenshot", "tab", "url in browser"],
}

# 9 LLM specialist adapters (priority 50 — model-driven work)
ADAPTER_AGENT_KEYWORDS: dict[str, list[str]] = {
    "forge": ["codegen", "generate code", "write function", "implement function",
              "code for", "refactor code", "write class"],
    "nexus": ["compare", "versus", " vs ", "difference between", "evaluate options",
              "trade-offs", "tradeoffs"],
    "oracle": ["plan", "architecture", "design strategy", "roadmap",
               "break down", "milestones"],
    "phantom": ["scrape", "extract page", "extract text from url", "crawl",
                "pull content", "website content"],
    "cipher": ["security", "audit code", "vulnerability", "cve", "encrypt",
               "threat model", "harden"],
    "herald": ["draft", "newsletter", "announcement", "press release",
               "write update", "compose message"],
    "atlas": ["sql query", "database query", "select from", "schema",
              "migrate database", "query the database"],
    "scribe": ["documentation", "document the", "write docs", "readme",
               "api reference", "changelog"],
    "sentinel": ["diagnose", "debug error", "troubleshoot", "root cause",
                 "log analysis", "why is it failing"],
}

# Unified dict: all 15 agent ids.
CAPABILITIES: dict[str, list[str]] = {**TOOL_AGENT_KEYWORDS, **ADAPTER_AGENT_KEYWORDS}

__all__ = ["CAPABILITIES", "TOOL_AGENT_KEYWORDS", "ADAPTER_AGENT_KEYWORDS"]
