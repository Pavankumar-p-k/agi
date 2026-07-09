# Workflow Architecture Audit — Phase 2 (Document 6)

> **Purpose:** Trace the entire workflow system — from step definition intake through execution, retry, compensation, recovery, artifact management, learning, and calibration.
>
> **Scope:** `core/workflow/` (15 files), integration with planner, activity, execution, and learning systems.

---

## Table of Contents

1. [Workflow System Overview](#1-workflow-system-overview)
2. [WorkflowEngine — The Orchestrator](#2-workflowengine--the-orchestrator)
3. [WorkflowStore — Persistence Layer](#3-workflowstore--persistence-layer)
4. [Workflow Lifecycle (State Machine)](#4-workflow-lifecycle-state-machine)
5. [Compensation System](#5-compensation-system)
6. [Recovery & Heartbeat](#6-recovery--heartbeat)
7. [Artifact Management](#7-artifact-management)
8. [Learning & Calibration System](#8-learning--calibration-system)
9. [Event System](#9-event-system)
10. [Execution Graph & Tracker](#10-execution-graph--tracker)
11. [LongHorizonFSM](#11-longhorizonfsm)
12. [Integration Points](#12-integration-points)
13. [Ownership Matrix](#13-ownership-matrix)
14. [Duplication Analysis](#14-duplication-analysis)
15. [Findings](#15-findings)
16. [Recommendations](#16-recommendations)

---

## 1. Workflow System Overview

### Architecture

```
  StepDefinition (from planner/agent)
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │                  WorkflowEngine                      │
  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
  │  │ Lifecycle │  │ Compensa-│  │ Recovery/Heart-  │  │
  │  │  Manager  │  │   tion   │  │    beat Monitor  │  │
  │  └──────────┘  └──────────┘  └──────────────────┘  │
  └──────────────────────┬──────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
      WorkflowStore           ArtifactStore
      (SQLite, 5 tables)      (via WorkflowStore)
              │
              ▼
      ┌──────────────────────────────────────────────────┐
      │               Learning System                     │
      │  WorkflowHistoryStore → CalibrationEngine →      │
      │                       WorkflowCalibrationStore   │
      │         → Predictions → DecisionEvidence         │
      └──────────────────────────────────────────────────┘
```

### File Inventory (15 files)

```
core/workflow/
├── __init__.py              — Public API re-exports
├── models.py                — WorkflowStatus, StepStatus, WorkflowStep,
│                               WorkflowInstance, StepDefinition
├── engine.py                — WorkflowEngine (606 lines) — main orchestrator
├── storage.py               — WorkflowStore (487 lines) — SQLite persistence
├── recovery.py              — recover_active_workflows() — crash recovery
├── artifact_store.py        — ArtifactStore + ArtifactRef
├── context.py               — ExecutionContext + ContextManager
├── events.py                — Re-exports workflow event constants
├── heartbeat_monitor.py     — HeartbeatMonitor — periodic stale detection
├── graph.py                 — ExecutionGraph + ExecutionNode
├── tracker.py               — ExecutionTracker + FocusMode
├── recorder.py              — WorkflowExecutionRecorder — outcome persistence
├── calibration.py           — WorkflowCalibrationEngine — metrics computation
├── learning_models.py       — WorkflowFingerprint, WorkflowOutcome,
│                               WorkflowTemplate, RecoveryMode
└── learning_store.py        — WorkflowHistoryStore + WorkflowCalibrationStore
└── long_horizon_fsm.py      — LongHorizonFSM (639 lines) — deterministic
                                multi-phase FSM
```

---

## 2. WorkflowEngine — The Orchestrator

### 2.1 Class Summary

| Property | Value |
|----------|-------|
| **File** | `core/workflow/engine.py` |
| **Lines** | 606 |
| **Backend** | `WorkflowStore` (SQLite), `ArtifactStore`, `ContextManager` |
| **Async** | Yes — each workflow runs as an `asyncio.Task` |
| **Running state** | `self._running: dict[str, asyncio.Task]` |

### 2.2 Public Interface

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `start_workflow` | `(workflow_type, steps: list[StepDefinition], session_id, owner, timeout_seconds, execution_context, parent_workflow_id, retry_budget, launch_background)` | `WorkflowInstance` | Creates and launches workflow |
| `resume_workflow` | `(workflow_id)` | None | Resumes after crash |
| `cancel_workflow` | `(workflow_id)` | None | Cancels running workflow |
| `get_status` | `(workflow_id)` | `dict` | Status + progress |
| `list_workflows` | `(status, limit)` | `list[WorkflowInstance]` | Filtered listing |

### 2.3 Internal Methods

| Method | Purpose |
|--------|---------|
| `_run_workflow(wf, start_time)` | Main execution loop — iterates steps, handles retry/compensation |
| `_execute_step(wf, step, context)` | Executes single step via `execute_tool_block()` |
| `_compensate_workflow(wf)` | Reverse-order compensation of completed steps |
| `_record_workflow_outcome(wf, start_time)` | Non-blocking outcome recording |
| `_trigger_improvement_detection()` | Auto-generates improvement proposals after terminal states |

### 2.4 Execution Flow

```
start_workflow()
  │
  ├── Generate IDs (wf_<hex>, step_<wf_id>_s<idx>)
  ├── Create WorkflowInstance (status=PENDING)
  ├── Persist via WorkflowStore.create_workflow()
  ├── Record goal/agent tasks via ActivityManager
  ├── Create ExecutionContext
  ├── Emit WORKFLOW_STARTED event
  └── Launch asyncio.Task(_run_workflow())
        │
        ▼
  _run_workflow()
    │
    ├── Set status=RUNNING
    ├── Loop over wf.steps:
    │   ├── Update last_heartbeat
    │   ├── Skip COMPLETED steps
    │   ├── PENDING → _execute_step()
    │   ├── FAILED → retry if budget allows, else compensate/fail
    │   └── Emit step events
    ├── All done → COMPLETED
    ├── Unrecoverable → FAILED
    ├── Emit terminal event
    ├── Record outcome
    └── Trigger improvement detection
```

---

## 3. WorkflowStore — Persistence Layer

### 3.1 Database Schema (5 tables in `data/workflow.db`)

#### `workflow_instances`

| Column | Type | Notes |
|--------|------|-------|
| `workflow_id` | TEXT PK | `wf_<hex>` |
| `workflow_type` | TEXT NOT NULL | Template type |
| `status` | TEXT NOT NULL | WorkflowStatus enum |
| `current_step` | INTEGER | Index into steps |
| `created_at` | TEXT NOT NULL | ISO datetime |
| `updated_at` | TEXT NOT NULL | ISO datetime |
| `last_heartbeat` | TEXT NOT NULL | ISO datetime |
| `session_id` | TEXT | Session association |
| `owner` | TEXT | Owner identifier |
| `timeout_seconds` | INTEGER nullable | Global timeout |
| `retry_count` | INTEGER | Total retries |
| `retry_budget` | INTEGER | Max retries |
| `parent_workflow_id` | TEXT nullable | For nesting |
| `workflow_version` | INTEGER | Version counter |
| `execution_context` | TEXT | JSON blob |
| `artifacts` | TEXT | JSON list |
| `compensated_steps` | TEXT | JSON list of step IDs |

#### `workflow_steps`

| Column | Type | Notes |
|--------|------|-------|
| `step_id` | TEXT PK | `wf_id_s<idx>` |
| `workflow_id` | TEXT NOT NULL FK | Parent |
| `idempotency_key` | TEXT NOT NULL | For safe retry |
| `tool_name` | TEXT NOT NULL | Tool to invoke |
| `status` | TEXT | PENDING/RUNNING/COMPLETED/FAILED |
| `input_data` | TEXT | JSON |
| `output_data` | TEXT | JSON |
| `error` | TEXT nullable | Error message |
| `retry_count` | INTEGER | Per-step retries |
| `timeout_seconds` | INTEGER nullable | Per-step timeout |
| `max_retries` | INTEGER | Default 3 |
| `compensation_tool` | TEXT nullable | Undo tool |
| `compensation_data` | TEXT | JSON |
| `compensated` | INTEGER | Boolean flag |

#### `workflow_events` — Append-only event log
(workflow_id, event_type, data JSON, timestamp)

#### `workflow_contexts` — Execution context per workflow
(workflow_id PK, owner, session_id, variables_json, artifacts_json, metadata_json)

#### `workflow_artifacts` — Artifact metadata
(artifact_id PK, workflow_id FK, name, artifact_type, path, size_bytes, checksum, metadata_json)

### 3.2 Key Methods

| Method | Description |
|--------|-------------|
| `create_workflow(wf)` | Single-transaction insert of instance + all steps |
| `update_workflow(wf)` | Updates status, step, heartbeat, retry, context, artifacts, compensated_steps |
| `update_step(step)` | Updates step status, timing, output, error, retry, compensated |
| `get_workflow(id)` | Full fetch: instance + all steps |
| `list_active_workflows()` | RUNNING workflows |
| `append_event(event)` | Persist event |
| `create_context(ctx)` / `get_context(id)` / `update_context(ctx)` | Context CRUD |
| `create_artifact(ref)` / `get_artifact(id)` / `list_artifacts(wf_id)` / `search_artifacts(query)` | Artifact CRUD |

### 3.3 Thread Safety

Thread-safe via `threading.Lock()`. Each method opens/closes its own connection.

### 3.4 Migration System

`_init_db()` runs `ALTER TABLE ADD COLUMN` statements in try/except blocks for graceful schema evolution. Currently handles 6 post-creation columns.

---

## 4. Workflow Lifecycle (State Machine)

### 4.1 State Enum (WorkflowStatus)

```
PENDING ──→ RUNNING ──→ COMPLETED
                │
                ├──→ FAILED
                │       │
                │       └──→ COMPENSATING ──→ COMPENSATED
                │               │                │
                │               └──→ COMPENSATION_FAILED
                │
                └──→ CANCELLED

RUNNING → WAITING → RETRYING → RUNNING  (retry loop)
RUNNING → RECOVERING → RUNNING          (crash recovery)
```

### 4.2 Sub-statuses

| Status | Meaning | Next Statuses |
|--------|---------|--------------|
| `PENDING` | Created, not yet started | RUNNING |
| `RUNNING` | Actively executing | COMPLETED, FAILED, WAITING, RECOVERING, CANCELLED |
| `WAITING` | Async step in progress | RUNNING (resume) |
| `RETRYING` | Retry in progress | RUNNING (retry) |
| `RECOVERING` | Post-crash recovery | RUNNING (resume) |
| `COMPLETED` | All steps done | Terminal |
| `FAILED` | Unrecoverable failure | COMPENSATING |
| `CANCELLED` | Explicit cancellation | Terminal |
| `COMPENSATING` | Undoing completed steps | COMPENSATED, COMPENSATION_FAILED |
| `COMPENSATED` | All steps undone | Terminal |
| `COMPENSATION_FAILED` | Partial undo | Terminal |

### 4.3 Step Lifecycle

`PENDING → RUNNING → COMPLETED | FAILED`

Step-level retry: `FAILED → (reset to PENDING) → RUNNING` (up to `max_retries` times, subject to `retry_budget`).

### 4.4 StepDefinition (Input Contract)

```python
@dataclass
class StepDefinition:
    tool_name: str          # Tool to execute
    input_data: dict        # Parameters
    timeout_seconds: int | None
    max_retries: int = 3
    compensation_tool: str | None  # Tool to undo this step
    compensation_data: dict
```

This is the contract between planners/agents and the workflow engine.

---

## 5. Compensation System

### 5.1 Trigger

Compensation is triggered when a step fails and retries are exhausted, but other steps already completed successfully.

### 5.2 Algorithm

```
1. Gather COMPLETED steps that have compensation_tool set
2. If none → return (no compensation needed)
3. Set status = COMPENSATING
4. For each completed step IN REVERSE ORDER:
   a. Execute compensation_tool with compensation_data
   b. If fails → COMPENSATION_FAILED
   c. If succeeds → mark step.compensated = True
5. All compensated → status = COMPENSATED
```

### 5.3 Design Properties

| Property | Detail |
|----------|--------|
| **Order** | Reverse execution order (LIFO) |
| **Tool-based** | Uses same `execute_tool_block()` mechanism as normal steps |
| **Per-step** | Each step defines its own `compensation_tool` and `compensation_data` |
| **Cancellable** | Early exit if workflow is cancelled mid-compensation |
| **Persistent** | `compensated_steps` list tracks which steps were undone |
| **Failure mode** | Partial compensation => `COMPENSATION_FAILED` status |

---

## 6. Recovery & Heartbeat

### 6.1 Heartbeat Mechanism

- `_run_workflow()` updates `wf.last_heartbeat = datetime.utcnow()` at the start of each step-iteration
- `HeartbeatMonitor` runs as a background asyncio task every 10 seconds
- Staleness threshold: 60 seconds since last heartbeat
- `WorkflowInstance.is_stale` property: `True` if RUNNING/COMPENSATING with heartbeat > 60s

### 6.2 Recovery Flow (`recover_active_workflows()`)

```
For each workflow with status RUNNING, RECOVERING, or COMPENSATING:
  1. If heartbeat age < 60s → skip (still alive)
  2. Set status = RECOVERING, persist
  3. Call engine.resume_workflow()
  4. If COMPENSATING → resume as compensation task
  5. Emit WORKFLOW_RECOVERED event
```

### 6.3 Startup Integration

In `core/lifespan.py`:
1. Create `WorkflowEngine`
2. Run `recover_active_workflows(engine)` (async task)
3. Start `HeartbeatMonitor` (background task)
4. Both run during app startup

---

## 7. Artifact Management

### 7.1 ArtifactRef Data Model

```python
@dataclass
class ArtifactRef:
    artifact_id: str     # art_<hex>
    workflow_id: str
    name: str
    artifact_type: str   # e.g., "file", "image", "email"
    path: str            # Filesystem path
    size_bytes: int | None
    checksum: str | None # SHA-256 hex
    metadata: dict
```

### 7.2 ArtifactStore

| Method | Description |
|--------|-------------|
| `register_artifact(wf_id, name, type, path, metadata)` | Computes SHA-256 + size, creates record |
| `get_artifact(id)` | Fetch by ID |
| `list_artifacts(wf_id)` | Per-workflow listing |
| `search_artifacts(query)` | LIKE search on name/type/path |
| `delete_artifact(id)` | Remove record |

---

## 8. Learning & Calibration System

### 8.1 Architecture

```
WorkflowEngine → terminal state
       │
       ▼
WorkflowExecutionRecorder.record_workflow()
       │
       ├── Build WorkflowOutcome (fingerprint, success, duration, cost, quality, recovery_mode)
       │
       ▼
WorkflowHistoryStore.save_outcome()   (append-only, never overwritten)
       │
       ▼
WorkflowCalibrationEngine.recalibrate()
       │
       ├── Group outcomes by fingerprint granularity
       ├── Compute weighted stats (success_rate, avg_duration, avg_cost, avg_quality)
       ├── Apply time decay to confidence
       │
       ▼
WorkflowCalibrationStore.save_calibration()  (UPSERT — derived cache, overwritten)
       │
       ▼
DecisionEvidence.predict()  →  WorkflowCalibrationEngine.predict()
                                  │
                                  └── Fallback chain: most specific → least specific
```

### 8.2 RecoveryMode Enum (best → worst)

| Mode | Meaning |
|------|---------|
| `FIRST_TRY` | Completed without retries |
| `AFTER_RETRY` | Completed after step retries |
| `AFTER_REPLAN` | Completed after planner replanning |
| `AFTER_PROVIDER_SWAP` | Completed after provider switch |
| `AFTER_COMPENSATION` | Completed after compensation |
| `AFTER_HUMAN_APPROVAL` | After human intervention |
| `FAILED` | Did not complete |

### 8.3 WorkflowFingerprint

Deterministic key from: `task_type`, `complexity`, `project_size`, `languages`, `frameworks`, `capabilities`, `artifact_types`, `requirements`.

### 8.4 Fallback Chain

```
(4,3,2,1) — task_type + languages + frameworks + project_size  (most specific)
(4,3,2,0) — task_type + languages + frameworks
(4,3,0,0) — task_type + languages
(4,0,0,0) — task_type only
(0,0,0,0) — empty (least specific)
```

### 8.5 Calibration Metrics

Computed for each fingerprint level:
- `success_rate` = successes / total
- `avg_duration_ms`, `avg_cost`, `avg_quality`
- `first_try_rate`, `recovered_rate`, `failed_rate`
- `confidence` = evidence_count (40%) + variance (30%) + stability (30%)
- Time decay: `decayed_confidence = confidence × exp(-age_days / half_life_days)`

---

## 9. Event System

### 9.1 Event Types (15)

| Event | When |
|-------|------|
| `WORKFLOW_STARTED` | Workflow created |
| `WORKFLOW_RESUMED` | After crash recovery |
| `STEP_STARTED` | Step execution begins |
| `STEP_COMPLETED` | Step succeeds |
| `STEP_FAILED` | Step fails |
| `WORKFLOW_COMPLETED` | All steps done |
| `WORKFLOW_FAILED` | Unrecoverable failure |
| `WORKFLOW_CANCELLED` | Cancellation |
| `WORKFLOW_RECOVERED` | Crash recovery |
| `COMPENSATION_STARTED` | Compensation begins |
| `COMPENSATION_STEP_STARTED` | Per-step compensation |
| `COMPENSATION_STEP_COMPLETED` | Compensation step succeeds |
| `COMPENSATION_STEP_FAILED` | Compensation step fails |
| `WORKFLOW_COMPENSATED` | All compensation done |
| `COMPENSATION_FAILED` | Compensation overall fails |

### 9.2 Event Flow

Persisted to `workflow_events` table → broadcast via EventBus → WebSocket delivery.

---

## 10. Execution Graph & Tracker

### 10.1 ExecutionGraph

| Aspect | Detail |
|--------|--------|
| **File** | `core/workflow/graph.py` |
| **Structure** | Tree of `ExecutionNode` objects |
| **Operations** | `add_node()`, `insert_after()`, `remove_node()`, `reorder_children()` |
| **Node fields** | label, type, status, confidence, estimate, elapsed, files, artifacts, logs, children |
| **Purpose** | Runtime plan representation for the tracker |

### 10.2 ExecutionTracker

| Aspect | Detail |
|--------|--------|
| **File** | `core/workflow/tracker.py` |
| **Backend** | In-memory (`_graphs: dict[str, ExecutionGraph]`) |
| **Methods** | `create_goal()`, `complete_goal()`, `fail_goal()`, `add_node()`, `update_node()` |
| **FocusMode** | Singleton tracking active session, queue, pause state |
| **Events** | GOAL_CREATED, GOAL_COMPLETED, GOAL_FAILED, GOAL_UPDATED, plus 10 node events |

---

## 11. LongHorizonFSM

| Aspect | Detail |
|--------|--------|
| **File** | `core/workflow/long_horizon_fsm.py` |
| **Lines** | 639 |
| **States** | 10: START, PLAN, PREPARE, EXECUTE_PHASE, VALIDATE, ADVANCE, REPLAN, RECOVER, COMPLETE, FAIL |
| **Phases** | research → plan → build → test → repair → retest → deliver |
| **Loop detection** | Same tool 3x, same phase 3x, same state 8x, no artifacts after 8 actions |
| **Stall detection** | 30s without state transition |
| **Purpose** | Deterministic multi-phase state machine for long-running autonomous builds |

Not directly integrated with `WorkflowEngine` — lives alongside it for alternative use cases.

---

## 12. Integration Points

### 12.1 With Planner

```
Planner → AgentRouter → ParallelAgentExecutor
                                 │
                      BaseAgent.plan() → list[StepDefinition]
                                 │
                                 ▼
                         WorkflowEngine.start_workflow()
```

### 12.2 With Pipeline

```
PipelineExecutor.__init__()
  ├── Creates WorkflowEngine
  └── Wires WorkflowExecutionRecorder for learning feedback
```

### 12.3 With Activity System

```
start_workflow()     → ActivityManager.record_goal(), record_agent_tasks()
_execute_step()      → ActivityManager.record_task_result()
workflow completed   → ActivityManager.record_completion()
recorder             → ActivityStore lookups by workflow_id
```

### 12.4 With Decision/Evidence System

```
WorkflowCalibrationEngine.predict()
    → DecisionEvidence (workflow_success dimension, 25% weight)
```

### 12.5 With REST API

| Endpoint | Method | Handler |
|----------|--------|---------|
| `GET /api/workflows` | list | `WorkflowEngine.list_workflows()` |
| `GET /api/workflows/{id}` | get | `WorkflowEngine.get_status()` |
| `POST /api/workflows/{id}/resume` | resume | `WorkflowEngine.resume_workflow()` |
| `POST /api/workflows/{id}/cancel` | cancel | `WorkflowEngine.cancel_workflow()` |

### 12.6 With Agent Tools

| Tool | Action |
|------|--------|
| `do_workflow_start(content)` | Start from JSON definition |
| `do_workflow_resume(content)` | Resume by ID |
| `do_workflow_cancel(content)` | Cancel by ID |
| `do_workflow_status(content)` | Get status by ID |
| `do_workflow_list(content)` | List with status filter |

### 12.7 With Lifespan/Startup

```
app startup
  ├── Create WorkflowEngine
  ├── recover_active_workflows()
  └── Start HeartbeatMonitor
```

---

## 13. Ownership Matrix

| Component | Owner | Creator | Reader | Writer | Destroyer | Persistence | Lifetime |
|-----------|-------|---------|--------|--------|-----------|-------------|----------|
| **WorkflowEngine** | `core/workflow/engine.py` | Per-process | API, tools, agents | Self | Process death | In-memory (_running dict) | Process |
| **WorkflowStore** | `core/workflow/storage.py` | Per-instance (via engine) | Engine, API, recorder | Engine, API | Process death | SQLite (workflow.db) | Persistent |
| **WorkflowInstance** | WorkflowEngine | start_workflow() | get_status() | Self (transitions) | cancel/complete | WorkflowStore | Per-workflow |
| **WorkflowStep** | WorkflowEngine | start_workflow() | Engine loop | Engine (execute) | Compensation | WorkflowStore | Per-step |
| **WorkflowRecovery** | `core/workflow/recovery.py` | Lifespan startup | Recovery function | Recovery function | Process death | In-memory | Per-startup |
| **HeartbeatMonitor** | `core/workflow/heartbeat_monitor.py` | Lifespan startup | Self (loop) | Engine (heartbeat update) | Process death | In-memory (background task) | Process |
| **ArtifactStore** | `core/workflow/artifact_store.py` | Per-instance (via engine) | API, tools | Engine, tools | delete_artifact() | WorkflowStore | Persistent |
| **ExecutionContext** | `core/workflow/context.py` | start_workflow() | Steps, tools | Steps, tools | Workflow completion | WorkflowStore | Per-workflow |
| **ExecutionTracker** | `core/workflow/tracker.py` | Module import (singleton) | Progress routes | Progress routes | Process death | In-memory | Process |
| **ExecutionGraph** | `core/workflow/graph.py` | Tracker | Tracker, routes | Tracker | Process death | In-memory | Process |
| **WorkflowExecutionRecorder** | `core/workflow/recorder.py` | Per-instance (observer) | Engine (callback) | Self (record) | Process death | In-memory (delegates to stores) | Process |
| **WorkflowHistoryStore** | `core/workflow/learning_store.py` | Per-instance | Calibration, queries | Recorder | Not implemented | SQLite (workflow_learning.db) | Persistent |
| **WorkflowCalibrationStore** | `core/workflow/learning_store.py` | Per-instance | DecisionEvidence, queries | CalibrationEngine | clear() | SQLite (workflow_learning.db) | Persistent |
| **WorkflowCalibrationEngine** | `core/workflow/calibration.py` | Per-instance | DecisionEvidence | Self (recalibrate) | Process death | In-memory (delegates to stores) | Process |
| **LongHorizonFSM** | `core/workflow/long_horizon_fsm.py` | Per-instance | Automation loop | Automation loop | Process death | In-memory | Per-execution |

---

## 14. Duplication Analysis

### 14.1 Workflow vs LongHorizonFSM

| Dimension | WorkflowEngine | LongHorizonFSM |
|-----------|---------------|----------------|
| **Purpose** | General-purpose sequential step executor | Multi-phase LLM execution FSM |
| **States** | 11 (PENDING→COMPLETED with retry/compensation) | 10 (START→FAIL with phases) |
| **Step type** | Tool-based (ToolBlock) | Agent action-based (allowed_tools per state) |
| **Persistence** | Full SQLite (5 tables) | None (serializable via context dict) |
| **Recovery** | Heartbeat + WorkflowRecovery | Manual (from context dict) |
| **Compensation** | Reverse-order tool execution | None |
| **Learning** | Full history + calibration | None |
| **Overlap** | Both execute sequential steps with retry | Low — different abstraction levels |

### 14.2 WorkflowStore vs Other Store in workflow.db

`WorkflowStore` is one of 4 systems sharing `data/workflow.db`:

| Store | Tables | Prefix |
|-------|--------|--------|
| WorkflowStore | workflow_instances, workflow_steps, workflow_events, workflow_contexts, workflow_artifacts | `workflow_*` |
| PlanStore | plans | `plans` |
| ActivityStore | activity_nodes, activity_edges | `activity_*` |
| KnowledgeStore | knowledge_items, experience_summaries | `knowledge_*` |

This is a shared-database pattern, not duplication — each store manages its own tables.

### 14.3 ExecutionGraph/Tracker vs WorkflowEngine

| Dimension | ExecutionGraph + Tracker | WorkflowEngine |
|-----------|----------------------|---------------|
| **Role** | Runtime goal representation + lifecycle | Step execution orchestrator |
| **Backend** | In-memory | SQLite + async tasks |
| **Recovery** | None (volatile) | Full (heartbeat + recovery) |
| **Relationship** | Tracker creates goals, engine executes them | Engine records steps into tracker's activity system |
| **Overlap** | Low — complementary, not duplicative | |

### 14.4 WorkflowHistoryStore (separate DB)

Workflow learning data lives in a dedicated database (`workflow_learning.db`) separate from `workflow.db`. This is intentional — append-only history should not share a database with transactional workflow state.

---

## 15. Findings

### F-1: Well-Designed Architecture with No Major Duplication
Unlike the memory and planner systems, the workflow system has a single orchestrator (`WorkflowEngine`), a single persistence layer (`WorkflowStore`), and a well-defined input contract (`StepDefinition`). No significant internal duplication.

### F-2: WorkflowRecovery and HeartbeatMonitor Provide Production-Grade Resilience
Heartbeat-based stale detection (10s check, 60s threshold) plus automatic recovery on startup make this the most resilient subsystem in the codebase. The recovery mechanism handles both RUNNING and COMPENSATING states.

### F-3: Learning System Is Feature-Complete but Loosely Coupled
The WorkflowHistoryStore → CalibrationEngine → CalibrationStore pipeline works, but outcomes feed back into decision-making only if DecisionEvidence explicitly queries `predict()`. There is no automatic weight update mechanism.

### F-4: Idempotency Keys Exist but Are Not Enforced
`WorkflowStep.idempotency_key` is generated (`<wf_id>_s<idx>`) but never checked for duplicate execution. The engine trusts that a step will not be re-executed if already `COMPLETED` (via the skip-COMPLETED check), but there is no deduplication at the step level.

### F-5: Compensation Is Tool-Dependent
Compensation must be explicitly designed into each `StepDefinition`. There is no automatic compensation for write operations (e.g., file creation, database writes). If `compensation_tool` is not set, compensation is skipped.

### F-6: LongHorizonFSM Is Unintegrated
The 639-line state machine exists alongside `WorkflowEngine` but is not wired into it. It duplicates the concept of sequential state execution without sharing any code or interfaces with the main workflow system.

### F-7: ExecutionTracker Is In-Memory with No Recovery
The tracker's `_graphs` dict is volatile. On process restart, all in-progress goal graphs are lost. WorkflowEngine steps survive (via SQLite + recovery) but their graph representation in the tracker does not.

### F-8: WorkflowStore Schema Migrations Are Best-Effort
The `_init_db()` migration system uses try/except around each `ALTER TABLE` — if a migration fails, the system continues silently with a potentially outdated schema.

### F-9: No Workflow Timeout Enforcement
Global `timeout_seconds` is stored but never enforced in the execution loop. Per-step timeouts are enforced via `asyncio.wait_for()`, but the overall workflow does not have a deadline check.

### F-10: Calibration Confidence Decay Is Applied but Not Tuned
The time-decay formula (`confidence × exp(-age_days / half_life_days)`) uses a hardcoded half-life. There is no mechanism to tune this based on observed prediction accuracy.

---

## 16. Recommendations

### R-1: (Low) Enforce Idempotency Keys
Check `idempotency_key` before step execution. If a step with the same key was already completed, skip it. This would make retry-after-crash truly safe.

### R-2: (Low) Add Workflow-Level Timeout Enforcement
Check `timeout_seconds` in the execution loop and transition to FAILED if exceeded. Currently only per-step timeouts are enforced.

### R-3: (Low) Wire LongHorizonFSM into WorkflowEngine
Either refactor LongHorizonFSM to use `StepDefinition` and run via `WorkflowEngine`, or extract shared state-machine logic into a common base class.

### R-4: (Low) Persist ExecutionGraph for Recovery
Add an `execution_graphs` table to `WorkflowStore` so that the tracker's goal graphs survive restarts. This would enable full recovery of the goal visualization layer.

### R-5: (Low) Add Automatic Compensation Registration
Create a registry of common compensation strategies (e.g., `create_file` → `delete_file`, `send_email` → no-op) so steps don't need to define `compensation_tool` manually.

### R-6: (Low) Tune Calibration Half-Life from Accuracy Data
Use the `PlanOutcomeStore` prediction-vs-actual data to automatically adjust the calibration confidence half-life for each template type.

### R-7: (Low) Add Schema Migration Versioning
Replace try/except migrations with a versioned schema system (schema_version table, sequential migrations). This would prevent silent migration failures.
