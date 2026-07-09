# Deletion & Migration Tracker — Phase 4 (Document 14)

> **Purpose:** Track every module, file, database, and public interface scheduled for removal. Each entry has a reason, replacement, dependency audit, and planned delete date. No deletion may proceed without a completed Removal Verification Report (template in CODE_OWNERSHIP_AUDIT.md §15).
>
> **Rule:** Before deleting anything, complete a Removal Verification Report, link it here, and wait one review cycle. The "Migration Completed" column must be 100% before "Delete Date" is reached.

---

## Lifecycle

```
IDENTIFIED → PLANNED → IN_PROGRESS (migration) → VERIFIED (Removal Report complete) → REMOVED
```

### Legend

| Status | Meaning |
|--------|---------|
| 🆕 IDENTIFIED | Scheduled for removal, no work started |
| 📋 PLANNED | Removal plan exists, dependencies known |
| 🔧 IN PROGRESS | Active migration work underway |
| ✅ VERIFIED | Removal Verification Report completed, ready to delete |
| 🗑 REMOVED | Deleted from codebase |
| ⏸ BLOCKED | Blocked by another task or decision |

---

## 1. Deprecated Modules (Core)

| # | Module | Path | Reason | Replacement | Depends On | Status |
|---|--------|------|--------|-------------|------------|--------|
| D01 | `core/memory.py` | `core/memory.py` | System C memory manager; deprecated since v3.2, superseded by `memory/` package | `memory/MemoryFacade` | WP-007 (Memory Unification), System B migration | 🆕 IDENTIFIED |
| D02 | `core/memory_vector.py` | `core/memory_vector.py` | Duplicate ChromaDB vector store; fold into mem0 adapter | `memory/mem0_adapter.py` (single ChromaDB instance) | WP-007 (vector merge) | 🆕 IDENTIFIED |
| D03 | `core/plan_manager.py` | `core/plan_manager.py` | JSON-based in-memory plan manager; no persistence, no thread safety | PlanStore / UnifiedStore | WP-006 (Planner Unification) | 🆕 IDENTIFIED |
| D04 | `core/database_models.py` | `core/database_models.py` | Sync ORM models sharing `data/jarvis.db` with async ORM; SQLAlchemy sync engine adds complexity | `core/database.py` (async ORM only) | WP-009 (Storage Consolidation) | 🆕 IDENTIFIED |
| D05 | `core/pipeline.py` (RuntimePipeline) | `core/pipeline.py` | Legacy 10-phase RuntimePipeline; dual execution path with canonical pipeline | `core/pipeline/pipeline.py` (canonical 19-stage pipeline) | WP-002 (Canonical Pipeline) | 🆕 IDENTIFIED |
| D06 | `core/control_loop.py` | `core/control_loop.py` | 1132-line build automation loop with its own event/memory/UI system; duplicates WorkflowEngine | WorkflowEngine + EventBus + MemoryFacade | WP-002, WP-007, WP-008 | 🆕 IDENTIFIED |
| D07 | `core/runtime/registry.py` | `core/runtime/registry.py` | Unused — exists but never referenced outside its own module | Remove (no replacement needed) | Confirmation audit | 🆕 IDENTIFIED |

---

## 2. Deprecated Modules (Brain)

