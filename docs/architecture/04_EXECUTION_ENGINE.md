# PHASE 4 — Execution Engine Audit

## Scope

Audit every execution engine component:

| # | Component | File(s) |
|---|-----------|---------|
| 1 | AgentGraph | `core/agents/graph.py`, `core/agents/parallel_executor.py` |
| 2 | WorkflowEngine | `core/workflow/engine.py`, `core/workflow/models.py`, `core/workflow/storage.py` |
| 3 | Planner | `core/planner/state_machine.py`, `core/planner/executor.py` |
| 4 | Scheduler | `core/scheduler/scheduler.py`, `core/scheduler/queue.py`, `core/scheduler/worker.py` |
| 5 | Automation | `brain/automation/loop.py` |
| 6 | Background Tasks | (no dedicated class — `asyncio.create_task` pattern) |
| 7 | Execution Nodes | `core/workflow/graph.py`, `core/agents/graph.py`, `core/planner/dag.py` |
| 8 | Task Queue | `core/scheduler/queue.py` |

---

## 1. AgentGraph (AgentExecutionGraph + ParallelAgentExecutor)

| Slot | Answer | File:Line |
|------|--------|-----------|
| **Who starts?** | `PlannerStateMachine._execute_agents()` calls `ParallelAgentExecutor.execute(graph)` | `core/planner/state_machine.py:343` |
| **Who calls?** | `PlannerStateMachine` → `ParallelAgentExecutor.run_node()` per node | `core/agents/parallel_executor.py:80` |
| **Who executes?** | Each `_run_node` calls `agent.execute(ec)` on the assigned Agent from `AgentRouter` | `core/agents/parallel_executor.py:134` |
| **Who finishes?** | All nodes reach terminal status; `graph_completed` AgentEvent emitted | `core/agents/parallel_executor.py:179` |
| **Who publishes events?** | `_emit(AgentEvent)` — agent-scoped internal list, NOT global EventBus (`emit_events` can be False) | `core/agents/parallel_executor.py:39-41` |
| **Who writes memory?** | None directly. Caller (`PlannerStateMachine`) calls `activity_recorder.record_*` | `core/planner/state_machine.py:349-359` |
| **Who updates UI?** | None directly. No WebSocket or EventBus integration. | — |

**Status:** CORRECT (used within PlannerStateMachine only)
**Reality score:** 7/10 — clean DAG model, phase barriers work, but zero global EventBus integration means UI never sees these events.

---

## 2. WorkflowEngine

| Slot | Answer | File:Line |
|------|--------|-----------|
| **Who starts?** | `start_workflow()` called by `ExecutionManager`, `AutomationLoop._execute_step()`, REST API, `do_workflow_start()` tool | `core/workflow/engine.py:70` |
| **Who calls?** | `_run_workflow(wf)` created as `asyncio.create_task()` | `core/workflow/engine.py:145` |
| **Who executes?** | `_execute_step()` → `execute_tool_block()` from `core.tools.execution`; or `_execute_fsm_step()` for FSM type | `core/workflow/engine.py:370`, `core/workflow/engine.py:520` |
| **Who finishes?** | All steps pass → COMPLETED; step fails beyond retry → compensation → FAILED; `_trigger_improvement_detection()` | `core/workflow/engine.py:326-345` |
| **Who publishes events?** | `_store.append_event()` → `WorkflowEvent` (STARTED, STEP_STARTED, STEP_COMPLETED, STEP_FAILED, COMPLETED, FAILED, CANCELLED, COMPENSATION_*) → `WorkflowStore.append_event` calls `global_event_bus.publish_sync()` | `core/workflow/storage.py:70-85` |
| **Who writes memory?** | `_record_workflow_outcome()` → `WorkflowExecutionRecorder.record_workflow()` (writes to `WorkflowHistoryStore`, NOT `MemoryFacade`) | `core/workflow/engine.py:359-368` |
| **Who updates UI?** | Via `global_event_bus.publish_sync()` → EventBus._broadcast() → WebSocket clients | `core/event_bus.py` |

