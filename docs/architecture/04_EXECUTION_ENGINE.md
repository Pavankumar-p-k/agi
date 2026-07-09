# Execution Engine Audit — Phase 4 (Document 04)

> **Purpose:** Audit every execution engine in the system — who starts, who calls, who executes, who finishes, who publishes events, who writes memory, who updates UI. Produce ONE canonical execution graph and mark all duplicates.
>
> **DO NOT CHANGE CODE.** This is a read-only audit.

---

## 1. Engine Inventory

| # | Engine | File(s) | LOC | Purpose |
|---|--------|---------|-----|---------|
| 1 | Controller Loop | core/control_loop.py | 1132 | Full-stack build automation: interpret→plan→build→validate→fix→deploy |
| 2 | WorkflowEngine | core/workflow/engine.py | 606 | Durable multi-step execution with retries, compensation, events |
| 3 | PlannerStateMachine | core/planner/state_machine.py | 391 | PLAN→DECOMPOSE→ROUTE→EXECUTE→VERIFY→COMPLETE |
| 4 | Scheduler | core/scheduler/scheduler.py | 409 | Autonomous tick-based scheduler with worker pool |
| 5 | AutomationLoop | rain/automation/loop.py | ~1600 | Build automation loop: plan→generate→verify→build→test→verify→finish |
| 6 | StateGraph | core/graph/graph.py | 88 | Async node-by-node graph execution with SSE streaming |
| 7 | GraphExecutor | core/distribution/graph/executor.py | 155 | Distributed graph execution across workers |
| 8 | Pipeline Stage 14 | core/pipeline/stages/execution.py | 404 | Pipeline execution stage with ProviderManager fallback chain |
| 9 | UnifiedBrain | rain/UnifiedBrain.py | 543 | Full autonomous cognitive core |
| 10 | Pipeline Entry | core/pipeline/pipeline.py | 335 | Canonical 19-stage pipeline entry point |
| 11 | ParallelAgentExecutor | core/agents/parallel_executor.py | ~300 | Parallel agent execution with dependency graph |
| 12 | Scheduler Executors | core/scheduler/executors.py | 182 | Adapter layer between Scheduler and real subsystems |
| — | Central Tool Dispatcher | core/tools/execution.py | 3024 | All engines ultimately call this (except brain executors) |

---

## 2. Engine 1: Controller Loop (core/control_loop.py)

**Purpose:** "The heart of JARVIS autonomy" — interprets goals, plans, builds, validates, iterates until done.

### Execution Flow
`
START (called from agent_tools.py / external)
  project = ProjectState(name, description)
  plan = plan_site(description) → tasks
  goal = interpret_goal(description, plan)
  for task in tasks (parallel, MAX_PARALLEL=2):
    template_analyzer.analyze(task)
    if template match: execute shell command from SHELL_TASK_TEMPLATES
    else: AgentLauncher(task).run()
  real_validator.validate(): URL check, file existence, QualityScorer
  pattern_memory.lookup() → auto-fix if known
  plan_evolution() → mutate plan if stuck
  is_done()? → COMPLETE / FAILED
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | gent_tools.py (via do_build), CLI | Direct function call |
| **Calls engine** | Self — owns the entire loop | Synchronous with asyncio sub-tasks |
| **Executes work** | AgentLauncher, shell commands, QualityScorer | AgentLauncher spawns LLM agents |
| **Finishes** | Self — returns completion dict | "FAILED" or "COMPLETE" |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | None (does not use EventBus) |
| **Memory written** | core/pattern_failure_memory.py, checkpoint_manager.py |
| **UI updated** | None |

---

## 3. Engine 2: WorkflowEngine (core/workflow/engine.py)

**Purpose:** Durable multi-step execution with idempotency keys, retries, compensation, event publishing.

### Execution Flow
`
WorkflowEngine.start_workflow(type, steps, ...)
  UUID workflow_id, step_ids, idempotency_keys
  WorkflowStore.create_workflow() → SQLite (APPENDS event: WORKFLOW_STARTED)
  if launch_background: asyncio.create_task(_run_workflow(wf))