| # | Module | Path | Reason | Replacement | Depends On | Status |
|---|--------|------|--------|-------------|------------|--------|
| D08 | `brain/planner/` | `brain/planner/` | Fixed 3-node DAG, in-memory only, no persistence; incompatible output format | CorePlanner protocol (`core/planner/`) | WP-006 (Planner Unification) | 🆕 IDENTIFIED |
| D09 | `brain/memory/` | `brain/memory/` | System B agent-facing memory; 4 stores (episodic, semantic, task, decision) that duplicate memory/ package | MemoryFacade backends (`memory/`): `EpisodicStore`, `FactStore` (merged), `DecisionStore` | WP-007 (Memory Unification) | 🆕 IDENTIFIED |
| D10 | `brain/goals/` | `brain/goals/` | Duplicate goal CRUD with `PlanStore`; incompatible status enum, shares `data/brain.db` | UnifiedStore (merged `goals_plans` table) | WP-006 (Planner Unification) | 🆕 IDENTIFIED |
| D11 | `brain/executor/executor.py` | `brain/executor/executor.py` | Separate tool dispatch system that bypasses `core/tools/execution.py`; causes dual execution universe | `execute_tool_block()` via canonical dispatch | WP-007 (after memory migration) | 🆕 IDENTIFIED |
| D12 | `brain/persistence.py` | `brain/persistence.py` | Checkpoint/decision storage in `data/brain.db`; duplicates `core/checkpoint_manager.py` | Unified CheckpointStore | WP-009 (after brain.db migration) | 🆕 IDENTIFIED |

---

## 3. Legacy Pipeline & Execution

| # | Module | Path | Reason | Replacement | Depends On | Status |
|---|--------|------|--------|-------------|------------|--------|
| D13 | RuntimePipeline class | `core/pipeline.py` (class) | 10-phase pipeline parallel to canonical 19-stage pipeline | `Pipeline.execute()` | WP-002 | 🆕 IDENTIFIED |
| D14 | 10-phase state enum | `core/runtime_pipeline.py` | Phase constants for RuntimePipeline | Remove (no replacement) | D13 | 🆕 IDENTIFIED |
| D15 | LangGraph pipeline references | Various graph defs | Legacy pipeline config using LangGraph | Canonical pipeline stage config | D13 | 🆕 IDENTIFIED |
| D16 | `pipeline.run()` callers | All files calling `.run()` instead of `.execute()` | Dual-method API; `.execute()` is the canonical method | Standardize on `.execute()` | D13 | 🆕 IDENTIFIED |
| D17 | `NON_ADMIN_BLOCKED_TOOLS` | `core/tools/security.py` | Hardcoded blocklist bypasses capability registry and RBAC | Scope-based RBAC via `CapabilityRegistry.lookup(scope=user.scopes)` | WP-003 | 🆕 IDENTIFIED |

---

## 4. Event Bus Duplicates

| # | Module | Path | Reason | Replacement | Depends On | Status |
|---|--------|------|--------|-------------|------------|--------|
| D18 | PluginEventBus | `plugin_system/core.py` | Second event bus for plugins; creates 3-event-bus fragmentation | Canonical EventBus with namespace isolation (`plugin.{id}.*`) | WP-004 (Event Bus Unification) | 🆕 IDENTIFIED |
| D19 | Runtime protocol handler | `core/runtime.py` | Config change notification protocol; reinvents EventBus subscription | EventBus subscription to `config.changed` | WP-004, WP-005 | 🆕 IDENTIFIED |
| D20 | WorkflowEngine SQLite event log | `core/workflow/storage.py` (events table) | Workflow events written to SQLite but not broadcast; no subscribers can react | Canonical EventBus publish (`workflow.*` namespace) in addition to SQLite log | WP-004 | 🆕 IDENTIFIED |
| D21 | Scheduler tick callbacks | `core/scheduler/scheduler.py` | Synchronous callbacks instead of EventBus events | Canonical EventBus publish (`scheduler.tick`) | WP-004 | 🆕 IDENTIFIED |

---

## 5. Storage (Databases & Files)

