# ADR-005: Event Bus Consolidated in core.event_bus

**Status:** Accepted  
**Date:** 2026-07-05  
**Phase:** 1b  

## Context

Event pub/sub was scattered across:
- `core/event_bus.py` — core sync `EventBus` class
- `core/event_system.py` — redundant event system module
- `events/` — standalone event definitions directory
- `brain/events/event_bus.py` — re-exported from `core.event_bus` but imported as two-hop detour
- `core/plugins/events.py` — plugin-specific event bus
- `core/workflow/events.py` — workflow-specific event bus
- `core/agents/events.py` — agent-specific events

No single authority for event types, delivery, or logging.

## Decision

**`core/event_bus.py` is the canonical event bus. All event communication goes through it.**

1. `core/event_system.py` → removed (merged into `core/event_bus.py`)
2. `events/` directory → removed (types moved to `core/event_bus.py`)
3. `brain/events/event_bus.py` → kept as legacy re-export shim for backward compat
4. Plugin events, workflow events, and agent events keep their own type definitions but use `core.event_bus.EventBus` for dispatch

## Consequences

**Positive:**
- Single `EventBus` class with consistent `emit()` / `on()` / `off()` API
- Event logging centralized
- Plugin events, workflow events, agent events all dispatch through the same bus

**Negative:**
- 23 brain modules still import through the `brain/events` two-hop re-export (not a functional issue, just a style one)
- Plugin event types are defined in `core/plugins/events.py` rather than co-located with the bus (intentional — plugins are a separate concern)

**Migration:** Direct imports from `core.event_bus` are preferred. `brain/events` re-exports to be removed in v4.0.
