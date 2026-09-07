# EXECUTION ENGINE AUDIT — MJ Architecture

**Generated:** 2026-07-18  
**Scope:** All execution engines in MJ codebase  
**Method:** READ ONLY — trace every start/call/execute/finish/event/memory/UI path  

---

## Executive Summary

**5 EXECUTION ENGINES** discovered. **1 CANONICAL** (Pipeline), **4 DUPLICATE/DORMANT**.

| Engine | Status | Stages | Entry Points |
|--------|--------|--------|--------------|
| **Pipeline (Canonical)** | ACTIVE | 19 stages | REST, WS, CLI, Voice, TUI, Discord, Slack, Telegram, Matrix, IRC, Scheduler |
| **StateGraph (Legacy Agent)** | DORMANT | 8 nodes | `/ws/agent_stream`, `/api/v1/agent`, CLI fallback |
| **WorkflowEngine** | ACTIVE | N steps | Build API, Scheduler, Governance |
| **ActivityScheduler** | ACTIVE | 5 executors | Background tick (5s), Opportunities |
| **PCAutomation (Legacy)** | DEPRECATED | 7 actions | `automation.routes`, TalkBack |

---

## Engine 1: Canonical Pipeline (ACTIVE)

**File:** `core/pipeline/pipeline.py:Pipeline.execute()`  
**Entry Point:** `core/pipeline/pipeline.py:process_message(request, services)`

### Execution Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CANONICAL PIPELINE (19 STAGES)                       │
│  Receive → LoadContext → Auth → Tenant → AuthZ → Resource → RateLimit       │
│      → Intent → ContextRetrieval → Knowledge → Reasoning → Planner         │
│      → PlanValidator → CapabilitySelection → Execution → Verification      │
│      → Epistemic → Reflection → Learning → PolicyOpt → Memory              │
│      → Notification → Metrics → Explainability → Formatter                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Execution Graph

| Step | Who Starts | Who Calls | Who Executes | Who Finishes | Who Publishes Events | Who Writes Memory | Who Updates UI |
|------|------------|-----------|--------------|--------------|---------------------|-------------------|----------------|
| **Receive** | Transport | `process_message()` | `ReceiveStage` | `ReceiveStage` | `request.received` | — | — |
| **LoadContext** | Pipeline | `LoadContextStage` | `LoadContextStage` | `LoadContextStage` | `context.loaded` | `HistoryService.load()` | — |
| **Auth** | Pipeline | `AuthenticationStage` | `AuthenticationStage` | `AuthenticationStage` | `auth.verified` | — | — |
| **Tenant** | Pipeline | `TenantResolutionStage` | `TenantResolutionStage` | `TenantResolutionStage` | `tenant.resolved` | — | — |
| **AuthZ** | Pipeline | `AuthorizationStage` | `AuthorizationStage` | `AuthorizationStage` | `authz.granted` | — | — |
| **Resource** | Pipeline | `ResourceAccessStage` | `ResourceAccessStage` | `ResourceAccessStage` | `resource.granted` | — | — |
| **RateLimit** | Pipeline | `RateLimitStage` | `RateLimitStage` | `RateLimitStage` | `rate.limited` | — | — |
| **Intent** | Pipeline | `IntentStage` | `IntentStage` | `IntentStage` | `intent.classified` | — | — | — |
| **ContextRetrieval** | Pipeline | `ContextRetrievalStage` | `ContextRetrievalStage` | `ContextRetrievalStage` | `context.retrieved` | `MemoryFacade.recall()` | — |
| **Knowledge** | Pipeline | `KnowledgeStage` | `KnowledgeStage` | `KnowledgeStage` | `knowledge.queried` | `MemoryFacade.search_vectors()` | — |
| **Reasoning** | Pipeline | `ReasoningStage` | `ReasoningStage` | `ReasoningStage` | `reasoning.complete` | — | — | Streaming deltas |
| **Planner** | Pipeline | `PlannerStage` | `PlannerStage` | `PlannerStage` | `plan.created` | — | — | — |
| **PlanValidator** | Pipeline | `PlanValidatorStage` | `PlanValidatorStage` | `PlanValidatorStage` | `plan.validated` | — | — | — |
| **CapabilitySelection** | Pipeline | `CapabilitySelectionStage` | `CapabilitySelectionStage` | `CapabilitySelectionStage` | `capability.selected` | — | — | — |
| **Execution** | Pipeline | `ExecutionStage` | `ExecutionStage` → `Runtime` → `ToolExecutor` | `ExecutionStage` | `execution.started/completed` | `MemoryFacade.store_trace()` | Tool progress |
| **Verification** | Pipeline | `VerificationStage` | `VerificationStage` | `VerificationStage` | `verification.passed/failed` | — | — | — |
| **Epistemic** | Pipeline | `EpistemicTaggingStage` | `EpistemicTaggingStage` | `EpistemicTaggingStage` | `epistemic.tagged` | — | — | — |
| **Reflection** | Pipeline | `ReflectionStage` | `ReflectionStage` | `ReflectionStage` | `reflection.complete` | — | — | — |
| **Learning** | Pipeline | `LearningStage` | `LearningStage` | `LearningStage` | `learning.recorded` | — | — | — |
| **PolicyOptimization** | Pipeline | `PolicyOptimizationStage` | `PolicyOptimizationStage` | `PolicyOptimizationStage` | `policy.optimized` | — | — | — |
| **Memory** | Pipeline | `MemoryStage` | `MemoryStage` | `MemoryStage` | `memory.stored` | `MemoryFacade.store()` | — |
| **Notification** | Pipeline | `NotificationStage` | `NotificationStage` | `NotificationStage` | `notification.sent` | — | — | Push/WS |
| **Metrics** | Pipeline | `MetricsStage` | `MetricsStage` | `MetricsStage` | `metrics.recorded` | — | — | — |
| **Explainability** | Pipeline | `ExplainabilityStage` | `ExplainabilityStage` | `ExplainabilityStage` | `explain.generated` | — | — | — |
| **Formatter** | Pipeline | `FormatterStage` | `FormatterStage` | `FormatterStage` | `response.formatted` | — | — | Final response |