_run_workflow(wf):
  wf.status = RUNNING
  while wf.current_step < len(wf.steps):
    step = wf.steps[wf.current_step]
    if PENDING: _execute_step()
    if FAILED: check retry → retry or compensate

    _execute_step():
      step.status = RUNNING, APPENDS event: STEP_STARTED
      ToolBlock(tool_name, json.dumps(input_data))
      result = execute_tool_block(block, ...)   # ← calls core/tools/execution.py
      if success: step=COMPLETED, APPENDS event: STEP_COMPLETED
      else: step=FAILED, APPENDS event: STEP_FAILED
      activity_recorder.record_task_result()

  if all done: status=COMPLETED, APPENDS event: WORKFLOW_COMPLETED
  if failed: _compensate_workflow() or FAILED
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | core/tools/workflow_tools.py, agents, API | WorkflowEngine.start_workflow() |
| **Calls engine** | execute_tool_block() via core/tools/execution.py | Delegates actual tool execution |
| **Executes work** | core/tools/execution.py:execute_tool_block() | 3024-line dispatcher |
| **Finishes** | Self — sets COMPLETED/FAILED/COMPENSATED | Cleans _running dict |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | 12 types via _store.append_event() (SQLite records, NOT EventBus): WORKFLOW_STARTED, STEP_STARTED, STEP_COMPLETED, STEP_FAILED, WORKFLOW_COMPLETED, WORKFLOW_FAILED, WORKFLOW_CANCELLED, COMPENSATION_STARTED, COMPENSATION_STEP_STARTED, COMPENSATION_STEP_COMPLETED, COMPENSATION_STEP_FAILED, COMPENSATION_FAILED, WORKFLOW_COMPENSATED |
| **Memory written** | ctivity_recorder.record_goal(), ecord_agent_tasks(), ecord_task_result(), ecord_completion(), ecord_failure() |
| **UI updated** | _trigger_improvement_detection() on completion |

---

## 4. Engine 3: PlannerStateMachine (core/planner/state_machine.py)

**Purpose:** Deterministic state machine: PLAN→DECOMPOSE→ROUTE→EXECUTE→VERIFY→COMPLETE/FAILED.

### Execution Flow
`
PlannerStateMachine.run(goal):
  1. PLAN: classify(goal) → template_id. If none: FAILED
  2. DECOMPOSE: decompose_goal(goal) → SubGoal tree
  3. ROUTE (if router): find_best_agent_for_subgoal(leaf) → agent_id
  4. EXECUTE-VERIFY loop:
     Mode A (router): _execute_agents()
       → build_graph_from_tasks(tasks, edges)
       → ParallelAgentExecutor.execute(graph)
       → returns {artifacts, errors}
     Mode B (callback): execute_fn(goal, executor)
  5. VERIFY: check artifacts against _VERIFICATION_RULES
     passed → COMPLETE | failed+retries<2 → re-EXECUTE | else → FAILED
  6. activity_recorder.record_completion() or record_failure()
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | rain/UnifiedBrain.py, core/planner/replan.py | PlannerStateMachine.run(goal) |
| **Calls engine** | PlannerExecutor.create_plan(), GoalDecomposer.decompose() | Classification and decomposition |
| **Executes work** | ParallelAgentExecutor.execute() (Mode A) OR callback (Mode B) | Delegates to agent graph |
| **Finishes** | Self — returns result dict state=COMPLETE/FAILED | Calls activity_recorder |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | None directly |
| **Memory written** | ctivity_recorder.* methods (goal, subgoals, agent_tasks, task_result, completion, failure) |
| **UI updated** | None |

---

## 5. Engine 4: Scheduler (core/scheduler/scheduler.py)

**Purpose:** Persistent autonomous activity scheduler with concurrent worker pool. Tick-based: refresh→cleanup→fill slots→launch.

### Execution Flow
`
Scheduler.start():
  _state = RUNNING, _task = asyncio.create_task(_run())

_run(): while _state != STOPPED: if RUNNING: tick(); sleep(tick_interval)