**Status:** CORRECT
**Reality score:** 9/10 — complete lifecycle, idempotency, compensation, retry, persistence, global EventBus, outcome recording.
**Note:** Memory writes go to `WorkflowHistoryStore` not `MemoryFacade` — separate from the main memory system.

---

## 3. Planner (PlannerStateMachine)

| Slot | Answer | File:Line |
|------|--------|-----------|
| **Who starts?** | `run(goal)` called by external callers (Scheduler worker, CLI, automation loops) | `core/planner/state_machine.py:110` |
| **Who calls?** | `run()` transitions through states: PLAN → DECOMPOSE → ROUTE → EXECUTE → VERIFY → COMPLETE/FAILED | `core/planner/state_machine.py:132-249` |
| **Who executes?** | Mode 1 (native): `_execute_agents()` → `build_graph_from_tasks()` → `ParallelAgentExecutor.execute()` → agents. Mode 2: `_execute()` → caller's `execute_fn` | `core/planner/state_machine.py:170-175`, `core/planner/state_machine.py:277` |
| **Who finishes?** | VERIFY passes → COMPLETE; VERIFY fails after max retries → FAILED; health/replan engine can retry | `core/planner/state_machine.py:206-247` |
| **Who publishes events?** | `activity_recorder.record_goal()`, `record_subgoals()`, `record_completion()`, `record_failure()`. NO direct EventBus integration. | `core/planner/state_machine.py:143-153, 242-246` |
| **Who writes memory?** | Only through `activity_recorder`. No direct `MemoryFacade` calls. | — |
| **Who updates UI?** | None directly. No EventBus, no WebSocket. | — |

**Status:** DRIFT — defines a full workflow lifecycle (PLAN→DECOMPOSE→ROUTE→EXECUTE→VERIFY→COMPLETE) that overlaps with WorkflowEngine's step-by-step execution. Neither delegates to the other; two competing orchestrators.
**Reality score:** 6/10 — good state machine design, but no global EventBus integration, no memory writes, and duplicates WorkflowEngine lifecycle.

---

## 4. Scheduler

| Slot | Answer | File:Line |
|------|--------|-----------|
| **Who starts?** | `start()` creates `asyncio.create_task(self._run())` which calls `tick()` on interval | `core/scheduler/scheduler.py:165-171` |
| **Who calls?** | Application startup, REST API (`start/stop/pause/resume`) | — |
| **Who executes?** | `tick()` → `get_best_n_chain_aware()` → `_run_worker(act)` per activity → executor from `SchedulerRegistry` or `execute_fn` | `core/scheduler/scheduler.py:212, 287` |
| **Who finishes?** | Worker completes → `queue.mark_completed(aid)` → `publish_completed()` + `intelligence.record()` | `core/scheduler/scheduler.py:347-398` |
| **Who publishes events?** | `execution_manager.publish_progress()` (start/pause/resume/tick), `publish_completed()`, `publish_failed()`. Also `global_event_bus.publish_sync(scheduler.tick)` | `core/scheduler/scheduler.py:170, 190, 199, 207, 440-451` |
| **Who writes memory?** | `execution_manager.record_trace()` → `MemoryFacade.store_trace()` | `core/scheduler/scheduler.py:353, 397` |
| **Who updates UI?** | Via `execution_manager._publish_event()` → EventBus → WebSocket broadcast | — |

**Status:** CORRECT
**Reality score:** 8/10 — autonomous tick loop, persistence, chain-aware scheduling, intelligence/prediction, EventBus integration, memory traces.
**Note:** `SchedulerWorker` (`core/scheduler/worker.py:45`) is minimal/placeholder — executes via caller-provided planner_fn, no substantive logic.

---

## 5. Automation (AutomationLoop)