| # | Module / File | Path | Reason | Replacement | Depends On | Status |
|---|--------------|------|--------|-------------|------------|--------|
| D22 | `data/auth.json` | `data/auth.json` | Non-transactional JSON user storage; crash-unsafe | SQLite `users` table in `data/system.db` | WP-009a | 🆕 IDENTIFIED |
| D23 | `data/sessions.json` | `data/sessions.json` | Non-transactional JSON session storage; crash-unsafe | SQLite `sessions` table in `data/system.db` | WP-009a | 🆕 IDENTIFIED |
| D24 | `data/brain.db` | `data/brain.db` | Fragmented brain state (goals + memory + checkpoints in one file); 8 tables shared by 3 systems | Migrate to bounded-context DBs (`data/memory.db`, `data/planner.db`, `~/.jarvis/user.db`) | WP-009c | 🆕 IDENTIFIED |
| D25 | `data/workflow.db` (shared) | `data/workflow.db` | 3 owners (WorkflowStore, PlanStore, ActivityStore) in one file; implicit schema coupling | Per-context DBs (`data/workflow.db` — workflow only, `data/planner.db`, `data/memory.db`) | WP-009c | 🆕 IDENTIFIED |
| D26 | `database.db` (project root) | `database.db` | Unknown origin; no owner committed in CODE_OWNERSHIP_AUDIT | Determine origin first; likely merge or remove | Investigation | 🆕 IDENTIFIED |
| D27 | `ai_os_memory.db` | `ai_os_memory.db` | Unowned orphan database used by deprecated `core/memory.py` | Integrate into `data/memory.db` or remove | D01 (core/memory.py removal) | 🆕 IDENTIFIED |
| D28 | `data/jarvis_memory.db` | `data/jarvis_memory.db` | FactStore backing DB; migrate to bounded-context `data/memory.db` | `data/memory.db` (bounded-context memory DB) | WP-009c | 🆕 IDENTIFIED |
| D29 | `data/jarvis.db` (shared async+sync ORM) | `data/jarvis.db` | Two ORM systems sharing one database; schema conflicts possible | `data/app.db` (single async ORM, Alembic-managed) | WP-009b (Alembic coverage) | 🆕 IDENTIFIED |
| D30 | `~/.jarvis/decision_memory.json` | `~/.jarvis/decision_memory.json` | Non-transactional JSON decision history | SQLite `DecisionStore` in `data/memory.db` | WP-007 (DecisionStore) | 🆕 IDENTIFIED |
| D31 | `~/.jarvis/checkpoints/*.json` | `~/.jarvis/checkpoints/` | Non-transactional JSON checkpoint files; crash-corruptible | SQLite CheckpointStore in `~/.jarvis/user.db` | WP-009d | 🆕 IDENTIFIED |
| D32 | `data/brain.db` → `data/planner.db` | (goals data) | GoalManager, PlanManager goals migrated to UnifiedStore | `data/planner.db` (UnifiedStore) | D10 | 🆕 IDENTIFIED |
| D33 | `data/pc_agent.db` | `data/pc_agent.db` | Standalone agent DB; consolidate into bounded-context | `~/.jarvis/user.db` or own context | WP-009d | 🆕 IDENTIFIED |
| D34 | `~/.jarvis/feedback.db` | `~/.jarvis/feedback.db` | Standalone feedback store; consolidate | `~/.jarvis/user.db` | WP-009d | 🆕 IDENTIFIED |
| D35 | `~/.jarvis/benchmark.db` | `~/.jarvis/benchmark.db` | Standalone benchmark store; consolidate | `~/.jarvis/user.db` | WP-009d | 🆕 IDENTIFIED |
| D36 | `~/.jarvis/orchestration.db` | `~/.jarvis/orchestration.db` | Standalone orchestration store; consolidate | `~/.jarvis/user.db` | WP-009d | 🆕 IDENTIFIED |

---

## 6. UI & Frontend

| # | Module | Path | Reason | Replacement | Depends On | Status |
|---|--------|------|--------|-------------|------------|--------|
| D37 | Legacy WebSocket event format | `websocket/` (if exists) | Old event format incompatible with Observation Hub | New `observation.*` event format via EventBus | WP-004 | 🆕 IDENTIFIED |

---

## 7. Configuration

| # | Module | Path | Reason | Replacement | Depends On | Status |
|---|--------|------|--------|-------------|------------|--------|
| D38 | `_scan_env_vars()` at import | `core/config_registry.py` | Environment variable caching at import time; stale values after process start | Live `os.environ.get()` on every `get()` call | WP-005 | 🆕 IDENTIFIED |
| D39 | `SettingsStore` standalone reads | `core/settings/store.py` | Settings store bypassing ConfigService resolution chain | Route through ConfigService | WP-005 | 🆕 IDENTIFIED |