tick():
  1. _queue.refresh() → refresh from store + ActivityGraph
  2. _cleanup_workers() → remove done tasks
  3. available = max_workers - running_count
  4. _queue.get_best_n_chain_aware(available)
  5. Pre-check executors → fail fast if no executor
  6. Launch: asyncio.create_task(_run_worker(act))

_run_worker(activity):
  1. Intelligence.predict(activity.node_type)
  2. ResumeEngine.find_resume_point(aid)
  3. Execute: _execute_fn OR _resolve_executor(activity)
     → executor(activity_id, goal, metadata)
     → queue.mark_completed(aid)
  4. Intelligence.record() → outcome for calibration
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | core/main.py, core/lifespan.py | Scheduler.start() at boot |
| **Calls engine** | Self — internal tick loop | Scheduler.tick() |
| **Executes work** | SchedulerRegistry.get(key) → executor function | Research/build/repair/email/benchmark/opportunity/default/pipeline executors |
| **Finishes** | queue.mark_completed() or queue.mark_failed() | Worker cleanup |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | _fire_tick_callbacks() (synchronous callbacks, NOT EventBus) |
| **Memory written** | ActivityIntelligence.record() (prediction calibration) |
| **UI updated** | None |

---

## 6. Engine 5: AutomationLoop (rain/automation/loop.py)

**Purpose:** Strict phase-based autonomous build loop with targeted repair, verification gates, failure memory, plan evolution.

### Execution Flow
`
AutomationLoop.start() → asyncio.create_task(_run_loop())

_run_loop(): while _running: if not paused: _tick()

_tick(): goals.list_active() → get_highest_priority() → _build_project(goal)

_build_project(goal):  -- THE MAIN BUILD PIPELINE --
  PLAN: LLM prompt → {project_name, language, files, build_command, test_command}
  GENERATE: Write plan[files] to disk
  VERIFY GATES: verify_gates(proj_dir, plan) → static checks. Repair if fail.
  BUILD LOOP (MAX_REPAIR_ATTEMPTS=10):
    shell build_command
    if fail: classify_error(build_output) → regex registry → apply_fix() → rebuild
    if still fail: _plan_evolution() → mutate plan → regenerate → rebuild
  TEST LOOP: shell test_command → analyze → repair → retest
  VERIFY: LLM checks against requirements
  RUNTIME VALIDATION: start app → screenshot → LLM validate
  COMPLETION TRACKING: RequirementTracker → keyword match
  FINISH: goals.complete(goal_id)
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | rain/UnifiedBrain.py | AutomationLoop.start() |
| **Calls engine** | Self — internal tick loop | Picks from GoalManager |
| **Executes work** | Shell commands, core/llm_router.complete() | Error classification via regex (no LLM) |
| **Finishes** | goals.complete() or goals.fail() | Updates GoalManager |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | None (does not use EventBus) |
| **Memory written** | memory.store_trace() (brain MemoryManager), FailureMemory.store() (pattern DB), ArchitecturalMemory.learn() (JSON file) |
| **UI updated** | None |

---

## 7. Engine 6: StateGraph (core/graph/graph.py)

**Purpose:** Async node-by-node graph execution with SSE streaming for WebSocket UI.

### Execution Flow
`
StateGraph.execute(state: AgentState):
  current = _entry node
  while current and current != "__end__":
    if current == "__pause__": yield SSE "paused"; return
    yield SSE "phase_change" → current
    state = await fn(state)   ← call registered node function
    for event in state.events: yield SSE event
    edge = _edges[current]
    if string: current = edge
    if tuple:  current = router(state) → path_map[decision]
    if none:   current = "__end__"
  yield SSE "error" (if state.error); yield SSE "[DONE]"
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | core/agents/agent_graph.py (agent loop runtime) | StateGraph.execute(AgentState) |
| **Calls engine** | Self — walks DAG edges | Node functions registered via dd_node(name, fn) |
| **Executes work** | Registered node functions | Each node receives and mutates AgentState |
| **Finishes** | When current == "__end__" or __pause__ | Yields [DONE] SSE event |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | SSE events via async generator: phase_change, paused, custom events, error, [DONE] |
| **Memory written** | Writes to AgentState (in-memory, not persisted by graph) |
| **UI updated** | SSE stream → WebSocket → frontend (real-time progress) |