### Who Starts/Calls/Executes/Finishes/Events/Memory/UI — Summary

| Responsibility | Owner |
|----------------|-------|
| **Starts** | Transport adapter → `process_message()` |
| **Calls** | `Pipeline.execute()` → each `Stage.execute()` |
| **Executes** | Each `Stage.execute()` → `ExecutionStage` → `Runtime` → `ToolExecutor` |
| **Finishes** | `FormatterStage` → `Response` |
| **Events** | Each stage → `global_event_bus` (Pipeline hooks + stage events) |
| **Memory** | `MemoryStage` → `MemoryFacade` (5 backends) |
| **UI** | Transport adapter → WebSocket/REST/CLI/TUI/Voice |

---

## Engine 2: StateGraph / Legacy Agent Loop (DORMANT)

**File:** `core/graph/graph.py:StateGraph.execute()` + `core/graph/nodes.py`  
**Entry Points:** `/ws/agent_stream`, `/api/v1/agent`, CLI fallback (`_disable_pipeline`)

### Execution Graph (8 Nodes)

```
setup_node → plan_node → think_node → route_node → tool_call_node → pause_node → resume_node → sub_agent_node
```

| Step | Who Starts | Who Calls | Who Executes | Who Finishes | Events | Memory | UI |
|------|------------|-----------|--------------|--------------|--------|--------|----|
| setup | WS/Agent API | `StateGraph.execute()` | `setup_node()` | `setup_node` | `phase_change` | `session_db` | WS |
| plan | Graph | Graph | `plan_node()` | `plan_node` | `phase_change` | — | — |
| think | Graph | Graph | `think_node()` (LLM streaming) | `think_node` | `delta`, `tool_call_delta` | — | SSE deltas |
| route | Graph | Graph | `route_node()` (parse tools) | `route_node` | — | — | — |
| tool_call | Graph | Graph | `tool_call_node()` (concurrent) | `tool_call_node` | `tool_start`, `tool_output` | `session_db` checkpoint | SSE |
| pause | Graph | Graph | `pause_node()` (HITL) | `pause_node` | `human_review` | `checkpoint_store` | WS `human_review` |
| resume | API | `resume_node()` | `resume_node()` | `resume_node` | `resume_approved` | — | WS |
| sub_agent | Graph | Graph | `_run_sub_agent()` | `_run_sub_agent` | — | — | — |

**Status:** DORMANT — Only used by `/ws/agent_stream`, `/api/v1/agent`, CLI fallback (`_disable_pipeline`)

---

## Engine 3: WorkflowEngine (ACTIVE)

**File:** `core/workflow/engine.py:WorkflowEngine`  
**Entry Points:** Build API, Scheduler, Governance, Startup recovery

### Execution Graph

```
start_workflow() → _run_workflow() → _execute_step() → execute_tool_block()
     ↓                    ↓                    ↓                    ↓
  persist           _execute_step()      execute_tool_block()   record_trace()
  workflow          (idempotency)         (tools)                (memory)
```

