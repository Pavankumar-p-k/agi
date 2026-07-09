# Planner Architecture Audit — Phase 1 (Document 5)

> **Purpose:** Trace every planning system in the codebase — from goal intake through decomposition, template matching, evidence gathering, state machine execution, health monitoring, and replanning.
>
> **Scope:** All planner classes across `core/planner/`, `brain/planner/`, pipeline stages, specialized planners, and goal management systems.

---

## Table of Contents

1. [Planner System Overview](#1-planner-system-overview)
2. [Core Planner (`core/planner/`)](#2-core-planner-coreplanner)
3. [Brain Planner (`brain/planner/`)](#3-brain-planner-brainplanner)
4. [Pipeline Planner Stages](#4-pipeline-planner-stages)
5. [Goal Management Systems](#5-goal-management-systems)
6. [Specialized Planners](#6-specialized-planners)
7. [Plan Execution & State Machine](#7-plan-execution--state-machine)
8. [Evidence, Health, & Replanning](#8-evidence-health--replanning)
9. [Goal Decomposition Strategy](#9-goal-decomposition-strategy)
10. [Ownership Matrix](#10-ownership-matrix)
11. [Duplication Analysis](#11-duplication-analysis)
12. [Integration Points](#12-integration-points)
13. [Findings](#13-findings)
14. [Recommendations](#14-recommendations)

---

## 1. Planner System Overview

### Four Distinct Planner Subsystems

| System | Location | Approach | Output | Status |
|--------|----------|----------|--------|--------|
| **Core Planner** | `core/planner/` (15 files) | Template-based + keyword decomposition → evidence-scored state machine | `SubGoal` tree + `ExecutionPlan` | Active — primary workflow planner |
| **Brain Planner** | `brain/planner/` (3 files) | DAG-based fixed 3-node structure | `TaskGraph` (DAG) | Active — autonomous agent planner |
| **Pipeline Planner** | `core/pipeline/stages/planner.py` | Flat step list from reasoning assessment | `context.plan` (dict) | Active — inline pipeline planning |
| **Specialized Planners** | Scattered across `core/` | Domain-specific (research, browser, code, horizon, strategy) | Varied | Active — independent |

### Goal Management Systems

| System | Location | Backend | Status |
|--------|----------|---------|--------|
| **GoalManager** | `brain/goals/goal_manager.py` | SQLite (`goals.db` or `brain.db`) | Active — primary goal CRUD |
| **PlanStore** | `core/planner/store.py` | SQLite (`workflow.db`, `plans` table) | Active — plan tree storage |
| **PlanManager** | `core/plan_manager.py` | JSON files (`data/plans/`) | Legacy |
| **ExecutionTracker** | `core/workflow/tracker.py` | In-memory (`_graphs` dict) | Active — runtime goal tracking |

---

## 2. Core Planner (`core/planner/`)

### 2.1 File Inventory (15 files)

```
core/planner/
├── __init__.py          — Exports: PlannerTemplate, ExecutionPlan, SubGoal, PlannerExecutor,
│                          PlannerStateMachine, State, GoalDecomposer, classify, extract_parameters,
│                          get_template, list_templates, match_required_tools, TEMPLATES
├── models.py            — PlannerTemplate, ExecutionPlan, SubGoal (dataclasses)
├── classifier.py        — classify(), extract_parameters() — keyword-based template matching
├── templates.py         — 4 workflow templates, tool-to-step mappings
├── decomposer.py        — GoalDecomposer — deterministic keyword-based decomposition
├── store.py             — PlanStore — SQLite persistence for plans
├── executor.py          — PlannerExecutor — plan creation, step tracking, enforcement
├── state_machine.py     — PlannerStateMachine — full lifecycle (7 states)
├── strategies.py        — StrategyGenerator — multi-strategy candidate generation (6 strategies)
├── comparison.py        — ComparativeScorer — 5-dimension candidate scoring
├── evidence.py          — PlanEvidenceEngine — evidence from 5 stores
├── outcomes.py          — PlanOutcomeStore — prediction vs actual tracking
├── health.py            — PlanHealthEngine — 7-signal health evaluation
└── replan.py            — ReplanEngine — alternative plan generation with deltas
```

### 2.2 Core Data Structures

**`SubGoal`** — Recursive tree node:
```
id, description, template_id, step_name, agent_id,
children: list[SubGoal], parameters: dict,
status: str, error: Optional[str]
```
Properties: `is_leaf`, `is_complete`. Method: `flatten()` → depth-first leaf list.

**`ExecutionPlan`** — Linear step tracking against template:
```
template_id, parameters: dict,
steps: list, completed_steps: list,
pending_steps: list, failed_steps: list,
current_index: int
```
Properties: `is_complete`, `missing_steps`, `halted_early`.

**`PlannerTemplate`** — Workflow template definition:
```
template_id, name, description,
required_steps: list, optional_steps: list,
success_conditions: list, failure_conditions: list
```

### 2.3 Template Registry (4 Templates)

| Template ID | Required Steps | Steps |
|-------------|---------------|-------|
| `research_build_validate_email` | 5 | research, build, test, validate, email |
| `android_app_build` | 5 | research, build, test, apk, email |
| `research_build_email` | 3 | research, build, email |
| `build_validate_notify` | 4 | build, test, validate, notify |

Tool-to-step mappings: `browser_navigate`→research, `build_project`→build, `run_tests`→test, `send_email`→email, etc.

### 2.4 PlanStore Schema

| Column | Type | Purpose |
|--------|------|---------|
| `id` | TEXT PK | UUID |
| `goal` | TEXT | Original goal string |
| `status` | TEXT | draft → approved → executing → completed/failed |
| `root_node` | TEXT | JSON serialized SubGoal tree |
| `created_at` | TEXT | ISO timestamp |
| `updated_at` | TEXT | ISO timestamp |

### 2.5 Class Interface Summary

| Class | Lines | Key Methods |
|-------|-------|-------------|
| `GoalDecomposer` | ~200 | `decompose(goal) → SubGoal` |
| `PlanStore` | ~120 | `create()`, `get()`, `list_all()`, `update_status()`, `update_node()`, `delete()` |
| `PlannerExecutor` | ~200 | `create_plan()`, `decompose_goal()`, `record_step()`, `get_missing_steps()`, `inject_task()`, `finalize()` |
| `PlannerStateMachine` | ~250 | `run(goal) → dict`, `_route_leaves()`, `_execute_agents()`, `_verify()` |
| `StrategyGenerator` | ~150 | `generate(goal, strategies) → list[dict]` |
| `ComparativeScorer` | ~120 | `compare(goal, candidates) → dict` |
| `PlanEvidenceEngine` | ~200 | `get_evidence(plan_id)`, `get_risks()`, `get_alternatives()`, `get_confidence()` |
| `PlanOutcomeStore` | ~80 | `create()`, `record_execution()`, `record_completion()` |
| `PlanHealthEngine` | ~180 | `evaluate(plan_id) → health_level` |
| `ReplanEngine` | ~100 | `get_options(plan_id) → dict` |

---

## 3. Brain Planner (`brain/planner/`)

### 3.1 Structure

```
brain/planner/
├── __init__.py     — Exports: TaskGraph, TaskNode, Planner
├── planner.py      — Planner class: plan(), replan()
└── task_graph.py   — TaskNode, TaskGraph (DAG)
```

### 3.2 Classes

**`Planner`** — Fixed 3-node DAG planner:
- `plan(goal, context) → TaskGraph` — always produces: `create_directory → write_file → run_command`
- `replan(graph, failed_node_id, error_context) → TaskGraph` — removes failed node, merges alternative
- "LLM is unreliable for structured JSON output" is the stated reason for fixed structure

**`TaskGraph`** — DAG-based execution graph:
- `add_node()`, `remove_node()`, `add_dependency()`
- `has_cycle()` (DFS), `topological_sort()` (Kahn's algorithm)
- `get_execution_queue()` — ready nodes sorted by dependency count
- `get_critical_path()` — longest path
- `mark_completed()`, `mark_failed()`, `mark_running()`
- `progress() → float`, `completed_count`, `failed_count`, `pending_count`

**`TaskNode`** — DAG node dataclass:
- `id`, `label`, `description`, `status`, `depends_on`, `agent_type`, `tools_allowed`, `result`, `error`, `metadata`

### 3.3 Integration

Used by `UnifiedBrain.plan_goal()`:
1. Fetches Goal from GoalManager
2. Calls brain `Planner.plan()` → produces TaskGraph
3. Executes via `execute_with_verification()`
4. Stores results back to GoalManager

---

## 4. Pipeline Planner Stages

### 4.1 PlannerStage

| Property | Value |
|----------|-------|
| **File** | `core/pipeline/stages/planner.py` |
| **Stage position** | After ReasonerStage (stage 11) |
| **Input** | `context.reasoning_assessment`, `context.raw_input` |
| **Logic** | If complexity=="simple" → single "respond" step. Else → decompose assessment requirements into steps (research, browser, coding, respond) |
| **Output** | `context.plan = {"goal": raw_input, "steps": [...]}` |

### 4.2 PlanValidatorStage

| Property | Value |
|----------|-------|
| **File** | `core/pipeline/stages/plan_validator.py` |
| **Stage position** | After PlannerStage (stage 12) |
| **Validation rules** | Plan not None, steps non-empty list, each step has intent+objective, constraints must be dict |
| **Output** | `context.plan_validated = True/False` |

---

## 5. Goal Management Systems

### 5.1 GoalManager (`brain/goals/`)

| Aspect | Detail |
|--------|--------|
| **File** | `brain/goals/goal_manager.py` |
| **Model** | `Goal` dataclass (objective, status, progress, priority, parent_goal_id, blockers, next_action, tags, result, deadline, id, timestamps) |
| **Status enum** | `ACTIVE`, `PAUSED`, `COMPLETED`, `FAILED`, `CANCELLED` |
| **Backend** | SQLite (WAL mode, `threading.Lock`) — table `goals` with indexes on status, priority, parent_goal_id |
| **DB path** | Configurable — used by `brain/` subsystems at `data/brain.db` or `data/goals.db` |
| **CRUD** | `create()`, `get()`, `update()`, `delete()` |
| **Queries** | `list_active()`, `list_by_status()`, `get_highest_priority()`, `get_goal_tree()`, `count()` |
| **Lifecycle** | `add_blocker()`, `remove_blocker()`, `set_progress()`, `complete()`, `fail()` |

### 5.2 GoalGenerator (`brain/goal_generator.py`)

Autonomous goal creation from world observation:
- Disk < 10% free → cleanup goal (priority 8)
- CPU > 90% → investigate goal (priority 7)
- LLM fallback for complex opportunities/threats (15s timeout)
- Deduplication via 50-char prefix match
- Publishes `GoalAutoCreated` event

### 5.3 PlanManager (`core/plan_manager.py`) — Legacy

| Aspect | Detail |
|--------|--------|
| **Backend** | JSON files in `data/plans/` |
| **Lifecycle** | pending_setup → pending_approval → approved/rejected → executing → completed |
| **Methods** | `create_plan()`, `get_plan()`, `approve_plan()`, `reject_plan()`, `execute_plan()` |
| **Status** | Legacy — predates PlanStore |

### 5.4 ExecutionTracker (`core/workflow/tracker.py`)

| Aspect | Detail |
|--------|--------|
| **Backend** | In-memory `_graphs: dict[str, ExecutionGraph]` |
| **Methods** | `create_goal()`, `complete_goal()`, `fail_goal()`, `add_node()`, `update_node()` |
| **Events** | GOAL_CREATED, GOAL_COMPLETED, GOAL_FAILED, GOAL_UPDATED, NODE_CREATED, etc. |

---

## 6. Specialized Planners

| Planner | File | Purpose | Method |
|---------|------|---------|--------|
| `ResearchPlanner` | `core/research/planner.py` | Question-driven research with sub-goals | `create_plan()`, `refine()` |
| `ChangePlanner` | `core/coding/change_planner.py` | Code change plan generation | LLM-based structured plan |
| `MigrationPlanner` | `core/coding/architecture_reasoning.py` | Multi-step code migration | Uses ChangePlanner |
| `HorizonPlanner` | `core/horizon_planner.py` | Long-term goal → milestones | JSON file-backed |
| `BrowserPlanner` | `core/tools/browser_planner.py` | Browser automation planning | Strategic sub-goal decomposition |
| `StrategyGenerator` | `core/strategy/v2/planner.py` | Strategic planning for codebase improvement | v2 strategy framework |
| `SelfModificationPlanner` | `core/self_modification/planner.py` | Self-modification planning | Phase-based |
| `OrchestrationPlanner` | `core/providers/orchestration/planner.py` | Provider-level orchestration | Capability-driven |
| `GoalGenerator` | `brain/goal_generator.py` | Autonomous goal creation | World observation + LLM |

---

## 7. Plan Execution & State Machine

### 7.1 State Machine (PlannerStateMachine)

```
State: PLAN → DECOMPOSE → ROUTE → EXECUTE → VERIFY → COMPLETE
                                        ↓              ↓
                                     (loop)         FAILED
```

**State Details:**

| State | Action | Output |
|-------|--------|--------|
| `PLAN` | classify goal → template ID | template_id |
| `DECOMPOSE` | GoalDecomposer.decompose() → SubGoal tree | root SubGoal |
| `ROUTE` | AgentRouter → assign agent_ids to leaves | agent assignments |
| `EXECUTE` | ParallelAgentExecutor or callback | artifacts |
| `VERIFY` | Template-specific artifact checks (max 2 retries) | passed/failed |
| `COMPLETE` | Record success | result dict |
| `FAILED` | Record failure (after max retries) | error dict |

### 7.2 Execution Modes

1. **Native agent routing** (recommended): `PlannerStateMachine._execute_agents()` builds dependency graph from phases, runs `ParallelAgentExecutor`
2. **Callback-based** (legacy): Caller provides `execute_fn(step)`
3. **Direct enforcement**: `PlannerExecutor.inject_task()` bypasses LLM choice gate and forces execution of a required step

### 7.3 Plan Evolution

When plans fail during execution, the `AutomationLoop._plan_evolution()` (in `brain/automation/loop.py`) can mutate the plan mid-execution using LLM root-cause analysis after 3+ build failures.

---

## 8. Evidence, Health, & Replanning

### 8.1 Evidence Sources (PlanEvidenceEngine)

| Source | Store | Signal |
|--------|-------|--------|
| Past experiences | KnowledgeStore (experience_summaries) | Similar goal outcomes |
| Knowledge items | KnowledgeStore (knowledge_items) | Patterns, principles, heuristics |
| Research facts | FactStore | Domain knowledge |
| Failure patterns | PatternFailureMemory | Known error patterns |
| Activity graph | ActivityStore | Historical stats |
| Similarity scorer | Strategy → SimilarityScorer | Experience matching score |

### 8.2 Health Signals (PlanHealthEngine)

| Signal | Source | Threshold for penalty |
|--------|--------|----------------------|
| Confidence collapse | PlanEvidenceEngine.confidence | < 0.3 below baseline |
| Risk trend | PlanEvidenceEngine.risks | Critical > 1 or Warning > 3 |
| Outcome accuracy | PlanOutcomeStore | < 50% prediction accuracy |
| Workflow failures | SchedulerStore | Any failed activities |
| Schedule delays | SchedulerStore | Activity > 24h overdue |
| Knowledge updates | KnowledgeStore | New relevant items since creation |
| Research contradictions | FactStore.find_contradictions() | Any contradictions |

**Health levels:** `healthy` (≥0.80) → `watch` (≥0.55) → `replan_recommended` (≥0.30) → `replan_required` (<0.30)

### 8.3 Replanning (ReplanEngine)

- Generates alternative strategies via StrategyGenerator
- Scores each candidate via ComparativeScorer
- Computes deltas (overall_change, confidence_change, expected_improvements)
- Returns sorted options

### 8.4 Prediction vs Actual (PlanOutcomeStore)

Tracks: predicted_confidence, predicted_success_rate, predicted_duration_days, predicted_risk_score, predicted_cost vs actual_success, actual_duration_seconds, actual_failures, actual_cost.

---

## 9. Goal Decomposition Strategy

### 9.1 Core Planner (GoalDecomposer) — Purely Deterministic

No LLM calls. Keyword-driven heuristics:

1. **Feature extraction** (`_find_features`): Parses "with X, Y, Z", "including X, Y, Z", "featuring X, Y, Z" patterns
2. **Project components** (`_find_project_components`): Detects "Requirements:" sections, "X with Y" patterns, sentence-list goals
3. **Phase detection** (`_find_phases`): Splits on "then", "next", "after that", "finally"
4. **Sub-goal rules** (16 rules): Maps keyword patterns to step names (research, build, test, validate, email, notify, codegen, security, docs, analytics, synthesize, monitor, planning, extraction)

### 9.2 Classification (classifier.py) — Purely Deterministic

4 keyword rules mapping goal text to template IDs:
- `["android","apk"]` → `android_app_build`
- `["research","build","validate","email"]` → `research_build_validate_email`
- `["research","build","email"]` → `research_build_email`
- `["build","test","validate","notify"]` → `build_validate_notify`

### 9.3 Strategy Inference (StrategyGenerator) — Purely Deterministic

Keyword-based strategy detection (6 strategies): flutter, native_android, react_native, web_first, ios_first, backend_first.

---

## 10. Ownership Matrix

| Component | Owner | Creator | Reader | Writer | Destroyer | Persistence | Lifetime |
|-----------|-------|---------|--------|--------|-----------|-------------|----------|
| **GoalManager** | `brain/goals/goal_manager.py` | Module constructor | brain subsystems, routes | brain subsystems, routes | Process death | SQLite | Persistent |
| **PlanStore** | `core/planner/store.py` | Per-instance | PlannerExecutor, analytics | PlannerExecutor, routes | delete() method | SQLite (workflow.db) | Persistent |
| **PlanOutcomeStore** | `core/planner/outcomes.py` | Per-instance | PlanHealthEngine | PlannerExecutor | Not implemented | SQLite (workflow.db) | Persistent |
| **GoalDecomposer** | `core/planner/decomposer.py` | Per-instance | PlannerStateMachine, PlanStore | None (pure function) | N/A | None | Per-call |
| **PlannerStateMachine** | `core/planner/state_machine.py` | Per-instance | Executor | Self (state transitions) | Process death | In-memory | Per-plan |
| **PlannerExecutor** | `core/planner/executor.py` | Per-instance | Pipeline, benchmarks | Pipeline, benchmarks | Process death | In-memory | Per-process |
| **PlanManager** (legacy) | `core/plan_manager.py` | Module constructor | Legacy routes | Legacy routes | Process death | JSON files | Persistent |
| **ExecutionTracker** | `core/workflow/tracker.py` | Module constructor | Progress routes | Progress routes | Process death | In-memory | Process |
| **Planner** (brain) | `brain/planner/planner.py` | Module import | UnifiedBrain | UnifiedBrain | Process death | In-memory | Process |
| **TaskGraph** (brain) | `brain/planner/task_graph.py` | Planner.plan() | UnifiedBrain | Planner.replan() | Process death | Checkpoint (ProjectPersistence) | Per-goal |
| **StrategyGenerator** | `core/planner/strategies.py` | Per-instance | ReplanEngine | Self | Process death | In-memory | Per-call |
| **ComparativeScorer** | `core/planner/comparison.py` | Per-instance | ReplanEngine | Self | Process death | In-memory | Per-call |
| **PlanEvidenceEngine** | `core/planner/evidence.py` | Per-instance | PlanHealthEngine | Self | Process death | In-memory | Per-call |
| **PlanHealthEngine** | `core/planner/health.py` | Per-instance | ReplanEngine, monitoring | Self | Process death | In-memory | Per-call |
| **ReplanEngine** | `core/planner/replan.py` | Per-instance | Monitoring, automation | Self | Process death | In-memory | Per-call |
| **GoalGenerator** | `brain/goal_generator.py` | Per-instance | Self (auto) | GoalManager | Process death | In-memory | Process |
| **PlanStage** | `core/pipeline/stages/planner.py` | Stage factory | Pipeline | Self | Per-request | None | Per-request |
| **PlanValidatorStage** | `core/pipeline/stages/plan_validator.py` | Stage factory | Pipeline | Self | Per-request | None | Per-request |

---

## 11. Duplication Analysis

### 11.1 Goal Storage (3x overlap + 1 in-memory)

| System | Backend | Schema | Status |
|--------|---------|--------|--------|
| `GoalManager` (brain/) | SQLite | Goal dataclass (12 fields) | Active |
| `PlanStore` (core/) | SQLite | plan row with JSON root_node | Active |
| `PlanManager` (core/) | JSON files | Plan dataclass | Legacy |
| `ExecutionTracker` (core/) | In-memory | ExecutionGraph | Active |

**Impact:** Creating a goal in GoalManager does not create it in PlanStore, and vice versa. The pipeline PlannerStage creates its own flat plan dict that is never persisted to any store.

### 11.2 Planner Implementations (3x overlap)

| System | Approach | Output | When Used |
|--------|----------|--------|-----------|
| `core/planner/` | Template-based + keyword decomposition | SubGoal tree + ExecutionPlan | Workflow orchestration |
| `brain/planner/` | Fixed 3-node DAG | TaskGraph | Autonomous agent execution |
| Pipeline PlannerStage | Flat step list | context.plan dict | Inline request processing |

**Impact:** Three planners with three different output formats. No shared planner interface or protocol.

### 11.3 Decomposition (2x overlap)

| System | Approach | Entry Point |
|--------|----------|-------------|
| `core/planner/decomposer.py` | Keyword heuristics (16 rules) | `GoalDecomposer.decompose()` |
| `brain/cognitive_patterns.py` | LLM-based | `CognitivePatterns.plan()` |

### 11.4 Plan Lifecycle States (3x incompatible enums)

| System | States |
|--------|--------|
| PlanStore | draft → approved → executing → completed/failed |
| PlanManager | pending_setup → pending_approval → approved/rejected → executing → completed |
| PlannerStateMachine | PLAN → DECOMPOSE → ROUTE → EXECUTE → VERIFY → COMPLETE/FAILED |

### 11.5 Goal Status Enums (3x incompatible)

| System | Values |
|--------|--------|
| `brain/goals/goal.py` | ACTIVE, PAUSED, COMPLETED, FAILED, CANCELLED |
| `core/research/planner.py` | PENDING, IN_PROGRESS, ANSWERED, GAP, CONTRADICTED |
| `core/workflow/tracker.py` | active, completed, failed |

---

## 12. Integration Points

### 12.1 Pipeline Flow

```
ReceiveStage → LoadContextStage → ... → IntentStage → ReasonerStage
                                                          │
                                                          ▼
                                                    PlannerStage
                                                          │
                                                          ▼
                                                  PlanValidatorStage
                                                          │
                                                          ▼
                                              CapabilitySelectionStage → ExecutionStage
```

### 12.2 Memory & Knowledge Integration

```
PlannerStage                         PlanEvidenceEngine
    │                                       │
    ▼                                       ▼
context.plan ──→ Execution           KnowledgeStore (experiences, knowledge)
                                      PatternFailureMemory (failure patterns)
                                      FactStore (research facts)
                                      ActivityStore (historical stats)
                                      SimilarityScorer (experience matching)
                                                │
                                                ▼
                                          PlanHealthEngine
                                                │
                                                ▼
                                          ReplanEngine
```

### 12.3 Agent Integration

```
PlannerStateMachine._route_leaves()
    → AgentRouter.find_best_agent_for_subgoal()
    → ParallelAgentExecutor.execute()
```

### 12.4 Workflow Integration

```
PlanStore → PlanOutcomeStore → WorkflowHistoryStore
    │                              │
    ▼                              ▼
PlannerAnalytics             WorkflowCalibrationStore
    │
    ▼
PlannerImprovementDetector → PlannerExperimentManager
```

### 12.5 API Routes

| Route | Handler | System |
|-------|---------|--------|
| `/api/plans/goal` | Goal submission | PlanManager (legacy) |
| `/api/progress/goal` | Goal CRUD | ExecutionTracker |
| `/api/progress/goals?status=` | List goals | ExecutionTracker |
| `/api/progress/goal/{id}/complete` | Complete goal | ExecutionTracker |
| `/api/progress/goal/{id}/fail` | Fail goal | ExecutionTracker |

---

## 13. Findings

### F-1: Three Parallel Planner Systems with No Shared Interface
`core/planner/`, `brain/planner/`, and the pipeline `PlannerStage` all create plans independently with different output formats (`SubGoal` tree vs `TaskGraph` DAG vs flat dict). There is no `Planner` protocol or abstract base class.

### F-2: No LLM in Core Planning
The `GoalDecomposer`, `classifier`, and `StrategyGenerator` are entirely keyword/deterministic. This makes the system predictable but limits it to known patterns (4 templates, 16 sub-goal rules, 6 strategies). Any goal outside these patterns falls back to a flat single-step plan.

### F-3: Three Goal Storage Systems
`GoalManager` (SQLite), `PlanStore` (SQLite), and `PlanManager` (JSON) all store goal/plan data with incompatible schemas and no synchronization. The pipeline `PlannerStage` creates plan data that is never persisted at all.

### F-4: Three Incompatible Status Enums
PlanStore (4 states), PlanManager (6 states), and PlannerStateMachine (7 states) use different status values for the same lifecycle concept, making cross-system coordination error-prone.

### F-5: Brain Planner Produces a Fixed 3-Node DAG
The `brain/planner/Planner` always produces the same structure (`create_directory → write_file → run_command`). The code comment says "LLM is unreliable for structured JSON output" — this represents a known limitation, not a design choice.

### F-6: Evidence Engine Has Strong Integration but No Feedback Loop
`PlanEvidenceEngine` queries 5 stores for evidence, but there is no mechanism for plan outcomes to feed back into those stores' confidence/importance scores. The evidence flows one way.

### F-7: PlanHealthEngine Is Sophisticated but Underutilized
The 7-signal health evaluation system exists and is feature-complete, but it is not wired into any automatic replanning trigger. The `ReplanEngine.get_options()` must be called explicitly — there is no health-monitoring loop.

### F-8: PlanOutcomeStore tracks predictions vs actuals but nothing consumes it for learning
The outcome store records predicted vs actual for success, duration, risk, and cost — but no system uses this data to improve future predictions.

### F-9: Pipeline Planner and Core Planner Are Unconnected
`PlannerStage` (pipeline) creates a simple flat step list from reasoning assessment output. `core/planner/` creates hierarchical SubGoal trees. They operate on the same request but produce different plan representations, neither referencing the other.

### F-10: GoalManager and PlanStore Use Different Databases
GoalManager stores goals in `brain.db` (or `goals.db`), PlanStore stores plans in `workflow.db`. Querying across goal/plan boundaries requires cross-database joins that are not implemented.

### F-11: Decomposition Is Stateless
Each `GoalDecomposer.decompose()` call is entirely independent with no memory of previous decompositions. This means the same goal decomposed twice produces the same tree, even if the first execution failed and the system should try a different approach.

### F-12: StrategyGenerator Has 6 Strategies but Only One Is Usable
The 6 strategies (flutter, native_android, react_native, web_first, ios_first, backend_first) are all platform/language-specific. For non-software goals (research, data analysis, system administration), strategy generation returns empty.

---

## 14. Recommendations

### R-1: (Critical) Unify Planners Under a Common Interface
Define a `Planner` protocol or ABC with `create_plan(goal, context) → Plan` where `Plan` is a union type or common base. Migrate `core/planner/` as the primary implementation and deprecate `brain/planner/` and the pipeline `PlannerStage` flat-dict approach.

### R-2: (High) Unify Goal/Plan Storage
Merge `GoalManager` (goals with progress/blockers) and `PlanStore` (plan trees with lifecycle) into a single SQLite-backed store. The store should support both goal metadata and plan decomposition in a single schema, in a single database.

### R-3: (High) Add LLM-Based Decomposition as Fallback
Extend `GoalDecomposer` to use LLM-based decomposition when keyword rules cannot match the goal. This would handle the long tail of goals that current heuristics miss.

### R-4: (High) Wire PlanHealthEngine into Automatic Replanning
Add a monitoring loop that periodically evaluates active plans and triggers `ReplanEngine` when health drops below `replan_recommended`. This closes the evidence→health→replan loop.

### R-5: (Medium) Harmonize Status Enums
Define a single set of plan/goal lifecycle statuses used across all systems. Use an enum with clear transition rules.

### R-6: (Medium) Close the Prediction Feedback Loop
Use `PlanOutcomeStore` data to retrain/update prediction models. Feed accuracy metrics back into `PlanEvidenceEngine` confidence calculations.

### R-7: (Medium) Add Plan Persistence to Pipeline
The pipeline `PlannerStage` should persist its plan output to `PlanStore`, not just leave it in `context.plan`. This would enable health monitoring and replanning for pipeline-initiated plans.

### R-8: (Low) Link Brain Planner to Core Planner
Replace the fixed 3-node DAG in `brain/planner/` with the `core/planner/` implementation, or at minimum share the same `SubGoal`/`Plan` data structures. The brain planner's DAG capabilities (topological sort, critical path) could be added to core planner's execution model.

### R-9: (Low) Expand Template Registry
Add templates for common non-software workflows: data analysis, system administration, research, monitoring. Each template should have its own verification rules.

### R-10: (Low) Add Decomposition Memory
Cache decomposition results keyed by goal text hash so that re-execution of the same goal can adapt based on prior outcomes rather than producing the identical tree.