| Slot | Answer | File:Line |
|------|--------|-----------|
| **Who starts?** | `start()` creates `asyncio.create_task(self._run_loop())` which polls UnifiedStore for active goals | `brain/automation/loop.py:272-278` |
| **Who calls?** | `AgentOrchestrator` (`core/agent_orchestrator.py`) or `ControlLoop` | — |
| **Who executes?** | `_build_project()` runs 7 phases: plan→generate→verify_gates→build→test→verify→finish. Uses LLM calls, shell commands, `_execute_step()` (wraps WorkflowEngine), `executor.execute_graph_node()` as fallback | `brain/automation/loop.py:375-494` |
| **Who finishes?** | All phases pass → `goals.complete()` + `publish_completed()`. Build failure after max repairs + plan evolution → `goals.fail()` | `brain/automation/loop.py:491-493, 434-455` |
| **Who publishes events?** | `execution_manager.publish_progress()` per phase, `publish_completed()`, `publish_failed()`. Also `record_trace()` and `record_decision()` | `brain/automation/loop.py:389-493` |
| **Who writes memory?** | `execution_manager.record_trace()` → `MemoryFacade.store_trace()`. Also `record_decision()` → `MemoryFacade.store_decision()`. Also `FailureMemory` and `ArchitecturalMemory` (local caches). Direct `self.memory.store_trace()` in build/test phases. | `brain/automation/loop.py:392-393, 456-457, 467-468, 493, 1158, 1880` |
| **Who updates UI?** | Via `execution_manager._publish_event()` → EventBus → WebSocket broadcast | — |

**Status:** DUPLICATE — `_build_project()` implements its own 7-phase lifecycle (plan→generate→verify_gates→build→test→verify→finish) that duplicates what WorkflowEngine + PlannerStateMachine already provide. The `_execute_step()` method creates single-step WorkflowEngine workflows, acknowledging the canonical path but still wrapping it.
**Reality score:** 6/10 — full EventBus/memory integration but duplicates workflow orchestration and bypasses Planner for planning.

---

## 6. Background Tasks

No dedicated `BackgroundTask` or `BackgroundTaskManager` class.

The pattern `asyncio.create_task()` is used pervasively:

| Usage | File | Line |
|-------|------|------|
| WorkflowEngine._run_workflow | `core/workflow/engine.py` | 145 |
| Scheduler._run | `core/scheduler/scheduler.py` | 169 |
| Scheduler._run_worker | `core/scheduler/scheduler.py` | 269 |
| AutomationLoop._run_loop | `brain/automation/loop.py` | 278 |
| ControlLoop.resume_build | `core/control_loop.py` | 315 |

**Status:** DORMANT — no abstraction, no lifecycle management, no cancellation policy, no event publishing for background task lifecycle.
**Reality score:** 2/10 — raw `asyncio.create_task()` everywhere, no consistency.

---

## 7. Execution Nodes

**Three separate node/graph data models:**

| Model | File | Purpose | Can execute? |
|-------|------|---------|--------------|
| `ExecutionNode` / `ExecutionGraph` | `core/workflow/graph.py` | User goal execution tree | No — data model only |
| `GraphNode` / `AgentExecutionGraph` | `core/agents/graph.py` | Parallel agent DAG with phase barriers | Yes — `get_ready_nodes()`, `mark_*()` |
| `TaskNode` / `TaskGraph` | `core/planner/dag.py` | Task dependency DAG | No — data model only (topological sort, critical path) |

| Scope | Answer | File:Line |
|-------|--------|-----------|
| **Who starts?** | Each graph is created by its owning component (PlannerStateMachine, ControlLoop, ExecutionTracker) | — |
| **Who calls?** | `AgentExecutionGraph`: ParallelAgentExecutor. `ExecutionGraph`: ExecutionTracker. `TaskGraph`: callers use topo sort manually. | — |
| **Who executes?** | Only `AgentExecutionGraph` has an executor (ParallelAgentExecutor). `ExecutionGraph` and `TaskGraph` are pure data models. | — |
| **Who finishes?** | Graphs are passive containers — lifecycle managed by owner. | — |
| **Who publishes events?** | `ExecutionTracker` emits GOAL_*/NODE_* events via EventBus. `AgentExecutionGraph` emits AgentEvent (internal). `TaskGraph`: no events. | `core/workflow/tracker.py:108-239` |
| **Who writes memory?** | None directly. | — |
| **Who updates UI?** | `ExecutionTracker` events → EventBus → WebSocket. | — |