| Step | Who Starts | Who Calls | Who Executes | Who Finishes | Events | Memory | UI |
|------|------------|-----------|--------------|--------------|--------|--------|----|
| start_workflow | API/Scheduler | `start_workflow()` | `WorkflowEngine` | `WorkflowEngine` | `workflow.started` | — | — |
| _run_workflow | Engine | `_run_workflow()` | `WorkflowEngine` | `WorkflowEngine` | `step.started/completed` | `ActivityRecorder` | Poll `/status` |
| _execute_step | Engine | `_execute_step()` | `execute_tool_block()` | `WorkflowEngine` | `step.completed/failed` | `ActivityRecorder` | Poll |
| compensate | Engine | `_compensate_workflow()` | `execute_tool_block()` | `WorkflowEngine` | `compensation.*` | — | Poll |
| recover | Startup | `recover_active_workflows()` | `WorkflowEngine` | `WorkflowEngine` | `workflow.recovered` | — | — |

**Status:** ACTIVE — Separate domain (multi-step + compensation), used by Build API, Scheduler, Governance

---

## Engine 4: ActivityScheduler (ACTIVE)

**File:** `core/scheduler/scheduler.py:Scheduler`  
**Entry Point:** Background tick (5s) → `Scheduler.tick()`

### Execution Graph

```
tick() → _cleanup_workers() → queue.get_best_n_chain_aware() → _run_worker() → executor()
```

| Step | Who Starts | Who Calls | Who Executes | Who Finishes | Events | Memory | UI |
|------|------------|-----------|--------------|--------------|--------|--------|----|
| tick | Background | `tick()` | `Scheduler` | `Scheduler` | `scheduler.tick` | Intelligence | Poll `/status` |
| _run_worker | Scheduler | `_run_worker()` | `_run_worker()` | `ExecutorFn` | `activity.started/resumed/completed` | Intelligence records | Poll |
| executor | Scheduler | `executor()` | Provider/Tool | `Provider` | `activity.completed/failed` | Intelligence records | Poll |

**Executors (5):** `research_executor`, `build_executor`, `repair_executor`, `email_executor`, `benchmark_executor` → all delegate to **Pipeline** via `_run_via_pipeline()`

**Status:** ACTIVE — Background tick (5s), all executors → Pipeline

---

## Engine 5: PCAutomation (DEPRECATED)

**File:** `automation/pc_automation.py:PCAutomation`  
**Entry Points:** `automation/routes.py`, TalkBack

### Execution Graph

```
execute_command() → parser.parse() → wa.send_to_contact() / browser.youtube_play() / launch_app() / sys_ctrl
```

| Step | Who Starts | Who Calls | Who Executes | Who Finishes | Events | Memory | UI |
|------|------------|-----------|--------------|--------------|--------|--------|----|
| parse | HTTP/TalkBack | `execute_command()` | `parser.parse()` | `parser` | Returns dict | None | JSON |
| whatsapp | Parser | `wa.send_to_contact()` | Selenium | Selenium | — | None | JSON |
| youtube | Parser | `browser.youtube_play()` | Selenium | Selenium | — | None | JSON |
| launch_app | Parser | `launch_app()` | subprocess | subprocess | — | None | JSON |
| system | Parser | `sys_ctrl.*` | pyautogui/subprocess | subprocess | — | None | JSON |

**Status:** DEPRECATED — Header says "Use core/desktop/controller.py instead"

---

## Engine 6: ToolExecutor (INTERNAL)

**File:** `core/tools/executor.py:ToolExecutor`  
**Called By:** `ExecutionStage` → `Runtime` → `ToolExecutor`

| Step | Who Starts | Who Calls | Who Executes | Who Finishes | Events | Memory | UI |
|------|------------|-----------|--------------|--------------|--------|--------|----|
| execute | `ExecutionStage` | `ToolExecutor.execute()` | `ToolExecutor` | `ToolExecutor` | `tool_start`, `tool_output` | `MemoryFacade.store_trace()` | Tool progress |

---

## Engine 7: Brain Executor (INTERNAL)

**File:** `brain/executor.py:Executor`  
**Used By:** `brain/automation/loop.py:AutomationLoop` (legacy)

| Step | Who Starts | Who Calls | Who Executes | Who Finishes |
|------|------------|-----------|--------------|--------------|
| run | AutomationLoop | `executor.run()` | `Executor` | `Executor` |

---

