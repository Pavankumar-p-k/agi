# JARVIS AI Operating System Architecture

## Objective

Upgrade the existing JARVIS monorepo into a modular AI operating system without deleting files, reducing module count, or breaking legacy APIs.

The new runtime is additive. Existing systems remain in place and are wrapped behind a new `backend/jarvis_os` operating layer.

## Target Topology

```text
                        +----------------------+
                        |   FastAPI Gateway    |
                        |  backend/core/main   |
                        +----------+-----------+
                                   |
                                   v
                        +----------------------+
                        |      Agent OS        |
                        |   backend/jarvis_os  |
                        +----------+-----------+
                                   |
         +-------------------------+--------------------------+
         |                         |                          |
         v                         v                          v
+----------------+     +----------------------+     +----------------------+
|  Reasoning     |     |   World Model        |     |   Tool Router        |
|  Engine        |     |   Memory Engine      |     |   Dynamic Adapters   |
+--------+-------+     +-----------+----------+     +----------+-----------+
         |                         |                           |
         v                         v                           v
+----------------+     +----------------------+     +----------------------+
| Planning       |     | Long-term knowledge  |     | Automation / Vision  |
| Engine         |     | Environment state    |     | Filesystem / ADB     |
+--------+-------+     | Vector recall        |     | Brain / Learning     |
         |             +-----------+----------+     +----------+-----------+
         v                         |                           |
+----------------+                 |                           |
| Executor       |<----------------+---------------------------+
| Engine         |
+--------+-------+
         |
         v
+----------------+     +----------------------+     +----------------------+
| Safety Layer   |     | Learning Engine      |     | Observability        |
| Risk + policy  |     | Student AGI bridge   |     | Events / metrics     |
+--------+-------+     +-----------+----------+     +----------------------+
         |
         v
+----------------------+
| Self-Improvement     |
| Reflection loop      |
+----------------------+
```

## Runtime Loop

```text
observe -> analyze -> plan -> validate -> execute -> reflect -> learn -> improve
```

1. `AgentRuntime` stores the incoming goal in the world model.
2. `ReasoningEngine` analyzes the request using legacy autonomy if available, then adds memory context and tool candidates.
3. `PlanningEngine` converts the goal into one or more `PlanStep` actions.
4. `SafetyLayer` scores risk per action and blocks or gates high-risk operations.
5. `Executor` invokes routed tools with retries and audit storage.
6. `LearningEngine` updates skills and optionally teaches the Student AGI subsystem.
7. `SelfImprovementLoop` records tool success/failure patterns and feeds them back into learning.

## Service Interaction Diagram

```text
Client
  |
  v
/os/agent/think
  |
  v
AgentRuntime
  |
  +--> WorldModel.observe(goal)
  |
  +--> ReasoningEngine.analyze()
  |       |
  |       +--> autonomy.get_orchestrator()   (optional legacy bridge)
  |       +--> WorldModel.query()
  |       +--> ToolRouter.recommend_tools()
  |
  +--> PlanningEngine.build_plan()
  |
  +--> SafetyLayer.validate(step)
  |
  +--> Executor.execute_plan()
  |       |
  |       +--> ToolRouter.invoke(tool)
  |       +--> WorldModel.store_experience()
  |
  +--> ReasoningEngine.reflect()
  +--> LearningEngine.learn_from_execution()
  +--> SelfImprovementLoop.capture()
  |
  v
Structured OS response
```

## New Modules Added

All modules are additive and preserve the existing tree:

- `backend/jarvis_os/contracts.py`
  Defines stable runtime contracts: goals, plans, risk assessments, tool specs, and execution reports.
- `backend/jarvis_os/cache.py`
  Adds a small TTL cache for read-heavy tool and model operations.
- `backend/jarvis_os/reasoning.py`
  Centralizes goal interpretation and legacy orchestrator bridging.