---

## 8. Engine 7: GraphExecutor (core/distribution/graph/executor.py)

**Purpose:** Drives DistributedGraph across workers. Schedule→dispatch→collect→checkpoint lifecycle.

### Execution Flow
`
GraphExecutor.execute(graph, runtime_context):
  graph.state = RUNNING
  while graph.has_unfinished() and not graph.is_terminal():
    assignments = scheduler.schedule_ready_nodes(graph)
    dispatch_tasks = [asyncio.create_task(_dispatch(node, worker_id))]
    await asyncio.wait(dispatch_tasks, timeout=poll_interval)
    for (node, result) in assignments:
      if exception: scheduler.on_node_failed()
      else: node.result=result; node.status=COMPLETED
    checkpointer.save(graph)   ← checkpoint each wave
  graph.state = FAILED or COMPLETED

_dispatch(node, worker_id):
  WorkerRequest(request=node.request, ...)
  transport.send(wr, address=worker_id) → WorkerResponse
  return {text, observations, metrics}
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | core/distribution/graph/scheduler.py (DependencyAwareScheduler) | GraphExecutor.execute(graph) |
| **Calls engine** | DependencyAwareScheduler.schedule_ready_nodes() | Picks ready nodes |
| **Executes work** | Worker processes via Transport layer | WorkerResponse from remote/local workers |
| **Finishes** | Self — sets graph.state = COMPLETED/FAILED/CANCELLED | Checkpointer saves final state |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | None (does not use EventBus) |
| **Memory written** | GraphCheckpointer.save() (checkpoints graph state) |
| **UI updated** | None |

---

## 9. Engine 8: Pipeline Stage 14 (core/pipeline/stages/execution.py)

**Purpose:** Pipeline execution stage. ProviderManager with fallback (LiteLLM→Ollama). Runtime for multi-step plan execution.

### Execution Flow
`
ExecutionStage.execute(context):
  if plan exists:
    Runtime.execute_plan(plan, capabilities, context):
      for each step:
        executor = _build_executor(intent, capabilities)
        result = await executor.execute(step, context)
        update ActivityManager nodes (subgoal + tool_call)
        create Observation → context.observations
      return combined text
  else (no plan):
    ProviderManager.execute(raw_input):
      LiteLLMProvider.complete(prompt) → route_request → router.acompletion()
      if fail: OllamaFallbackProvider.complete(prompt) → httpx.post(ollama_url)
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | Pipeline stage runner | Stage 14 of 19 |
| **Calls engine** | Self — Runtime.execute_plan() or ProviderManager.execute() | |
| **Executes work** | LLM providers (LiteLLM, Ollama) or StepExecutors | core/llm_router.py for LLM |
| **Finishes** | Self — returns StageResult(CONTINUE/FAIL) | Sets context.execution_state, context.outcome |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | None directly |
| **Memory written** | ActivityManager node updates via core/activity/ |
| **UI updated** | None directly |

---

## 10. Engine 9: UnifiedBrain (rain/UnifiedBrain.py)

**Purpose:** "Unified cognitive core" — orchestrates reasoning, planning, memory, goals, executor, verifier, automation, observers, world model, learning, self-improvement.

