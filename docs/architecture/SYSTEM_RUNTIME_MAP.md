# System Runtime Map — Phase 4 (Document 13)

> **Purpose:** Master runtime ownership map. Every component answers Owner, Creates, Reads, Writes, Publishes, Consumes, Stores, Memory, Thread, Lifetime, Shutdown, Recovery. This is the canonical "system map" that ties together all 12 prior audits.
>
> **Prerequisites:** All 12 architecture audits, TARGET_ARCHITECTURE.md, CODE_OWNERSHIP_AUDIT.md.
>
> **Rule:** Before changing any subsystem, consult this map. If the subsystem's Owner or Lifetime is unclear, do not change it.

---

## Table of Contents

1. [Legend](#legend)
2. [Entry Points & Transport](#2-entry-points--transport)
3. [Pipeline & Request Processing](#3-pipeline--request-processing)
4. [Planner](#4-planner)
5. [Workflow Engine](#5-workflow-engine)
6. [Scheduler](#6-scheduler)
7. [Execution Engine (Tool Dispatch)](#7-execution-engine-tool-dispatch)
8. [Memory & Knowledge](#8-memory--knowledge)
9. [Event Bus](#9-event-bus)
10. [Identity & Permissions](#10-identity--permissions)
11. [Configuration](#11-configuration)
12. [Storage & Persistence](#12-storage--persistence)
13. [Brain & Autonomous Systems](#13-brain--autonomous-systems)
14. [Legacy Subsystems (Deprecated)](#14-legacy-subsystems-deprecated)
15. [Request-Lifecycle Flow Diagram](#15-request-lifecycle-flow-diagram)
16. [Recovery Matrix](#16-recovery-matrix)
17. [Shutdown Sequence](#17-shutdown-sequence)

---

## 1. Legend

### Column Definitions

| Column | Meaning |
|--------|---------|
| **Owner** | Team/individual responsible. From CODE_OWNERSHIP_AUDIT.md. |
| **Creates** | State objects, dataclasses, or persistent records this component introduces. |
| **Reads** | State objects, databases, or configuration this component queries. |
| **Writes** | State objects, databases, or files this component mutates. |
| **Publishes** | Event types this component emits. |
| **Consumes** | Event types or inputs this component subscribes to. |
| **Stores** | Database files or storage backends this component uses persistently. |
| **Memory** | In-memory state (singletons, caches, module-level dicts). |
| **Thread** | Thread-safety mechanism or lack thereof. |
| **Lifetime** | How long the component and its state survive. |
| **Shutdown** | How the component stops cleanly. |
| **Recovery** | What state survives a crash and how it is restored. |

### Owner Abbreviations

| Abbreviation | Owner |
|---|---|
| **Core** | Core Platform |
| **Security** | Security team |
| **Memory** | Memory team |
| **Planner** | Planner team |
| **Workflow** | Workflow team |
| **Execution** | Execution team |
| **Brain** | Brain/Autonomous team |
| **MCP** | MCP/Integrations team |
| **Providers** | Provider/LLM team |

### Status Abbreviations

| Abbreviation | Meaning |
|---|---|
| — | Current/active (no deprecation planned) |
| ⚠ | Deprecated — no new changes, migration in progress |
| 🗑 | Scheduled for removal (see DELETION_MIGRATION_TRACKER.md) |
| ✦ | Target-architecture component (not yet implemented) |

---

## 2. Entry Points & Transport

### 2.1 HTTP Server (FastAPI)

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | `Request` dataclass from HTTP request, `Response` dataclass |
| **Reads** | Config, auth headers, route parameters |
| **Writes** | HTTP response |
| **Publishes** | — |
| **Consumes** | HTTP requests on routes |
| **Stores** | — |
| **Memory** | FastAPI app instance, router registrations |
| **Thread** | Async per-request; no shared mutable state |
| **Lifetime** | Process-lifetime |
| **Shutdown** | FastAPI shutdown event → close DB connections, stop scheduler |
| **Recovery** | None (stateless) |

### 2.2 WebSocket Manager

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | WebSocket connections, SSE events |
| **Reads** | Pipeline `Response` |
| **Writes** | Outbound WebSocket messages, SSE stream |
| **Publishes** | SSE events from StateGraph (`phase_change`, `paused`, `error`, `[DONE]`) |
| **Consumes** | Pipeline `Response`, StateGraph async generator |
| **Stores** | — |
| **Memory** | Active connection pool (`_connections: dict`) — no thread safety |
| **Thread** | Not thread-safe (`_connections` dict without locks) |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close all connections |
| **Recovery** | None — in-flight connections lost on crash |

### 2.3 MCP Servers

| Column | Detail |
|--------|--------|
| **Owner** | MCP |
| **Creates** | MCP tool requests |
| **Reads** | Pipeline `Request`, tool definitions |
| **Writes** | MCP responses |
| **Publishes** | MCP tool results |
| **Consumes** | MCP client requests |
| **Stores** | — |
| **Memory** | Server instances |
| **Thread** | Async |
| **Lifetime** | Process-lifetime |
| **Shutdown** | MCP server shutdown |
| **Recovery** | None |

### 2.4 CLI / Daemon

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | `Request` from CLI args |
| **Reads** | Config, stdin |
| **Writes** | stdout, stderr |
| **Publishes** | — |
| **Consumes** | CLI commands |
| **Stores** | — |
| **Memory** | `ConversationManager._sessions` (module-level dict) |
| **Thread** | Not thread-safe (`_sessions` dict without locks) |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Process exit |
| **Recovery** | None |

---

## 3. Pipeline & Request Processing

### 3.1 Pipeline Entry (`core/pipeline/pipeline.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | `PipelineContext`, iterates 19 stages |
| **Reads** | `Request`, all stage results from context |
| **Writes** | `PipelineContext` (aggregates all stage writes), `ArchitectureMetrics` |
| **Publishes** | — (individual stages publish) |
| **Consumes** | `Request` from transport adapters |
| **Stores** | — |
| **Memory** | `Pipeline._stages` list, `_hooks` registry |
| **Thread** | Async per-request; `Pipeline` singleton but stage list is effectively immutable after init |
| **Lifetime** | Per-request (context), process-lifetime (pipeline singleton) |
| **Shutdown** | None needed |
| **Recovery** | None — per-request context lost on crash |

### 3.2 Pipeline Stages (19 stages)

| Stage | File | Owner | Creates | Reads | Writes |
|-------|------|-------|---------|-------|--------|
| 1. Receive | `receive.py` | Core | `parsed_request` | Raw transport input | `context.parsed_request` |
| 2. Load Context | `load_context.py` | Core | `metadata`, `session_id`, `user_id` | Session store, config | `context.metadata`, `context.session_id`, `context.user_id` |
| 3. Authentication | `auth.py` | Security | `AuthenticationResult` | AuthManager, IdentityService | `context.identity` |
| 4. Tenant Resolution | `tenant_resolution.py` | Core | `tenant_id` | Identity store | `context.tenant_resolution` |
| 5. Authorization | `authorization.py` | Security | `AuthorizationResult` | PolicyEngine | `context.authz_result` |
| 6. Resource Access | `resource_access.py` | Security | `ResourceGrant` | Resource store | `context.resource_grant` |
| 7. Rate Limit | `rate_limit.py` | Core | Rate-limit check | AuthRateLimiter | Context pass-through (currently no-op) |
| 8. Intent | `intent.py` | Core | `classification` | None (keyword-based) | `context.classification` |
| 9. Context Retrieval | `context_retrieval.py` | Memory | `retrieved_context` | MemoryFacade, PreferenceProfile | `context.retrieved_context` |
| 10. Reasoner | `reasoner.py` | Core | `reasoning_assessment` | Config, context | `context.reasoning_assessment` |
| 11. Planner | `planner.py` | Planner | `plan` (SubGoal tree) | Planner (CorePlanner), PlanStore | `context.plan` |
| 12. Plan Validator | `plan_validator.py` | Planner | `plan_validated` flag | Plan schema | `context.plan_validated` |
| 13. Capability Selection | `capability_selection.py` | Core | `selected_capabilities` | CapabilityRegistry (currently hardcoded dict) | `context.selected_capabilities` |
| 14. Execution | `execution.py` | Execution | `execution_state`, `outcome`, `observations` | LLM providers, tools | `context.execution_state`, `context.outcome`, `context.observations` |
| 15. Verification | `verification.py` | Core | `verdicts` list | Outcome | `context.verification_result` |
| 16. Epistemic Tagging | `epistemic_tagging.py` | Core | `epistemic_tags` | Outcome, verdicts | `context.epistemic_tags` |
| 17. Memory | `memory.py` | Memory | `StoreDecision`, `memory_refs` | MemoryFacade | `context.store_decision`, `context.memory_refs` |
| 18. Format | `formatting.py` | Core | `formatted_response` | Entire context | `context.formatted_response` |

**Shared properties for all stages:**

| Property | Detail |
|----------|--------|
| **Publishes** | Via Observation Hub after execution (stage produces observation → hub → EventBus) |
| **Consumes** | `PipelineContext` (read prior stage fields, write own fields) |
| **Stores** | — |
| **Memory** | None per-stage; stage instances are effectively stateless |
| **Thread** | Async per-request; `STAGE_OWNERSHIP` dict is global mutable state |
| **Lifetime** | Per-request |
| **Shutdown** | Pipeline.cancel() flag checked between stages |
| **Recovery** | None |

---

## 4. Planner

### 4.1 CorePlanner (`core/planner/`) — Reference Implementation

| Column | Detail |
|--------|--------|
| **Owner** | Planner |
| **Creates** | `Plan` (SubGoal tree), plan evidence, plan health assessment |
| **Reads** | PlanStore, KnowledgeStore, FactStore, context |
| **Writes** | PlanStore (SQLite), PlanEvidenceEngine, PlanHealthEngine |
| **Publishes** | — (no events directly) |
| **Consumes** | Goal string, context from pipeline |
| **Stores** | `data/workflow.db` (shares with WorkflowStore, ActivityStore) → **target:** `data/planner.db` |
| **Memory** | `PlanEvidenceEngine` (in-memory), `PlanHealthEngine` (in-memory), `GoalDecomposer` (state machine), `ComparativeScorer`, `StrategyGenerator` |
| **Thread** | `PlanStore` uses `threading.Lock`; in-memory engines have no thread safety |
| **Lifetime** | Process-lifetime (engines), per-request (plan context) |
| **Shutdown** | None needed |
| **Recovery** | PlanStore persists plans to SQLite → survive crash. In-memory engine state (evidence, health) is lost. |

### 4.2 Pipeline PlannerStage (`core/pipeline/stages/planner.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Planner |
| **Creates** | Plan dict in `PipelineContext` |
| **Reads** | Goal from classification, CorePlanner protocol |
| **Writes** | `context.plan` |
| **Publishes** | — |
| **Consumes** | Intent classification |
| **Stores** | Delegates to PlanStore |
| **Memory** | None |
| **Thread** | Async per-request |
| **Lifetime** | Per-request |
| **Shutdown** | None |
| **Recovery** | None |

### 4.3 Brain Planner (`brain/planner/`) ⚠ Deprecated

| Column | Detail |
|--------|--------|
| **Owner** | Planner (deprecating) |
| **Creates** | Fixed 3-node TaskGraph DAG |
| **Reads** | Goal from UnifiedBrain, LLM |
| **Writes** | `TaskGraph` (in-memory) |
| **Publishes** | — |
| **Consumes** | Goal string |
| **Stores** | None (in-memory only) |
| **Memory** | `planner` singleton, `TaskGraph`, `TaskNode` instances |
| **Thread** | None |
| **Lifetime** | Per-goal |
| **Shutdown** | Plan completion or cancellation |
| **Recovery** | None (entirely in-memory) |

### 4.4 UnifiedStore ✦ Target Architecture

| Column | Detail |
|--------|--------|
| **Owner** | Planner |
| **Creates** | Merged `goals_plans` table, unified status enum |
| **Reads** | All goal/plan data |
| **Writes** | `goals_plans`, `plan_outcomes` tables |
| **Publishes** | `goal.created`, `goal.updated`, `goal.completed` (target) |
| **Consumes** | Planner protocol, GoalManager, PlanStore data sources |
| **Stores** | `data/planner.db` (SQLite) |
| **Memory** | In-memory cache (optional target) |
| **Thread** | `threading.Lock` (target) |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close DB connection |
| **Recovery** | Full SQLite persistence |

---

## 5. Workflow Engine

### 5.1 WorkflowEngine (`core/workflow/engine.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Workflow |
| **Creates** | `WorkflowInstance`, `StepDefinition`, workflow events (12 types), idempotency keys |
| **Reads** | WorkflowStore, StepDefinition list |
| **Writes** | WorkflowStore (SQLite), ActivityRecorder (goal, tasks, results, completion, failure) |
| **Publishes** | 12 SQLite append events (NOT on EventBus): `WORKFLOW_STARTED`, `STEP_STARTED`, `STEP_COMPLETED`, `STEP_FAILED`, `WORKFLOW_COMPLETED`, `WORKFLOW_FAILED`, `WORKFLOW_CANCELLED`, `COMPENSATION_STARTED`, `COMPENSATION_STEP_STARTED`, `COMPENSATION_STEP_COMPLETED`, `COMPENSATION_STEP_FAILED`, `WORKFLOW_COMPENSATED` |
| **Consumes** | `start_workflow(type, steps, ...)` from tools, agents, API |
| **Stores** | `data/workflow.db` (5 tables: workflows, workflow_steps, workflow_events, workflow_compensation, workflow_learning) |
| **Memory** | `WorkflowEngine._running: dict` (in-memory active workflow tracker) |
| **Thread** | `WorkflowStore` uses `threading.Lock`; engine is async-safe |
| **Lifetime** | Process-lifetime (engine), per-workflow (instance) |
| **Shutdown** | Complete/cancel all running workflows; clear `_running` dict |
| **Recovery** | Full SQLite persistence for stored workflows. In-memory `_running` dict lost on crash → WorkflowStore can reload active workflows. |

### 5.2 WorkflowStore (`core/workflow/storage.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Workflow |
| **Creates** | Workflow and step records in SQLite |
| **Reads** | `data/workflow.db` |
| **Writes** | Workflow instances, step state, events, compensation records |
| **Publishes** | — |
| **Consumes** | WorkflowEngine CRUD calls |
| **Stores** | `data/workflow.db` |
| **Memory** | In-memory SQLite connection pool |
| **Thread** | `threading.Lock` |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close SQLite connection |
| **Recovery** | Full (SQLite WAL, transactional) |

### 5.3 ExecutionTracker (`core/workflow/tracker.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Workflow |
| **Creates** | `ExecutionNode` instances (in-memory DAG) |
| **Reads** | WorkflowStore |
| **Writes** | `ExecutionGraph` (in-memory, **not persisted** currently) |
| **Publishes** | — |
| **Consumes** | WorkflowEngine step outcomes |
| **Stores** | None (in-memory) → **target:** persist execution graph |
| **Memory** | `ExecutionGraph` DAG entirely in-memory |
| **Thread** | Not explicitly thread-safe |
| **Lifetime** | Per-workflow |
| **Shutdown** | Discarded on workflow completion |
| **Recovery** | **None** — execution graph is lost on crash (target: persist to SQLite) |

---

## 6. Scheduler

### 6.1 Scheduler (`core/scheduler/scheduler.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | Tick cycle, worker tasks (asyncio), activity execution |
| **Reads** | ActivityQueue, ActivityGraph, SchedulerRegistry |
| **Writes** | Queue state, worker state, ActivityIntelligence (calibration data) |
| **Publishes** | `_fire_tick_callbacks()` (synchronous callbacks, NOT EventBus) |
| **Consumes** | Scheduler.start() at boot, tick interval |
| **Stores** | `data/workflow.db` (via ActivityStore) |
| **Memory** | `_state` (RUNNING/STOPPED/PAUSED), `_task`, `_workers` dict, queue |
| **Thread** | Async; uses `asyncio.Lock` for queue |
| **Lifetime** | Process-lifetime |
| **Shutdown** | `Scheduler.stop()` → set `_state = STOPPED`, cancel `_task`, await worker completion |
| **Recovery** | Work queue survives in SQLite (ActivityStore). In-memory worker state lost. |

### 6.2 Scheduler Executors (`core/scheduler/executors.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | Specific executor results (research, build, repair, email, benchmark, opportunity, default, pipeline) |
| **Reads** | Activity metadata, goals |
| **Writes** | Results to queue |
| **Publishes** | — |
| **Consumes** | `_resolve_executor()` by node_type |
| **Stores** | — |
| **Memory** | None (each executor is a function, stateless) |
| **Thread** | Async-safe |
| **Lifetime** | Per-activity (executor runs once per activity) |
| **Shutdown** | None |
| **Recovery** | None |

### 6.3 ActivityIntelligence (`core/scheduler/intelligence.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | Prediction/calibration data for activity outcomes |
| **Reads** | Activity history |
| **Writes** | Calibration records |
| **Publishes** | — |
| **Consumes** | Activity results |
| **Stores** | `data/workflow.db` |
| **Memory** | In-memory prediction cache |
| **Thread** | Not explicitly thread-safe |
| **Lifetime** | Process-lifetime |
| **Shutdown** | None |
| **Recovery** | SQLite persistence for calibration data |

---

## 7. Execution Engine (Tool Dispatch)

### 7.1 Central Tool Dispatcher (`core/tools/execution.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Execution |
| **Creates** | `ToolBlock`, `ToolResult`, MCP requests, native tool calls, sub-agent spawns |
| **Reads** | Tool definitions, tool_factory, security context |
| **Writes** | Tool results, sandbox output |
| **Publishes** | — (no events; called synchronously) |
| **Consumes** | Tool requests from WorkflowEngine, PlannerStateMachine, Scheduler, AgentLauncher, AgentState |
| **Stores** | — |
| **Memory** | Nested closures, mutable dicts within the 3024-line function |
| **Thread** | **No thread safety** — 3024-line monolith with nested mutable state |
| **Lifetime** | Per-call (function invocation) |
| **Shutdown** | None |
| **Recovery** | None (stateless per-call) |

### 7.2 Tool Factory (`core/tools/tool_factory.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Execution |
| **Creates** | Tool instances |
| **Reads** | Tool module definitions |
| **Writes** | `_tools` dict (global cache), `_initialized` flag |
| **Publishes** | — |
| **Consumes** | `create()` calls |
| **Stores** | — |
| **Memory** | Module-level `_initialized: bool`, `_tools: dict` |
| **Thread** | **Thread-hostile** — `_initialized` and `_tools` are module-level mutable globals without locks |
| **Lifetime** | Process-lifetime |
| **Shutdown** | None (tools are never explicitly cleaned up) |
| **Recovery** | None |

### 7.3 StateGraph (`core/graph/graph.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Execution |
| **Creates** | SSE event stream (phase_change, paused, custom, error, [DONE]) |
| **Reads** | `AgentState` |
| **Writes** | `AgentState` (mutated by node functions) |
| **Publishes** | SSE events via async generator → WebSocket → UI |
| **Consumes** | `AgentState` from agent loop |
| **Stores** | — |
| **Memory** | `AgentState` in-memory (not persisted) |
| **Thread** | Async-only (single-threaded DAG walk) |
| **Lifetime** | Per-agent-loop |
| **Shutdown** | DAG reaches `__end__` or `__pause__` |
| **Recovery** | None |

### 7.4 ParallelAgentExecutor (`core/agents/parallel_executor.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Execution |
| **Creates** | Parallel agent task results |
| **Reads** | Agent dependency graph |
| **Writes** | Node completion status (in-memory) |
| **Publishes** | Optional: `emit_events=False` by default |
| **Consumes** | Execution plan from PlannerStateMachine |
| **Stores** | — |
| **Memory** | In-memory graph state (pending/ready/completed nodes) |
| **Thread** | Async-safe (asyncio task management) |
| **Lifetime** | Per-plan-execution |
| **Shutdown** | All tasks complete or fail |
| **Recovery** | None |

### 7.5 AgentGraph (`core/agents/agent_graph.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Execution |
| **Creates** | Agent runtime loop, calls StateGraph |
| **Reads** | Agent definitions, tool registry |
| **Writes** | Agent state via node functions |
| **Publishes** | — |
| **Consumes** | Requests from pipeline or brain |
| **Stores** | — |
| **Memory** | Agent runtime, `AgentOrchestrator` singleton |
| **Thread** | Not explicitly thread-safe |
| **Lifetime** | Process-lifetime (orchestrator), per-request (runtime) |
| **Shutdown** | Agent loop completion |
| **Recovery** | None |

### 7.6 Controller Loop (`core/control_loop.py`) ⚠

| Column | Detail |
|--------|--------|
| **Owner** | Execution |
| **Creates** | `ProjectState`, build plan, task list, validation results |
| **Reads** | Template analyzer, pattern_failure_memory, QualityScorer |
| **Writes** | `pattern_failure_memory.py` (JSON), `checkpoint_manager.py`, `plan_evolution()` |
| **Publishes** | **None** — does not use EventBus |
| **Consumes** | `do_build()` from agent_tools.py or CLI |
| **Stores** | JSON files (pattern memory, checkpoints) |
| **Memory** | `ProjectState` (per-build), loop state (in-memory) |
| **Thread** | Async sub-tasks; master loop is synchronous |
| **Lifetime** | Per-build-project |
| **Shutdown** | Loop completes (COMPLETE or FAILED) |
| **Recovery** | Partial via checkpoint_manager (JSON files) |

---

## 8. Memory & Knowledge

### 8.1 MemoryFacade (`memory/memory_facade.py`) — Unified API

| Column | Detail |
|--------|--------|
| **Owner** | Memory |
| **Creates** | Memory store/recall operations delegated to backends |
| **Reads** | All backends (TieredMemory, Mem0Adapter, FactStore, EmbeddingMemory, DecisionMemory) |
| **Writes** | All backends |
| **Publishes** | — |
| **Consumes** | `store()`, `recall()`, `search()`, `delete()` from pipeline, API, brain |
| **Stores** | Delegates to backends |
| **Memory** | Singleton reference (`memory`), lazy backend imports |
| **Thread** | Not consistently thread-safe — delegates to backends without coordination |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close backend connections |
| **Recovery** | Full via SQLite backends; hot cache (TieredMemory) is lost |

### 8.2 TieredMemory (`memory/tiered_memory.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Memory |
| **Creates** | Hot/warm/cold memory tiers |
| **Reads** | Mem0 (warm), Qdrant/vector (cold) |
| **Writes** | Hot tier (in-memory, max 10 entries), warm tier (Mem0), cold tier (vector) |
| **Publishes** | — |
| **Consumes** | `remember()`, `recall()` calls |
| **Stores** | Mem0 (external), vector DB (Chroma/Qdrant) |
| **Memory** | Hot cache dict (max 10 entries) — **no thread safety** |
| **Thread** | **No thread safety on hot path** (target: add Lock) |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Flush hot cache to warm tier |
| **Recovery** | Warm/cold tiers survive crash; hot cache lost |

### 8.3 FactStore (`memory/fact_store.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Memory |
| **Creates** | Fact records in SQLite |
| **Reads** | `data/jarvis_memory.db` |
| **Writes** | Facts, embeddings |
| **Publishes** | — |
| **Consumes** | `store_facts()`, `query_facts()` |
| **Stores** | `data/jarvis_memory.db` |
| **Memory** | `get_fact_store()` singleton, internal connection cache |
| **Thread** | `threading.Lock` (internal) |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close SQLite connection |
| **Recovery** | Full SQLite persistence |

### 8.4 Brain Memory (`brain/memory/`) ⚠ Deprecated

| Column | Detail |
|--------|--------|
| **Owner** | Memory (deprecating) |
| **Creates** | EpisodicMemory, SemanticMemory, TaskMemory, DecisionMemory records |
| **Reads** | `data/brain.db` |
| **Writes** | Brain memory stores |
| **Publishes** | — |
| **Consumes** | UnifiedBrain, AutomationLoop, LearningEngine |
| **Stores** | `data/brain.db` |
| **Memory** | `memory_manager` singleton (brain/memory/memory_manager.py:144) |
| **Thread** | `threading.Lock` per sub-provider (4 providers) |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close brain.db connection |
| **Recovery** | Full SQLite persistence |

### 8.5 KnowledgeStore (`core/long_term_memory/`)

| Column | Detail |
|--------|--------|
| **Owner** | Memory |
| **Creates** | Knowledge records, consolidations |
| **Reads** | `data/workflow.db` |
| **Writes** | Knowledge, extracts, consolidations |
| **Publishes** | — |
| **Consumes** | Planner, Strategy |
| **Stores** | `data/workflow.db` (shares with WorkflowStore, PlanStore) |
| **Memory** | `Consolidator`, `Extractor` instances |
| **Thread** | Not explicitly thread-safe |
| **Lifetime** | Process-lifetime |
| **Shutdown** | None |
| **Recovery** | SQLite persistence |

---

## 9. Event Bus

### 9.1 Canonical EventBus (`core/event_bus.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | Event subscription/dispatch system |
| **Reads** | Subscriber registry |
| **Writes** | None (dispatches to subscribers) |
| **Publishes** | ~79 event types across namespaces: `system.*`, `plugin.{id}.*` |
| **Consumes** | `publish()` calls from all layers |
| **Stores** | — |
| **Memory** | `_subscribers: dict[str, list[callable]]` — module-level singleton |
| **Thread** | Sync dispatch — subscriber exception crashes the emit |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Clear subscriber registry |
| **Recovery** | None (in-memory subscriptions lost on crash — subscribers must re-register) |

### 9.2 Brain EventBus (`brain/`) ⚠

| Column | Detail |
|--------|--------|
| **Owner** | Brain |
| **Creates** | Separate brain event dispatch system |
| **Reads** | Brain subscriber registry |
| **Writes** | — |
| **Publishes** | 8 event types: `GoalCreated`, `GoalCompleted`, `GoalFailed`, `TaskCompleted`, `TaskFailed`, `MemoryStored`, `VerificationPassed`, `VerificationFailed` |
| **Consumes** | Brain subsystem publishers |
| **Stores** | — |
| **Memory** | Brain-internal subscriber registry |
| **Thread** | Not known |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Clear brain subscribers |
| **Recovery** | None |

### 9.3 WorkflowEngine Event Log (SQLite) ⚠

| Column | Detail |
|--------|--------|
| **Owner** | Workflow |
| **Creates** | SQLite event records (12 types) |
| **Reads** | `data/workflow.db` (workflow_events table) |
| **Writes** | Append-only event log |
| **Publishes** | **Not broadcast** — written to SQLite only |
| **Consumes** | WorkflowEngine step lifecycle |
| **Stores** | `data/workflow.db` |
| **Memory** | None |
| **Thread** | Thread-safe via WorkflowStore lock |
| **Lifetime** | Per-workflow-step |
| **Shutdown** | None |
| **Recovery** | Full SQLite persistence |

---

## 10. Identity & Permissions

### 10.1 IdentityService (`core/identity/service.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Security |
| **Creates** | `IdentityContext`, `Identity`, `AuthenticationState` |
| **Reads** | AuthManager, PolicyEngine |
| **Writes** | `IdentityContext` (frozen, per-request) |
| **Publishes** | — |
| **Consumes** | Request from pipeline |
| **Stores** | — |
| **Memory** | `get_identity_service()` singleton |
| **Thread** | Thread-safe via frozen dataclasses |
| **Lifetime** | Process-lifetime (service), per-request (context) |
| **Shutdown** | None |
| **Recovery** | None |

### 10.2 AuthManager (`core/auth.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Security |
| **Creates** | User records, session tokens, TOTP secrets |
| **Reads** | `data/auth.json`, `data/sessions.json` → **target:** SQLite |
| **Writes** | Auth JSON, session JSON, bcrypt hashes |
| **Publishes** | — |
| **Consumes** | Login, logout, validate requests |
| **Stores** | `data/auth.json`, `data/sessions.json` (JSON not transactional → **target:** SQLite) |
| **Memory** | In-memory dict for active sessions (alongside JSON) |
| **Thread** | No explicit thread safety |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Flush sessions to JSON |
| **Recovery** | JSON files survive crash but may be corrupt (non-transactional writes) |

### 10.3 PolicyEngine (`core/authz/`)

| Column | Detail |
|--------|--------|
| **Owner** | Security |
| **Creates** | RBAC evaluation results |
| **Reads** | YAML policy files |
| **Writes** | — (read-only evaluator) |
| **Publishes** | — |
| **Consumes** | Authorization requests |
| **Stores** | YAML config files |
| **Memory** | Loaded YAML policies (cached) |
| **Thread** | Read-only, effectively thread-safe |
| **Lifetime** | Process-lifetime |
| **Shutdown** | None |
| **Recovery** | YAML files survive crash |

### 10.4 PermissionManager (`core/permission/manager.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Security |
| **Creates** | Permission grants, audit log entries |
| **Reads** | Permission registry |
| **Writes** | `_grants` dict, `_audit_log` list |
| **Publishes** | — |
| **Consumes** | Permission checks from execution |
| **Stores** | — (entirely in-memory) |
| **Memory** | `PermissionManager` singleton, `_grants: dict`, `_audit_log: list` |
| **Thread** | **No thread safety** — concurrent grant/revoke races |
| **Lifetime** | Process-lifetime |
| **Shutdown** | None (all in-memory state lost) |
| **Recovery** | **None** — zero persistence. All grants and audit logs lost on restart. |

### 10.5 Authorizer Facade ✦ Target Architecture

| Column | Detail |
|--------|--------|
| **Owner** | Security |
| **Creates** | `AuthorizationResult` |
| **Reads** | PolicyEngine, PermissionManager, AuthManager |
| **Writes** | Authorization decision |
| **Publishes** | — |
| **Consumes** | `authorize(user, scope, resource)` |
| **Stores** | — |
| **Memory** | Authorization cache (per-request, target) |
| **Thread** | Target: thread-safe via frozen output |
| **Lifetime** | Process-lifetime (facade), per-request (result) |
| **Shutdown** | None |
| **Recovery** | None |

---

## 11. Configuration

### 11.1 ConfigRegistry (`core/config_registry.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | Config resolution chain |
| **Reads** | Environment variables (`_scan_env_vars()` at import), config.yaml |
| **Writes** | — (read-only resolution) |
| **Publishes** | `config.changed` (target), `config.reloaded` (target) |
| **Consumes** | `get(key, default)` calls |
| **Stores** | config.yaml |
| **Memory** | `ConfigRegistry` singleton, env var cache populated at import |
| **Thread** | Read-only after init; thread-safe |
| **Lifetime** | Process-lifetime |
| **Shutdown** | None |
| **Recovery** | None (config is static per process start) |

### 11.2 SettingsStore (`core/settings/store.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | Settings records |
| **Reads** | `~/.jarvis/settings/` |
| **Writes** | Settings changes |
| **Publishes** | — |
| **Consumes** | Settings API calls |
| **Stores** | JSON files in `~/.jarvis/settings/` |
| **Memory** | Settings cache |
| **Thread** | Not explicitly thread-safe |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Save settings |
| **Recovery** | JSON files survive crash; may be stale |

---

## 12. Storage & Persistence

### 12.1 Async ORM (`core/database.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | ORM session, all 24 async ORM tables |
| **Reads** | `data/jarvis.db` (shared with sync ORM) |
| **Writes** | All ORM-managed data |
| **Publishes** | — |
| **Consumes** | SQLAlchemy queries |
| **Stores** | `data/jarvis.db` → **target:** `data/app.db` |
| **Memory** | SQLAlchemy engine, session factory |
| **Thread** | SQLAlchemy async engine is thread-safe |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close engine, dispose connection pool |
| **Recovery** | Full SQLite transactional recovery |

### 12.2 Sync ORM (`core/database_models.py`) 🗑

| Column | Detail |
|--------|--------|
| **Owner** | Core (deprecating) |
| **Creates** | Sync ORM models (24 tables, shared with async ORM) |
| **Reads** | `data/jarvis.db` |
| **Writes** | ORM-managed data |
| **Publishes** | — |
| **Consumes** | Legacy synchronous callers |
| **Stores** | `data/jarvis.db` |
| **Memory** | SQLAlchemy sync engine |
| **Thread** | SQLAlchemy sync engine adds threading complexity |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close engine |
| **Recovery** | Full SQLite |

### 12.3 ActivityStore (`core/activity/storage.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Core |
| **Creates** | Activity nodes, edges |
| **Reads** | `data/workflow.db` |
| **Writes** | Activity graph data |
| **Publishes** | — |
| **Consumes** | Pipeline, scheduler, API |
| **Stores** | `data/workflow.db` (shared with WorkflowStore, PlanStore) |
| **Memory** | `ActivityStore` instance |
| **Thread** | `threading.Lock` |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close SQLite connection |
| **Recovery** | Full SQLite |

### 12.4 CheckpointStore (`core/persistence/store.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Execution |
| **Creates** | Checkpoint records |
| **Reads** | SQLite |
| **Writes** | Checkpoint data |
| **Publishes** | — |
| **Consumes** | Checkpoint save/load requests |
| **Stores** | SQLite |
| **Memory** | `CheckpointStore` instance |
| **Thread** | `threading.Lock` |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close connection |
| **Recovery** | Full SQLite |

### 12.5 CheckpointManager (`core/checkpoint_manager.py`) 🗑

| Column | Detail |
|--------|--------|
| **Owner** | Execution |
| **Creates** | JSON checkpoint files |
| **Reads** | `~/.jarvis/checkpoints/*.json` |
| **Writes** | JSON checkpoint files (non-transactional) |
| **Publishes** | — |
| **Consumes** | Pipeline, controller loop |
| **Stores** | `~/.jarvis/checkpoints/` (JSON files) |
| **Memory** | `CheckpointManager` singleton |
| **Thread** | Likely none |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Save final checkpoint |
| **Recovery** | JSON files may be corrupt (non-atomic writes) |

### 12.6 Brain Persistence (`brain/persistence.py`) 🗑

| Column | Detail |
|--------|--------|
| **Owner** | Brain (deprecating) |
| **Creates** | `Checkpoint`, `DecisionRecord` |
| **Reads** | `data/brain.db` |
| **Writes** | Checkpoints, decisions in brain.db |
| **Publishes** | — |
| **Consumes** | Brain automation loop |
| **Stores** | `data/brain.db` |
| **Memory** | `ProjectPersistence` instance |
| **Thread** | `threading.Lock` |
| **Lifetime** | Process-lifetime |
| **Shutdown** | Close brain.db |
| **Recovery** | Full SQLite |

---

## 13. Brain & Autonomous Systems

### 13.1 UnifiedBrain (`brain/UnifiedBrain.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Brain |
| **Creates** | `MemoryManager` (brain), `GoalManager`, `Planner` (brain), `Executor`, `Verifier`, `AutomationLoop`, `ObserverManager`, `WorldModel`, `LearningEngine`, `GoalGenerator`, `SelfImprovementEngine`, `ToolRegistry` |
| **Reads** | Brain memory, goals, world model |
| **Writes** | Brain memory, goals, tool registry, all sub-engine state |
| **Publishes** | Brain EventBus (8 types): `GoalCreated`, `GoalCompleted`, `GoalFailed`, `TaskCompleted`, `TaskFailed`, `MemoryStored`, `VerificationPassed`, `VerificationFailed` |
| **Consumes** | Startup from `core/main.py` or `brain/__init__.py` |
| **Stores** | `data/brain.db` |
| **Memory** | `UnifiedBrain` singleton (543 lines), all sub-engine singletons (15+ brain singletons) |
| **Thread** | Not explicitly documented — brain subsystems have their own locks |
| **Lifetime** | Process-lifetime |
| **Shutdown** | `brain.stop()` → stops AutomationLoop, ObserverManager, GoalGenerator, all sub-engines |
| **Recovery** | SQLite persistence for goals, memory, checkpoints. In-memory engine state lost. |

### 13.2 AutomationLoop (`brain/automation/loop.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Brain |
| **Creates** | Build project data (plan, generated files, verification results) |
| **Reads** | GoalManager, brain memory, FailureMemory |
| **Writes** | Brain MemoryManager (traces), FailureMemory (error patterns), ArchitecturalMemory (JSON), GoalManager (complete/fail) |
| **Publishes** | **None** — does not use EventBus |
| **Consumes** | Goal from GoalManager |
| **Stores** | `data/brain.db` (via brain MemoryManager) |
| **Memory** | `AutomationLoop` singleton, loop state (`_running`, `_paused`), FailureMemory (in-memory pattern registry) |
| **Thread** | Async tick loop |
| **Lifetime** | Process-lifetime |
| **Shutdown** | `stop()` → set `_running = False`, exit tick loop |
| **Recovery** | GoalManager persists goals in brain.db. In-memory FailureMemory lost. |

### 13.3 Brain Executor (`brain/executor/executor.py`) ⚠

| Column | Detail |
|--------|--------|
| **Owner** | Brain |
| **Creates** | `ActionResult` |
| **Reads** | Tool definitions, brain memory |
| **Writes** | Action results, brain memory |
| **Publishes** | — |
| **Consumes** | Action requests from brain subsystems |
| **Stores** | — |
| **Memory** | `executor` singleton (brain/executor/executor.py:187) |
| **Thread** | Not documented |
| **Lifetime** | Process-lifetime |
| **Shutdown** | None |
| **Recovery** | None |

### 13.4 LearningEngine (`brain/learning_engine.py`)

| Column | Detail |
|--------|--------|
| **Owner** | Brain |
| **Creates** | Learning records |
| **Reads** | Brain memory |
| **Writes** | Brain memory (learning data) |
| **Publishes** | — |
| **Consumes** | Automation loop outcomes |
| **Stores** | `data/brain.db` |
| **Memory** | `LearningEngine` singleton |
| **Thread** | Not documented |
| **Lifetime** | Process-lifetime |
| **Shutdown** | None |
| **Recovery** | SQLite persistence |

---

## 14. Legacy Subsystems (Deprecated)

All subsystems marked with 🗑 have a complete entry in DELETION_MIGRATION_TRACKER.md.

| Module | Status | Key Issue | Replacement |
|--------|--------|-----------|-------------|
| `core/memory.py` | 🗑 | System C memory, JSON+SQLite | `memory/MemoryFacade` |
| `core/memory_vector.py` | 🗑 | Duplicate ChromaDB vector store | mem0 adapter |
| `brain/planner/` | 🗑 | Fixed 3-node DAG, in-memory | CorePlanner protocol |
| `brain/memory/` | 🗑 | System B memory, separate DB | MemoryFacade backends |
| `brain/goals/` | 🗑 | Duplicate goal CRUD | UnifiedStore |
| `core/plan_manager.py` | 🗑 | JSON plan manager, in-memory | PlanStore / UnifiedStore |
| `core/database_models.py` | 🗑 | Sync ORM shared with async | `core/database.py` |
| `core/pipeline.py` (RuntimePipeline) | 🗑 | Legacy 10-phase pipeline | Canonical pipeline |
| `data/auth.json` | 🗑 | Non-transactional JSON | SQLite in system.db |
| `data/sessions.json` | 🗑 | Non-transactional session storage | SQLite in system.db |
| `data/brain.db` | 🗑 | Fragmented brain state | Bounded-context DBs |
| `data/workflow.db` (shared) | 🗑 | 3 owners in 1 file | Per-context DBs |
| `database.db` (root) | 🗑 | Unknown origin | Determine then remove |
| `ai_os_memory.db` | 🗑 | Unowned orphan DB | Integrate or remove |
| `PluginEventBus` | 🗑 | Second event bus | Namespaced canonical EventBus |
| `Runtime protocol` | 🗑 | Config change listeners | EventBus subscription |
| `NON_ADMIN_BLOCKED_TOOLS` | 🗑 | Hardcoded blocklist | Scope-based RBAC |

---

## 15. Request-Lifecycle Flow Diagram

```
Signal (HTTP/WS/MCP/CLI/Scheduler)
    │
    ▼
Transport Adapter
    │
    ▼
Pipeline.execute(Request → PipelineContext)
    │
    ├── 1.  ReceiveStage         (Core)      — parse request
    ├── 2.  LoadContextStage     (Core)      — load session/user/metadata
    ├── 3.  AuthenticationStage  (Security)  — auth check
    ├── 4.  TenantResolution     (Core)      — resolve tenant
    ├── 5.  AuthorizationStage   (Security)  — authz check
    ├── 6.  ResourceAccessStage  (Security)  — resource grant
    ├── 7.  RateLimitStage       (Core)      — rate limit (currently no-op)
    ├── 8.  IntentStage          (Core)      — classify intent
    ├── 9.  ContextRetrievalStage(Memory)    — recall from memory
    ├── 10. ReasonerStage        (Core)      — assess complexity
    ├── 11. PlannerStage         (Planner)   — create plan
    │         └── CorePlanner / PlanStore
    ├── 12. PlanValidatorStage   (Planner)   — validate plan structure
    ├── 13. CapabilitySelection  (Core)      — bind capabilities
    │         └── CapabilityRegistry
    ├── 14. ExecutionStage       (Execution) — execute plan steps
    │         ├── Runtime.execute_plan()
    │         │   └── execute_tool_block()  →  MCP / Native / Sub-agent
    │         └── ProviderManager (LLM fallback)
    ├── 15. VerificationStage    (Core)      — verify outcomes
    ├── 16. EpistemicTaggingStage(Core)      — tag confidence/provenance
    ├── 17. MemoryStage          (Memory)    — store to MemoryFacade
    ├── 18. MetricsStage         (Core)      — aggregate metrics
    └── 19. FormatStage          (Core)      — format response
    │
    ▼
Response → Transport Adapter → Client

    ──── SEPARATE EXECUTION UNIVERSES ────

UnifiedBrain (brain/)
    ├── AutomationLoop (tick-based goal build loop)
    ├── Brain Executor (separate tool dispatch, NOT execute_tool_block)
    ├── Brain EventBus (separate from canonical EventBus)
    └── Brain MemoryManager (separate from MemoryFacade)

ControllerLoop (core/control_loop.py)
    ├── Build automation (plan → build → validate → fix → deploy)
    ├── pattern_failure_memory (separate from brain FailureMemory)
    ├── checkpoint_manager (separate from brain ProjectPersistence)
    └── No EventBus usage
```

---

## 16. Recovery Matrix

| Component | Persistence Mechanism | Survives Crash? | Recovery Path |
|-----------|----------------------|-----------------|---------------|
| PipelineContext | None (in-memory) | ❌ | Request lost |
| PlannerState | SQLite (PlanStore) + in-memory engines | ⚠ Partial | Plan data survives; engine state re-created |
| WorkflowState | SQLite (WorkflowStore) + in-memory ExecutionGraph | ⚠ Partial | Workflow instances survive; execution graph lost |
| Scheduler Queue | SQLite (ActivityStore) | ✅ Full | Queue items survive |
| Tool Dispatcher | None (stateless per-call) | ✅ N/A | Stateless |
| Memory System A | SQLite + Mem0 + ChromaDB | ✅ Full | Data survives |
| Memory System B | SQLite (brain.db) | ✅ Full | Data survives |
| Memory System C | SQLite (ai_os_memory.db) | ✅ Full | Data survives |
| Identity/Permission | None (in-memory) | ❌ | All grants and audit logs lost |
| AuthManager | JSON files | ⚠ Partial | Data survives but may be corrupt |
| EventBus | None (in-memory subscriptions) | ❌ | All subscriptions lost; subscribers re-register at boot |
| Brain EventBus | None (in-memory) | ❌ | All brain subscriptions lost |
| Workflow Events | SQLite append log | ✅ Full | Event log survives |
| Config | YAML + env (read at import) | ✅ Full | Re-read on restart |
| Checkpoints (JSON) | JSON files | ⚠ Partial | May be corrupt (non-atomic writes) |
| Checkpoints (brain.db) | SQLite | ✅ Full | Data survives |
| Session state | In-memory + JSON | ❌ | Active sessions lost |
| Browser state | In-memory + JSON dumps | ⚠ Partial | Session dumps survive; active pages lost |
| Desktop state | In-memory | ❌ | All state lost |
| Permission grants | In-memory | ❌ | All grants reset |
| Audit log | In-memory list | ❌ | No forensic trail |
| Rate limit counters | In-memory | ❌ | Rate limits reset |
| Provider router | In-memory scoring cache | ❌ | Cold-start re-learning |
| LLM provider state | In-memory | ❌ | Provider selection history lost |

---

## 17. Shutdown Sequence

```
Shutdown Order (first to last)
    │
    1. Pipeline.cancel()              — stop accepting new requests
    2. Scheduler.stop()               — stop tick, cancel workers
    3. WorkflowEngine                  — complete/cancel active workflows
    4. UnifiedBrain.stop()            — stop AutomationLoop, ObserverManager, GoalGenerator
    5. ControllerLoop                  — complete active build projects
    6. WebSocket Manager               — close all connections
    7. EventBus                        — clear subscriber registry
    8. MemoryFacade backends           — close DB connections, flush caches
    9. Brain MemoryManager             — close brain.db
    10. ConfigRegistry                 — save settings
    11. ActivityStore                  — flush pending writes
    12. Checkpoint / Persistence       — save final checkpoints
    13. AuthManager                    — flush sessions to JSON (target: SQLite)
    14. Database engines               — close async + sync ORM engines
    15. Main process exit
```

*End of SYSTEM_RUNTIME_MAP.md — 25+ subsystems mapped, 3 execution universes documented, 18 legacy components tracked for deletion, 16-category recovery matrix, full shutdown sequence.*
