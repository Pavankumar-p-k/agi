# ADR-004: Agent Registry is Canonical

**Status:** Accepted  
**Date:** 2026-07-05  
**Phase:** 1e  

## Context

Agent execution was fragmented across:
- `core/sub_agents/` — 13 legacy LLM-prompt agents (Maestro, Nexus, Forge, etc.)
- `core/agents/` — new `BaseAgent` system with browser, build, email, research agents
- `core/agent_registry.py` — registry API with `get_agent(name)`
- `core/agents/router.py` — sub-module with `find_agent_for_goal()`
- `core/agent_runtime.py` — multi-round tool-call execution

The legacy agents were imported directly by multiple callers, bypassing the registry.

## Decision

**`core.agent_registry.get_agent()` and `core.agents.registry` are the canonical agent lookup APIs.**

1. Legacy sub-agents moved to `core/agents/_legacy/` (physical isolation)
2. Adapters in `core/agents/adapters/` wrap legacy agents into `BaseAgent` interface
3. `core/agent_registry.py` is the top-level public API
4. New agents MUST extend `BaseAgent` and register via `agent_registry.register()`

## Consequences

**Positive:**
- Single lookup API (`get_agent()`, `get_agents_for_capability()`, `list_agents()`)
- Legacy agents isolated behind adapters; new code never imports `_legacy/` directly
- Adapters provide a uniform `can_handle()` / `execute()` interface

**Negative:**
- Two benchmark files import legacy agents directly (acceptable for benchmarking)
- `core/providers/adapters/forge.py` imports from `_legacy` (provider integration use case)
- Legacy agents still functional but cannot be removed until all adapters are replaced

**Known gaps:**
- `core/agents/_legacy/` directory can be removed once all adapters are rewritten as native `BaseAgent` subclasses
