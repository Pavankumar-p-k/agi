# State Architecture Audit — Phase 0 (Document 2)

> **Purpose:** Answer every question about state in the system — where it lives, who owns it, who creates/reads/writes/destroys it, how it persists, thread safety, and recovery.
>
> **Scope:** 14 state domains across the entire codebase.
>
> **Prerequisite for:** All remaining audits. State is the foundation of every subsystem.

---

## Table of Contents

1. [State Overview Matrix](#1-state-overview-matrix)
2. [Conversation & Session State](#2-conversation--session-state)
3. [Pipeline State](#3-pipeline-state)
4. [Planner State](#4-planner-state)
5. [Workflow State](#5-workflow-state)
6. [Agent State](#6-agent-state)
7. [Browser State](#7-browser-state)
8. [Desktop State](#8-desktop-state)
9. [Memory State](#9-memory-state)
10. [Activity State](#10-activity-state)
11. [Goal State](#11-goal-state)
12. [Identity & Permission State](#12-identity--permission-state)
13. [Execution State](#13-execution-state)
14. [Checkpoint & Recovery State](#14-checkpoint--recovery-state)
15. [Runtime State](#15-runtime-state)
16. [Global State Index](#16-global-state-index)
17. [Thread Safety Audit](#17-thread-safety-audit)
18. [Persistence Map](#18-persistence-map)
19. [Recovery Analysis](#19-recovery-analysis)
20. [Findings & Recommendations](#20-findings--recommendations)

---

## 1. State Overview Matrix

| State Domain | Owner | Lifetime | Persistence | Thread Safe | Recovery | Duplicates |
|---|---|---|---|---|---|---|
| Conversation | `SessionManager` / `ConversationManager` | Per-session | JSON files + SQLite | No | Partial (SQLite) | 2 managers, 2 formats |
| Pipeline | `PipelineContext` | Per-request | None (in-memory) | No (async-only context) | None | — |
| Planner | `PlanStore` / `GoalManager` | Per-goal/plan | SQLite | Yes (Lock) | Full (SQLite) | 2 planners (brain + core) |
| Workflow | `WorkflowStore` / `WorkflowEngine` | Per-workflow | SQLite | Yes (Lock) | Full (SQLite) | — |
| Agent | `AgentRegistry` / SubAgent instances | Process-lifetime / per-task | In-memory + JSON | No | None | 2 agent systems (core + brain) |
| Browser | `BrowserManager` | Process-lifetime | JSON files | Async-safe | Partial | — |
| Desktop | `DesktopController` / `SafetyManager` | Process-lifetime | In-memory | No | None | — |
| Memory | `MemoryFacade` / `MemoryManager` / `TieredMemory` | Process-lifetime | SQLite + JSON + Vector DB | Partial (brain.memory has Lock) | Full (SQLite) | **3 concurrent systems** |
| Activity | `ActivityStore` / `ActivityManager` | Per-activity | SQLite | Yes (Lock) | Full (SQLite) | — |
| Goal | `GoalManager` | Per-goal | SQLite | Yes (Lock) | Full (SQLite) | Duplicated in brain + core |
| Identity | `IdentityContext` dataclass | Per-request | None (in-memory) | No (frozen) | None | — |
| Permission | `PermissionManager` | Process-lifetime | In-memory | No | None | — |
| Execution | `executor` singleton / `execute_tool_block()` | Process-lifetime / per-call | None (in-memory) | No | None | 2 execution systems |
| Checkpoint | `CheckpointManager` / `ProjectPersistence` | Per-project | JSON + SQLite | Yes (Lock) | Full (both) | **2 redundant systems** |
| Runtime | `RuntimeContext` | Per-request | None (in-memory) | No (frozen) | None | — |

---

## 2. Conversation & Session State

### State Objects

| Object | Location | Type | Fields |
|--------|----------|------|--------|
| `ConversationManager` | `session.py` | Class instance | `_sessions: dict[str, Session]` (module-level singleton) |
| `Session` (dataclass) | `session.py` / `core/session.py` | Dataclass | `session_id`, `user_id`, `messages: list`, `created_at`, `updated_at`, `metadata: dict` |
| `SessionManager` | `core/session_db.py` | Class instance | Per-user session lists in SQLite |
| `ProjectContext` | `core/routing/project_context.py` | Dataclass | `project_path`, `session_id`, `user_id`, `code_index: CodeIndex` |
| `ContextManager` | `core/routing/project_context.py` | Module-level singleton | `_contexts: dict[str, ProjectContext]` |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | `jarvis.py` → `cmd_cli()` creates `ConversationManager`. `get_context_manager()` creates `ContextManager`. |
| **Reader** | Pipeline stages, route handlers, chat handlers |
| **Writer** | `ConversationManager.add_message()`, pipeline identity/context stages |
| **Destroyer** | Session expiry (not explicitly implemented — sessions persist in memory until process death) |
| **Persistence** | `~/.jarvis/sessions/` (JSON per-session) via `SessionManager.save_session()`. Also `core/session_db.py` (SQLite via `session_db.Session` model) |
| **Thread Safety** | None. `_sessions` dict is accessed without locks. |

### Duplicate Session Systems

| System | Module | Format | Used By |
|--------|--------|--------|---------|
| `ConversationManager` | `session.py` (root) | In-memory dict of sessions | CLI, older chat paths |
| `SessionManager` | `core/session_db.py` | SQLite via SQLAlchemy | Pipeline, API routes |
| `Session` (SQLAlchemy model) | `core/database_models.py` | SQLite ORM | Various core operations |

### Issues

1. **Two session systems** — root `session.py` uses in-memory dicts, `core/session_db.py` uses SQLite. Messages are duplicated across both.
2. **No session expiry** — sessions grow unboundedly in memory.
3. **No thread safety** — concurrent requests to `ConversationManager._sessions` can corrupt data.

---

## 3. Pipeline State

### State Objects

| Object | Location | Type | Fields (~35 total) |
|--------|----------|------|---------------------|
| `PipelineContext` | `core/pipeline/context.py` | Dataclass | `request`, `response`, `identity`, `auth_result`, `authz_result`, `resource_access`, `resource_grant`, `security_context`, `tenant_resolution`, `capability`, `plan`, `decisions`, `outcomes`, `observations`, `metrics`, `user_preferences`, `memory_context`, `stage_results`, `error`, `metadata`, `deterministic_services` |
| `Pipeline` | `core/pipeline/pipeline.py` | Class (global singleton via `get_pipeline()`) | `_stages: list[tuple[str, PipelineStage]]`, `_hooks: HookRegistry`, `_context: PipelineContext` |
| `Request` | `core/pipeline/messages.py` | Dataclass | `message_id`, `channel`, `user_id`, `session_id`, `text`, `attachments`, `metadata`, `timestamp` |
| `Response` | `core/pipeline/messages.py` | Dataclass | `message_id`, `text`, `data`, `error`, `metadata` |
| `Decision` | `core/pipeline/decision.py` | Dataclass | `stage`, `timestamp`, `reason`, `confidence`, `data` |
| `Outcome` | `core/pipeline/outcome.py` | Dataclass | `decision_id`, `result`, `observations: list[Observation]` |
| `Observation` | `core/pipeline/observation.py` | Dataclass | `type`, `source`, `data`, `timestamp`, `fingerprint` |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | `Pipeline.execute()` creates `PipelineContext` per request |
| **Reader** | All 19 pipeline stages read from `PipelineContext` |
| **Writer** | Each stage writes its result to `PipelineContext` via `set_stage_field()` |
| **Destroyer** | Garbage collected after request completes |
| **Persistence** | None. Entirely in-memory. |
| **Thread Safety** | Async-only (each request has its own context). No locks needed. |
| **Recovery** | None. If the process dies mid-request, context is lost. |

### Issues

1. **`PipelineContext` has ~35 fields** — largest per-request object in the system. Adding a stage means adding a field.
2. **`STAGE_OWNERSHIP`** in `base.py` is a global mutable dict that maps stages to context fields. Modifications affect all pipelines.
3. **No serialization** — pipeline context cannot be checkpointed mid-execution.
4. **`Pipeline` singleton** — `get_pipeline()` returns a single global instance. If multiple pipelines with different stage configurations are needed, this pattern breaks.

---

## 4. Planner State

### Duplicate Planner Systems

#### System A: `brain/planner/` (legacy brain planner)

| Object | Location | Type |
|--------|----------|------|
| `planner` singleton | `brain/planner/planner.py:66` | `Planner` instance (in-memory) |
| `TaskGraph` | `brain/planner/task_graph.py` | DAG of `TaskNode` objects |
| `TaskNode` | `brain/planner/task_graph.py` | Dataclass with `id`, `type`, `status`, `dependencies`, `result` |

**Persistence:** None. Entirely in-memory.
**Lifetime:** Per-goal. Created by `Planner.create_plan()`, destroyed on completion.

#### System B: `core/planner/` (core planner)

| Object | Location | Type |
|--------|----------|------|
| `PlanStore` | `core/planner/store.py` | SQLite-backed |
| `PlanEvidenceEngine` | `core/planner/evidence.py` | In-memory |
| `PlanHealthEngine` | `core/planner/health.py` | In-memory |
| `ReplanEngine` | `core/planner/replan.py` | In-memory |
| `GoalDecomposer` | `core/planner/decomposer.py` | In-memory state machine |
| `ComparativeScorer` | `core/planner/comparison.py` | In-memory |
| `StrategyGenerator` | `core/planner/strategies.py` | In-memory |

**Persistence:** `PlanStore` uses SQLite (`data/workflow.db`). Remaining engines are in-memory.
**Thread Safety:** `PlanStore` uses `threading.Lock`. Others have no thread safety.

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | Pipeline `PlannerStage` calls `GoalDecomposer.decompose()`, creates plan from request |
| **Reader** | Pipeline stages, `PlanValidatorStage`, API routes |
| **Writer** | Planner stage, replan engine, plan health engine |
| **Destroyer** | Plan completion or cancellation |
| **Persistence** | Core planner uses SQLite (`data/workflow.db`). Brain planner is in-memory only. |

### Issues

1. **Two planner systems** — brain/planner (legacy, in-memory) and core/planner (SQLite-backed). No synchronization between them.
2. **`core/planner/store.py` and `core/workflow/storage.py` share `data/workflow.db`** — implicit coupling through shared database file.
3. **Planner state spans 7 files** — `store.py`, `evidence.py`, `health.py`, `replan.py`, `decomposer.py`, `comparison.py`, `strategies.py`. No single state owner.

---

## 5. Workflow State

### State Objects

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `WorkflowEngine` | `core/workflow/engine.py` | Class singleton | In-memory + delegates to store |
| `WorkflowStore` | `core/workflow/storage.py` | Class instance | SQLite (`data/workflow.db`) |
| `ExecutionNode` | `core/workflow/graph.py` | Dataclass | In-memory (tracked via tracker) |
| `WorkflowTracker` | `core/workflow/tracker.py` | Class instance | In-memory |
| `StepDefinition` | `core/workflow/models.py` | Dataclass | Serialized in store |
| `WorkflowStatus` | `core/workflow/models.py` | Enum | Checked at runtime |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | `WorkflowEngine.create_workflow()` |
| **Reader** | API routes, scheduler, pipeline adapters |
| **Writer** | `WorkflowEngine.execute_step()`, `WorkflowStore.save_workflow()` |
| **Destroyer** | Workflow completion or cancellation |
| **Persistence** | `WorkflowStore` (SQLite). In-flight step state is ephemeral. |
| **Thread Safety** | `WorkflowStore` uses `threading.Lock`. Engine is async-safe. |

### Issues

1. **Workflow engine depends on `ActivityStore` and `PlanStore`** — all sharing `data/workflow.db` with no documented schema ownership.
2. **No compensation/rollback** — if a workflow step fails mid-execution, no rollback mechanism exists.
3. **`StepDefinition` and `WorkflowStatus` are duplicated** — defined in both `core/workflow/models.py` and `core/pipeline/stages/execution.py` (as `ProviderResult`).
4. **`FocusMode` enum in tracker** — suggests partial workflow tracking exists but is incomplete.

---

## 6. Agent State

### State Objects

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `AgentRegistry` | `core/agents/registry.py` | Module-level singleton | In-memory dict |
| `SubAgent` instances | `core/agents/_legacy/*.py` | 9 class instances | In-memory |
| `AgentRuntime` | `core/agent_runtime.py` | Class instance | In-memory |
| `AgentOrchestrator` | `core/agent_orchestrator.py` | Module-level singleton | In-memory |
| `ExecutionGraph` | `core/agents/execution_graph.py` | In-memory DAG | In-memory |
| `UnifiedBrain` | `brain/UnifiedBrain.py:543` | Module-level singleton | In-memory + delegates to stores |
| `executor` singleton | `brain/executor/executor.py:187` | Module-level singleton | In-memory |
| `ComputerAgent` | `pc_agent/computer_agent.py:220` | Module-level singleton | In-memory + SQLite |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | `AgentRegistry.register()`, `UnifiedBrain.__init__()`, `ComputerAgent.__init__()` |
| **Reader** | Pipeline, API routes, skill loader |
| **Writer** | Agent runtime, tool execution, brain automation loop |
| **Destroyer** | Process termination (no explicit teardown) |
| **Persistence** | `ComputerAgent` uses SQLite (`data/pc_agent.db`). Other agents are in-memory only. |

### Issues

1. **3 independent agent systems** — `core/agents/` (registry-based), `brain/` (UnifiedBrain monolithic), `pc_agent/` (standalone computer agent). No coordination.
2. **Legacy agents (9 files in `_legacy/`)** — `atlas.py`, `cipher.py`, `forge.py`, `herald.py`, `nexus.py`, `oracle.py`, `phantom.py`, `scribe.py`, `sentinel.py`. All are in-memory singletons with no persistence.
3. **Agent execution graph** — 100% in-memory. Lost on crash.

---

## 7. Browser State

### State Objects

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `BrowserManager` | `core/browser_manager.py` | Module-level singleton | JSON files in `data/browser_sessions/` |
| `BrowserSession` | `core/tools/browser_tools.py` | Dataclass | In-memory + dump to JSON |
| `browser` singleton | `automation/pc_automation.py:173` | `BrowserManager` (Selenium) | In-memory |
| `BrowserPlanner` | `core/tools/browser_planner.py` | Class instance | In-memory |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | `BrowserManager.new_session()`, `BrowserManager.get()` (lazy Selenium init) |
| **Reader** | Pipeline browser capability, MCP server, API routes |
| **Writer** | Navigation, click, type actions |
| **Destroyer** | `BrowserManager.close_session()`, process death |
| **Persistence** | Session dumps to `data/browser_sessions/` as JSON |
| **Thread Safety** | Async-safe via `asyncio.Lock` in `BrowserManager` |

### Issues

1. **Duplicate browser managers** — `core/browser_manager.py` (playwright-based) and `automation/pc_automation.py` (selenium-based). Different APIs, different persistence.
2. **JSON session dump** — unstructured, schema-less. Not usable for replay without the same page state.

---

## 8. Desktop State

### State Objects

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `DesktopController` | `core/desktop/controller.py` | Module-level singleton | In-memory |
| `ScreenCapture` | `core/desktop/screen.py` | Module-level singleton | In-memory |
| `WindowController` | `core/desktop/window.py` | Module-level singleton | In-memory |
| `SafetyManager` | `core/desktop/controller.py` | Module-level singleton | In-memory (rate-limit state + forbidden regions) |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | Module-level instantiation at import |
| **Reader** | Pipeline desktop capability, provider adapter |
| **Writer** | Click, type, screenshot, window operations |
| **Destroyer** | Process termination only |
| **Persistence** | None. All in-memory. |
| **Thread Safety** | None. `SafetyManager` has no locks. |

### Issues

1. **All desktop state is in-memory** — cursor position, window handles, screen dimensions are lost on restart.
2. **`SafetyManager` uses in-memory rate limiting** — a process restart resets all rate limits.
3. **No session isolation** — desktop state is global to the process. Two concurrent users share desktop state.

---

## 9. Memory State

### Three Concurrent Memory Systems

#### System A: `memory/` (new facade)

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `MemoryFacade` (singleton `memory`) | `memory/memory_facade.py` | Module-level singleton | Delegates to sub-systems |
| `TieredMemory` (singleton `tiered_memory`) | `memory/tiered_memory.py` | Module-level singleton | Hot: in-memory. Warm: Mem0. Cold: Qdrant/vector |
| `Mem0Adapter` (singleton `mem0_memory`) | `memory/mem0_adapter.py` | Module-level singleton | Mem0 (external memory service) |
| `FactStore` | `memory/fact_store.py` | Factory singleton via `get_fact_store()` | SQLite (`data/jarvis_memory.db`) |
| `EmbeddingMemory` | `memory/embedding_memory.py` | Factory singleton | SQLite + numpy vectors |
| `DecisionMemory` (singleton `decision_memory`) | `memory/decision_memory.py` | Module-level singleton | JSON (`~/.jarvis/decision_memory.json`) |

#### System B: `brain/memory/` (legacy brain memory)

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `MemoryManager` (singleton `memory_manager`) | `brain/memory/memory_manager.py:144` | Module-level singleton | SQLite (`data/brain.db`) |
| `EpisodicMemory` | `brain/memory/episodic.py` | Instance | SQLite |
| `SemanticMemory` | `brain/memory/semantic.py` | Instance | SQLite |
| `TaskMemory` | `brain/memory/task.py` | Instance | SQLite |
| `DecisionMemory` | `brain/memory/decision.py` | Instance | SQLite |

#### System C: `core/memory*` (core memory)

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `MemoryManager` | `core/memory.py` | Class instance | SQLite (`ai_os_memory.db` at root) |
| `MemoryVectorStore` | `core/memory_vector.py` | Class instance | Chroma/Qdrant |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | Each module creates its singleton at import time |
| **Reader** | Pipeline memory stage, context retrieval, brain automation, skill execution |
| **Writer** | Memory storage operations across all 3 systems |
| **Destroyer** | Never explicitly destroyed (process lifetime) |
| **Persistence** | 4 databases: `data/brain.db`, `data/jarvis_memory.db`, `ai_os_memory.db`, `~/.jarvis/decision_memory.json` |
| **Thread Safety** | `brain/memory/` sub-providers use `threading.Lock`. `memory/` systems are not consistently thread-safe. |

### Issues

1. **3 concurrent memory systems** — each with its own schema, storage location, and access patterns. No synchronization between them.
2. **4 separate databases** — `data/brain.db`, `data/jarvis_memory.db`, `ai_os_memory.db`, `~/.jarvis/decision_memory.json`. Data fragmentation.
3. **`MemoryFacade` delegates to `TieredMemory` and `Mem0Adapter` via lazy imports** — if one fails, the facade silently degrades (returns `None` for properties).
4. **`DecisionMemory`** is duplicated in both `memory/` (JSON) and `brain/memory/` (SQLite). Different data, different schemas.

---

## 10. Activity State

### State Objects

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `ActivityStore` | `core/activity/storage.py` | Class instance | SQLite (`data/workflow.db`) |
| `ActivityManager` | `core/activity/manager.py` | Class instance | In-memory + delegates to store |
| `ActivityRecorder` | `core/activity/recorder.py` | Class instance | In-memory |
| `ReplayAssembler` | `core/activity/replay.py` | Class instance | Read-only |
| `ResumeEngine` | `core/activity/resume.py` | Class instance | Reads from manager/store |
| `ActivityNode` | `core/activity/models.py` | Dataclass | Serialized in store |
| `ActivityEdge` | `core/activity/models.py` | Dataclass | Serialized in store |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | `Pipeline.execute()` → `ActivityManager.create_activity()`, or explicit via API |
| **Reader** | Pipeline, replan engine, resume engine, API routes |
| **Writer** | `ActivityRecorder.record()`, `ActivityManager.update_activity()` |
| **Destroyer** | `ActivityManager.cleanup()` (manual), never automatic |
| **Persistence** | SQLite (`data/workflow.db`). Shared with WorkflowStore and PlanStore. |
| **Thread Safety** | `ActivityStore` uses `threading.Lock`. `ActivityManager` and `Recorder` are not explicitly thread-safe. |

### Issues

1. **`data/workflow.db` shared by 3 stores** — `ActivityStore`, `WorkflowStore`, `PlanStore` all write to the same SQLite database. Schema collisions possible.
2. **Activity graph grows unbounded** — `cleanup()` must be called manually. No TTL or archival.
3. **`ReplayAssembler` and `ResumeEngine`** both read the activity graph but use different access patterns (in-memory vs store queries).
4. **Activity recording is synchronous** — `Pipeline.execute()` calls `ActivityRecorder.record()` inline, adding latency to every request.

---

## 11. Goal State

### Duplicate Goal Systems

#### System A: `brain/goals/` (legacy brain goals)

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `GoalManager` | `brain/goals/goal_manager.py` | Class instance | SQLite (`data/brain.db`) |
| `Goal` | `brain/goals/goal.py` | Dataclass | Serialized in store |
| `GoalStatus` | `brain/goals/goal.py` | Enum | Checked at runtime |

**Thread Safety:** `threading.Lock` in `GoalManager`.

#### System B: `core/plan_manager.py` (core goals/plans)

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `PlanManager` | `core/plan_manager.py` | Class instance | In-memory |
| `Plan` | `core/plan_manager.py` | Dataclass | In-memory |

**Thread Safety:** None.

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | `GoalGenerator` (brain), pipeline planner stage, automation loop |
| **Reader** | Brain executor, verifier, world model, automation loop |
| **Writer** | `GoalManager.update_goal()`, automation loop |
| **Destroyer** | Goal completion (`GoalStatus.COMPLETED/FAILED`) |
| **Persistence** | `brain/goals/` → SQLite (`data/brain.db`). `core/plan_manager.py` → in-memory only. |

### Issues

1. **Two goal systems** — `brain/goals/` (SQLite-backed) and `core/plan_manager.py` (in-memory). Plans created in the pipeline via `PlanManager` are not persisted.
2. **`GoalManager` and `PlanManager` have overlapping concepts** — both manage "things to accomplish" but with different persistence guarantees.
3. **Goal auto-generation** via `GoalGenerator` creates goals autonomously — no user visibility or control.

---

## 12. Identity & Permission State

### State Objects

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `IdentityContext` | `core/identity/models.py` | Frozen dataclass | In-memory (per-request) |
| `UserIdentity` | `core/identity/models.py` | Frozen dataclass | In-memory |
| `SessionIdentity` | `core/identity/models.py` | Frozen dataclass | In-memory |
| `ResourceScope` | `core/identity/resource_scope.py` | Dataclass | In-memory |
| `TenantResolutionResult` | `core/identity/tenant_resolver.py` | Dataclass | In-memory |
| `AuthenticationResult` | `core/pipeline/authentication_result.py` | Dataclass | In-memory |
| `AuthorizationResult` | `core/pipeline/authorization_result.py` | Dataclass | In-memory |
| `ResourceGrant` | `core/pipeline/resource_grant.py` | Dataclass | In-memory |
| `SecurityContext` | `core/pipeline/security_context.py` | Dataclass | In-memory |
| `PermissionManager` | `core/permission/manager.py` | Singleton | In-memory |
| `Permission` | `core/permission/manager.py` | Dataclass | In-memory |
| `AuditEntry` | `core/permission/manager.py` | Dataclass | In-memory |
| `PermissionManager` (SDK) | `provider_sdk/permissions.py:104` | Singleton | In-memory |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | Pipeline identity stages, `get_identity_service()`, `PermissionManager.__init__()` |
| **Reader** | Pipeline stages (auth, authorization, resource access), provider router |
| **Writer** | Identity/resolved during pipeline execution, permission grants registered during bootstrap |
| **Destroyer** | Per-request identity destroyed with request. Permission manager lives forever. |
| **Persistence** | None. All identity and permission state is in-memory. |
| **Thread Safety** | Frozen dataclasses (identity) are thread-safe by immutability. Permission manager has no locks. |

### Issues

1. **Zero persistence** — user identities, role assignments, and permission grants are all in-memory. Lost on restart.
2. **Two PermissionManagers** — `core/permission/manager.py` and `provider_sdk/permissions.py`. Different permission sets, no synchronization.
3. **Audit logs are in-memory** — `PermissionManager._audit_log` is a list. Lost on crash. No forensic trail.
4. **`IdentityContext` is assembled from multiple sources** — auth, authorization, tenant resolution, resource access. If any stage fails, identity is incomplete.

---

## 13. Execution State

### State Objects

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `executor` singleton | `brain/executor/executor.py:187` | `Executor` instance | In-memory |
| `execute_tool_block()` | `core/tools/execution.py` | Module-level function | In-memory (uses nested closures for state) |
| `ActionResult` | `brain/executor/executor.py` | Dataclass | In-memory (result only) |
| `VerificationResult` | `brain/executor/verifier.py` | Dataclass | In-memory (result only) |
| `ToolBlock` | `core/tools/_constants.py` | Dataclass | In-memory (definition only) |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | Pipeline execution stage, agent execution, tool calls |
| **Reader** | Pipeline, agents, skill system |
| **Writer** | Tool functions write results |
| **Destroyer** | Result returned, then garbage collected |
| **Persistence** | None. Execution state is purely ephemeral. |
| **Thread Safety** | None. `execute_tool_block()` is a 3,024-line function with nested state (closures, dicts). No locks. |

### Issues

1. **3,024-line `execute_tool_block()`** — the largest function in the codebase. Contains nested closures, mutable dicts, and branch-heavy logic — all in a single function with no thread safety.
2. **Two executor systems** — `brain/executor/executor.py` (brain's Executor class) and `core/tools/execution.py` (tool dispatch). `brain/executor/` delegates to `core/tools/execution.py` for some operations.
3. **No execution history** — tool calls and their results are not recorded anywhere. No audit trail.
4. **`Verifier`** in brain has state (`verifier` singleton) but no persistence of verification results.

---

## 14. Checkpoint & Recovery State

### Duplicate Checkpoint Systems

#### System A: `CheckpointManager` (core)

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `CheckpointManager` | `core/checkpoint_manager.py` | Module-level singleton | JSON files in `~/.jarvis/checkpoints/` |
| Checkpoints | `~/.jarvis/checkpoints/*.json` | JSON files | One file per checkpoint |

#### System B: `ProjectPersistence` (brain)

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `ProjectPersistence` | `brain/persistence.py` | Instance | SQLite (`data/brain.db`) |
| `Checkpoint` | `brain/persistence.py` | Dataclass | Serialized in brain.db |
| `DecisionRecord` | `brain/persistence.py` | Dataclass | Serialized in brain.db |

### State Lifecycle

| Aspect | System A (core) | System B (brain) |
|--------|-----------------|-------------------|
| **Creator** | `CheckpointManager.save_checkpoint()` | `ProjectPersistence.save_checkpoint()` |
| **Reader** | `CheckpointManager.load_checkpoint()` | `ProjectPersistence.load_checkpoint()` |
| **Writer** | Pipeline execution, activity engine | Brain automation loop |
| **Destroyer** | Manual cleanup only | No destroy mechanism |
| **Persistence** | JSON files per checkpoint | SQLite table in brain.db |
| **Thread Safety** | Likely none | Uses `threading.Lock` |

### Issues

1. **Two redundant checkpoint systems** — different formats, different locations, different consumers. No single source of truth.
2. **`CheckpointManager` uses JSON files** — not transactional. A crash mid-write corrupts the checkpoint.
3. **`ProjectPersistence` stores checkpoints in brain.db** — but `brain.db` is also used by goals, memory, and persistence. Schema coupling.

---

## 15. Runtime State

### State Objects

| Object | Location | Type | Persistence |
|--------|----------|------|-------------|
| `RuntimeContext` | `core/runtime/context.py` | Dataclass | In-memory |
| `RuntimeRegistry` | `core/runtime/registry.py` | Singleton (lazy) | In-memory |
| `ExecutionRuntime` | `core/runtime/providers.py` | Dataclass | In-memory |
| `RuntimeServices` | `core/runtime/providers.py` | Dataclass | In-memory |

### State Lifecycle

| Aspect | Detail |
|--------|--------|
| **Creator** | `RuntimeRegistry.create()` or pipeline initialization |
| **Reader** | Pipeline stages, provider infrastructure |
| **Writer** | Runtime services are injected at creation time (immutable after) |
| **Destroyer** | Process termination |
| **Persistence** | None. All in-memory. |
| **Thread Safety** | Frozen dataclasses — immutable by design. |

### Issues

1. **RuntimeRegistry is not actually used** — it exists in `core/runtime/registry.py` but is never referenced in the dependency graph outside of its own module.
2. **`RuntimeContext` duplicates fields from `PipelineContext`** — both hold identity, scope, and grant information.
3. **No runtime health tracking** — the runtime has no state for uptime, request count, error rate, or resource usage (that lives in `monitors/` instead).

---

## 16. Global State Index

### Singleton Instances (65 total — see DEPENDENCY_GRAPH_AUDIT.md §5)

All 65 singletons are created at module load time or during bootstrap. Key categories:

| Category | Count | Examples |
|----------|-------|----------|
| Brain singletons | 15 | `unified_brain`, `reasoning_engine`, `executor`, `planner`, `memory_manager`, etc. |
| Core provider singletons | 8 | `provider_registry`, `provider_router`, `provider_memory`, `provider_budget` |
| Capability singletons | 4 | `capability_registry`, `capability_negotiator`, `capability_graph`, `composition_engine` |
| Memory singletons | 6 | `memory` (facade), `tiered_memory`, `mem0_memory`, `decision_memory`, etc. |
| Monitor singletons | 3 | `resource_monitor`, `service_health`, `alert_router` |
| SDK singletons | 5 | `lifecycle_manager`, `discovery_service`, `registration_pipeline`, etc. |
| Miscellaneous | 24 | `channel_controller`, `mcp_server`, `computer_agent`, `config`, `event_bus`, etc. |

### Module-Level Mutable State (see DEPENDENCY_GRAPH_AUDIT.md §6)

| Location | Variable | Type | Risk |
|----------|----------|------|------|
| `api/research_routes.py` | `_jobs: dict` | In-memory dict | Lost on restart, no thread safety |
| `api/website_routes.py` | `_jobs: dict` | In-memory dict | Lost on restart, no thread safety |
| `api/vision_routes.py` | `_tasks: dict` | In-memory dict | Lost on restart, no thread safety |
| `mcp/email_server.py` | `_ACCOUNT_CACHE: dict` | Module-level cache | Cached credentials, no expiry |
| `core/pipeline/base.py` | `STAGE_OWNERSHIP: dict` | Global config dict | Mutable, shared across all pipelines |
| `core/pipeline/stages/__init__.py` | `DEFAULT_STAGES: list` | Global pipeline config | Mutable list, any import can modify |
| `skills/*/main.py` (8 skills) | Various lists/dicts | Skill state | All in-memory, lost on restart |

---

## 17. Thread Safety Audit

### Thread-Safe (with explicit locks)

| State Object | Lock Type | Location |
|-------------|-----------|----------|
| `WorkflowStore` | `threading.Lock` | `core/workflow/storage.py` |
| `ActivityStore` | `threading.Lock` | `core/activity/storage.py` |
| `PlanStore` | `threading.Lock` | `core/planner/store.py` |
| `GoalManager` | `threading.Lock` | `brain/goals/goal_manager.py` |
| `ProjectPersistence` | `threading.Lock` | `brain/persistence.py` |
| `brain.memory` sub-providers | `threading.Lock` | `brain/memory/*.py` (4 providers) |
| `BrowserManager` | `asyncio.Lock` | `core/browser_manager.py` |
| `assistant/wake_word.py` | `threading.Lock` | Double-checked locking singleton |
| `assistant/tts.py` | `threading.Lock` | Double-checked locking singleton |
| `integrations/gmail/auth.py` | `threading.Lock` | Double-checked locking singleton |
| `FactStore` | `threading.Lock` | `memory/fact_store.py` (internal) |

### Not Thread-Safe (Risk Areas)

| State Object | Risk | Location |
|-------------|------|----------|
| `ConversationManager._sessions` | Concurrent access corrupts session data | `session.py` |
| `All API route `_jobs` dicts` | Concurrent requests lose job tracking | `api/*.py` |
| `execute_tool_block()` | 3,024-line function with nested state | `core/tools/execution.py` |
| `PermissionManager._audit_log` | Lost audit entries under concurrent access | `core/permission/manager.py` |
| `PermissionManager._grants` | Race conditions on grant/revoke | `core/permission/manager.py` |
| `Pipeline.DEFAULT_STAGES` | Stage list modification race | `core/pipeline/stages/__init__.py` |
| `STAGE_OWNERSHIP` dict | Ownership map modification race | `core/pipeline/base.py` |
| `DesktopController` | Concurrent desktop access conflicts | `core/desktop/controller.py` |
| `MemoryFacade` | Concurrent memory access (delegates) | `memory/memory_facade.py` |
| `TieredMemory` | Hot/warm/cold tier concurrency | `memory/tiered_memory.py` |
| `AgentRegistry` | Agent registration race | `core/agents/registry.py` |
| `ProviderMemory` | Concurrent provider score updates | `core/providers/memory.py` |
| `ProviderRouter` | Concurrent routing decisions | `core/providers/router.py` |

---

## 18. Persistence Map

### Database Files

| Database File | Location | Owner | Tables |
|--------------|----------|-------|--------|
| `data/workflow.db` | Project root | `WorkflowStore`, `PlanStore`, `ActivityStore` | workflows, plans, activities, nodes, edges |
| `data/brain.db` | Project root | `GoalManager`, `brain.MemoryManager` (4 providers), `ProjectPersistence` | goals, episodic, semantic, task, decision, checkpoints, decisions |
| `data/jarvis_memory.db` | Project root | `FactStore` | facts, embeddings |
| `ai_os_memory.db` | Project root | `core.memory.MemoryManager` | memory entries |
| `data/pc_agent.db` | Project root | `ComputerAgent` | snapshots, app state |
| `~/.jarvis/feedback.db` | User home | `FeedbackStore` | routing decisions, calibration, outcomes |
| `~/.jarvis/benchmark.db` | User home | `BenchmarkStore` | benchmark results |
| `~/.jarvis/orchestration.db` | User home | `OrchestrationStore` | orchestration plans |
| `~/.jarvis/provider_budgets/budgets.json` | User home | `ProviderBudgetManager` | budget state |
| `~/.jarvis/provider_memory/memory.json` | User home | `ProviderMemory` | provider scores |
| `~/.jarvis/decision_memory.json` | User home | `DecisionMemory` | decision records |
| `~/.jarvis/checkpoints/*.json` | User home | `CheckpointManager` | step checkpoints |
| `~/.jarvis/sessions/*.json` | User home | `SessionManager` | session dumps |
| `data/browser_sessions/*.json` | Project root | `BrowserManager` | browser session state |

### SQLite Databases: 8 separate files

| # | File | Tables | Schema Duplication |
|---|------|--------|-------------------|
| 1 | `data/workflow.db` | ~12 tables | `workflows`, `plans`, `activities` — related but in one file |
| 2 | `data/brain.db` | ~8 tables | Goals + Memory + Checkpoints — implicit coupling |
| 3 | `data/jarvis_memory.db` | ~3 tables | Standalone fact store |
| 4 | `ai_os_memory.db` | ~5 tables | Standalone core memory |
| 5 | `data/pc_agent.db` | ~3 tables | Standalone agent |
| 6 | `~/.jarvis/feedback.db` | ~4 tables | Standalone feedback |
| 7 | `~/.jarvis/benchmark.db` | ~3 tables | Standalone benchmarks |
| 8 | `~/.jarvis/orchestration.db` | ~3 tables | Standalone orchestration |

### JSON Persistence: 4 locations

| Path | Content | Format Risk |
|------|---------|-------------|
| `~/.jarvis/sessions/*.json` | Session message history | Not transactional |
| `~/.jarvis/checkpoints/*.json` | Execution checkpoints | Not transactional, crash-unsafe |
| `~/.jarvis/decision_memory.json` | Decision history | Not transactional |
| `~/.jarvis/provider_budgets/budgets.json` | Budget tracking | Not transactional |

---

## 19. Recovery Analysis

### What Can Be Recovered (by persistence mechanism)

| Mechanism | Recoverable State | Recovery Path |
|-----------|------------------|---------------|
| SQLite databases | Goals, memory, activities, workflows, plans, checkpoints, feedback, benchmarks | Full recovery — data survives crash |
| JSON files (sessions) | Conversation history | Read from JSON on startup — may be stale |
| JSON files (checkpoints) | Step-level execution state | Load checkpoint — but only if file was written completely |
| In-memory only | Pipeline context, runtime context, permissions, audit logs, agent registry, session state, execution state, desktop state, browser state (runtime) | **Lost entirely** on crash |

### What CANNOT Be Recovered

| State | Why | Impact |
|-------|-----|--------|
| In-flight pipeline execution | Context is in-memory only | Request lost on crash. User must retry. |
| Permission grants | `PermissionManager` is in-memory only | All grants reset on restart. System becomes permissive. |
| Audit log | In-memory list in `PermissionManager` | No forensic evidence after restart. |
| Rate limit state | In-memory counters | Rate limits reset on restart. Temporary DoS vulnerability window. |
| Active browser sessions | In-memory WebSocket/page handles | Leaked browser processes on crash. |
| Desktop safety zones | In-memory forbidden regions | Safety resets on restart. |
| Conversation manager state | In-memory sessions dict | All active sessions lost. Users must re-authenticate. |
| Provider router decisions | In-memory scoring cache | Provider selection history lost. Cold-start re-learning. |
| Provider memory state | JSON file (victim of partial writes) | JSON corruption risk — no atomic writes. |

### Existing Recovery Mechanisms

| Mechanism | Location | What It Recovers |
|-----------|----------|-----------------|
| `ResumeEngine` | `core/activity/resume.py` | Workflow/activity state from ActivityStore |
| `ReplayAssembler` | `core/activity/replay.py` | Reconstructs execution traces from ActivityStore |
| `CheckpointManager.load_checkpoint()` | `core/checkpoint_manager.py` | Loads saved execution step state |
| `ProjectPersistence.load_checkpoint()` | `brain/persistence.py` | Loads brain-level checkpoint |
| `SetupEngine.resume_needed()` | `core/setup/engine.py` | Detects interrupted first-run setup |

---

## 20. Findings & Recommendations

### Critical Findings

| # | Finding | Impact |
|---|---------|--------|
| F1 | **3 concurrent memory systems** (memory/, brain/memory/, core/memory*) with 4 separate databases | Data fragmentation. Queries return incomplete results. |
| F2 | **2 checkpoint systems** (JSON + SQLite) with no coordination | Recovery paths diverge. No single "resume from crash" point. |
| F3 | **65 singletons with no lifecycle management** | Implicit initialization order. No teardown. Impossible to test in isolation. |
| F4 | **Zero persistence for identity/permissions** | All grants and roles lost on restart. |
| F5 | **In-memory audit log** | No forensic capability. Compliance violation. |
| F6 | **`execute_tool_block()` is 3,024 lines with no thread safety** | Single worst point of failure in the system. |
| F7 | **8+ separate SQLite databases** | Unnecessary I/O overhead. No cross-database queries possible. |

### High-Priority Recommendations

| # | Recommendation | Target |
|---|---------------|--------|
| R1 | **Consolidate to 1-2 databases** — merge workflow.db + brain.db + jarvis_memory.db into a single schema. Keep user-home databases (~/.jarvis/*.db) as an optional overlay. | F7 |
| R2 | **Unify memory systems** — keep `memory/` facade, deprecate `brain/memory/` and `core/memory*`. Migrate data to the facade's backing store. | F1 |
| R3 | **Unify checkpoint systems** — keep `core/checkpoint_manager.py` (SQLite), remove JSON-based `CheckpointManager` + `ProjectPersistence` checkpoint features. | F2 |
| R4 | **Add persistence to identity/permissions** — store grants, roles, and audit logs in SQLite. At minimum, make the audit log durable. | F4, F5 |
| R5 | **Add lifecycle management** — create `AppContext.initialize()` and `AppContext.shutdown()` that manages singleton creation/destruction order. | F3 |
| R6 | **Break up `execute_tool_block()`** — extract each tool dispatch path into its own function. Add thread safety (or document async-only requirement). | F6 |

### Medium-Priority Recommendations

| # | Recommendation | Target |
|---|---------------|--------|
| R7 | **Add thread safety to all API `_jobs` dicts** — use `asyncio.Lock` or `dict` + `Lock` wrapper. | API routes |
| R8 | **Add session expiry** — TTL on `ConversationManager._sessions` entries. | Conversation state |
| R9 | **Add transactional JSON writes** — write to temp file, then atomic rename. All JSON persistence paths. | Checkpoints, decisions, sessions |
| R10 | **Consolidate `ConversationManager` and `SessionManager`** — single session system with SQLite backing. | Duplicate session systems |
| R11 | **Consolidate `PermissionManager`** (core + SDK) — single permission registry. | Duplicate permission systems |
| R12 | **Add thread safety to `PermissionManager`** — at minimum, `threading.Lock` on `_grants` and `_audit_log`. | Permission state |
| R13 | **Remove shared `data/workflow.db` coupling** — give WorkflowStore, PlanStore, and ActivityStore separate tables with clear ownership. | Activity state |

---

## Appendix A: State Ownership Matrix

| State Domain | Primary Owner | Secondary Owner | Deprecated Owner |
|-------------|---------------|-----------------|-----------------|
| Conversation | `core/session_db.py` | `session.py` | — |
| Pipeline | `core/pipeline/context.py` | — | — |
| Planner | `core/planner/store.py` | `brain/planner/planner.py` | — |
| Workflow | `core/workflow/storage.py` | `core/activity/` | — |
| Agent | `core/agents/registry.py` | `brain/UnifiedBrain.py` | `core/agents/_legacy/` |
| Browser | `core/browser_manager.py` | `automation/pc_automation.py` | — |
| Desktop | `core/desktop/controller.py` | — | — |
| Memory | `memory/memory_facade.py` | `brain/memory/memory_manager.py` | `core/memory*.py` |
| Activity | `core/activity/storage.py` | — | — |
| Goal | `brain/goals/goal_manager.py` | `core/plan_manager.py` | — |
| Identity | `core/identity/models.py` (transient) | — | — |
| Permission | `core/permission/manager.py` | `provider_sdk/permissions.py` | — |
| Execution | `core/tools/execution.py` | `brain/executor/executor.py` | — |
| Checkpoint | `core/checkpoint_manager.py` | `brain/persistence.py` | — |
| Runtime | `core/runtime/registry.py` (unused) | — | — |

---

## Appendix B: State Lifecycle Summary

| Duration | State Objects | Count |
|----------|--------------|-------|
| Per-request | PipelineContext, Request, Response, IdentityContext, SecurityContext, Outcome, Observation, RuntimeContext | ~10 |
| Per-session | ConversationManager._sessions, Session, ProjectContext | ~3 |
| Per-goal/plan | TaskGraph, Plan, Goal, GoalManager entries | ~5 |
| Per-workflow | WorkflowStore entries, ExecutionNode state | ~3 |
| Process-lifetime | All 65 singletons, all module-level state, all in-memory caches | ~100+ |

---

*End of STATE_ARCHITECTURE_AUDIT.md — 14 state domains mapped, 65+ singletons listed, 8 SQLite databases cataloged, 7 critical findings, 13 recommendations.*