## Canonical Execution Graph (Single Source of Truth)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRANSPORT LAYER                                   │
│  REST │ WebSocket │ CLI │ Voice │ TUI │ Discord │ Slack │ Telegram │ IRC │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      TRANSPORT ADAPTERS                                     │
│  rest_adapter │ ws_adapter │ channel_adapter │ voice_adapter │ cli_adapter │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CANONICAL PIPELINE (19 Stages)                         │
│  Receive → LoadContext → Auth → Tenant → AuthZ → Resource → RateLimit       │
│  → Intent → ContextRetrieval → Knowledge → Reasoning → Planner             │
│  → PlanValidator → CapabilitySelection → Execution → Verification          │
│  → Epistemic → Reflection → Learning → PolicyOpt → Memory                  │
│  → Notification → Metrics → Explainability → Formatter                     │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┬──────────────┐
              ▼              ▼              ▼              ▼
         ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
         │EventBus  │  │WebSocket │  │ Memory   │  │ Inbox    │
         │(global)  │  │ (stream) │  │ Facade   │  │ (notifs) │
         └──────────┘  └──────────┘  └──────────┘  └──────────┘
              │            │            │            │
              ▼            ▼            ▼            ▼
       ┌─────────────────────────────────────────────────────────────────┐
       │                      UI LAYER                                   │
       │  Web │ TUI │ CLI │ Voice │ Discord │ Slack │ Telegram │ Channels│
       └─────────────────────────────────────────────────────────────────┘
```

---

## Duplicate / Dormant / Drift Inventory

| Path | Status | Issue |
|------|--------|-------|
| `core/graph/` (StateGraph) | **DORMANT** | LangGraph fallback only |
| `core/agent_loop.py` fallback | **DRIFT** | `_disable_pipeline` flag |
| `api/agent_routes.py` | **DORMANT** | Uses `build_default_graph()` |
| `automation/pc_automation.py` | **DEPRECATED** | 100% duplicate of `core/desktop/controller.py` |
| `automation/routes.py` | **DUPLICATE** | Legacy HTTP routes |
| `brain/UnifiedBrain.py` | **DUPLICATE** | Duplicates Intent/Planner/Execution/Memory |
| `core/event_bus.py:PluginEventBus` | **DEPRECATED** | Use `global_event_bus` + `namespace="plugin"` |
| `core/event_bus.py:get_bus()` | **LEGACY** | Use `global_event_bus` |
| `core/config.py` | **DEPRECATED** | Shim → `ConfigurationService` |

---

## Canonical Execution Graph (Single Source of Truth)

```
USER INPUT
    │
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  TRANSPORT ADAPTERS (normalize → Request)                          │
│  REST │ WebSocket │ Channel │ Voice │ CLI │ Scheduler │ MCP       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│  CANONICAL PIPELINE (19 stages)                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ RECEIVE → LOAD_CONTEXT → AUTH → TENANT → AUTHZ → RESOURCE   │  │
│  │ → RATE_LIMIT → INTENT → CONTEXT_RETRIEVAL → KNOWLEDGE       │  │
│  │ → REASONING → PLANNER → PLAN_VALIDATOR → CAPABILITY_SELECT  │  │
│  │ → EXECUTION → VERIFICATION → EPISTEMIC → REFLECTION        │  │
│  │ → LEARNING → POLICY_OPT → MEMORY → NOTIFICATION → METRICS  │  │
│  │ → EXPLAINABILITY → FORMATTER                                 │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌────────────┐ ┌────────────┐ ┌────────────┐
       │ EventBus   │  │ WebSocket  │  │ Memory    │
       │ (global)   │  │ (stream)   │  │ Facade    │
       └────────────┘  └────────────┘  └────────────┘
              │            │            │
              ▼            ▼            ▼
       ┌────────────────────────────────────────────────────────────┐
       │                    UI LAYER                                 │
       │  Web │ TUI │ CLI │ Voice │ Discord │ Slack │ Telegram │  │
       └────────────────────────────────────────────────────────────┘
```

---

## Constitutional Rules (Enforced)

1. **ONE PIPELINE** — All request processing goes through 19-stage pipeline
2. **ONE EVENTBUS** — `global_event_bus` is the only event system
3. **ONE CONFIG** — `ConfigurationService` is the only config source
4. **ONE MEMORY** — `MemoryFacade` is the only memory interface
5. **ONE PLANNER** — `PlannerExecutor` is the only planner
6. **ONE EXECUTOR** — `ToolExecutor` wraps all tool calls
7. **ONE SAFETY** — `SafetyManager` + `KillSwitch` are the only guards
8. **ONE PROVIDER ROUTER** — `ProviderRouter` selects all providers
8. **ONE CAPABILITY REGISTRY** — All capabilities registered here
10. **NO SHELL WITHOUT ALLOWLIST** — `bash`/`python` tools require explicit allowlist
11. **NO SILENT FAILURES** — Every error must raise or return structured error
12. **AUDIT EVERYTHING** — Every decision, execution, config change logged
13. **TENANT ISOLATION** — Every request carries `resource_scope.tenant_id`
14. **PLUGIN HOOKS ONLY** — Extensions via `Pipeline.hooks` + `EventBus`
15. **VERSIONED ARCHITECTURE** — `Pipeline.version` incremented on breaking changes

---

*This document is the Constitution of MJ. All engineering decisions must reference this architecture. Any deviation requires Architecture Review Board approval.*

**End of Execution Engine Audit**