### Execution Flow (Startup)
`
UnifiedBrain.__init__():
  Creates: MemoryManager, GoalManager, Planner, Executor, Verifier
  Creates: AutomationLoop, ObserverManager, WorldModel
  Creates: LearningEngine, GoalGenerator, SelfImprovementEngine
  Creates: ToolRegistry, registers all tools
  Connects Brain EventBus (separate from canonical EventBus)
  Starts AutomationLoop (if auto_start=True)
  Starts ObserverManager (file system, system monitor, time observer)
  Starts GoalGenerator (autonomous goal creation)
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | core/main.py, rain/__init__.py | UnifiedBrain() constructor |
| **Calls engine** | Sub-engines: AutomationLoop, ObserverManager, GoalGenerator | |
| **Executes work** | Brain's own Executor (rain/executor/executor.py) | Different from core/tools/execution.py! |
| **Finishes** | Sub-engines stop independently | rain.stop() → stops all sub-engines |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | Brain EventBus (separate): GoalCreated, GoalCompleted, GoalFailed, TaskCompleted, TaskFailed, MemoryStored, VerificationPassed, VerificationFailed |
| **Memory written** | Brain MemoryManager (separate from core memory/), GoalManager, WorldModel |
| **UI updated** | None |

---

## 11. Engine 10: Pipeline Entry Point (core/pipeline/pipeline.py)

**Purpose:** Canonical entry point process_message(). Creates PipelineContext from Request, runs 19-stage pipeline, returns Response.

### Execution Flow
`
process_message(request):
  ctx = PipelineContext(request_id, transport, user_id, ...)
  ctx.identity = IdentityService.create_context()
  for stage in pipeline._stages:
    result = await stage.execute(ctx)
    if result.outcome == FAIL or HALT: break
    ctx = result.context
  response = Response(text, error, data, metadata)
  return response
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | All entry points: HTTP, WS, MCP, CLI, Scheduler | pipeline_executor() → process_message() |
| **Calls engine** | 19 stages sequentially | Each stage executes independently |
| **Executes work** | Stage 14 (ExecutionStage) does LLM/tool work; stage 17 (MemoryStage) writes memory | |
| **Finishes** | Self — constructs Response, returns it | |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | Via individual stages |
| **Memory written** | Stage 17: MemoryStage → MemoryFacade |
| **UI updated** | Response → transport adapter → client |

---

## 12. Engine 11: ParallelAgentExecutor (core/agents/parallel_executor.py)

**Purpose:** Executes agent tasks in parallel with dependency graph support.

### Execution Flow
`
ParallelAgentExecutor.execute(graph, workflow_id):
  max_parallel = graph.max_parallel
  while graph.has_pending():
    ready = graph.get_ready_nodes()
    for node in ready (up to max_parallel):
      asyncio.create_task(execute_node(node))
    await any_task_completed()
    graph.mark_completed(node)
  return {artifacts, error}
`

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | PlannerStateMachine._execute_agents() | |
| **Calls engine** | Self — manages parallel execution | Depends on AgentGraph for dependencies |
| **Executes work** | Individual agent tasks | Each agent has its own execution logic |
| **Finishes** | Self — returns artifacts dict | |

### Events/Memory/UI
| Action | Details |
|--------|---------|
| **Events published** | Optional: emit_events=False by default |
| **Memory written** | Via individual agent executors |
| **UI updated** | None |

---

## 13. Engine 12: Scheduler Executors (core/scheduler/executors.py)

**Purpose:** Adapter layer between Scheduler and real subsystems.

### Executors
| Executor | Calls | Purpose |
|----------|-------|---------|
| esearch_executor | do_browser_research() | Web research |
| uild_executor | do_build_project() | Software builds |
| epair_executor | do_repair_project() | Build repairs |
| email_executor | _call_mcp_tool("mcp__email__send_email") | Send emails |
| enchmark_executor | un_benchmark() | Run benchmarks |
| opportunity_executor | → esearch_executor() | Opportunity research |
| default_executor | execute_tool_block() | Fallback: any tool type |
| pipeline_executor | process_message(Request(...)) | Routes through canonical pipeline |

### Roles
| Role | Who | Details |
|------|-----|---------|
| **Starts** | Scheduler._run_worker() → _resolve_executor() | Scheduler resolves by node_type |
| **Calls engine** | Self — each executor wraps a specific tool | |
| **Executes work** | Various: browser_research, build_tools, MCP, execute_tool_block(), process_message() | |
| **Finishes** | Returns result dict to Scheduler worker | Queue item marked completed/failed |

---

## 14. The Central Tool Dispatcher (core/tools/execution.py)