**Status:** DUPLICATE — three separate graph data models for execution plans. All three represent "a set of tasks with dependencies."
**Reality score:** 4/10 — triple redundancy with different field names and capabilities. `ExecutionNode` at 248 lines, `GraphNode` at 351 lines, `TaskNode` at 262 lines = 861 total lines for essentially the same concept.

---

## 8. Task Queue

No dedicated `TaskQueue` class. The canonical queue is `SchedulerQueue` (`core/scheduler/queue.py`).

| Scope | Answer | File:Line |
|-------|--------|-----------|
| **Who starts?** | Created by `Scheduler.__init__()` | `core/scheduler/scheduler.py:74` |
| **Who calls?** | `Scheduler.tick()` calls `refresh()`, `get_best_n_chain_aware()`, `mark_running/mark_completed/mark_failed()` | `core/scheduler/scheduler.py:231, 245, 268, 330, 347, 358` |
| **Who executes?** | Queue is passive — delegates execution to Scheduler. | — |
| **Who finishes?** | `mark_completed()/mark_failed()` called by Scheduler's worker. | `core/scheduler/queue.py:204-216` |
| **Who publishes events?** | None directly — Scheduler wraps all queue operations with EventBus calls. | — |
| **Who writes memory?** | None directly. Scheduler calls `record_trace()` separately. | — |
| **Who updates UI?** | None directly. | — |

**Status:** CORRECT
**Reality score:** 7/10 — persistent, dependency-aware, chain-aware, scored. Only used by Scheduler (not shared with other components).

---

## Canonical Execution Graph

```
                      ┌─────────────────────────────────────┐
                      │          APPLICATION STARTUP         │
                      └──────────────────┬──────────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
          ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
          │   Scheduler      │  │   ControlLoop    │  │ AutomationLoop   │
          │   start()        │  │   run_build()    │  │   start()        │
          │   _run()→tick()  │  │   _execute_loop()│  │   _run_loop()    │
          │   tick interval  │  │   retry loop     │  │   _tick()        │
          └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
                   │                     │                     │
                   ▼                     ▼                     ▼
          ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
          │  SchedulerQueue  │  │  Plan + DAG       │  │  UnifiedStore    │
          │  refresh()       │  │  (site_plan)      │  │  get_active()    │
          │  get_best_n()    │  │  _create_plan()   │  │  get_highest()   │
          └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
                   │                     │                     │
                   ▼                     ▼                     ▼
          ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────────────┐
          │  SchedulerWorker │  │  AgentLauncher   │  │ AutomationLoop          │
          │  execute()       │  │  launch(agent,   │  │ _build_project()        │
          │  ─→ execute_fn   │  │    prompt)       │  │ plan→generate→gates     │
          │    or            │  │                  │  │ →build→test→verify      │
          │  ─→ PlannerSM    │  │                  │  │ →runtime→complete       │
          └────────┬─────────┘  └────────┬─────────┘  └────────┬────────────────┘
                   │                     │                     │
                   ▼                     ▼                     │
          ┌────────────────────────────────────┐               │
          │    PlannerStateMachine.run()        │◄─────────────┘
          │    PLAN→DECOMPOSE→ROUTE→EXECUTE     │
          │    →VERIFY→COMPLETE/FAILED          │
          └────────────────┬───────────────────┘
                           │
               ┌───────────┴───────────┐
               ▼                       ▼
     ┌──────────────────┐   ┌──────────────────┐
     │  _execute_agents │   │  _execute        │
     │  (router mode)   │   │  (callback mode) │
     └────────┬─────────┘   └────────┬─────────┘
              │                      │
              ▼                      ▼
     ┌──────────────────┐   ┌──────────────────┐
     │ AgentExecGraph   │   │ execute_fn       │
     │ build from tasks │   │ (caller-provided)│
     └────────┬─────────┘   └──────────────────┘
              │
              ▼
     ┌────────────────────────────┐
     │ ParallelAgentExecutor      │
     │ execute(graph)             │
     │ ─→ AgentExecutionGraph     │
     │   ─→ GraphNode per task    │
     │   ─→ get_ready_nodes()     │
     │   ─→ agent.execute(ec)     │
     └────────┬───────────────────┘
              │
              ▼
     ┌────────────────────────────┐
     │ ExecutionManager           │
     │ start_workflow()           │
     │ publish_progress/completed │
     │ record_trace/decision      │
     └────────┬───────────────────┘
              │
              ▼
     ┌────────────────────────────┐
     │ WorkflowEngine             │
     │ start_workflow()           │
     │ _run_workflow()            │
     │ _execute_step()            │
     │ ─→ execute_tool_block()    │
     │ ─→ WorkflowStore.append    │
     │ ─→ global_event_bus        │
     └────────┬───────────────────┘
              │
              ▼
     ┌────────────────────────────┐
     │ Post-Execution Flow        │
     │                            │
     │  1. EventBus.publish()     │
     │     → WorkflowEvents       │
     │     → execution.* events   │
     │     → scheduler.tick       │
     │     → AgentEvent (limited) │
     │                            │
     │  2. MemoryFacade           │
     │     → store_trace()        │
     │     → store_decision()     │
     │     (via ExecutionManager  │
     │      or direct calls)      │
     │                            │
     │  3. WebSocket broadcast    │
     │     → EventBus._broadcast()│
     │     → /ws/{session_id}     │
     │                            │
     │  4. WorkflowHistoryStore   │
     │     → WorkflowRecorder     │
     │     → learning system      │
     └────────────────────────────┘
```

