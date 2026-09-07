# Implementation Master Plan

> **Purpose:** The single document developers follow to migrate JARVIS from its current architecture to the target architecture defined across 13 audits and 15 ADRs. No other planning document is needed.
>
> **Prerequisites:** All 13 architecture audits, TARGET_ARCHITECTURE.md, CODE_OWNERSHIP_AUDIT.md, ADR-001 through ADR-015. Read those for context; this document is the execution plan.
>
> **Rule:** Before writing any code, tag the current codebase as `v3-freeze` or `architecture-freeze`. No feature work, no UI work, no optimization — only architecture migration until this plan is complete.

---

## Table of Contents

1. [Dependency DAG](#1-dependency-dag)
2. [Work Packages](#2-work-packages)
3. [Parallelization Matrix](#3-parallelization-matrix)
4. [Breaking Changes](#4-breaking-changes)
5. [Migration Checkpoints](#5-migration-checkpoints)
6. [Risk Register](#6-risk-register)
7. [Testing Matrix](#7-testing-matrix)

---

## 1. Dependency DAG

```
Legend:
  │   = depends on (vertical flow)
  ─   = no dependency (parallel)
  ▼   = completion milestone

                        ┌──────────────────────────────────────────────────┐
                        │         WP-001: Thread Safety                    │
                        │         (tool_factory, singletons)               │
                        │         Risk: CRITICAL    Est: 2-3 days         │
                        └──────────────────┬───────────────────────────────┘
                                           │
                  ┌────────────────────────┼────────────────────────────┐
                  │                        │                            │
                  ▼                        ▼                            ▼
   ┌──────────────────────────┐   ┌───────────────────┐   ┌──────────────────────┐
   │ WP-002: Canonical        │   │ WP-004: Event Bus │   │ WP-005: Config       │
   │ Pipeline (remove         │   │ Unification        │   │ Unification           │
   │ RuntimePipeline, enforce │   │ (1 bus, async,    │   │ (single service,      │
   │ pipeline-only path)      │   │ namespaces)        │   │ env live-read)        │
   │ Risk: HIGH   Est: 5-7d  │   │ Risk: MED   Est: 3d│   │ Risk: LOW    Est: 2d  │
   └──────────┬───────────────┘   └────────┬──────────┘   └──────────┬───────────┘
              │                            │                         │
              ▼                            │                         │
   ┌──────────────────────────┐            │                         │
   │ WP-003: Capability       │            │                         │
   │ Registry (replace        │            │                         │
   │ hardcoded dict,          │            │                         │
   │ blocklist → RBAC)        │            │                         │
   │ Risk: MED    Est: 3-4d  │            │                         │
   └──────────┬───────────────┘            │                         │
              │                            │                         │
              ▼                            ▼                         │
   ┌──────────────────────────┐   ┌──────────────────────┐          │
   │ WP-006: Planner          │   │ WP-008: Workflow      │          │
   │ (CorePlanner protocol,   │   │ (idempotency, timeout,│          │
   │ UnifiedStore, LLM        │   │ ExecutionGraph,       │          │
   │ fallback)                │   │ LongHorizonFSM)       │          │
   │ Risk: HIGH   Est: 7-10d │   │ Risk: LOW    Est: 4d  │          │
   └──────────┬───────────────┘   └──────────┬────────────┘          │
              │                            │                         │
              ▼                            │                         │
   ┌──────────────────────────┐            │                         │
   │ WP-007: Memory           │            │                         │
   │ (MemoryFacade unification,│           │                         │
   │ brain/memory migration,   │           │                         │
   │ embedding standardize)    │           │                         │
   │ Risk: HIGH   Est: 8-12d  │           │                         │
   └──────────┬───────────────┘            │                         │
              │                            │                         │
              └────────────┬───────────────┘                         │
                           │                                          │
                           ▼                                          │
              ┌──────────────────────────────┐                        │
              │ WP-009: Storage Consolidation │                       │
              │ (bounded-context DBs,         │                       │
              │ Alembic coverage, Auth→SQLite)│                       │
              │ Risk: MED    Est: 10-14d     │                       │
              └──────────┬───────────────────┘                        │
                         │                                            │
                         ▼                                            │
              ┌──────────────────────────────┐                        │
              │ WP-010: Identity & Permission │ ◄──────────────────────┘
              │ (Authorizer facade, scope     │   (needs WP-005 config
              │ RBAC, unified user model)     │    for policy loading)
              │ Risk: MED    Est: 5-7d       │
              └──────────┬───────────────────┘
                         │
                         ▼
              ┌──────────────────────────────┐
              │ WP-011: Cleanup & Removal     │
              │ (delete deprecated modules,   │
              │ Removal Verification Reports) │
              │ Risk: LOW    Est: 3-5d       │
              └──────────────────────────────┘
```

---

## 2. Work Packages

---

### WP-001: Thread Safety

**Files:** `core/tools/tool_factory.py`, `core/singleton_manager.py`, `memory/tiered_memory.py` (hot tier)

**Depends on:** None

**Risk:** Critical — thread-hostile global state crashes concurrent requests

**Rollback:** Revert changes to tool_factory.py and singleton_manager.py

**Estimated LOC:** +80, -20

**Owner:** Core Platform

#### Scope

1. Replace module-level `_initialized` flag with `threading.Lock` + `threading.Event` in `tool_factory.py`
2. Replace module-level `_tools` dict with `threading.Lock`-guarded dict in `tool_factory.py`
3. Add `threading.Lock` to TieredMemory hot path (concurrent `remember`/`recall`)
4. Audit singleton_manager.py for other thread-hostile patterns

#### Acceptance Criteria

- [ ] 4 concurrent requests can execute tools without race conditions or corrupted state
- [ ] tool_factory.create() is safe to call from multiple threads
- [ ] TieredMemory.remember() and .recall() are safe under concurrent access
- [ ] All existing tests pass without modification
- [ ] Performance test: 50 concurrent requests complete without error

#### Tests

- `tests/tools/test_tool_factory.py`: thread-safety test (spawn 10 concurrent callers, verify no corruption)
- `tests/memory/test_tiered_memory.py`: concurrent remember/recall test
- `tests/architecture/test_architecture_audit.py`: existing audit tests pass

---

### WP-002: Canonical Pipeline

**Files:** `core/pipeline.py`, `core/control_loop.py`, `core/entry/manager.py`, all pipeline stages, `core/runtime.py`, `core/runtime_pipeline.py` (delete)

**Depends on:** WP-001

**Risk:** High — removes the only alternative request path; any missed caller causes unreachable functionality

**Rollback:** Restore RuntimePipeline class, revert entry point callers, revert stage changes

**Estimated LOC:** +200, -350

**Owner:** Core Platform

#### Scope

1. Audit every call to RuntimePipeline (direct instantiation, `pipeline.run()`, phase API)
2. Migrate all callers to `Pipeline.execute()`
3. Remove `RuntimePipeline` class and all its supporting code
4. Add `core/entry/manager.py` adapter for non-HTTP transports (CLI, daemon, WebSocket, MCP)
5. If EpistemicTaggingStage adds no value, remove it; if it adds value, implement proper tagging

#### Acceptance Criteria

- [ ] No code in the repository imports or references `RuntimePipeline`
- [ ] All entry points (HTTP, WebSocket, MCP, CLI, daemon) go through `Pipeline.execute()`
- [ ] `PipelineContext` is properly constructed for non-HTTP transports (identity, trace_id, metadata)
- [ ] All 19 canonical stages execute for every request
- [ ] No regression in request latency (>5% increase requires investigation)

#### Tests

- `tests/pipeline/test_pipeline.py`: all existing tests pass
- `tests/architecture/test_pipeline_contract.py`: pipeline contract checks pass
- `tests/entry/test_cli_adapter.py`: CLI → Pipeline integration
- `tests/entry/test_ws_adapter.py`: WebSocket → Pipeline integration
- `tests/entry/test_mcp_adapter.py`: MCP → Pipeline integration

---

### WP-003: Capability Registry

**Files:** `core/tools/capability_registry.py`, `core/pipeline/stages/capability_selection.py`, `core/tools/security.py`, `core/control_loop.py`

**Depends on:** WP-002

**Risk:** Medium — every existing tool needs a registry entry; missing entry = silent unavailability

**Rollback:** Restore hardcoded dict in CapabilitySelectionStage, restore NON_ADMIN_BLOCKED_TOOLS

**Estimated LOC:** +150, -80

**Owner:** Core Platform

#### Scope

1. Populate `CapabilityRegistry.registry` with entries for all ~60 tools (tool_name, required_scopes, required_permissions, agent_type)
2. Replace hardcoded dict in `CapabilitySelectionStage` with `CapabilityRegistry.lookup()`
3. Replace `NON_ADMIN_BLOCKED_TOOLS` list with scope-based RBAC from CapabilityRegistry
4. Update `control_loop.py` agent routing to use CapabilityRegistry's `agent_type`

#### Acceptance Criteria

- [ ] Every tool has a CapabilityRegistry entry
- [ ] CapabilitySelectionStage returns results from the registry, not from hardcoded dict
- [ ] `NON_ADMIN_BLOCKED_TOOLS` is removed and replaced by scope checks
- [ ] Agent routing uses capability data, not name matching
- [ ] No tool is silently unavailable (test: execute every tool through the pipeline)

#### Tests

- `tests/tools/test_capability_registry.py`: registry CRUD, lookup by scope, lookup by agent_type
- `tests/pipeline/test_capability_selection.py`: stage returns correct capabilities
- `tests/security/test_scope_rbac.py`: blocklist replacement, admin vs non-admin scopes
- `tests/agents/test_agent_routing.py`: routing uses capability data

---

### WP-004: Event Bus Unification

**Files:** `core/event_bus.py`, `plugin_system/core.py`, `core/runtime.py`

**Depends on:** WP-001

**Risk:** Medium — all subscribers must migrate to new API; namespace enforcement may break existing plugin subscriptions

**Rollback:** Restore old EventBus, PluginEventBus, and Runtime protocol

**Estimated LOC:** +180, -100

**Owner:** Core Platform

#### Scope

1. Add namespace support to canonical EventBus: `system.*`, `plugin.{id}.*`
2. Prevent plugins from subscribing to `system.*` by default
3. Add async subscriber dispatch (wrap callbacks in try/except, log exceptions, continue)
4. Migrate PluginEventBus to use canonical EventBus with namespace isolation
5. Migrate Runtime protocol handlers to subscribe to `config.changed` on EventBus
6. Remove PluginEventBus class; remove Runtime protocol from config change flow
7. Register subscribers for all 8 currently dropped events (rag.*, workflow.idempotency_hit, config.validation_error, memory.fact_conflict, memory.index_updated, database.connection_pooled)

#### Acceptance Criteria

- [ ] Single EventBus instance handles all system and plugin events
- [ ] Plugin events are namespaced (`plugin.{id}.event_type`); plugins cannot subscribe to `system.*`
- [ ] A subscriber exception does not crash the emit sequence
- [ ] Runtime protocol handlers use EventBus subscription for config changes
- [ ] All 8 previously-dropped events have at least one subscriber

#### Tests

- `tests/core/test_event_bus.py`: async dispatch, error isolation, namespace isolation, wildcard matching
- `tests/plugins/test_plugin_events.py`: plugin events namespaced, system events blocked
- `tests/core/test_runtime_events.py`: runtime subscriptions migrated

---

### WP-005: Config Unification

**Files:** `core/config_registry.py`, `core/config_schema.py`, `core/config.py`, `core/configuration/service.py`, `core/settings/store.py`

**Depends on:** WP-001, WP-004 (for event notification)

**Risk:** Low — backward-compatible shims; all existing callers continue to work

**Rollback:** Restore old shims, remove ConfigService wrapper

**Estimated LOC:** +120, -60

**Owner:** Core Platform

#### Scope

1. Replace env var cache (`_scan_env_vars()` at import) with live `os.environ.get()` on every `get()` call
2. Add file watcher (`watchdog`) for config.yaml changes; publish `config.reloaded` event on change
3. Route `SettingsStore` reads through ConfigService (single resolution chain)
4. Route both REST config endpoints (`/config`, `/settings`) through ConfigService
5. Add automatic masking for sensitive values (`configuration.get(key, raw=True)` vs default mask)

#### Acceptance Criteria

- [ ] All existing callers of `configuration.get()`, `SettingsStore.get()`, and `config.*` work unchanged
- [ ] Environment variables set after application start are picked up without reload()
- [ ] Editing config.yaml triggers `config.reloaded` event
- [ ] `/config` and `/settings` REST endpoints return consistent values
- [ ] `openai.api_key` and other sensitive values are masked in logs by default

#### Tests

- `tests/config/test_unified_service.py`: resolution chain, live env read, file watcher
- `tests/config/test_sensitive_masking.py`: masked by default, raw=True returns value
- `tests/api/test_config_endpoints.py`: both endpoints return same values

---

### WP-006: Planner Unification

**Files:** `core/planner/` (extend), `brain/planner/` (deprecate), `brain/goals/` (deprecate), `core/planner/store.py` (extend), new UnifiedStore

**Depends on:** WP-002, WP-003

**Risk:** High — 4 incompatible goal/plan stores must be merged; brain planner DAG logic must be reimplemented

**Rollback:** Restore brain/planner, brain/goals, old PlanStore

**Estimated LOC:** +400, -250

**Owner:** Planner

#### Scope

1. Define `Planner` ABC/protocol in `core/planner/` with `create_plan(goal, context) → Plan`
2. Implement LLM-based decomposition fallback: if keyword heuristics produce < 2 sub-goals, call LLM
3. Create `UnifiedStore` with single `goals_plans` table and unified status enum
4. Migrate PlanStore, GoalManager, brain goals, and task store data into UnifiedStore
5. Replace brain planner's internal planner with CorePlanner
6. Wire `PlanHealthEngine` into automatic replanning
7. Deprecate `brain/planner/` and `brain/goals/`

#### Acceptance Criteria

- [ ] `Planner` protocol defined and implemented by CorePlanner
- [ ] Brain planner uses CorePlanner under the hood
- [ ] All goal/plan data lives in UnifiedStore (single table, unified status)
- [ ] Keyword heuristic decomposition unchanged for known tasks; LLM fallback activates for novel tasks
- [ ] PlanHealthEngine triggers automatic replanning for stalled plans
- [ ] No data loss — all existing plans survive migration

#### Tests

- `tests/planner/test_planner_protocol.py`: all planners implement the same interface
- `tests/planner/test_unified_store.py`: CRUD, status transitions, cross-user isolation
- `tests/planner/test_llm_fallback.py`: fallback activates for novel tasks, not for known tasks
- `tests/planner/test_replanning.py`: PlanHealthEngine triggers replanning correctly
- `tests/migration/test_goal_data_migration.py`: all 4 sources → UnifiedStore, no data loss

---

### WP-007: Memory Unification

**Files:** `memory/` (extend), `brain/memory/` (deprecate), `core/memory.py` (deprecate), `core/memory_vector.py` (deprecate), `memory/fact_store.py`, `memory/embedding_memory.py`

**Depends on:** WP-002

**Risk:** High — 6 independent stores per interaction, incompatible embedding formats, System B consumers must be migrated

**Rollback:** Restore brain/memory/ backends, revert MemoryFacade changes, restore old embedding format

**Estimated LOC:** +500, -300

**Owner:** Memory

#### Scope

1. Move `brain/memory/` stores (EpisodicMemory, SemanticMemory, TaskMemory, DecisionMemory) into `memory/` package as MemoryFacade backends
2. Register new backends in MemoryFacade: `EpisodicStore`, `DecisionStore`
3. Migrate System B consumers (UnifiedBrain, automation loop, learning engine) to MemoryFacade
4. Standardize embedding serialization: adopt `struct.pack` format everywhere; migrate existing `np.tobytes` data
5. Merge 2 ChromaDB instances → 1 vector store
6. Remove `core/memory.py` and `core/memory_vector.py`
7. Implement two-phase memory write: primary store (Mem0/FactStore) → async propagation to secondary stores

#### Acceptance Criteria

- [ ] MemoryFacade.store() writes to all registered backends (facts, episodes, decisions, tiers)
- [ ] MemoryFacade.recall() queries all backends, deduplicates by content, reranks by relevance+recency+confidence
- [ ] System B consumers use MemoryFacade, not brain/memory/
- [ ] All embeddings use the same binary format (`struct.pack`)
- [ ] Single ChromaDB instance serves all vector queries
- [ ] Two-phase write: primary write is synchronous; secondary propagation is async but guaranteed
- [ ] `core/memory.py` and `core/memory_vector.py` are removed

#### Tests

- `tests/memory/test_unified_facade.py`: store/recall through all backends, dedup, rerank
- `tests/memory/test_episodic_store.py`: CRUD, timestamp queries
- `tests/memory/test_decision_store.py`: CRUD, outcome recording
- `tests/memory/test_embedding_standardization.py`: struct.pack round-trip, old data migration
- `tests/memory/test_vector_merge.py`: single ChromaDB instance, correct results
- `tests/memory/test_two_phase_write.py`: sync + async propagation, crash recovery
- `tests/migration/test_brain_memory_migration.py`: brain consumers → MemoryFacade

---

### WP-008: Workflow Enhancements

**Files:** `core/workflow/engine.py`, `core/workflow/storage.py`, `core/workflow/models.py`, `core/workflow/recorder.py`

**Depends on:** WP-001

**Risk:** Low — additive changes; existing workflows continue unchanged

**Rollback:** Revert idempotency enforcement, timeout, ExecutionGraph persistence

**Estimated LOC:** +200, -20

**Owner:** Workflow

#### Scope

1. Enforce idempotency keys: UNIQUE index on `workflow_steps.idempotency_key`; return cached result on duplicate
2. Auto-generate idempotency keys for pipeline-initiated workflows (use trace_id)
3. Subscribe Telemetry and Monitoring to `workflow.idempotency_hit`
4. Add workflow-level timeout: `WorkflowEngine.start_workflow(timeout_seconds=N)` — hard stop after N seconds
5. Persist ExecutionGraph to workflow.db (currently in-memory only)
6. Integrate LongHorizonFSM as a workflow step type

#### Acceptance Criteria

- [ ] Duplicate idempotency key returns cached result instead of creating new execution
- [ ] Pipeline-initiated workflows always have idempotency keys
- [ ] `workflow.idempotency_hit` is logged and monitored
- [ ] Workflow with timeout=N stops executing after N seconds
- [ ] ExecutionGraph survives process restart
- [ ] LongHorizonFSM can be used as a workflow step

#### Tests

- `tests/workflow/test_idempotency.py`: duplicate key → cache hit, in-progress → DUPLICATE status
- `tests/workflow/test_timeout.py`: timeout stops execution, raises TimeoutError
- `tests/workflow/test_execution_graph.py`: persisted graph survives restart
- `tests/workflow/test_fsm_integration.py`: LongHorizonFSM as workflow step

---

### WP-009: Storage Consolidation

**Files:** Multiple — every file that creates/manages a SQLite database or JSON file, `core/database.py`, `core/database_models.py`, `core/auth.py`, `memory/fact_store.py`, `core/workflow/storage.py`, `core/planner/store.py`, `core/activity/storage.py`, `core/persistence/store.py`, `brain/persistence.py`

**Depends on:** WP-006, WP-007, WP-008

**Risk:** Medium — 27+ databases to 5 bounded-context databases, data migration, Alembic coverage

**Rollback:** Restore original database files, revert connection strings

**Estimated LOC:** +600, -400

**Owner:** Core Platform + each bounded-context owner

#### Scope

**Sub-WP-009a: AuthManager → SQLite**
1. Create `users` and `sessions` tables in `data/system.db`
2. Write Alembic migration
3. Migrate AuthManager from JSON files (sessions.json, auth.json) to SQLite
4. Keep JSON as read-only fallback during migration window

**Sub-WP-009b: Alembic Coverage**
1. Audit all 24+ ORM tables — ensure every table has an Alembic revision
2. Add missing Alembic migrations (gap: 13 of 24 tables uncovered)
3. Replace `create_all()` calls with Alembic `upgrade()`

**Sub-WP-009c: Bounded-Context DBs**
1. Create `data/memory.db` — migrate FactStore, EmbeddingMemory, episodic/decision data out of their current DBs
2. Create `data/workflow.db` — targets for sync ORM models, WorkflowStore, ActivityStore
3. Create `data/planner.db` — UnifiedStore, PlanStore, goal data
4. Update connection strings and file paths across all consumers
5. Remove old DB files after verification

**Sub-WP-009d: User-Scoped State**
1. Migrate `~/.jarvis/*.db` → `~/.jarvis/user.db`
2. Migrate CheckpointStore, AgentGraph, BrowserManager, DesktopController state

#### Acceptance Criteria

- [ ] AuthManager reads from and writes to SQLite (JSON files read-only during migration)
- [ ] Every table has an Alembic migration
- [ ] `create_all()` calls are removed from production code
- [ ] All 5 bounded-context databases exist and are populated correctly
- [ ] All old DB files are removed after data verification
- [ ] No cross-context foreign keys
- [ ] All existing tests pass with new database layout

#### Tests

- `tests/storage/test_auth_migration.py`: JSON → SQLite, data integrity, rollback
- `tests/storage/test_alembic_coverage.py`: every table has a migration
- `tests/storage/test_bounded_context_isolation.py`: no cross-context foreign keys
- `tests/storage/test_migration_data_integrity.py`: row counts, checksums after migration
- `tests/storage/test_user_db_migration.py`: ~/.jarvis/*.db → user.db

---

### WP-010: Identity & Permission

**Files:** `core/auth.py`, `core/authz/`, `core/permission/`, `core/identity/`, `core/tools/security.py`

**Depends on:** WP-009 (Auth → SQLite), WP-005 (config for policy loading)

**Risk:** Medium — three authorization systems must be unified; scope changes affect every tool call

**Rollback:** Restore old AuthContext, disable Authorizer facade, restore individual authz calls

**Estimated LOC:** +250, -150

**Owner:** Security

#### Scope

1. Create unified `Authorizer` facade: single `authorize(user, scope, resource)` call that delegates to PolicyEngine (RBAC), PermissionManager (risk), and AuthManager (privileges)
2. Merge `IdentityContext` and `AuthContext` into single `Identity` dataclass (frozen, 6 fields: user, session, agent, tenant, authentication_state, scopes)
3. Replace `NON_ADMIN_BLOCKED_TOOLS` with scope-based RBAC using CapabilityRegistry (coordinate with WP-003)
4. Encrypt OAuth token storage (currently plaintext in JSON)
5. Deprecate old auth context classes

#### Acceptance Criteria

- [ ] `Authorizer.authorize()` replaces all direct calls to PolicyEngine, PermissionManager, AuthManager
- [ ] Single `Identity` dataclass used throughout pipeline and authz
- [ ] Tool access controlled by scope, not blocklist
- [ ] OAuth tokens encrypted at rest
- [ ] Old auth context classes (AuthContext, IdentityContext) deprecated

#### Tests

- `tests/identity/test_authorizer.py`: unified facade, delegation to sub-engines
- `tests/identity/test_identity_dataclass.py`: frozen, all fields, backward compat
- `tests/security/test_scope_rbac.py`: scope-based tool access, no blocklist
- `tests/security/test_oauth_encryption.py`: tokens encrypted at rest, decrypt for API calls

---

### WP-011: Cleanup & Removal

**Files:** Multiple — every deprecated module, JSON file, old DB file

**Depends on:** WP-002 through WP-010

**Risk:** Low — all consumers already migrated; deletion only

**Rollback:** Not needed (files can be restored from git)

**Estimated LOC:** -800 (net deletion)

**Owner:** Core Platform (coordinated)

#### Scope

For each deprecated module, produce a Removal Verification Report (template in CODE_OWNERSHIP_AUDIT.md §15) before deletion:

1. Remove `core/memory.py` (after WP-007)
2. Remove `core/memory_vector.py` (after WP-007)
3. Remove `brain/planner/` (after WP-006)
4. Remove `brain/memory/` (after WP-007)
5. Remove `brain/goals/` (after WP-006)
6. Remove `core/database_models.py` sync ORM (after WP-009 migration)
7. Remove `sessions.json` (after WP-009)
8. Remove `auth.json` (after WP-009)
9. Remove `data/brain.db` (after WP-009)
10. Remove `data/workflow.db` (replaced by bounded-context DBs)
11. Remove `database.db` from project root (after WP-009)
12. Standardize database path conventions
13. Create DatabaseRegistry with health endpoints

#### Acceptance Criteria

- [ ] Every deletion has a completed Removal Verification Report
- [ ] Zero references to deprecated modules remain in codebase
- [ ] Test suite passes without deprecated modules
- [ ] Application starts without deprecated modules
- [ ] No data loss — all data migrated before deletion

#### Tests

- `tests/architecture/test_no_deprecated_imports.py`: grep CI — fail if deprecated module imported by non-exempt consumer

---

## 3. Parallelization Matrix

| Track | Developer | WP-001 | WP-002 | WP-003 | WP-004 | WP-005 | WP-006 | WP-007 | WP-008 | WP-009 | WP-010 | WP-011 |
|-------|-----------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| **A** | Core Platform | ██ | ██ | ██ | | | | | | | | |
| **B** | Platform Ext | | | | ██ | ██ | | | | | | |
| **C** | Planner | | | | | | ██ | | | | | |
| **D** | Memory | | | | | | | ██ | | | | |
| **E** | Workflow | | | | | | | | ██ | | | |
| **F** | Storage | | | | | | | | | ██ | | |
| **G** | Security | | | | | | | | | ██ | ██ | |
| **H** | Cleanup | | | | | | | | | | | ██ |

### Dependency Blocking

| Week | Track A | Track B | Track C | Track D | Track E | Track F | Track G | Track H |
|------|---------|---------|---------|---------|---------|---------|---------|---------|
| 1-2  | WP-001 | — | — | — | — | — | — | — |
| 2-3  | WP-002 | WP-004 | — | — | WP-008 | — | — | — |
| 3-4  | WP-002 | WP-004 | — | — | WP-008 | — | — | — |
| 4-5  | WP-003 | WP-005 | — | WP-007 | — | — | — | — |
| 5-6  | WP-003 | — | WP-006 | WP-007 | — | — | — | — |
| 6-8  | — | — | WP-006 | WP-007 | — | — | — | — |
| 8-10 | — | — | — | — | — | WP-009 | WP-010 | — |
| 10-12| — | — | — | — | — | WP-009 | — | — |
| 12-13| — | — | — | — | — | — | — | WP-011 |

### What Can Parallelize

| Work Packages | Why Safe |
|---------------|----------|
| WP-004 (Event Bus) + WP-005 (Config) | Both depend on WP-001 only; no cross-dependency |
| WP-006 (Planner) + WP-007 (Memory) | Both depend on WP-002; no cross-dependency between planner and memory |
| WP-008 (Workflow) + WP-002 (Pipeline) | WP-008 depends on WP-001, can start same time as WP-002 |
| WP-009a (Auth→SQLite) + WP-009c (bounded context DBs) | Auth migration is isolated from other storage changes |
| WP-010 (Identity) + WP-009 (Storage) | WP-010 depends on WP-009 for SQLite auth tables; must be sequential within a track but can overlap with other work |

---

## 4. Breaking Changes

| # | Old API | New API | Affected Consumers | Migration |
|---|---------|---------|-------------------|-----------|
| 1 | `RuntimePipeline(pipeline).run(request)` | `Pipeline.execute(context)` | CLI, daemon, WebSocket, MCP, internal callers | Wrap in adapter; remove old class |
| 2 | `execute_tool_block(tool_type, content)` | `CapabilityRegistry.execute(capability_id, input)` | WorkflowEngine, control_loop, tests | Map tool_type to capability_id via registry |
| 3 | `brain.memory.MemoryManager.store(episode)` | `MemoryFacade.store(messages, user_id, memory_types=["episodic"])` | UnifiedBrain, automation loop, learning engine | Import memory/ instead of brain/memory/ |
| 4 | `brain.planner.Planner.create_plan(goal)` | `CorePlanner(protocol).create_plan(goal, context)` → `Plan` | UnifiedBrain | Implement CorePlanner protocol |
| 5 | `GoalManager.create_goal(desc)` / `PlanStore.create_plan(goal_id)` | `UnifiedStore.create_goal(desc)` | brain/goals, planner, API | Single method call |
| 6 | `NON_ADMIN_BLOCKED_TOOLS = [...]` | `CapabilityRegistry.lookup(scope=user.scopes)` | security.py, capability_selection.py | Replace list with registry query |
| 7 | `AuthManager.validate_token(token)` → `_sessions[token]` | `AuthManager.validate_token(token)` → SQLite query | identity, middleware | Internal implementation change; API unchanged |
| 8 | `EventBus.emit(type, data)` (sync, no namespace) | `EventBus.emit(type, data, namespace="system")` | All publishers | Add namespace parameter |
| 9 | `PluginEventBus.emit(type, data)` | `EventBus.emit(type, data, namespace=f"plugin.{id}")` | All plugins | Replace PluginEventBus import with EventBus |
| 10 | `configuration.get(key)` (env cached at import) | `configuration.get(key)` (live env read) | All consumers | No API change; behavior change (env changes picked up immediately) |
| 11 | `core/memory.MemoryManager` | `memory.MemoryFacade` | MCP memory server, brain similarity | Update import path |
| 12 | Multiple ChromaDB instances | Single ChromaDB instance | All vector query callers | Update connection string |

### Breaking Change Mitigation

- **#1-#5**: Keep old API as deprecated shim for 1 release cycle. Log deprecation warning on each call.
- **#6**: Keep `NON_ADMIN_BLOCKED_TOOLS` as read-only reference during transition; remove after all callers use registry.
- **#7**: No API change (internal only).
- **#8-#9**: Accept both old and new emit signatures during transition.
- **#10**: Behavior change — document in changelog; no code change needed by consumers.
- **#11-#12**: Deprecated imports with `__getattr__` shim in `core/memory.py`.

---

## 5. Migration Checkpoints

After each checkpoint: run full test suite, verify no regressions, benchmark performance.

### Checkpoint 1: Foundation Complete

**Trigger:** WP-001 done

**Verification:**
- [ ] 50 concurrent requests complete without error
- [ ] tool_factory thread-safe
- [ ] TieredMemory thread-safe
- [ ] All existing tests pass (no regressions from thread-safety changes)

**Performance:** Same or better (no added latency)

---

### Checkpoint 2: Pipeline Unification Complete

**Trigger:** WP-002 + WP-003 done

**Verification:**
- [ ] No RuntimePipeline references in codebase
- [ ] All entry points go through canonical Pipeline.execute()
- [ ] CapabilitySelectionStage uses registry, not hardcoded dict
- [ ] NON_ADMIN_BLOCKED_TOOLS removed
- [ ] All existing tests pass
- [ ] Agent routing uses capability data

**Performance:** Compare latency before/after for HTTP and WebSocket requests. Accept <5% increase.

---

### Checkpoint 3: Event Bus + Config Unified

**Trigger:** WP-004 + WP-005 done

**Verification:**
- [ ] Single EventBus with namespaces
- [ ] Config changes picked up without restart
- [ ] Sensitive values masked in logs
- [ ] Both REST config endpoints return same values
- [ ] All existing tests pass

**Performance:** No measurable impact (event dispatch + config resolution are sub-millisecond)

---

### Checkpoint 4: Planner Complete

**Trigger:** WP-006 done

**Verification:**
- [ ] CorePlanner protocol implemented
- [ ] Brain planner uses CorePlanner
- [ ] UnifiedStore has all goal/plan data
- [ ] LLM fallback activates for novel tasks
- [ ] PlanHealthEngine triggers replanning
- [ ] No data loss from 4 old stores

**Performance:** Compare plan creation time before/after. LLM fallback adds latency for novel tasks (acceptable).

---

### Checkpoint 5: Memory Complete

**Trigger:** WP-007 done

**Verification:**
- [ ] MemoryFacade has all backends (facts, episodes, decisions, tiers, vector)
- [ ] System B consumers use MemoryFacade
- [ ] Single embedding format (struct.pack)
- [ ] Single ChromaDB instance
- [ ] Two-phase write operational
- [ ] `core/memory.py` and `core/memory_vector.py` removed

**Performance:** Compare recall latency before/during/after. Two-phase write may increase write latency slightly (acceptable). Recall should be same or faster.

---

### Checkpoint 6: Workflow Complete

**Trigger:** WP-008 done

**Verification:**
- [ ] Idempotency enforced (duplicate keys return cached result)
- [ ] Workflow timeout works
- [ ] ExecutionGraph persisted
- [ ] LongHorizonFSM integrated
- [ ] `workflow.idempotency_hit` monitored

**Performance:** Negligible overhead (idempotency key lookup is a single indexed query)

---

### Checkpoint 7: Storage Complete

**Trigger:** WP-009 done

**Verification:**
- [ ] AuthManager uses SQLite (JSON read-only fallback)
- [ ] Alembic covers every table
- [ ] No `create_all()` in production code
- [ ] 5 bounded-context databases operational
- [ ] All old DB files removed
- [ ] No cross-context foreign keys

**Performance:** SQLite queries are equivalent or faster than JSON file reads. Verify with benchmark.

---

### Checkpoint 8: Identity Complete

**Trigger:** WP-010 done

**Verification:**
- [ ] `Authorizer.authorize()` replaces all direct authz calls
- [ ] Single `Identity` dataclass used everywhere
- [ ] Tool access controlled by scope, not blocklist
- [ ] OAuth tokens encrypted
- [ ] Old auth context classes deprecated

**Performance:** Authorizer adds a facade layer (<0.1ms per call). Acceptable.

---

### Checkpoint 9: Cleanup Complete

**Trigger:** WP-011 done

**Verification:**
- [ ] Every deletion has a completed Removal Verification Report
- [ ] Zero references to deprecated modules
- [ ] Full test suite passes
- [ ] Application starts cleanly
- [ ] No data loss

**Performance:** Deletions only remove code; no performance impact.

---

## 6. Risk Register

| # | Risk | WP | Probability | Impact | Mitigation | Rollback |
|---|------|----|-------------|--------|------------|----------|
| R1 | **Thread-safety fix introduces new race** | 001 | Low | Critical (crashes under load) | Exhaustive concurrent test with 50 threads; code review by 2 developers | Revert tool_factory.py changes |
| R2 | **Pipeline migration misses a caller** | 002 | Medium | High (unreachable functionality) | Grep for all `RuntimePipeline`, `pipeline.run()`, `run_pipeline`, `Phase.*` references; add import-monitoring CI rule | Restore RuntimePipeline class |
| R3 | **Capability Registry entry missing for a tool** | 003 | Medium | High (tool silently unavailable) | Automated audit: compare registry keys vs tool file list; integration test that calls every tool | Add missing entry (non-breaking) |
| R4 | **Memory data loss during unification** | 007 | High | Critical (user data lost) | Two-phase write (primary sync, secondary async); backup all stores before migration; checksum verification after migration | Restore from backup |
| R5 | **Embedding format migration corrupts vectors** | 007 | Medium | High (silent result degradation) | Write both formats during transition; compare cosine similarity results before/after | Revert to old format, re-migrate |
| R6 | **Planner data migration loses goals** | 006 | High | High (lost planning state) | Row-count verification across all 4 old stores vs UnifiedStore; keep old DBs as backup for 1 week | Restore old stores |
| R7 | **Event bus namespace enforcement breaks plugins** | 004 | Medium | Medium (plugin functionality lost) | Staged rollout: warning-only mode for 1 week, then enforcement; test all plugins in staging | Disable namespace enforcement |
| R8 | **Auth JSON→SQLite migration loses sessions** | 009 | Medium | Medium (users must re-login) | Keep JSON as read-only fallback during migration; duplicate writes to both stores for 1 week | Restore JSON as primary |
| R9 | **Config live env read causes performance regression** | 005 | Low | Low (50 dict lookups per get()) | Profile before/after; cache env var fd if needed | Revert to cached read |
| R10 | **Storage migration (27→5 DBs) exceeds timeline** | 009 | High | High (blocks Identity + Cleanup) | Parallelize sub-packages (Auth migration independent from bounded-context DB creation); deliver incremental value per sub-package | Complete sub-packages independently |
| R11 | **Bounded-context DBs introduce cross-context performance issues** | 009 | Medium | Medium (service-to-service call overhead) | Profile cross-context query patterns before migration; denormalize hot paths if needed | Add cross-context foreign keys as last resort |
| R12 | **Authorizer facade adds latency to every tool call** | 010 | Low | Medium (authorization overhead) | Profile before/after; cache authorization results per-request (PipelineContext scope) | Bypass facade for known-hot paths |

---

## 7. Testing Matrix

| WP | Unit Tests | Integration Tests | E2E Tests | Performance Tests | Regression Tests |
|----|-----------|------------------|-----------|-------------------|-----------------|
| **001** | tool_factory concurrency (10 threads, 100 calls), TieredMemory concurrent access | — | 50 concurrent HTTP requests | 50 concurrent requests vs 1 (compare latency) | All existing tests pass |
| **002** | Pipeline stage execution, adapter conversion | CLI+WS+MCP → Pipeline integration | Full request round-trip through each entry point | Request latency before/after (HTTP, WebSocket, CLI) | All pipeline tests pass |
| **003** | Registry CRUD, scope lookup, agent_type lookup | CapabilitySelectionStage with registry vs hardcoded dict | Call every tool through pipeline | Registry lookup latency (<1ms) | All security tests pass |
| **004** | Namespace enforcement, async dispatch, error isolation | Plugin events with namespace, system event blocking | Full plugin lifecycle with new EventBus | Event dispatch latency before/after | All event bus tests pass |
| **005** | Resolution chain (6 levels), live env read, file watcher | REST config endpoints consistency | Config change → event → subscriber chain | Config.get() latency before/after | All config tests pass |
| **006** | Planner protocol conformance, UnifiedStore CRUD, LLM fallback activation | Brain planner → CorePlanner integration, 4-store data migration | Goal creation → decomposition → execution → completion | Plan creation time (keyword vs LLM fallback) | All planner tests pass |
| **007** | MemoryFacade backend registration, dedup, rerank, embedding format round-trip | System B consumer migration, two-phase write crash recovery | Full memory store → recall → fact extraction → preference update pipeline | Recall latency before/after, write latency (sync+async) | All memory tests pass |
| **008** | Idempotency key dedup, timeout enforcement, ExecutionGraph persistence | Workflow with timeout + idempotency + LongHorizonFSM step | Full workflow lifecycle with all enhancements | Overhead of idempotency lookup (<1ms) | All workflow tests pass |
| **009** | Auth SQLite CRUD, Alembic migration up+down, bounded-context isolation | JSON→SQLite data integrity, 27→5 DB migration | Full system startup with new DB layout | Query latency: SQLite vs JSON, cross-context call overhead | All storage tests pass |
| **010** | Authorizer facade delegation, Identity dataclass frozen+fields, scope RBAC | Unified auth path (Authorizer → all 3 engines) | Full request with auth → authorization → execution → response | Authorization latency before/after (<0.1ms) | All identity/security tests pass |
| **011** | — | — | Full system startup without deprecated modules | — | Full test suite passes, grep-zero deprecated imports |

### Testing Commands

```bash
# Run all architecture audit tests
pytest tests/architecture/ -v

# Run all unit tests
pytest tests/ -x --ignore=tests/architecture --ignore=tests/integration

# Run integration tests
pytest tests/integration/ -v

# Run performance benchmarks
pytest tests/performance/ --benchmark-only

# Verify zero deprecated imports
grep -r "from core.memory import\|from brain.planner\|from brain.memory\|from brain.goals" --include="*.py" || echo "OK"

# Full regression suite
pytest tests/ -v --timeout=120
```

---

## Appendix: Document Inventory

| Document | Path | Purpose |
|----------|------|---------|
| Dependency Graph Audit | `DEPENDENCY_GRAPH_AUDIT.md` | Bootstrap order, singleton dependencies, cycle risks |
| State Architecture Audit | `STATE_ARCHITECTURE_AUDIT.md` | 14 state domains, persistence, thread safety |
| Request Pipeline Audit | `REQUEST_PIPELINE_AUDIT.md` | 19 stages, 2 pipeline architectures |
| Execution Architecture Audit | `EXECUTION_ARCHITECTURE_AUDIT.md` | Tool dispatch, thread-hostile factory, security gaps |
| Data Flow Audit | `DATA_FLOW_AUDIT.md` | Data transformations, copies, serialization, divergence risks |
| Event Flow Audit | `EVENT_FLOW_AUDIT.md` | 79 events, 3 buses, 8 dropped, 1 duplicate |
| Memory Architecture Audit | `MEMORY_ARCHITECTURE_AUDIT.md` | 3 concurrent memory systems, 18+ stores |
| Planner Architecture Audit | `PLANNER_ARCHITECTURE_AUDIT.md` | 3 planners, 4 goal stores, incompatible status enums |
| Workflow Architecture Audit | `WORKFLOW_ARCHITECTURE_AUDIT.md` | Best-designed subsystem, minor improvements only |
| Identity & Permission Audit | `IDENTITY_PERMISSION_AUDIT.md` | 5 security layers, 3 AuthZ systems, 36-tool blocklist |
| Storage Architecture Audit | `STORAGE_ARCHITECTURE_AUDIT.md` | 27+ SQLite DBs, 60+ tables, partial Alembic |
| Configuration Audit | `CONFIGURATION_AUDIT.md` | 4 config systems, precedence, drift points |
| Target Architecture | `TARGET_ARCHITECTURE.md` | Target state per subsystem, implementation phases, ADRs |
| Code Ownership Audit | `CODE_OWNERSHIP_AUDIT.md` | Ownership per module, interface contracts, deprecation registry, Removal Verification Report template |
| ADR-001 | `ADR-001-configuration-service.md` | ConfigurationService is sole config owner |
| ADR-002 | `ADR-002-memory-package.md` | Memory package reorganization |
| ADR-003 | `ADR-003-request-classifier.md` | Request classifier architecture |
| ADR-004 | `ADR-004-agent-registry.md` | Agent registry |
| ADR-005 | `ADR-005-event-bus.md` | Event bus |
| ADR-006 | `ADR-006-canonical-pipeline.md` | Canonical pipeline |
| ADR-007 | `ADR-007-reasoning-engine.md` | Reasoning engine |
| ADR-008 | `ADR-008-runtime-v1.md` | Runtime v1 |
| ADR-009 | `ADR-009-memory-unification.md` | MemoryFacade as unified memory API |
| ADR-010 | `ADR-010-planner-unification.md` | CorePlanner as single planner protocol |
| ADR-011 | `ADR-011-bounded-context-databases.md` | Bounded-context DB strategy |
| ADR-012 | `ADR-012-pipeline-only-path.md` | Canonical pipeline as sole request path |
| ADR-013 | `ADR-013-capability-registry-centralization.md` | CapabilityRegistry as central authority |
| ADR-014 | `ADR-014-authmanager-migration.md` | AuthManager JSON→SQLite |
| ADR-015 | `ADR-015-idempotency-enforcement.md` | Idempotency enforcement in WorkflowEngine |
