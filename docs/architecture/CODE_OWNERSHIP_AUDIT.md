# Code Ownership Audit — Phase 4 (Document 10)

> **Purpose:** Define ownership boundaries, change policies, and interface contracts for every major module in the system. This is the final architectural contract that prevents future drift — all code changes must respect the boundaries defined here.
>
> **Scope:** All modules identified in the 9 prior audits, organized by architectural layer.

---

## Table of Contents

1. [Ownership Principles](#1-ownership-principles)
2. [Layer 1: Entry Points & Transport](#2-layer-1-entry-points--transport)
3. [Layer 2: Pipeline & Request Processing](#3-layer-2-pipeline--request-processing)
4. [Layer 3: Core Systems](#4-layer-3-core-systems)
5. [Layer 4: Planner & Workflow](#5-layer-4-planner--workflow)
6. [Layer 5: Memory & Knowledge](#6-layer-5-memory--knowledge)
7. [Layer 6: Identity & Permissions](#7-layer-6-identity--permissions)
8. [Layer 7: Storage & Persistence](#8-layer-7-storage--persistence)
9. [Layer 8: Brain & Autonomous Systems](#9-layer-8-brain--autonomous-systems)
10. [Layer 9: Tools & Execution](#10-layer-9-tools--execution)
11. [Layer 10: Integrations & External Services](#11-layer-10-integrations--external-services)
12. [Change Policies](#12-change-policies)
13. [Interface Contracts Registry](#13-interface-contracts-registry)
14. [Deprecated Modules Registry](#14-deprecated-modules-registry)
15. [Enforcement](#15-enforcement)

---

## 1. Ownership Principles

### OP-1: One Owner Per Module
Every file has exactly one owning team/individual. Shared modules have a designated primary owner.

### OP-2: Interface Over Implementation
Owners control their module's public interface (function signatures, data models, API contracts). Internal implementation details can be changed without cross-team coordination.

### OP-3: Deprecation Before Removal
Before removing any public interface, the owner must:
1. Mark it deprecated (with deprecation notice)
2. Wait one release cycle
3. Remove after all known consumers have migrated

### OP-4: Downward Dependencies Only
High-level layers may depend on low-level layers. Low-level layers must never depend on high-level layers. Violations are architectural debt.

### OP-5: Tests Follow Ownership
Every module owner is responsible for their module's tests. Cross-module integration tests are owned by the consuming layer.

---

## 2. Layer 1: Entry Points & Transport

### Ownership Table

| Module | Owner | Access Level | Dependencies | Change Policy |
|--------|-------|-------------|--------------|---------------|
| `core/main.py` (FastAPI app) | **Core Platform** | Public | All layers | Requires review |
| `core/websocket_manager.py` | **Core Platform** | Public | Pipeline | Requires review |
| `mcp/` (servers) | **MCP** | Public | Pipeline, Memory | Requires review |
| `daemon/` (background service) | **Core Platform** | Internal | Pipeline | Requires review |
| `api/` (route handlers) | **Core Platform** | Public | Pipeline, Identity | Requires review |

### Interface Contracts

| Contract | Provider | Consumers | Stability |
|----------|----------|-----------|-----------|
| `TransportAdapter` (abstract) | `core/entry/` | main.py, websocket, MCP | Stable |
| `Request` dataclass | `core/models/` | Pipeline | Stable |
| `WebSocketEvent` protocol | `core/websocket_manager.py` | MCP, API | Stable |

### Layer 1 Boundary Rules

```
Entry Point (HTTP, WS, MCP, CLI, Daemon)
    │
    │ MUST convert to Request dataclass
    ▼
Pipeline.execute(Request)
    │
    │ MUST NOT bypass pipeline (except health checks)
    ▼
Response ← FormatStage
```

**Violation detection**: Any file that imports from `core/` below the pipeline layer (e.g., `core/tools/`, `core/planner/`, `core/memory/`) without going through the pipeline is a violation.

---

## 3. Layer 2: Pipeline & Request Processing

### Ownership Table

| Module | Owner | Files | Dependencies | Change Policy |
|--------|-------|-------|--------------|---------------|
| `core/pipeline/` (executor, context) | **Core Platform** | `pipeline.py`, `context.py`, `store_decision.py` | Identity, RateLimit | Requires review |
| `core/pipeline/stages/` (19 stages) | **Core Platform** | 19 stage files | Layer 3-5 | Per-stage review |
| `core/entry/` (adapters) | **Core Platform** | `manager.py` | Pipeline | Requires review |

### Stage Ownership

| Stage | File | Owner | Change Policy |
|-------|------|-------|---------------|
| 1. Receive | `receive.py` | **Core Platform** | Requires review |
| 2. Load Context | `load_context.py` | **Core Platform** | Requires review |
| 3. Authentication | `auth.py` | **Security** | Requires security review |
| 4. Tenant Resolution | `tenant_resolution.py` | **Core Platform** | Requires review |
| 5. Authorization | `authorization.py` | **Security** | Requires security review |
| 6. Resource Access | `resource_access.py` | **Security** | Requires security review |
| 7. Rate Limit | `rate_limit.py` | **Core Platform** | Requires review |
| 8. Intent | `intent.py` | **Core Platform** | Requires review |
| 9. Context Retrieval | `context_retrieval.py` | **Memory** | Requires review |
| 10. Reasoner | `reasoner.py` | **Core Platform** | Requires review |
| 11. Planner | `planner.py` | **Planner** | Requires review |
| 12. Plan Validator | `plan_validator.py` | **Planner** | Requires review |
| 13. Capability Selection | `capability_selection.py` | **Core Platform** | Requires review |
| 14. Execution | `execution.py` | **Execution** | Requires review |
| 15. Verification | `verification.py` | **Core Platform** | Requires review |
| 16. Epistemic Tagging | `epistemic_tagging.py` | **Core Platform** | Requires review |
| 17. Memory | `memory.py` | **Memory** | Requires review |
| 18. Format | `formatting.py` | **Core Platform** | Requires review |

### Interface Contracts

| Contract | Provider | Consumers | Stability |
|----------|----------|-----------|-----------|
| `PipelineContext` dataclass | `core/pipeline/context.py` | All stages | Stable |
| `PipelineStage` protocol | `core/pipeline/stages/__init__.py` | Pipeline executor | Stable |
| `StoreDecision` dataclass | `core/pipeline/store_decision.py` | MemoryStage, consumers | Beta |

### Stage Execution Rules

```
Stage N
    │
    ├── Reads context (read-only for prior stages)
    ├── Writes context (write-only for own fields)
    │
    │   MUST NOT modify another stage's fields
    │   MUST NOT depend on stage ordering
    ▼
Stage N+1
```

---

## 4. Layer 3: Core Systems

### Ownership Table

| Module | Owner | Files | Dependencies | Change Policy |
|--------|-------|-------|--------------|---------------|
| `core/event_bus.py` | **Core Platform** | 1 | None | Requires review |
| `core/config*.py` | **Core Platform** | ~5 | None | Requires review |
| `core/settings/` | **Core Platform** | 2 | None | Requires review |
| `core/session*.py` | **Core Platform** | 2 | None | Requires review |
| `core/scheduler/` | **Core Platform** | ~8 | WorkflowStore, ActivityStore | Requires review |
| `core/errors.py` | **Core Platform** | 1 | None | Requires review |
| `core/result.py` | **Core Platform** | 1 | None | Stable (widely used) |
| `core/chroma_client.py` | **Memory** | 1 | Vector stores | Requires review |
| `core/embeddings.py` | **Memory** | 1 | Ollama | Requires review |

### Interface Contracts

| Contract | Provider | Consumers | Stability |
|----------|----------|-----------|-----------|
| `Result[T]` (Ok/Err monad) | `core/result.py` | All layers | Stable |
| `AppError` hierarchy | `core/errors.py` | All layers | Stable |
| `EventBus` (singleton) | `core/event_bus.py` | All layers | Stable |
| `ConfigRegistry` (singleton) | `core/config_registry.py` | All layers | Stable |

---

## 5. Layer 4: Planner & Workflow

### Ownership Table

| Module | Owner | Files | Dependencies | Change Policy |
|--------|-------|-------|--------------|---------------|
| `core/planner/` (Core Planner) | **Planner** | 15 | WorkflowStore, KnowledgeStore, FactStore | Requires review |
| `core/workflow/` (Workflow Engine) | **Workflow** | 15 | Store (self) | Requires review |
| `brain/planner/` (Brain Planner) | **Planner** (deprecating) | 3 | None | Deprecated — no new changes |
| `brain/goals/` (Goal Manager) | **Planner** (deprecating) | 3 | brain.db | Deprecated — migrating to UnifiedStore |

### Interface Contracts (Target Architecture)

| Contract | Provider | Consumers | Stability |
|----------|----------|-----------|-----------|
| `Planner` (protocol) | `core/planner/` (target) | Pipeline, Brain | Proposed |
| `StepDefinition` | `core/workflow/models.py` | Planner, WorkflowEngine | Stable |
| `WorkflowInstance` | `core/workflow/models.py` | API, tools | Stable |
| `UnifiedStore` | TBD | Planner, Workflow, Goals | Proposed |

### Planner Layer Rules

```
Goal String
    │
    ▼
Planner.create_plan() → SubGoal Tree
    │
    │ MUST NOT execute tools directly
    │ MUST NOT access storage outside PlanStore/UnifiedStore
    ▼
WorkflowEngine.start_workflow(StepDefinition list)
```

---

## 6. Layer 5: Memory & Knowledge

### Ownership Table

| Module | Owner | Files | Dependencies | Change Policy |
|--------|-------|-------|--------------|---------------|
| `memory/` (MemoryFacade, Tiered, Mem0, FactStore, Embedding) | **Memory** | 10 | ChromaDB, SQLite, Ollama | Requires review |
| `brain/memory/` (Brain memory — deprecating) | **Memory** | 6 | brain.db | Deprecated — migrating to memory/ |
| `core/long_term_memory/` (KnowledgeStore) | **Memory** | 6 | workflow.db | Requires review |
| `core/pattern_failure_memory.py` | **Execution** | 1 | JSON file | Requires review |
| `core/providers/memory.py` | **Providers** | 1 | JSON file | Requires review |
| `core/memory*.py` (deprecated) | **Memory** | 3 | None | Deprecated — removal planned |

### Interface Contracts (Target Architecture)

| Contract | Provider | Consumers | Stability |
|----------|----------|-----------|-----------|
| `MemoryFacade` (singleton) | `memory/memory_facade.py` | Pipeline, API, Brain | Beta — expanding |
| `FactStore` (singleton) | `memory/fact_store.py` | Pipeline, PreferenceProfile | Stable |
| `PreferenceProfile` | `memory/preference_profile.py` | ContextRetrievalStage | Stable |
| `KnowledgeStore` | `core/long_term_memory/store.py` | Planner, Strategy | Beta |

### Memory Layer Rules

```
All Writes
    │
    ▼
MemoryFacade.store()
    │
    ├── Facts → FactStore
    ├── Episodes → EpisodicStore (target)
    ├── Decisions → DecisionStore (target)
    └── Conversations → Tiered/Mem0

All Reads
    │
    ▼
MemoryFacade.recall()
    │
    └── Queries all backends → deduplicate → rerank
```

---

## 7. Layer 6: Identity & Permissions

### Ownership Table

| Module | Owner | Files | Dependencies | Change Policy |
|--------|-------|-------|--------------|---------------|
| `core/identity/` (IdentityService, models) | **Security** | 7 | AuthManager | Requires security review |
| `core/auth.py` (AuthManager) | **Security** | 1 | JSON files | Requires security review |
| `core/authz/` (PolicyEngine) | **Security** | 3 | YAML config | Requires security review |
| `core/permission/` (PermissionManager) | **Security** | 6 | In-memory | Requires security review |
| `core/oauth.py` | **Security** | 1 | authlib | Requires security review |
| `core/tools/security.py` | **Execution** | 1 | authz_engine | Requires security review |
| `core/middleware.py` (security headers) | **Security** | 1 | None | Requires security review |

### Interface Contracts

| Contract | Provider | Consumers | Stability |
|----------|----------|-----------|-----------|
| `IdentityContext` (frozen) | `core/identity/models.py` | Pipeline | Stable |
| `IdentityService` (singleton) | `core/identity/service.py` | Pipeline | Stable |
| `AuthenticationState` | `core/identity/models.py` | Pipeline | Stable |
| `AuthContext` | `core/authz/schema.py` | Pipeline, tool RBAC | Stable |
| `AuthorizationResult` | `core/identity/service.py` | Pipeline | Stable |

### Security Layer Rules

```
Request
    │
    │ Pipeline Stages 3-6 MUST run before any business logic
    │ IdentityContext MUST be created by IdentityService only
    │ AuthManager MUST use SQLite (target) not JSON files
    ▼
Tool Execution
    │
    │ is_authorized_to_execute() MUST be called before every tool
    │ PermissionManager.resolve() MUST be called for capability execution
    ▼
Response
```

---

## 8. Layer 7: Storage & Persistence

### Ownership Table

| Module | Owner | Files | Dependencies | Change Policy |
|--------|-------|-------|--------------|---------------|
| `core/database.py` (async ORM) | **Core Platform** | 1 | SQLAlchemy, Alembic | Requires review |
| `core/database_models.py` (sync ORM) | **Core Platform** (deprecating) | 1 | SQLAlchemy | No new tables — migration target |
| `core/workflow/storage.py` (WorkflowStore) | **Workflow** | 1 | SQLite (workflow.db) | Requires review |
| `core/planner/store.py` (PlanStore) | **Planner** | 1 | SQLite (workflow.db) | Requires review |
| `core/activity/storage.py` (ActivityStore) | **Core Platform** | 1 | SQLite (workflow.db) | Requires review |
| `core/persistence/store.py` (CheckpointStore) | **Execution** | 1 | SQLite | Requires review |
| `memory/fact_store.py` | **Memory** | 1 | SQLite (jarvis_memory.db) | Requires review |
| `brain/goals/goal_manager.py` | **Planner** (deprecating) | 1 | SQLite (brain.db) | Migrating to UnifiedStore |
| `core/cloud/cloud_memory.py` | **Core Platform** | 1 | Supabase + SQLite | Requires review |

### Target Storage Ownership (post-consolidation, bounded-context strategy)

| Database | Owner | Managed Tables | Migration Tool |
|----------|-------|---------------|---------------|
| `data/system.db` | **Core Platform** | Core system state | Alembic |
| `data/memory.db` | **Memory** | Memory data (facts, episodes, decisions, embeddings) | Alembic |
| `data/workflow.db` | **Workflow** | Workflow instances, steps, execution context (sync ORM target) | Alembic |
| `data/planner.db` | **Planner** | Goals, plans, plan health | Alembic |
| `~/.jarvis/user.db` | **Core Platform** | User-scoped state (checkpoints, agents, browser) | Alembic |

### Storage Layer Rules

```
ORM Models
    │
    │ MUST be defined in core/database.py (async) or migrated
    │ MUST have Alembic migration
    │ MUST NOT use create_all() in production
    ▼
Raw SQLite
    │
    │ MUST use WAL journal mode
    │ MUST use threading.Lock() for thread safety
    │ MUST have migration strategy (Alembic target)
    │ MUST NOT use JSON files for new features
    ▼
JSON Files (legacy only)
    │
    │ Auth: migration to SQLite planned
    │ OAuth: migration to encrypted storage planned
    │ memory.json: deprecated, removal planned
    ▼
```

---

## 9. Layer 8: Brain & Autonomous Systems

### Ownership Table

| Module | Owner | Files | Dependencies | Change Policy |
|--------|-------|-------|--------------|---------------|
| `brain/UnifiedBrain.py` | **Brain** | 1 | Memory (System B), Planner (brain), Goals | Requires review |
| `brain/automation/loop.py` | **Brain** | 1 | Memory (System B), Goals | Requires review |
| `brain/planner/` | **Planner** (deprecating) | 3 | None | Deprecated — migrating to CorePlanner |
| `brain/memory/` | **Memory** (deprecating) | 6 | brain.db | Deprecated — migrating to memory/ |
| `brain/goals/` | **Planner** (deprecating) | 3 | brain.db | Deprecated — migrating to UnifiedStore |
| `brain/learning_engine.py` | **Brain** | 1 | Memory (System B) | Requires review |
| `brain/self_improvement.py` | **Brain** | 1 | Memory (System B) | Requires review |
| `brain/skill_acquisition.py` | **Brain** | 1 | Memory (System B) | Requires review |
| `brain/world_model.py` | **Brain** | 1 | Memory (System B) | Requires review |
| `brain/cognitive_patterns.py` | **Brain** | 1 | LLM | Requires review |
| `brain/goal_generator.py` | **Brain** | 1 | WorldModel, GoalManager | Requires review |
| `brain/persistence.py` | **Brain** | 1 | brain.db | Requires review |

### Brain Migration Target

| Current Brain Module | Target Module | Status |
|---------------------|---------------|--------|
| `brain/memory/` → MemoryFacade | `memory/memory_facade.py` | Planned (Phase 2) |
| `brain/planner/` → CorePlanner | `core/planner/` | Planned (Phase 3) |
| `brain/goals/` → UnifiedStore | TBD | Planned (Phase 3) |
| `brain/automation/loop.py` → WorkflowEngine | `core/workflow/engine.py` | Investigation needed |
| `brain/learning_engine.py` → KnowledgeStore | `core/long_term_memory/` | Investigation needed |

---

## 10. Layer 9: Tools & Execution

### Ownership Table

| Module | Owner | Files | Dependencies | Change Policy |
|--------|-------|-------|--------------|---------------|
| `core/tools/execution.py` | **Execution** | 1 | tool_factory, security, memory | **Stable — requires architecture review** |
| `core/tools/tool_factory.py` | **Execution** | 1 | All tool modules | **Critical — thread safety fix needed** |
| `core/tools/security.py` | **Security** | 1 | authz_engine | Requires security review |
| `core/tools/*.py` (individual tools) | **Execution** | ~20+ | execution.py | Per-tool review |
| `core/agents/` (agent system) | **Execution** | ~15 | Pipeline, tools, memory | Requires review |
| `core/graph/` (agent graph) | **Execution** | ~5 | AgentState, tools | Requires review |
| `core/control_loop.py` | **Execution** | 1 | Pipeline, tools, DecisionMemory | Requires review |

### Interface Contracts

| Contract | Provider | Consumers | Stability |
|----------|----------|-----------|-----------|
| `ToolBlock` dataclass | `core/tools/execution.py` | WorkflowEngine, Pipeline | Stable |
| `ToolResult` dataclass | `core/tools/execution.py` | All callers | Stable |
| `BaseTool` (protocol) | `core/tools/base.py` | Tool implementations | Stable |
| `AgentState` dataclass | `core/graph/state.py` | Agent graph | Beta |
| `is_authorized_to_execute()` | `core/tools/security.py` | execution.py | Stable |

### Execution Layer Rules

```
Pipeline Stage 14 → execute_tool_block()
    │
    ├── is_authorized_to_execute()  (always, before execution)
    ├── PermissionManager.resolve() (always)
    ├── tool_factory.create()  (thread-safe — target)
    ├── tool.run()
    └── tool_factory.cleanup()
    │
    │ MUST NOT bypass security checks
    │ MUST NOT call pipeline stages directly
    │ MUST log all tool calls
    ▼
ToolResult
```

---

## 11. Layer 10: Integrations & External Services

### Ownership Table

| Module | Owner | Files | Dependencies | Change Policy |
|--------|-------|-------|--------------|---------------|
| `integrations/gmail/` | **Integrations** | ~5 | OAuth, Gmail API | Requires review |
| `integrations/whatsapp/` | **Integrations** | ~3 | Twilio API | Requires review |
| `integrations/calendar/` | **Integrations** | ~2 | Calendar API | Requires review |
| `mcp/` (MCP servers) | **MCP** | ~10 | Pipeline | Requires review |
| `provider_sdk/` | **Provider SDK** | ~10 | Permission system | Requires review |
| `core/providers/` (LLM providers) | **Providers** | ~20 | Config, memory | Requires review |
| `core/cloud/` (Supabase) | **Core Platform** | ~5 | Supabase SDK | Requires review |

### Integration Rules

```
External Service
    │
    │ MUST go through configured adapter/protocol
    │ MUST handle network errors gracefully
    │ MUST have timeout configuration
    │ MUST NOT access storage directly (go through core layers)
    ▼
Core Layer
```

---

## 12. Change Policies

### Policy Levels

| Level | Requires | Examples |
|-------|----------|---------|
| **Stable** | Architecture review + owner approval | Public interfaces (Result, IdentityContext, PipelineContext) |
| **Requires review** | Owner approval + code review | Most modules |
| **Requires security review** | Security team signoff + owner approval | auth.py, authz/, permission/, security.py |
| **Per-tool review** | Tool owner approval | Individual tool implementations |
| **Deprecated — no new changes** | Exception-only | brain/memory/, brain/planner/, core/memory.py |

### What Constitutes a Breaking Change

1. **Interface changes**: Adding/removing/renaming parameters in any public function or method
2. **Data model changes**: Adding/removing/renaming fields in dataclasses or SQL tables
3. **Dependency changes**: Adding/modifying module imports across layer boundaries
4. **Behavior changes**: Changing return values, error handling, or side effects
5. **Storage changes**: Modifying schema, migration path, or database location

### Change Approval Matrix

| Change Type | Small (< 50 lines) | Medium (50-200) | Large (> 200) |
|-------------|-------------------|-----------------|---------------|
| Bug fix in owned module | Self-reviewed | Owner review | Owner review |
| Bug fix cross-module | Owner review | Architecture review | Architecture review |
| New feature in owned module | Owner review | Architecture review | Architecture review |
| New feature cross-module | Architecture review | Architecture review | Architecture review |
| API/interface change | Architecture review | Architecture review | Architecture + Security |
| Storage schema change | Architecture review | Architecture review | Architecture + Security |
| Deprecation | Owner + announcement | Owner + announcement | Architecture review |
| Removal | Per deprecation policy | Per deprecation policy | Architecture review |

---

## 13. Interface Contracts Registry

### Critical Interfaces (must not change without architecture review)

| # | Interface | File | Consumers | Status |
|---|-----------|------|-----------|--------|
| 1 | `PipelineContext` | `core/pipeline/context.py` | 19 stages, 50+ fields | Stable |
| 2 | `PipelineStage.execute(context)` | `core/pipeline/stages/base.py` | Pipeline executor | Stable |
| 3 | `IdentityContext` | `core/identity/models.py` | Pipeline, services | Stable |
| 4 | `is_authorized_to_execute(tool, ctx)` | `core/tools/security.py` | execution.py | Stable |
| 5 | `ToolBlock` / `ToolResult` | `core/tools/execution.py` | WorkflowEngine, Pipeline | Stable |
| 6 | `Result[T]` (Ok/Err) | `core/result.py` | All layers | Stable |
| 7 | `MemoryFacade.store()/recall()` | `memory/memory_facade.py` | Pipeline, API, tools | Beta |
| 8 | `FactStore.store_facts()` | `memory/fact_store.py` | MemoryStage | Stable |
| 9 | `WorkflowEngine.start_workflow()` | `core/workflow/engine.py` | Agents, tools, API | Stable |
| 10 | `StepDefinition` | `core/workflow/models.py` | Planner → Workflow | Stable |
| 11 | `EventBus.publish()` | `core/event_bus.py` | All layers | Stable |
| 12 | `ConfigRegistry.get()` | `core/config_registry.py` | All layers | Stable |

### Interfaces Being Deprecated

| # | Interface | Replacement | Deprecated Since | Removal Target |
|---|-----------|-------------|-----------------|---------------|
| 1 | `core.memory.MemoryManager` | `memory.memory_facade.MemoryFacade` | v3.2 | After v4.0 |
| 2 | `core.memory.get_text_similarity()` | `memory/` utils | N/A (known dependency) | After System B migration |
| 3 | `brain.planner.Planner` | `core.planner.Planner` (target) | N/A | After Phase 3 |
| 4 | `brain.memory.MemoryManager` | `memory.memory_facade.MemoryFacade` | N/A | After Phase 2 |
| 5 | `brain.goals.GoalManager` | UnifiedStore | N/A | After Phase 3 |
| 6 | `Database URL` (legacy) | `JARVIS_DB__URL` env var | v3.2 | After v4.0 |

---

## 14. Deprecated Modules Registry

| Module | Path | Deprecated | Removal | Migration Target | Current Consumers |
|--------|------|-----------|---------|-----------------|-------------------|
| `core/memory.py` | Core memory manager | v3.2 | v4.0+ | `memory/` | MCP memory server (TODO), brain/memory similarity |
| `core/memory_vector.py` | ChromaDB vector store | N/A | Post-consolidation | mem0 adapter | Unknown |
| `core/plan_manager.py` | JSON plan manager | N/A | Post-UnifiedStore | PlanStore | Legacy routes |
| `core/database_models.py` | Sync ORM | N/A | Post-ORM-merge | async database.py | Multiple legacy consumers |
| `brain/planner/` | Fixed 3-node DAG | Target | Post-Phase 3 | CorePlanner | UnifiedBrain |
| `brain/memory/` | Agent-facing memory | Target | Post-Phase 2 | MemoryFacade | Brain subsystems |
| `brain/goals/` | Brain goal CRUD | Target | Post-Phase 3 | UnifiedStore | Brain subsystems |
| `data/auth.json` | Auth user storage | Target | Post-Phase 6 | SQLite auth | AuthManager |
| `data/sessions.json` | Auth session storage | Target | Post-Phase 6 | SQLite auth | AuthManager |

---

## 15. Removal Verification Report

> **Gate:** Before any module, file, database, or public interface is deleted, a Removal Verification Report must be completed and reviewed. No deletion — of any size — may proceed without this gate.
>
> **Rationale:** The 13 prior audits revealed extensive implicit dependencies, shared state, and undocumented consumers. Blind deletion risks silent data loss, runtime crashes, or regressions that surface weeks later.

### Report Template

Copy this template into the removal PR or issue. Fill all sections before requesting deletion approval.

```markdown
## Removal Verification Report: <target name>

### 1. Target
- **Module/File/DB**: <path>
- **Purpose**: <one-line summary of what it does>
- **Proposed Removal Date**: <YYYY-MM-DD>

### 2. Import Audit
- [ ] All direct imports identified (list below or link to grep output)
- [ ] All indirect (transitive) imports identified
- [ ] Dynamic imports / lazy imports identified (e.g., `importlib.import_module`, `__import__`)
- [ ] String-based references identified (e.g., `"core.memory.MemoryManager"`)
- [ ] No remaining import references

Direct imports:
```
<file1>:<line>: import <target>
<file2>:<line>: from <target> import ...
...
```

Indirect imports (trace through re-exports):
```
<fileA> → <fileB> (re-exports <target>) → <fileC> imports from <fileB>
...
```

### 3. Runtime Usage Audit
- [ ] Startup registration (e.g., `_REGISTRY_MAP`, `EventBus.subscribe`, `PluginManager.register`)
- [ ] Call frequency estimate (from monitoring or code analysis)
- [ ] Error-handling paths that reference this target
- [ ] Configuration keys that reference this target
- [ ] CLI argument or env var references

Runtime call sites:
```
<file>:<line>: <call_site>  # approximate frequency: <daily|hourly|per-request|startup-only>
...
```

### 4. Test Coverage Audit
- [ ] All direct tests identified
- [ ] Integration tests that transitively exercise this target
- [ ] Fixtures/mocks/setup code that references this target
- [ ] Test coverage % for this target (if measurable)

Test files:
```
tests/<path>  # <number> test cases directly covering target
tests/<path>  # <number> tests transitively covering target
```

### 5. Data Migration (for storage targets only)
- [ ] Schema of data to be migrated documented
- [ ] Migration script written and tested
- [ ] Rollback script written and tested
- [ ] Data integrity verified (checksum or row count after migration)
- [ ] No data loss (all columns mapped to target schema)
- [ ] Migration dry-run completed in staging

### 6. Replacement Verification
- [ ] Replacement module/file/DB is fully operational
- [ ] All consumers have been migrated to replacement
- [ ] Replacement handles all edge cases the original handled
- [ ] Replacement performance is equivalent or better
- [ ] Replacement error messages are equivalent or better

### 7. Switchover Plan
- [ ] Deploy order defined (original + replacement both present → migrate consumers → remove original)
- [ ] Feature flag or gradual rollout mechanism in place
- [ ] Monitoring alert for errors in replacement path
- [ ] Rollback plan documented (time to restore, data reimport needed)
- [ ] Communication sent to affected teams

### 8. Final Verification
- [ ] Zero references remaining (grep entire repo including docs, comments, config files)
- [ ] Test suite passes without this target
- [ ] Application starts without this target
- [ ] Integration/E2E tests pass
- [ ] Feature parity confirmed (replacement produces same outputs for same inputs)

### 9. Approvals
- [ ] **Module Owner**: <name> — <date>
- [ ] **Architecture Review**: <name> — <date>  (required if breaking change)
- [ ] **Security Review**: <name> — <date>  (required if security-adjacent)
- [ ] **Migration Owner**: <name> — <date>  (required if storage target)

---

## 16. Enforcement

### Automated Enforcement (Target)

| Rule | Enforcement | Mechanism |
|------|------------|-----------|
| Only IdentityService creates IdentityContext | **Currently enforced** | `test_architecture_audit.py` — lint check |
| Downward dependencies only | TBD | `import-lint` — ban upward imports |
| No bypassing pipeline | TBD | Code review — detect direct core/tools/ imports from API |
| Thread safety for shared state | TBD | Lint rule — require Lock for module-level state |
| Alembic migration for schema changes | TBD | CI check — detect create_table outside migration |

### Recommended Enforcement Additions

| Rule | Tool | Effort |
|------|------|--------|
| Layer boundary violations | `import-lint` or `pytest-arch` | 1-2 days to configure |
| Thread safety | Custom lint rule (Lock required for module-level mutable state) | 1 day |
| Migration coverage | CI step that compares `CREATE TABLE` in code vs Alembic | 1 day |
| Deprecated module imports | Grep in CI — fail if deprecated module imported by non-exempt consumer | 1 hour |

### Ownership Change Procedure

1. **Request**: File an issue with the owner's label
2. **Review**: Owner reviews the change against this document's contracts
3. **Approve**: Owner approves or routes to architecture/security review
4. **Merge**: Approved changes merged with ownership metadata in commit message
5. **Update**: This document is updated if interfaces change