### Arrow-by-arrow Reality

| Arrow | Path | Status |
|-------|------|--------|
| Startup → Scheduler | `app.start()` → `scheduler.start()` | CORRECT |
| Startup → ControlLoop | `app.start()` → `control_loop.run_build()` | CORRECT |
| Startup → AutomationLoop | `app.start()` → `automation_loop.start()` | CORRECT |
| Scheduler → SchedulerQueue | `tick()` → `refresh() / get_best_n()` | CORRECT |
| Scheduler → SchedulerWorker | `tick()` → `_run_worker()` → `SchedulerWorker.execute()` | CORRECT |
| SchedulerWorker → PlannerSM | `execute()` → `PlannerStateMachine.run()` (if no execute_fn) | CORRECT |
| ControlLoop → AgentLauncher | `_execute_plan()` → `launcher.launch()` | CORRECT |
| ControlLoop → ExecutionManager | `_execute_loop()` → `em.publish_* / record_*` | CORRECT |
| AutomationLoop → UnifiedStore | `_tick()` → `goals.get_highest_priority()` | CORRECT |
| AutomationLoop → PlannerSM | `_build_project()` does NOT use PlannerSM — uses own LLM plan | **DRIFT** |
| AutomationLoop → ExecutionManager | `_build_project()` → `em.publish_* / record_*` | CORRECT |
| AutomationLoop → WorkflowEngine | `_execute_step()` → `em.engine.start_workflow()` | CORRECT |
| PlannerSM → AgentExecutionGraph | `_execute_agents()` → `build_graph_from_tasks()` | CORRECT |
| AgentExecutionGraph → ParallelAgentExecutor | `ParallelAgentExecutor.execute(graph)` | CORRECT |
| ParallelAgentExecutor → Agent | `_run_node()` → `agent.execute(ec)` | CORRECT |
| ExecutionManager → WorkflowEngine | `start_workflow()` → `engine.start_workflow()` | CORRECT |
| WorkflowEngine → execute_tool_block | `_execute_step()` → `execute_tool_block()` | CORRECT |
| WorkflowEngine → EventBus | `WorkflowStore.append_event()` → `global_event_bus.publish_sync()` | CORRECT |
| Scheduler → EventBus | `_fire_tick_callbacks()` → `global_event_bus.publish_sync(scheduler.tick)` | CORRECT |
| Scheduler → MemoryFacade | `em.record_trace()` → `memory.store_trace()` | CORRECT |
| AutomationLoop → MemoryFacade | `em.record_trace/decision()` → `memory.store_*()` | CORRECT |
| ExecutionManager → MemoryFacade | `record_trace/decision()` → `memory.store_*()` | CORRECT |
| EventBus → WebSocket | `_broadcast()` → registered WS clients | CORRECT |
| WorkflowEngine → WorkflowRecorder | `_record_workflow_outcome()` → `WorkflowExecutionRecorder` | CORRECT |

