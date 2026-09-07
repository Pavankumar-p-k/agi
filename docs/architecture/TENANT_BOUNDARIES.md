# Tenant Boundaries (Phase 6B Planning)

Explicit ownership model before multi-tenancy implementation.

## Scope Model

| Component | Tenant Scoped? | Notes |
|---|---|---|
| Memory (facts, preferences) | Yes | Each tenant has isolated fact store and preference profile |
| Observations | Yes | `Observation.tenant_id` filters at query time |
| Activities | Yes | `ActivityGraph` nodes carry `tenant_id` |
| Scheduler queue | Usually yes | Per-tenant work queues, shared worker pool |
| Capability registry | Usually global | Capabilities are platform-wide; tenant-specific ones are metadata-tagged |
| Model providers | Shared | Provider pool is global; per-tenant rate limits via metadata |
| Runtime specification | Global | `RUNTIME_VERSION`, `Pipeline.version` are single global constants |
| Architecture metrics | Both | Metrics collected per-request (tenant-tagged) and rolled up globally |
| Event bus | Global | Events carry `tenant_id` in payload; subscribers filter by pattern |
| Observation Hub | Global | Single hub instance; filters by tenant at subscriber level |

## Implementation order

1. Add `tenant_id` to `PipelineContext` (optional, default `None`)
2. Add `tenant_id` to `Observation`, `ExtractedFact`, `Outcome`
3. Add `tenant_id` to `MemoryStage` queries (FactStore filtering)
4. Add tenant isolation to `SchedulerQueue` (per-tenant priority queues)
5. Add per-tenant rate limiting in `RateLimitStage`
6. Add `tenant_id` to snapshot serialization