---

## 8. Identity & Permissions

| # | Module | Path | Reason | Replacement | Depends On | Status |
|---|--------|------|--------|-------------|------------|--------|
| D40 | `AuthContext` (old) | `core/identity/models.py` | Superseded by unified `Identity` dataclass | `Identity` dataclass (frozen, 6 fields) | WP-010 | 🆕 IDENTIFIED |
| D41 | `IdentityContext` (old) | `core/identity/models.py` | Superseded by unified `Identity` dataclass | `Identity` dataclass | WP-010 | 🆕 IDENTIFIED |
| D42 | `provider_sdk/permissions.py` | `provider_sdk/permissions.py` | Second `PermissionManager` with no synchronization to `core/permission/manager.py` | Single `PermissionManager` in `core/permission/` | WP-010 | 🆕 IDENTIFIED |
| D43 | `PermissionManager._audit_log` (in-memory) | `core/permission/manager.py` | In-memory audit log lost on crash; compliance violation | Persisted audit log in SQLite | WP-010 | 🆕 IDENTIFIED |

---

## 9. Duplicate State & Checkpoints

| # | Module | Path | Reason | Replacement | Depends On | Status |
|---|--------|------|--------|-------------|------------|--------|
| D44 | `CheckpointManager` (JSON) | `core/checkpoint_manager.py` | Non-transactional JSON checkpoints; crash-corruptible | SQLite-based CheckpointStore | WP-009 | 🆕 IDENTIFIED |
| D45 | `ProjectPersistence` (checkpoint features) | `brain/persistence.py` | Checkpoint storage in `data/brain.db`; duplicates `core/checkpoint_manager.py` | Unified CheckpointStore in `~/.jarvis/user.db` | WP-009 | 🆕 IDENTIFIED |
| D46 | `ConversationManager` (in-memory) | `session.py` (root) | In-memory session dict with no thread safety; duplicates `core/session_db.py` | Single SQLite SessionManager | WP-009 | 🆕 IDENTIFIED |

---

## 10. Duplicate Memory Stores (System B → MemoryFacade)

| # | Store | Path | Reason | Replacement | Depends On | Status |
|---|-------|------|--------|-------------|------------|--------|
| M01 | `brain/memory/episodic.py` | `brain/memory/episodic.py` | Duplicate episodic store (System B) | `memory/` `EpisodicStore` (target) | WP-007 | 🆕 IDENTIFIED |
| M02 | `brain/memory/semantic.py` | `brain/memory/semantic.py` | Duplicate fact store (RDF + categories + decay) | `memory/fact_store.py` (merge schema) | WP-007 | 🆕 IDENTIFIED |
| M03 | `brain/memory/task.py` | `brain/memory/task.py` | Duplicate task episode store | `memory/` `EpisodicStore` (task episodes as sub-type) | WP-007 | 🆕 IDENTIFIED |
| M04 | `brain/memory/decision.py` | `brain/memory/decision.py` | Duplicate agent routing decision store | `memory/` `DecisionStore` (merge agent routing + self-reflection) | WP-007 | 🆕 IDENTIFIED |
| M05 | `core/memory.MemoryManager` | `core/memory.py` | Deprecated System C memory manager | `memory/MemoryFacade` | WP-007 | 🆕 IDENTIFIED |
| M06 | `core.memory_vector.MemoryVectorStore` | `core/memory_vector.py` | Duplicate ChromaDB vector store | `memory/mem0_adapter.py` (single ChromaDB instance) | WP-007 | 🆕 IDENTIFIED |
| M07 | Duplicate ChromaDB instance | ChromaDB config | Second vector store instance | Single ChromaDB instance | WP-007 | 🆕 IDENTIFIED |

---

## 11. Deprecated Interfaces