### Summary

- **25 arrows total**
- **22 CORRECT, 2 DRIFT, 1 DUPLICATE**

---

## Duplicate Detection

### D1: Three Graph Data Models

| # | File | Lines | Model | Unique features |
|---|------|-------|-------|-----------------|
| 1 | `core/workflow/graph.py` | 248 | `ExecutionNode` / `ExecutionGraph` | Tree, `can_skip`, `can_reorder`, `trust_level`, `agent_reasoning` |
| 2 | `core/agents/graph.py` | 351 | `GraphNode` / `AgentExecutionGraph` | DAG, `phase` barriers, `depends_on`, artifact handoff, serialization |
| 3 | `core/planner/dag.py` | 262 | `TaskNode` / `TaskGraph` | DAG, topological sort, critical path, cycle detection |

**DRIFT** — three models serving the same purpose. `AgentExecutionGraph` is the most capable (used by PlannerStateMachine). `ExecutionGraph` is used by `ExecutionTracker` for UI event emission. `TaskGraph` is used nowhere in the execution path (only by `ControlLoop._check_dag_consistency` at `core/control_loop.py:402`).

### D2: Two Workflow Orchestrators

| # | Component | Lifecycle | Used by |
|---|-----------|-----------|---------|
| 1 | `WorkflowEngine._run_workflow()` | step-by-step, retry, compensation, idempotency | ExecutionManager, AutomationLoop, REST API |
| 2 | `PlannerStateMachine.run()` | PLAN→DECOMPOSE→ROUTE→EXECUTE→VERIFY | SchedulerWorker (via execute_fn), legacy callers |

**DRIFT** — both define a complete workflow lifecycle but neither delegates to the other. `PlannerStateMachine` knows nothing about `WorkflowEngine` and vice versa. The canonical path should be `PlannerStateMachine` planning → `WorkflowEngine` executing.

### D3: AutomationLoop vs WorkflowEngine

`AutomationLoop._build_project()` implements a 7-phase pipeline (plan→generate→verify_gates→build→test→verify→finish). The `_execute_step()` helper creates single-step WorkflowEngine workflows, but the overall orchestration loop is a parallel implementation of what `WorkflowEngine._run_workflow()` already provides.

**DUPLICATE** — `_build_project()` should be refactored into `WorkflowEngine` steps with `PlannerStateMachine` for the planning/verification phase.

### D4: ControlLoop._execute_loop vs AutomationLoop._build_project

Both implement a build→validate→fix→repeat loop for software projects. `ControlLoop` (868 lines at `core/control_loop.py`) is older and web-focus (HTML generators). `AutomationLoop` (2034 lines at `brain/automation/loop.py`) is newer and Android-focus.

**DUPLICATE** — two separate autonomous build loops. Neither knows about the other. `ControlLoop` uses `AgentLauncher`, `AutomationLoop` uses `WorkflowEngine`. Both write to `MemoryFacade`.

### D5: SchedulerQueue as sole queue vs ad-hoc queuing

`SchedulerQueue` is the only queue, used exclusively by `Scheduler`. Other components queue work ad-hoc:
- `WorkflowEngine.start_workflow(launch_background=True)` creates its own background task
- `AutomationLoop` polls `UnifiedStore` on interval
- `ControlLoop.resume_build()` scans filesystem for pending projects

**DUPLICATE** — no single entry point for background work submission.

---

## Cross-Cutting Concerns

### EventBus Integration