**Purpose:** 3,024-line monolith. ALL engines call this (except brain's own executor).

### Callers
| Caller | Engine | How |
|--------|--------|-----|
| WorkflowEngine._execute_step() | Engine 2 | execute_tool_block(block, ...) |
| PlannerExecutor.inject_task() | Engine 3 helper | execute_tool_block(block, ...) |
| default_executor in scheduler | Engine 12 | execute_tool_block(block) |
| AgentLauncher | Engine 1 helper | Via execution.py |
| AgentState node functions | Engine 6 | Via execution.py |
| Various tool modules | Ad-hoc | rom core.tools.execution import execute_tool_block |

### NOT Calling execute_tool_block
| System | Their executor | How they execute |
|--------|---------------|-----------------|
| Brain's Executor | rain/executor/executor.py | ActionResult-based executor |
| AutomationLoop | core/llm_router.complete() | Direct LLM calls, shell commands |
| Pipeline Stage 14 | ProviderManager | LLM providers (LiteLLM/Ollama) |


---

## 15. Canonical Execution Graph

See diagram below (text-based).

\\\`n
                              ENTRY POINTS
                          HTTP / WS / MCP / CLI / Scheduler
                                     │
                          Engine 10: process_message()
                          19-stage canonical pipeline
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                       │
     Stage 11:PlannerStage  Stage 14:ExecutionStage   Engine 4:Scheduler
     (plan in ctx)           (LLM providers)           (tick pool)
              │                      │                       │
     Engine 6:StateGraph             │              Engine 12:Scheduler
     (agent loop)                    │              Executors
              │                      │                       │
     Engine 11:ParallelAgent         │              pipeline_executor
     Executor                        │              → process_message()
              │                      │                       │
              └──────────┬───────────┘                       │
                         │                                   │
              core/tools/execution.py  ──────────────────────┘
              3024-line execute_tool_block
                         │
            ┌────────────┼────────────┐
            │            │            │
       MCP Servers  Native Tools  Tool Executors

     ────────── BRAIN WORLD (separate execution universe) ──────────
     Engine 9: UnifiedBrain
       ├── Engine 5: AutomationLoop → LLM calls, shell
       ├── Brain Executor (NOT execute_tool_block)
       └── Brain EventBus (separate from system EventBus)

     Engine 2: WorkflowEngine
       Events → SQLite (NOT EventBus). Calls execution.py.

     Engine 1: Controller Loop
       Build automation, separate event/memory/UI system.

---


---

## 16. Duplicate Analysis

### Duplicate Execution Engines

| What | Engine A | Engine B | Overlap | Should Merge? |
|------|----------|----------|---------|---------------|
| Step execution | WorkflowEngine (retry+compensate) | Controller Loop (template tasks) | Both run step-by-step execution loops | Yes - Controller Loop should use WorkflowEngine |
| Plan execution | PlannerStateMachine (VERIFY loop) | WorkflowEngine (step loop) | Both track progress, retry on failure | Yes - PlannerStateMachine delegates to agents, not directly comparable |
| Autonomous ticks | Scheduler (tick-based) | AutomationLoop (tick-based goal loop) | Both poll, pick work, execute, record | Maybe - share tick pattern but different domains |
| Graph execution | StateGraph (DAG walk, SSE) | GraphExecutor (distributed DAG) | Both walk DAGs of nodes | No - different purposes |
| Tool dispatch | core/tools/execution.py | brain/executor/executor.py | Both call tools | Yes - brain should use core/tools/execution.py |
| Event bus | WorkflowEngine events (SQLite) | UnifiedBrain events (Brain EventBus) | Both record execution events | WorkflowEngine should publish to canonical EventBus |
| Memory writing | activity_recorder | MemoryFacade | Both record execution outcomes | Yes - unify behind MemoryFacade |
| Pipeline entry | process_message() (canonical) | Scheduler pipeline_executor() | Both call process_message() | No duplicate - Scheduler wraps it |

### Duplicate Event Systems Across Engines

| Engine | Event Storage | Event Types | Duplicate Of |
|--------|--------------|-------------|--------------|
| WorkflowEngine | SQLite append_event | 12 workflow events | Should be canonical EventBus |
| UnifiedBrain | Brain EventBus | 8 brain events | Separate from canonical EventBus |
| Scheduler | Tick callbacks | 1 tick event | Should be canonical EventBus |
| Canonical Pipeline | EventBus emit | ~79 event types | Reference implementation |
| StateGraph | SSE stream | 4 event types | UI-specific, not duplicate |

### Duplicate Memory/State Writing

| Engine | Writes To | Data | Overlap |
|--------|----------|------|---------|
| WorkflowEngine | activity_recorder | Goals, tasks, results, artifacts | Partial overlap with MemoryFacade |
| PlannerStateMachine | activity_recorder | Goals, subgoals, task results | Same activity_recorder! |
| AutomationLoop | brain MemoryManager | Traces, failures | Brain-specific, not in core memory |
| Pipeline Stage 17 | MemoryFacade | Messages, facts | Canonical memory path |
| Controller Loop | pattern_failure_memory | Error patterns | Brain FailureMemory has same purpose |

---

## 17. Findings

### F-1: Two Separate Execution Universes
core/ (pipeline, workflow, scheduler) and rain/ (UnifiedBrain, AutomationLoop, Brain Executor) are completely separate execution universes with their own tool dispatch, memory, events, and lifecycle. They do not share execution state.

**R-1:** The Brain's Executor should delegate to core/tools/execution.py. Brain MemoryManager should delegate to memory/MemoryFacade. Brain EventBus should be removed in favor of the canonical EventBus with namespace isolation (rain.* namespace).

### F-2: WorkflowEngine Events Not on EventBus
WorkflowEngine publishes 12+ detailed lifecycle events, but writes them to a SQLite append log instead of the canonical EventBus. No other system can subscribe to workflow events.

**R-2:** WorkflowEngine should publish all events to the canonical EventBus (workflow.* namespace) in addition to the SQLite log.

### F-3: Controller Loop Uses No EventBus, No MemoryFacade
Engine 1 (core/control_loop.py) is 1132 lines with its own pattern memory, checkpoint manager, and quality scorer. It does not use EventBus, MemoryFacade, or WorkflowEngine.

**R-3:** Controller Loop should be refactored to use WorkflowEngine for step execution and EventBus for lifecycle events. Its pattern_failure_memory duplicates brain/automation/loop.py FailureMemory.

### F-4: Three Different Event Bus Systems
- Canonical EventBus: used by pipeline, config, auth, plugins
- Brain EventBus: used by UnifiedBrain subsystems only
- WorkflowEngine SQLite events: written to workflow.db, not broadcast

**R-4:** Unify behind canonical EventBus with namespaces (system.*, workflow.*, rain.*).

### F-5: activity_recorder Is Used by Both WorkflowEngine and PlannerStateMachine
Both engines write to the same ctivity_recorder (ActivityManager). This creates a coupling point — changes to ActivityManager affect both engines.

**R-5:** Move activity recording into a dedicated service. Have both engines call the same service API.

### F-6: Scheduler Has Its Own Executor System Outside Pipeline
Scheduler executors (research, build, repair, email, benchmark, opportunity) bypass the canonical pipeline. Only pipeline_executor routes through process_message().

**R-6:** All scheduler executors should route through the canonical pipeline (pipeline_executor or equivalent). The pipeline already has auth, rate limiting, capability selection, and memory — scheduler executors bypass all of these.

### F-7: StateGraph Is the Only Engine That Updates the UI
StateGraph yields SSE events consumed by the WebSocket/frontend. No other engine has any UI feedback mechanism.

**R-7:** All long-running engines (WorkflowEngine, Scheduler, PlannerStateMachine) should publish progress events that the UI can subscribe to via EventBus → WebSocket bridge.

### F-8: core/tools/execution.py Is a 3024-Line Bottleneck
Every engine except brain/ calls execute_tool_block(). This monolith handles MCP dispatch, native tools, security, sandboxing, sub-agent spawning, and result formatting. Any change risks breaking all engines.

**R-8:** Break execute_tool_block() into a proper dispatcher with pluggable handlers per transport type (MCP, native, sub-agent). Make the dispatcher testable without invoking real tools.
