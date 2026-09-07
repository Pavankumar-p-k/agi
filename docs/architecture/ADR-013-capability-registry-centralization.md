# ADR-013: CapabilityRegistry as Central Authority

**Status:** Proposed  
**Date:** 2026-07-09  
**Phase:** 2  

## Context

The REQUEST_PIPELINE_AUDIT and IDENTITY_PERMISSION_AUDIT revealed four separate mechanisms for determining what a user/agent can do:

1. **Hardcoded dict** in `CapabilitySelectionStage` — maps phase names to tool names, bypasses the `CapabilityRegistry` class entirely
2. **`NON_ADMIN_BLOCKED_TOOLS`** list in `core/tools/security.py` — 36-tool blocklist that operates outside the scope/permission system
3. **Hardcoded agent routing** in `control_loop.py` — maps tasks to agents by name, outside any registry
4. **`CapabilityRegistry` class** — exists but has zero runtime consumers

This means:
- Adding a new tool requires updating 3+ separate locations
- Permission bypass through CapabilitySelectionStage's hardcoded dict (a tool not in the dict is silently unavailable)
- The blocklist and the capability registry can disagree on which tools are available
- Agent routing and capability mapping are entirely disconnected

## Decision

**CapabilityRegistry becomes the central authority for mapping intents → actions → permissions → agents.**

1. `CapabilityRegistry.registry` becomes the single source of truth with entries containing:
   - `capability_id → tool_name` (execution)
   - `capability_id → required_scopes` (RBAC)
   - `capability_id → required_permissions` (risk)
   - `capability_id → agent_type` (routing)
2. `CapabilitySelectionStage` queries CapabilityRegistry instead of its hardcoded dict.
3. `NON_ADMIN_BLOCKED_TOOLS` is replaced by scope-level RBAC driven from CapabilityRegistry entries.
4. Agent routing in `control_loop.py` uses CapabilityRegistry's `agent_type` field.

## Consequences

**Positive:**
- Single source of truth for tool capability → permission → routing
- Adding a new tool means one entry in CapabilityRegistry
- No bypass paths — all tool access is gated through the same registry
- Agent routing is driven by capability data, not hardcoded name matching

**Negative:**
- Every existing tool (~60+) needs a CapabilityRegistry entry — requires audit of each tool's required scopes and permissions
- Agent routing currently uses name matching — switching to capability-based routing may change which agent handles which tasks
- `NON_ADMIN_BLOCKED_TOOLS` removal must be coordinated with the Identity/Phase 6 work (scope system must be complete first)
