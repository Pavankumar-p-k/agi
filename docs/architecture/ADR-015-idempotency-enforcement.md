# ADR-015: Idempotency Enforcement in WorkflowEngine

**Status:** Proposed  
**Date:** 2026-07-09  
**Phase:** 7  

## Context

The WORKFLOW_ARCHITECTURE_AUDIT found that `WorkflowEngine` already generates idempotency keys for every workflow step, but:

1. **No deduplication is enforced** — if the same idempotency key is submitted twice, a new WorkflowInstance is created
2. **No idempotency key indexing** — looking up an existing key requires scanning all steps
3. **Consumers don't use idempotency keys** — callers of `WorkflowEngine.start_workflow()` do not pass idempotency keys
4. **`workflow.idempotency_hit` event is published but has zero subscribers** — no monitoring for idempotency key collisions

This means network retries, MCP reconnection storms, or duplicate event processing can create duplicate workflow executions with real side effects (tool calls, data mutations, external API calls).

## Decision

**WorkflowEngine enforces idempotency for all workflow submissions.**

1. `WorkflowEngine.start_workflow(step_definitions, idempotency_key: str | None = None)` — if an idempotency key is provided, check for existing completion before creating a new run.
2. Maintain a UNIQUE index on `workflow_steps.idempotency_key`.
3. If a duplicate idempotency key is detected:
   - Return the cached `WorkflowResult` if the previous run completed
   - Return `Status.DUPLICATE` if the previous run is in progress
   - Return `Status.FAILED` with original error if the previous run failed
4. Automatically generate idempotency keys for all pipeline-initiated workflows (using `PipelineContext.trace_id`).
5. Subscribe to `workflow.idempotency_hit` in Telemetry and Monitoring.

## Consequences

**Positive:**
- At-most-once execution guarantee for all idempotency-keyed workflows
- Idempotency key collisions are visible in monitoring
- Network retries and duplicate events produce safe cache hits instead of duplicate side effects

**Negative:**
- Idempotency key storage is permanent (keys must be retained for the lifetime of possible duplicates — at minimum TTL-based cleanup needed)
- Existing workflows without idempotency keys continue to have at-least-once semantics (opt-in migration)
- WorkflowStore schema change (UNIQUE index on idempotency_key) requires migration
