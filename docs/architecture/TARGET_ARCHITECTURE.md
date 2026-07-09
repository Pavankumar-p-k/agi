# Target Architecture — Phase 4 (Document 9)

> **Purpose:** Define the target state for the entire system based on all 8 prior audits. This document specifies what changes to implement and the priority order. No code changes should begin until this architecture is finalized and cross-referenced with all audit documents.
>
> **Prerequisites:** Dependency Graph, State, Request Pipeline, Memory, Planner, Workflow, Identity/Permission, and Storage audits — all must be internally consistent before this document is final.

---

## Table of Contents

1. [Architecture Principles](#1-architecture-principles)
2. [Target: Request Pipeline](#2-target-request-pipeline)
3. [Target: Memory Architecture](#3-target-memory-architecture)
4. [Target: Planner Architecture](#4-target-planner-architecture)
5. [Target: Workflow Architecture](#5-target-workflow-architecture)
6. [Target: Identity & Permissions](#6-target-identity--permissions)
7. [Target: Storage Architecture](#7-target-storage-architecture)
8. [Target: State Architecture](#8-target-state-architecture)
9. [Target: Execution Architecture](#9-target-execution-architecture)
10. [Target: Capability Registry](#10-target-capability-registry)
11. [Implementation Phases](#11-implementation-phases)
12. [Architecture Decision Records](#12-architecture-decision-records)

---

## 1. Architecture Principles

### P-1: Single Source of Truth
Every piece of data must live in exactly one place with a single owner. No duplicate stores, no redundant systems, no parallel implementations.

### P-2: Pipeline as the Sole Request Path
All requests — from all entry points (HTTP, MCP, WebSocket, CLI, internal) — must go through the 19-stage canonical pipeline. The legacy RuntimePipeline is removed.

### P-3: Unified Memory, Single Facade
One `MemoryFacade` serves all consumers (user-facing, agent-facing, brain subsystems). All memory backends are pluggable behind this facade.

### P-4: Planner Under a Common Interface
One `Planner` protocol. All planners (core, brain, pipeline, specialized) implement the same interface. The `core/planner/` implementation is the reference.

### P-5: Bounded-Context Storage, Managed Migrations
27+ databases consolidate to well-defined databases by bounded context (system, memory, workflow, planner) with Alembic migration coverage for all schemas. Each bounded context owns its schema; cross-context reads go through service APIs, not direct query access.

### P-6: Layered Security, Unified AuthZ
One authorization query (`Authorizer.authorize()`) that evaluates PolicyEngine scopes, PermissionManager risk, and AuthManager privileges in a single call.

### P-7: Workflow Engine as the Single Execution Backend
All multi-step execution goes through `WorkflowEngine`. LongHorizonFSM is either integrated or retired.

---

## 2. Target: Request Pipeline

### Current State (from REQUEST_PIPELINE_AUDIT.md)
- 19-stage canonical pipeline (primary)
- Legacy 10-phase RuntimePipeline (deprecated but still functional)
- RateLimitStage is a no-op
- EpistemicTaggingStage is trivial
- CapabilityRegistry is bypassed by hardcoded dict

### Target Design

```
receive → load_context → authentication → tenant_resolution → authorization → resource_access → rate_limit → intent → context_retrieval → reasoner → planner → plan_validator → capability_selection → execution → verification → epistemic_tagging → memory → format
  1           2                3                   4                  5                6             7         8               9             10        11          12               13               14           15             16             17       18       19
```

| Stage | Change | Rationale |
|-------|--------|----------|
| 7. RateLimitStage | **Implement** actual rate limiting from `AuthRateLimiter` | No-op stage provides no protection for non-HTTP entry points |
| 13. CapabilitySelectionStage | **Use registry** lookup instead of hardcoded dict | Bypass makes the capability registry meaningless |
| 16. EpistemicTaggingStage | **Implement** meaningful tagging or remove | Trivial implementation adds no value |
| All | **Remove** RuntimePipeline code paths | Eliminates maintenance burden of 2 parallel systems |

### RuntimePipeline Removal

| What | Action | Files Affected |
|------|--------|---------------|
| `RuntimePipeline` class | Remove | `core/pipeline.py`, `core/control_loop.py` |
| 10-phase state enum | Remove | `core/runtime_pipeline.py` (if exists) |
| LangGraph-based pipeline config | Remove | Graph definitions referencing legacy |
| `pipeline.run()` vs `pipeline.execute()` | Standardize on `execute()` | All callers |

---

## 3. Target: Memory Architecture

### Current State (from MEMORY_ARCHITECTURE_AUDIT.md)
- **System A**: `memory/` — MemoryFacade, TieredMemory, Mem0Adapter, FactStore, EmbeddingMemory (user-facing)
- **System B**: `brain/memory/` — MemoryManager, EpisodicMemory, SemanticMemory, TaskMemory, DecisionMemory (agent-facing)
- **System C**: `core/memory.py` — deprecated JSON-based MemoryManager
- **System D**: `core/memory_vector.py` — ChromaDB vector store
- 2 fact stores (FactStore + SemanticMemory), 2 decision memories, 3 vector stores
- 18+ persistent stores for memory data

### Target Design

```
                              ┌─────────────────────┐
                              │    MemoryFacade      │  (unified, sole consumer API)
                              │  store / recall /    │
                              │  search / delete     │
                              └──────────┬──────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
              ▼                          ▼                          ▼
    ┌──────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
    │  EpisodicStore    │    │   FactStore (merged) │    │  DecisionStore   │
    │  (episodes/tasks) │    │   RDF triples +      │    │  (agent routing  │
    │  SQLite-backed    │    │   embeddings)         │    │   + reflection)  │
    └──────────────────┘    │   SQLite + ChromaDB    │    │  SQLite-backed   │
                            └──────────────────────┘    └──────────────────┘
                                         │
                                         ▼
                              ┌──────────────────────┐
                              │   PreferenceProfile   │  (view over FactStore)
                              └──────────────────────┘
```

### Merges Required

| Merge | Absorb Into | Rationale |
|-------|------------|-----------|
| `brain/memory/` → `MemoryFacade` | `memory/memory_facade.py` | System B consumers migrate to unified facade |
| `brain/memory/semantic.py` → `FactStore` | `memory/fact_store.py` | Union of schemas (RDF + categories + decay) |
| `brain/memory/decision.py` → `DecisionStore` | New unified store | Merge agent routing + self-reflection |
| `brain/memory/episodic.py` → `EpisodicStore` | New store under facade | Task episodes as a first-class memory type |
| `brain/memory/task.py` → `EpisodicStore` | New store under facade | Execution traces become episodic sub-type |
| `core/memory.py` | **Remove** after migration | Deprecated since v3.2, all callers migrated |
| `memory/mem0_adapter.py` | **Retain** as vector backend | ChromaDB vector store for semantic search |
| `memory/embedding_memory.py` | **Retain** as cold tier | Ollama embedding + SQLite for high-importance items |
| `core/memory_vector.py` | **Remove** or integrate | Duplicate ChromaDB, fold into mem0 adapter |
| TieredMemory hot tier | **Retain** | RAM hot cache (max 10) remains as-is |

### Migration Steps (in order)

1. Move `brain/memory/` functionality into `memory/` package
2. Create unified `EpisodicStore` and `DecisionStore`
3. Migrate all System B consumers to use `MemoryFacade`
4. Add `get_text_similarity()` to `memory/` utils (remove System B's dependency on deprecated `core/memory.py`)
5. Remove `core/memory.py`
6. Merge `core/memory_vector.py` into mem0 adapter
7. Remove duplicate ChromaDB collection

---

## 4. Target: Planner Architecture

### Current State (from PLANNER_ARCHITECTURE_AUDIT.md)
- **Core Planner** (`core/planner/`): 15 files, template-based + keyword decomposition, evidence-scored state machine
- **Brain Planner** (`brain/planner/`): 3 files, fixed 3-node DAG
- **Pipeline Planner** (`core/pipeline/stages/planner.py`): flat step list in context dict
- **Specialized Planners**: 9+ independent planners (Research, Browser, Change, Migration, Horizon, etc.)
- **Goal Management**: 4 systems (GoalManager, PlanStore, PlanManager, ExecutionTracker)
- 3 incompatible status enums, 3 goal storage systems

### Target Design

```
                           ┌─────────────────┐
                           │  Planner Protocol│  (ABC with create_plan, replan)
                           └────────┬────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
    ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
    │   CorePlanner    │   │PipelinePlanner  │   │  Specialized    │
    │  (reference impl)│   │(wrapper that    │   │  Planners       │
    │  template-based  │   │ creates Core-   │   │  (Research,     │
    │  + evidence +    │   │ compatible plan)│   │  Browser, etc)  │
    │  state machine   │   └─────────────────┘   └─────────────────┘
    └─────────────────┘
            │
            ▼
    ┌─────────────────┐
    │   UnifiedStore   │  (PlanStore + GoalManager merged)
    │   SQLite-backed  │
    │   Single schema  │
    └─────────────────┘
```

### Merges Required

| Merge | Absorb Into | Rationale |
|-------|------------|-----------|
| `brain/planner/` | **Remove** — replace with unified CorePlanner | Fixed 3-node DAG is not useful; brain consumers use CorePlanner |
| Pipeline PlannerStage | **Retain** as thin wrapper | Produces SubGoal-compatible output, persists via UnifiedStore |
| `PlanStore` + `GoalManager` | **Merge** into UnifiedStore | Single goal/plan schema, single status enum |
| `PlanManager` (legacy) | **Remove** | JSON file storage is replaced by UnifiedStore |
| `PlanOutcomeStore` | **Retain** under UnifiedStore | Prediction vs actual tracking is valuable |

### UnifiedStore Schema (merged GoalManager + PlanStore)

```sql
-- Unified goals/plans table
goals_plans (
    id TEXT PK,
    objective TEXT NOT NULL,         -- original goal string
    status TEXT NOT NULL,            -- single unified enum
    plan_tree JSON,                  -- SubGoal tree (from PlanStore.root_node)
    progress REAL DEFAULT 0.0,       -- from GoalManager
    priority INTEGER DEFAULT 0,
    parent_goal_id TEXT,
    blockers JSON,
    next_action TEXT,
    tags JSON,
    result TEXT,
    deadline TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)

-- Prediction vs actual (from PlanOutcomeStore)
plan_outcomes (
    plan_id TEXT PK REFERENCES goals_plans(id),
    predicted_confidence REAL,
    predicted_duration_days REAL,
    predicted_risk_score REAL,
    actual_success INTEGER,
    actual_duration_seconds REAL,
    actual_failures INTEGER,
    executed_at TEXT,
    completed_at TEXT
)
```

### Unified Status Enum

```
PENDING → APPROVED → ACTIVE → COMPLETED
                    → REJECTED
              ACTIVE → FAILED → COMPENSATING → COMPENSATED
                      → CANCELLED
                      → PAUSED → ACTIVE
```

---

## 5. Target: Workflow Architecture

### Current State (from WORKFLOW_ARCHITECTURE_AUDIT.md)
- Well-designed single orchestrator (`WorkflowEngine`)
- Full persistence (5 tables in `workflow.db`)
- Heartbeat-based recovery
- Compensation logic
- Learning system (history + calibration + prediction)
- `LongHorizonFSM` exists as unintegrated alternative
- `ExecutionTracker` is in-memory with no recovery

### Target Design

```
   StepDefinition (from Planner)
        │
        ▼
  ┌─────────────────────────────────────────────┐
  │              WorkflowEngine                  │  (keep as-is, no major changes)
  │                                              │
  │  _run_workflow()                             │
  │  _execute_step()  [add idempotency check]   │
  │  _compensate_workflow()                      │
  │  _record_workflow_outcome()  [add feedback]  │
  └──────────────────────┬──────────────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
      WorkflowStore            ExecutionGraph
      (keep as-is)             (persist to SQLite
                                for crash recovery)
```

### Changes Required

| Change | Rationale | Priority |
|--------|-----------|----------|
| **Enforce idempotency keys** | Step-level dedup for safe retry-after-crash | Low |
| **Add workflow-level timeout** | Global deadline enforcement | Low |
| **Persist ExecutionGraph** | Tracker recovery after restart | Low |
| **Integrate LongHorizonFSM** | Convert to StepDefinition-based workflow | Low |
| **Add compensation registry** | Auto-compensation for common tool patterns | Low |

**Design decision**: The workflow system is the best-designed subsystem in the codebase. It requires minimal changes and should serve as the architectural model for other subsystems.

---

## 6. Target: Identity & Permissions

### Current State (from IDENTITY_PERMISSION_AUDIT.md)
- IdentityService (well-designed, pipeline-integrated)
- AuthManager (JSON file storage, bcrypt, sessions, TOTP)
- PolicyEngine (YAML-based RBAC scopes)
- PermissionManager (risk-based capability gating)
- 3 authorization systems, 3 user stores
- Pipeline RateLimitStage is no-op

### Target Design

```
        ┌──────────────────────────────────────────────────────┐
        │                   Authorizer                         │
        │  authorize(action, identity, resource) → AuthResult  │
        │  Unified entry point for ALL authorization checks    │
        └──────────────────────┬───────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ PolicyEngine │  │PermissionMgr │  │AuthManager   │
    │ (RBAC scopes)│  │(risk gates)  │  │(privileges)  │
    └──────────────┘  └──────────────┘  └──────────────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │   AuthDB     │
                                        │ (SQLite)     │
                                        │ users + sess │
                                        └──────────────┘
```

### Changes Required

| Change | Rationale | Priority |
|--------|-----------|----------|
| **AuthManager → SQLite** | Replace `auth.json`/`sessions.json` with SQLite | Medium |
| **Unified user model** | Single User model for AuthManager + Firebase + IdentityService | Medium |
| **Pipeline RateLimitStage** | Implement rate limiting at pipeline level | Medium |
| **Authorizer facade** | Single `authorize()` method across all 3 AuthZ systems | Low |
| **Encrypt OAuth tokens** | At-rest encryption for refresh tokens | Low |
| **Remove tool blocklist** | Replace `NON_ADMIN_BLOCKED_TOOLS` with scope-based RBAC | Low |

---

## 7. Target: Storage Architecture

### Current State (from STORAGE_ARCHITECTURE_AUDIT.md)
- 27+ SQLite databases, 60+ tables
- 2 ORM systems sharing `data/jarvis.db` with partial Alembic coverage
- 6+ JSON file stores
- 3 vector stores (2 ChromaDB + 1 Qdrant)
- No backup, no migration management for 90% of databases

### Target Design: 5 Databases

```
data/                          ~/.jarvis/
├── app.db              ─────  user.db
│   (ORM-managed)              (user-scoped stores)
│   • All 24 tables from       • agent_state
│     jarvis.db (async+sync)   • agent_checkpoints
│   • Alembic-managed          • cron
│   • Single ORM system        • commitments
│                               • principles
└── system.db                  • feedback
    (raw SQLite)               • oauth_tokens (encrypted)
    • workflow (5 tables)      • permission_audit
    • brain (7 tables)         • workflow_learning
    • memory (2 tables)
    • planner (2 tables)
    • scheduler, activity,
      knowledge, etc.
```

### Consolidation Plan

| Current Databases | Target Database | Migration Strategy |
|-------------------|----------------|-------------------|
| `data/jarvis.db` (async + sync) | `data/app.db` | Single ORM, Alembic for all 24 tables |
| `data/workflow.db` (all subsystems) | `data/system.db` | Merge via table namespace prefixes |
| `data/brain.db` | `data/system.db` | Copy tables, update paths |
| `data/jarvis_memory.db` | `data/system.db` | Copy tables, update paths |
| `data/goals.db` | `data/system.db` | Merge into UnifiedStore |
| `data/*.db` (specialized) | `data/system.db` | Add as new tables with owner prefix |
| `~/.jarvis/*.db` | `~/.jarvis/user.db` | Merge into single user DB |
| `ai_os_memory.db` | `data/system.db` or remove | Determine ownership |
| `database.db` | **Remove** | Determine origin first |
| JSON auth files | SQLite in system.db | AuthManager migration |
| ChromaDB + Qdrant | **Single ChromaDB** | Merge vector stores |

### Migration Strategy Approach

1. Create new tables in target databases alongside existing ones
2. Dual-write during migration period
3. Backfill data from old databases
4. Switch reads to new databases
5. Remove old databases

---

## 8. Target: State Architecture

### Current State (from STATE_ARCHITECTURE_AUDIT.md)
- 14 state domains, 8+ SQLite databases
- 3 concurrent memory systems, 2 checkpoint systems
- Inconsistent thread safety

### Target: State Ownership Matrix

| State Domain | Owner | Persistence | Thread Safety |
|-------------|-------|-------------|---------------|
| **Conversation** | `ConversationManager` | JSON files —> **Migrate to app.db (ChatHistory)** | Add lock |
| **Pipeline** | `PipelineContext` | None (per-request) | Async-only (no change) |
| **Planner** | `UnifiedStore` (merged) | `data/planner.db` | Already thread-safe |
| **Workflow** | `WorkflowEngine` | `data/workflow.db` | Already thread-safe |
| **Agent** | `AgentGraph` | `~/.jarvis/user.db` | Add lock |
| **Browser** | `BrowserManager` | JSON files —> **Migrate to user.db** | Add lock |
| **Desktop** | `DesktopController` | In-memory | Add lock |
| **Memory** | `MemoryFacade` (unified) | `data/memory.db` + ChromaDB | Add locks to hot path |
| **Activity** | `ActivityManager` | `data/system.db` | Already thread-safe |
| **Goal** | `UnifiedStore` | `data/planner.db` | Already thread-safe |
| **Identity** | `IdentityContext` | None (per-request, frozen) | Frozen (no change) |
| **Permission** | `AuthManager/PolicyEngine` | Auth → SQLite, Policy → YAML | Add lock to AuthManager |
| **Execution** | `executor` | In-memory | Add lock |
| **Checkpoint** | `CheckpointStore` (unified) | `~/.jarvis/user.db` | Already thread-safe |

---

## 9. Target: Execution Architecture

### Current State (from EXECUTION_ARCHITECTURE_AUDIT.md)
- `core/tools/execution.py` (3,024 lines) — central dispatcher
- Two execution systems (pipeline execution + agent graph)
- `tool_factory.py` is thread-hostile (global `_initialized`+`_tools` state)
- RateLimitStage no-op (not enforced in execution path)
- DecisionMemory used for agent routing in `control_loop.py`

### Target Design

```
Pipeline.execute()
    │
    ├── Pre-execution stages (1-13)
    │
    ├── Stage 14: ExecutionStage
    │       │
    │       ├── is_authorized_to_execute()  (tool-level RBAC)
    │       ├── PermissionManager.resolve()  (risk gate)
    │       ├── execute_tool_block()         (tool dispatch)
    │       │       │
    │       │       ├── tool_factory.create()  (thread-safe)
    │       │       ├── tool.run()             (actual execution)
    │       │       └── tool_factory.cleanup() (context exit)
    │       │
    │       └── DecisionMemory.record()   (learn from outcome)
    │
    └── Post-execution stages (15-19)
```

### Changes Required

| Change | Rationale | Priority |
|--------|-----------|----------|
| **Make tool_factory thread-safe** | Fix `_initialized`/`_tools` race | **Critical** |
| **Remove RuntimePipeline code paths** | Single execution path | **High** |
| **Integrate MemoryDrivenRouter into MemoryFacade** | Single decision entry point | Medium |
| **Remove hardcoded capability dict** | Use CapabilityRegistry from stage 13 | Medium |

---

## 10. Target: Capability Registry

### Current State (from REQUEST_PIPELINE_AUDIT.md)
- `CapabilityRegistry` class exists but is bypassed by hardcoded dict in `CapabilitySelectionStage`
- Capabilities are defined separately from tools, agents, and permissions

### Target Design

```
Stage 13: CapabilitySelectionStage
    │
    ├── Reads plan steps from context.plan
    ├── Maps each step to capability via CapabilityRegistry
    │       │
    │       ▼
    │   CapabilityRegistry
    │   ├── capability_id -> tool_name (execution)
    │   ├── capability_id -> required_scopes (RBAC)
    │   ├── capability_id -> required_permissions (risk)
    │   └── capability_id -> agent_type (routing)
    │
    └── Output: assigned capabilities → execution context
```

The CapabilityRegistry becomes **the central authority** for mapping intents → actions → permissions → agents, replacing:
- Hardcoded dict in CapabilitySelectionStage (pipeline)
- NON_ADMIN_BLOCKED_TOOLS list (tool security)
- Hardcoded agent routing in control_loop.py

---

## 11. Implementation Phases

### Phase 1: Foundation (Critical — blocking all other work)

| # | Task | Depends On | Effort |
|---|------|-----------|--------|
| 1.1 | Fix `tool_factory.py` thread safety | None | 1-2 days |
| 1.2 | Implement `RateLimitStage` in pipeline | None | 1 day |
| 1.3 | Add thread safety to `TieredMemory` hot path | None | 1 day |

### Phase 2: Pipeline & Request Path Unification (High — unblocks all downstream work)

| # | Task | Depends On | Effort |
|---|------|-----------|--------|
| 2.1 | Audit all RuntimePipeline callers | 1.* | 1 day |
| 2.2 | Migrate callers to canonical pipeline | 2.1 | 3-5 days |
| 2.3 | Remove RuntimePipeline code | 2.2 | 1 day |
| 2.4 | Use CapabilityRegistry in CapabilitySelectionStage (replace hardcoded dict) | 2.3 | 1 day |
| 2.5 | Add EpistemicTaggingStage or remove | None | 1 day |

### Phase 3: Planner Unification (High)

| # | Task | Depends On | Effort |
|---|------|-----------|--------|
| 3.1 | Define `Planner` protocol/ABC | 2.* | 1 day |
| 3.2 | Replace brain planner with CorePlanner | 3.1 | 2 days |
| 3.3 | Merge GoalManager + PlanStore into UnifiedStore | None | 3-5 days |
| 3.4 | Remove legacy PlanManager | 3.3 | 1 day |
| 3.5 | Add LLM-based decomposition as fallback | 3.1 | 2-3 days |
| 3.6 | Wire PlanHealthEngine into automatic replanning | 3.3 | 2 days |

### Phase 4: Memory Unification (High)

| # | Task | Depends On | Effort |
|---|------|-----------|--------|
| 4.1 | Move `brain/memory/` stores into `memory/` package | 2.* | 3-5 days |
| 4.2 | Add `EpisodicStore` and `DecisionStore` to MemoryFacade | 4.1 | 2-3 days |
| 4.3 | Migrate System B consumers to MemoryFacade | 4.2 | 2-3 days |
| 4.4 | Add `get_text_similarity()` to `memory/` utils | None | 1 day |
| 4.5 | Remove `core/memory.py` | 4.3, 4.4 | 1 day |
| 4.6 | Merge vector stores (2 ChromaDB → 1) | None | 2-3 days |
| 4.7 | Standardize embedding serialization (struct.pack vs np.tobytes) | None | 1 day |

### Phase 5: Storage Consolidation by Bounded Context (Medium)

| # | Task | Depends On | Effort |
|---|------|-----------|--------|
| 5.1 | Migrate AuthManager to SQLite | None | 2-3 days |
| 5.2 | Complete Alembic migration for all ORM tables | None | 2-3 days |
| 5.3 | Define bounded-context DBs: `data/system.db`, `data/memory.db`, `data/workflow.db`, `data/planner.db` | None | 2 days |
| 5.4 | Migrate `brain.db` tables into appropriate bounded-context DBs | 5.3 | 3-5 days |
| 5.5 | Migrate `~/.jarvis/*.db` → `~/.jarvis/user.db` | None | 2-3 days |
| 5.6 | Separate sync ORM models into `data/workflow.db` (bounded context) | 5.2 | 1 day |

### Phase 6: Identity & Permission Improvements (Medium)

| # | Task | Depends On | Effort |
|---|------|-----------|--------|
| 6.1 | Create unified user model | 5.1 | 2 days |
| 6.2 | Implement `Authorizer` facade | None | 2 days |
| 6.3 | Replace `NON_ADMIN_BLOCKED_TOOLS` with scope-based RBAC | 6.2 | 2 days |
| 6.4 | Encrypt OAuth token storage | None | 1 day |

### Phase 7: Workflow Enhancements (Low)

| # | Task | Depends On | Effort |
|---|------|-----------|--------|
| 7.1 | Enforce idempotency keys | 2.* | 1 day |
| 7.2 | Add workflow-level timeout | None | 1 day |
| 7.3 | Persist ExecutionGraph | None | 2 days |
| 7.4 | Integrate LongHorizonFSM | None | 3-5 days |

### Phase 8: Cleanup & Removal (Low — requires Removal Verification Report per deletion)

| # | Task | Depends On | Effort |
|---|------|-----------|--------|
| 8.1 | Remove `database.db` from project root | 5.* | 1 day |
| 8.2 | Standardize database path conventions | 5.* | 1 day |
| 8.3 | Remove `sessions.json` (migrated to SQLite) | 6.* | 1 day |
| 8.4 | Remove `auth.json` (migrated to SQLite) | 6.* | 1 day |
| 8.5 | Remove `core/memory.py` | 4.* | 1 day |
| 8.6 | Remove `brain/planner/` | 3.* | 1 day |
| 8.7 | Remove `brain/memory/` | 4.* | 1 day |
| 8.8 | Remove `brain/goals/` | 3.* | 1 day |
| 8.9 | Create DatabaseRegistry with health endpoints | 5.* | 2 days |
| 8.10 | Removal Verification Report gate | **Required before any deletion** | 1 day per deletion |

---

## 12. Architecture Decision Records

### ADR-001: MemoryFacade Is the Single Memory API
**Status**: Accepted
**Context**: Three concurrent memory systems create data fragmentation
**Decision**: All memory operations go through `MemoryFacade`. `brain/memory/` stores become backends behind the facade.

### ADR-002: CorePlanner Is the Single Planner Implementation
**Status**: Accepted
**Context**: Three planner systems with incompatible output formats
**Decision**: `core/planner/` is the reference implementation. Brain planner and pipeline planner adopt its protocol and output format.

### ADR-003: WorkflowEngine Is the Single Execution Backend
**Status**: Accepted
**Context**: Workflow execution is duplicated across engine, FSM, and inline code
**Decision**: All multi-step execution uses `WorkflowEngine`. LongHorizonFSM is integrated or retired.

### ADR-004: Bounded-Context Databases, Managed Migrations
**Status**: Proposed
**Context**: 27+ databases with no centralized management. Monolithic consolidation risked creating a single-point-of-failure and coupling unrelated domains.
**Decision**: Consolidate to databases by bounded context (`data/system.db`, `data/memory.db`, `data/workflow.db`, `data/planner.db`, `~/.jarvis/user.db`) with full Alembic coverage. Each bounded context owns its schema; cross-context reads go through service APIs.

### ADR-005: UnifiedStore Replaces PlanStore + GoalManager
**Status**: Proposed
**Context**: Goal/plan data split across 4 systems with incompatible schemas
**Decision**: Single `goals_plans` table with unified status enum.

### ADR-006: Authorizer Facade for Unified AuthZ
**Status**: Proposed
**Context**: Three authorization systems with different granularity levels
**Decision**: `Authorizer.authorize()` delegates to PolicyEngine (RBAC), PermissionManager (risk), and AuthManager (privileges).

### ADR-007: Pipeline Is the Only Request Path
**Status**: Accepted (from prior audits)
**Context**: Legacy RuntimePipeline still functional alongside canonical pipeline
**Decision**: The 19-stage canonical pipeline is the single entry point for all requests. RuntimePipeline is removed.

### ADR-008: CapabilityRegistry Is the Central Authority
**Status**: Proposed
**Context**: Capabilities defined separately from tools, agents, and permissions
**Decision**: CapabilityRegistry maps intent → tool → scope → permission → agent, replacing hardcoded dicts and blocklists.