| # | Interface | File | Reason | Replacement | Status |
|---|-----------|------|--------|-------------|--------|
| I01 | `core.memory.MemoryManager` | `core/memory.py` | Deprecated since v3.2 | `memory.memory_facade.MemoryFacade` | 🆕 IDENTIFIED |
| I02 | `core.memory.get_text_similarity()` | `core/memory.py` | Known dependency; needs `memory/` replacement | `memory/` utils | 🆕 IDENTIFIED |
| I03 | `brain.planner.Planner` | `brain/planner/planner.py` | Fixed 3-node DAG | `core.planner.Planner` protocol | 🆕 IDENTIFIED |
| I04 | `brain.memory.MemoryManager` | `brain/memory/memory_manager.py` | System B memory | `memory.memory_facade.MemoryFacade` | 🆕 IDENTIFIED |
| I05 | `brain.goals.GoalManager` | `brain/goals/goal_manager.py` | Duplicate goal CRUD | UnifiedStore | 🆕 IDENTIFIED |
| I06 | `Database URL` (legacy) | Various | Deprecated since v3.2 | `JARVIS_DB__URL` env var | 🆕 IDENTIFIED |

---

## 12. Removal Dependency Graph

```
Phase 2 (Pipeline)                      Phase 4 (Event Bus)                Phase 5 (Config)
D05 RuntimePipeline ─────────┐          D18 PluginEventBus                 D38 env cache at import
D13 RuntimePipeline class     │          D19 Runtime protocol              D39 SettingsStore standalone
D14 10-phase state enum       │          D20 Workflow SQLite events
D15 LangGraph config          │          D21 Scheduler tick callbacks
D16 pipeline.run() callers    │                │
                              │                │
Phase 3 (Capability)          │                │
D17 NON_ADMIN_BLOCKED_TOOLS   │                │
                              │                ▼
Phase 6 (Planner)             │          WP-002 + WP-003 + WP-004 + WP-005
D03 core/plan_manager.py      │                      │
D08 brain/planner/            │                      │
D10 brain/goals/              │                      │
I03 brain.planner.Planner     │                      │
I05 brain.goals.GoalManager   ├──────────────────────┘
                              │                      │
Phase 7 (Memory)              │                      │
D01 core/memory.py            │                      │
D02 core/memory_vector.py     │                      │
D09 brain/memory/             │                      │
D11 brain/executor/           │                      │
D30 decision_memory.json      │                      │
M01-M07 memory stores         │                      │
I01 core.memory.MemoryManager │                      │
I02 get_text_similarity()     │                      │
I04 brain.memory.MemoryManager│                      │
                              │                      │
Phase 8 (Workflow)            │                      │
D06 core/control_loop.py      │                      │
                              │                      │
                              ├──────────────────────┘
                              │
Phase 9 (Storage Consolidation)
D04 core/database_models.py
D12 brain/persistence.py
D22 data/auth.json
D23 data/sessions.json
D24 data/brain.db
D25 data/workflow.db (shared)
D26 database.db (root)
D27 ai_os_memory.db
D28 data/jarvis_memory.db
D29 data/jarvis.db
D31 checkpoints/*.json
D32 brain.db → planner.db
D33 data/pc_agent.db
D34 .jarvis/feedback.db
D35 .jarvis/benchmark.db
D36 .jarvis/orchestration.db
D44 CheckpointManager (JSON)
D45 ProjectPersistence (checkpoint)
D46 ConversationManager (in-memory)
I06 Legacy DB URL
      │
Phase 10 (Identity)
D40 Old AuthContext
D41 Old IdentityContext
D42 provider_sdk/permissions.py
D43 In-memory audit log
      │
Phase 11 (Cleanup — delete everything)
All above entries → Removal Verification Report → DELETE
```

---

## 13. Import Tracking (grep targets)

Run these before any deletion:

| Target | Grep Pattern | Expected Non-Exempt Results |
|--------|-------------|---------------------------|
| core.memory | `from core.memory import` or `import core.memory` | MCP memory server, brain similarity |
| core.memory_vector | `from core.memory_vector import` or `import core.memory_vector` | Unknown |
| brain.planner | `from brain.planner import` or `import brain.planner` | UnifiedBrain |
| brain.memory | `from brain.memory import` or `import brain.memory` | Brain subsystems |
| brain.goals | `from brain.goals import` or `import brain.goals` | Brain subsystems |
| core.plan_manager | `from core.plan_manager import` or `import core.plan_manager` | Legacy routes |
| core.database_models | `from core.database_models import` | Multiple legacy consumers |
| core.pipeline | `RuntimePipeline` or `pipeline.run()` | CLI, daemon, WebSocket, MCP |
| PluginEventBus | `PluginEventBus` or `from plugin_system.core` | Plugin system |
| NON_ADMIN_BLOCKED_TOOLS | `NON_ADMIN_BLOCKED_TOOLS` | security.py |
| AuthContext | `AuthContext` | identity/models.py users |
| IdentityContext | `IdentityContext` | Pipeline, services |

---

## 14. Removal Verification Report Index

Each deletion MUST have a completed Removal Verification Report (template: CODE_OWNERSHIP_AUDIT.md §15) before it is scheduled for deletion.

| # | Target | Report Link | Status | Reviewer | Date Completed |
|---|--------|-------------|--------|----------|----------------|
| — | — | — | — | — | — |

*Fill in as Removal Verification Reports are completed.*

---

## 15. Migration Backlog Integration

Items from `MIGRATION_BACKLOG.md` that require deletion:

| ID | File | Severity | Resolution |
|----|------|----------|------------|
| MEM-01 | `core/agents/_legacy/nexus.py` | Medium | Route memory writes through MemoryStage |
| MEM-02 | `core/context_builder.py` | Medium | Route memory writes through MemoryStage |
| MEM-03 | `core/routes/intelligence.py` | Medium | Route memory writes through MemoryStage |
| RSN-01 | `core/schemas.py` (ReasonResult) | Low | Replace with canonical `Decision` dataclass |
| VRF-01 | `core/plugins/verification.py` | Low | Implement as `Verifier` subclass |

---

## 16. Delete Readiness Checklist

Before deleting any item from this tracker:

- [ ] **Removal Verification Report** completed and linked in §14
- [ ] **No remaining imports** (grepped entire repo including docs, comments, config files)
- [ ] **No remaining runtime references** (startup registration, EventBus subscriptions, config keys, env vars, CLI args)
- [ ] **No remaining test references** (test imports, fixtures, mocks, setup code)
- [ ] **Data migration** verified (all data moved to replacement, integrity checked)
- [ ] **Replacement operational** (fully functional, no regressions)
- [ ] **Full test suite passes** without the deleted target
- [ ] **Application starts** cleanly without the deleted target
- [ ] **Rollback plan** documented (git revert or restore from backup)

---

## 17. Scheduled Delete Dates (Tentative)

| Phase | Target Dates | Items |
|-------|-------------|-------|
| Phase 2 | Week 2-3 | D05, D13-D16 (RuntimePipeline) |
| Phase 3 | Week 4-5 | D17 (NON_ADMIN_BLOCKED_TOOLS) |
| Phase 4 | Week 2-3 | D18-D21 (Event Bus duplicates) |
| Phase 5 | Week 2-3 | D38-D39 (Config cleanup) |
| Phase 6 | Week 5-7 | D03, D08, D10, I03, I05 (Planner) |
| Phase 7 | Week 4-7 | D01-D02, D09, D11, M01-M07, I01-I02, I04 (Memory) |
| Phase 8 | Week 3-4 | D06 (ControllerLoop — separate track) |
| Phase 9 | Week 8-11 | D04, D12, D22-D36, D44-D46, I06 (Storage) |
| Phase 10 | Week 10-12 | D40-D43 (Identity) |
| Phase 11 | Week 12-13 | All remaining (Cleanup & Removal) |

*End of DELETION_MIGRATION_TRACKER.md — 46 modules tracked for deletion, 10 removed interfaces, 7 memory stores, 15 databases/files, full dependency graph, import tracking patterns, delete readiness checklist.*