| Component | Global EventBus | Events Published |
|-----------|----------------|------------------|
| WorkflowEngine | ✅ | `workflow.*` (STARTED, STEP_STARTED, COMPLETED, FAILED, COMPENSATION_*) |
| Scheduler | ✅ | `scheduler.tick`, `execution.*` (via ExecutionManager) |
| AutomationLoop | ✅ | `execution.*` (via ExecutionManager) |
| ExecutionManager | ✅ | `execution.*` (workflow_started, completed, failed, progress) |
| ExecutionTracker | ✅ | `GOAL_*`, `NODE_*`, `MILESTONE`, `WARNING` (via `emit_event()`) |
| PlannerStateMachine | ❌ | No EventBus — only activity_recorder |
| AgentGraph/ParallelAgentExecutor | ❌ | No EventBus — only internal AgentEvent list |
| ControlLoop | ❌ | No EventBus — only ExecutionManager for progress/completed/failed |

### MemoryFacade Integration

| Component | MemoryFacade.store_trace() | MemoryFacade.store_decision() | Other memory |
|-----------|----------------------------|-------------------------------|--------------|
| ExecutionManager | ✅ | ✅ | — |
| Scheduler | ✅ | ❌ | ActivityIntelligence (SQLite) |
| AutomationLoop | ✅ | ✅ | FailureMemory, ArchitecturalMemory, direct memory.store_trace() |
| ControlLoop | ❌ | ✅ (via em.record_decision) | decision_memory, pattern_memory |
| WorkflowEngine | ❌ | ❌ | WorkflowHistoryStore (separate from MemoryFacade) |
| PlannerStateMachine | ❌ | ❌ | activity_recorder only |
| ParallelAgentExecutor | ❌ | ❌ | — |

### WebSocket / UI Integration

| Component | UI Updates | Mechanism |
|-----------|-----------|-----------|
| WorkflowEngine | ✅ | EventBus → WebSocket broadcast |
| ExecutionTracker | ✅ | `emit_event()` → EventBus → WebSocket |
| Scheduler | ✅ | ExecutionManager → EventBus → WebSocket |
| AutomationLoop | ✅ | ExecutionManager → EventBus → WebSocket |
| ExecutionManager | ✅ | `_publish_event()` → EventBus → WebSocket |
| PlannerStateMachine | ❌ | None |
| ParallelAgentExecutor | ❌ | None |
| ControlLoop | ❌ | None (only progress/completed via ExecutionManager) |

---

## Reality Scores Summary

| Component | Score | Status |
|-----------|-------|--------|
| WorkflowEngine | 9/10 | CORRECT |
| Scheduler | 8/10 | CORRECT |
| AgentGraph | 7/10 | CORRECT |
| Task Queue (SchedulerQueue) | 7/10 | CORRECT |
| AutomationLoop | 6/10 | DUPLICATE |
| PlannerStateMachine | 6/10 | DRIFT |
| Execution ExecutionNode | 4/10 | DUPLICATE |
| Background Tasks | 2/10 | DORMANT |

---

## Priority Consolidation Candidates

1. **Merge three graph models** into one canonical `ExecutionGraph` used by all components. Keep `phase` barriers from `AgentExecutionGraph` and `can_skip/can_reorder` from `ExecutionNode`.

2. **Make PlannerStateMachine delegate execution to WorkflowEngine** instead of running its own EXECUTE loop. `PlannerStateMachine` should own planning/verification; `WorkflowEngine` should own step execution.

3. **Refactor AutomationLoop._build_project() into WorkflowEngine steps** — each phase (plan, generate, gates, build, test, verify) should be a `StepDefinition` in a `WorkflowEngine` workflow.

4. **Merge ControlLoop and AutomationLoop** — one canonical autonomous build loop for all project types.

5. **Add SchedulerQueue as the universal queue** — all async work submission goes through `SchedulerQueue` to leverage persistence, dependency resolution, and scoring.

6. **Wire PlannerStateMachine and AgentGraph into global EventBus** — currently silent on the bus; UI clients never see planner/agent events.
