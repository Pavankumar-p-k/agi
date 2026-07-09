# ADR-011: Bounded-Context Database Strategy

**Status:** Proposed  
**Date:** 2026-07-09  
**Phase:** 5  

## Context

The STORAGE_ARCHITECTURE_AUDIT identified 27+ SQLite databases and 60+ tables with no consistent ownership model. The original target architecture proposed consolidating to 3-5 monolithic databases (`data/app.db`, `data/system.db`, `data/user.db`).

Further analysis from DATA_FLOW_AUDIT and EVENT_FLOW_AUDIT revealed:

1. **Different lifecycle requirements**: Memory data needs different backup frequency than auth data. Workflow data needs different retention than planner data.
2. **Different contention profiles**: WorkflowStore experiences high write contention. MemoryStore experiences high read contention. Mixing them in one DB creates unnecessary lock contention.
3. **Different isolation requirements**: Auth failures should not cascade into planner data unavailability.
4. **Migration risk**: Merging 27+ databases into any single database is a high-risk, long-duration effort with no incremental value until 100% complete.

## Decision

**Consolidate to databases by bounded context, not by a monolithic schema.**

| Database | Bounded Context | Owner | Contents |
|----------|----------------|-------|----------|
| `data/system.db` | System state | Core Platform | Activity, settings, scheduler state |
| `data/memory.db` | Memory & knowledge | Memory | Facts, episodes, decisions, embeddings |
| `data/workflow.db` | Workflow execution | Workflow | Workflow instances, steps, execution context (sync ORM target) |
| `data/planner.db` | Planning | Planner | Goals, plans, plan health |
| `~/.jarvis/user.db` | User-scoped state | Core Platform | Checkpoints, agent state, browser state, desktop state |

Cross-context reads must go through service APIs, not direct query access. No cross-context foreign keys.

## Consequences

**Positive:**
- Each bounded context can be migrated, backed up, and scaled independently
- Lower migration risk — each DB is migrated separately with incremental verification
- Clear ownership — each team owns their context's schema
- No cross-context lock contention
- Parallel migration possible (memory team works on `data/memory.db` while planner team works on `data/planner.db`)

**Negative:**
- More total databases (5 vs 3) — slightly more operational overhead
- Cross-context queries require service-to-service calls (no joins across contexts)
- Existing cross-context foreign keys must be removed (e.g., workflow_id referenced from planner context)
- Application code must know which service to call for data in another context