- `backend/jarvis_os/planning.py`
  Builds multi-step plans from subtasks and tool recommendations.
- `backend/jarvis_os/self_improvement.py`
  Adds the self-improving AGI loop to track tool performance and feed back learning.
- `backend/jarvis_os/tool_router/router.py`
  Resolves the previous import collision and provides the actual dynamic router implementation.

## Core Subsystems

### 1. Agent Core

`AgentRuntime` is now the stable runtime boundary.

Responsibilities:

- goal creation
- reasoning loop orchestration
- plan creation
- execution dispatch
- reflection and learning handoff

### 2. World Model Memory

`WorldModel` now persists to SQLite and supports:

- episodic memory via `memories`
- environment state via `environment_state`
- persistent knowledge via `knowledge`
- skill accumulation via `skills`
- execution experience tracking via `experiences`
- semantic retrieval using lightweight vector hashing

Legacy memory is preserved through optional mirroring into:

- `memory.store.MemoryStore`
- `memory.agi_memory.AGIMemory`

### 3. Goal-Driven Task Planning

`PlanningEngine` supports multi-step decomposition by splitting compound requests into subtasks and routing each to a specific tool.

Planner outputs remain additive and do not replace legacy autonomy plans.

### 4. Tool Routing System

`ToolRouter` exposes a tool catalog and dynamic recommendation flow.

Default adapters:

- `assistant_chat`
- `brain`
- `memory`
- `filesystem`
- `automation`
- `vision`
- `adb`
- `learning`

This keeps old modules intact while moving selection logic into one place.

### 5. Safety and Sandbox

`SafetyLayer` introduces:

- risk scoring by tool and action language
- path root enforcement
- approval gating for risky plans
- recent decision history
- sandbox profiles per tool

### 6. Executor Engine

`Executor` now handles:

- safety validation
- retry loops
- per-step latency tracking
- execution reports
- background job submission
- experience logging into the world model

### 7. Learning Engine Integration

`LearningEngine` now:

- updates skill scores from execution outcomes
- records feedback from reflections
- optionally loads the Student AGI runtime from `backend/learning/student_agi/student_agi_main.py`
- exposes teaching and synthesis hooks

### 8. Observability

`Observability` now tracks:

- retained event stream
- metrics and latency summaries
- health states per subsystem
- traces for plan execution

### 9. Performance Strategy

Current runtime-level optimization:

- TTL cache for read-only tool calls
- async executor flow
- background execution jobs
- lightweight in-process batching foundation through shared cache and tool routing

Next expansion path without breaking APIs:

1. Add LLM response cache keyed by prompt + role.
2. Batch embedding generation and semantic indexing offline.
3. Move executor jobs to a dedicated worker queue.
4. Add model routing weights to `ReasoningEngine`.
5. Add persistence-backed metrics export.

## Self-Improving AGI Loop

The new `SelfImprovementLoop` is the additive AGI feedback cycle:

```text
execution report
  -> tool success/failure aggregation
  -> reflection snapshot
  -> learning feedback update
  -> world-model storage
  -> improved future routing and safety defaults
```

This is intentionally constrained:

- it does not rewrite code automatically
- it does not bypass approval rules
- it improves policy and skill state from execution evidence

## Integration Points Preserved

No existing module was removed. The OS layer wraps:

- `backend/autonomy/*`
- `backend/assistant/*`
- `backend/automation/*`
- `backend/vision/*`
- `backend/memory/*`
- `backend/learning/student_agi/*`

`backend/core/main.py` now mounts `/os/*` routes and initializes the OS during backend startup.

## Recommended Next Steps

1. Add dedicated adapters for reminders, notes, media, and websocket systems.
2. Expand `PlanningEngine` with explicit dependency graphs across steps.
3. Introduce durable worker queues for long-running automation.
4. Add approval workflows exposed to Flutter for high-risk plans.
5. Add structured world-state patches from vision and automation outputs.
