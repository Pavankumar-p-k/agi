# SOURCE OF TRUTH — MJ Constitution

> Audit date: 2026-07-09
> Phase: Phase 6F complete — Runtime v1 (Identity, Multi-tenancy, Distribution, Distributed Graph).
> Phase 7 start: Intelligence Platform (ADR-009).
> Sections: 48 responsibility areas catalogued. 15 new overlapping systems identified. 6 deprecated subsystems tagged.
> Methodology: grep import analysis, file-by-file read, dependency tracing, parallel agent exploration.

---

## CLASSIFICATION KEY

| Tag | Meaning |
|-----|---------|
| ACTIVE | In production use, imported, wired into lifespan or routes |
| LEGACY | Still imported but superseded; maintained for backward compat |
| EXPERIMENTAL | Present in codebase but not on main execution path |
| DEAD | Zero production imports; can be removed |
| CONNECTED | Wired into EventBus or dependency injection |
| PARTIAL | Partially implemented; stubbed or incomplete |
| UNUSED | Defined but not invoked at runtime |

---

## 1. STARTUP

**Canonical future owner:** `core/main.py` + `core/lifespan.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Application entry point | `jarvis.py:main()` | ACTIVE | CLI parser, first-run setup dispatch. Entry: `jarvis:main` in pyproject.toml |
| FastAPI creation | `core/main.py:app = FastAPI(...)` | ACTIVE | Lifespan wired, middleware registered, 40+ routers mounted |
| Lifespan manager | `core/lifespan.py:lifespan()` | ACTIVE | Async context manager. 42 startup phases, ~20 shutdown phases |
| Config bootstrap | `core/config_init.py:init_config()` | ACTIVE | Called from main.py line 62. Loads ConfigurationService |
| Legacy config constants | `core/config.py` (module) | ACTIVE+DEAD | 12 dead variables: OLLAMA_URL, OLLAMA_MODEL, OLLAMA_PORTS, VOSK_MODEL_PATH, GITHUB_TOKEN, HYBRID_MAX_RETRIES, HYBRID_TIMEOUT_SECONDS, MUSIC_DIR, MAX_RETRIES, DAEMON_MODE, VAULT_PATH (shadowed), MAX_PARALLEL_BUILDS, PROJECTS_DIR (shadowed). 9 variables still actively imported |
| Typed config schema | `core/config_schema.py:JarvisConfig` | ACTIVE | Import-time singleton loaded at module level |
| Runtime config service | `core/configuration/service.py:ConfigurationService` | ACTIVE | 6-step resolution chain. Singleton via `configuration/__init__.py` |
| Config registry | `core/config_registry.py:Config` | ACTIVE | Wraps ConfigurationService with legacy fallback. 60+ config entries |
| Pydantic settings | `core/settings/store.py:SettingsStore` | ACTIVE | ~/.jarvis/settings.json management. Used by lifespan and routes |
| Setup wizard | `core/setup/engine.py:SetupEngine` | ACTIVE | CLI and API setup orchestration |
| Setup detector | `core/setup/detector.py` | ACTIVE | Broken import: `core/benchmark/perf_baseline.py` imports `mark_setup_state` which does not exist |
| Installer | `install.py:main()` | ACTIVE | Standalone one-line install script |

**Reality score:** 9/10 — Two overlapping config systems coexist (JarvisConfig import-time vs ConfigurationService runtime). Several dead constants.

---

## 2. REQUEST PROCESSING

**Canonical future owner:** `core/routes/websocket.py` + `core/agent_loop.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| WebSocket hub | `core/routes/websocket.py` | ACTIVE | /ws/agent_stream, /ws/chat_stream, /ws/logs, /ws/mcp/bridge, /ws/{device_id}/{user_id} |
| Chat streaming | `core/routes/chat.py` | ACTIVE | POST /api/chat, POST /api/agent/stream, POST /v1/chat/completions |
| HTTP route layer | `core/routes/` (36 files) | ACTIVE | All 36 routers wired into main.py |
| Middleware stack | `core/middleware.py`, `core/request_id.py` | ACTIVE | SecurityHeaders, RequestID, rate_limit, session_auth, plugin_hook |
| Legacy request classifier | `core/intent_router.py:extract_intent()` | ACTIVE | 750-line rule-based fallback. Used by websocket and main |
| Modern request classifier | `core/routing/request_classifier.py:classify_request()` | ACTIVE | Hybrid keyword+LLM classification. Used by /ws/agent_stream |
| Context manager | `core/routing/project_context.py:ContextManager` | ACTIVE | Session and project context tracking |
| Tool safety classifier | `core/routing/safety.py:classify_tool()` | ACTIVE | SAFE/CONFIRM/DANGEROUS classification |
| Handler layer | `routers/` (6 files) | ACTIVE | Chat handler, screen, setup, WhatsApp, dot panels, JarvisHub |
| Legacy model router shim | `core/model_router.py` | LEGACY | "BACKWARD-COMPAT SHIM" — re-exports from llm_router.py. Still imported by 7 files |
| Bridge auth | `core/gateway/auth.py:BridgeAuth` | ACTIVE | MCP Bridge WebSocket auth |
| Intent extraction | `core/intent_router.py:_rule_based()` | ACTIVE | 750+ lines of keyword rules. LLM primary, rule fallback |

**Reality score:** 8/10 — Two parallel routing paths coexist (legacy intent_router vs modern classify_request). model_router.py is a backward-compat shim.

---

## 3. GOAL UNDERSTANDING

**Canonical future owner:** `core/planner/` (classifier + decomposer)

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Goal interpreter | `core/goal_interpreter.py:interpret_goal()` | ACTIVE | LLM-powered vague goal -> structured project spec. Used by control_loop |
| Goal classifier | `core/planner/classifier.py:classify_goal()` | ACTIVE | Classifies goals by type and complexity |
| Goal decomposer | `core/planner/decomposer.py:GoalDecomposer` | ACTIVE | Decomposes goals into subgoals |
| Capability goal resolver | `core/capability/graph.py:CapabilityGraph.resolve_goal()` | ACTIVE | Goal template matching against capability graph |
| Capability composition | `core/capability/composition.py:CompositionEngine.compose()` | ACTIVE | Full goal->capability->provider resolution pipeline |
| Capability negotiator | `core/capability/negotiation.py:CapabilityNegotiator.resolve_goal()` | ACTIVE | Per-node provider negotiation with fallback |
| Governance task router | `core/governance/task_router.py:TaskRouter.route()` | ACTIVE | LLM rule-based task routing with keyword fallback |
| Brain goal generator | `brain/goal_generator.py:GoalGenerator` | ACTIVE | Autonomous goal generation: checks disk/CPU for immediate goals, LLM for complex. Evaluates world state |
| Brain unified goal | `brain/UnifiedBrain.py:create_goal()` | ACTIVE | Creates persistent Goal + publishes GoalCreated event. Wraps GoalManager |
| Brain goal classifier | `brain/goal_generator.py:_parse_goals()` | ACTIVE | Extracts JSON goal list from LLM answer tags |
| Brain world state eval | `brain/goal_generator.py:evaluate_world()` | ACTIVE | Checks resource thresholds (disk <10%, CPU >90%) + LLM-based opportunity detection |

**Reality score:** 9/10 — Cohesive pipeline. goal_interpreter is the primary entry, capability graph handles resolution. brain/GoalGenerator provides autonomous/self-triggered goal creation.

---

## 4. PLANNING

**Canonical future owner:** `core/planner/` (all modules)

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Plan manager | `core/plan_manager.py:PlanManager` | ACTIVE | GoalProcessor, plan lifecycle management |
| Plan evolution | `core/plan_evolution.py:PlanEvolutionEngine` | ACTIVE | Mid-run DAG mutation (add/remove/reorder nodes). Escape hatch |
| Plan routes | `core/plan_routes.py` | ACTIVE | FastAPI router for plan CRUD |
| Planner state machine | `core/planner/state_machine.py:PlannerStateMachine` | ACTIVE | 6 states: PLAN->DECOMPOSE->ROUTE->EXECUTE->VERIFY->COMPLETE |
| Planner executor | `core/planner/executor.py:PlannerExecutor` | ACTIVE | Plan execution orchestration |
| Plan store | `core/planner/store.py:PlanStore` | ACTIVE | SQLite-backed plan persistence |
| Plan evidence | `core/planner/evidence.py:PlanEvidenceEngine` | ACTIVE | Evidence collection for plan decisions |
| Plan comparison | `core/planner/comparison.py:ComparativeScorer` | ACTIVE | Multi-plan comparison scoring |
| Plan health | `core/planner/health.py:PlanHealthEngine` | ACTIVE | 7-signal plan health monitoring |
| Plan outcomes | `core/planner/outcomes.py:PlanOutcomeStore` | ACTIVE | Outcome tracking |
| Plan replan | `core/planner/replan.py:ReplanEngine` | ACTIVE | Replanning trigger engine |
| Plan strategies | `core/planner/strategies.py:StrategyGenerator` | ACTIVE | 8 strategy templates |
| Plan templates | `core/planner/templates.py` | ACTIVE | Workflow templates + tool mappings |
| Site planner | `core/site_planner.py:SitePlanner` | EXPERIMENTAL | 11 template types, 9 page types. Used by control_loop |
| Horizon planner | `core/horizon_planner.py:HorizonPlanner` | EXPERIMENTAL | JSON-backed long-term goal tracking. Used by admin routes |
| Control loop | `core/control_loop.py:ControlLoop` | ACTIVE | Orchestrates planning+build+validate+fix cycle. The heart of builds |
| Brain planner | `brain/planner/planner.py:Planner` | ACTIVE | Goal → 3-node DAG (create_directory → write_file → run_command). Simpler alternative to core/planner |
| Brain task graph | `brain/planner/task_graph.py:TaskGraph` | ACTIVE | DAG with topological sort, cycle detection, critical path, serialization |
| Brain plan (UnifiedBrain) | `brain/UnifiedBrain.py:plan()` | ACTIVE | Uses CognitivePatterns.decompose() to create Step list |
| Brain cognitive decompose | `brain/cognitive_patterns.py:decompose()` | ACTIVE | Splits complex problems into independent sub-problems via LLM |
| Brain cognitive plan | `brain/cognitive_patterns.py:plan()` | ACTIVE | Breaks goal into concrete ordered steps via LLM |
| Brain replan | `brain/planner/planner.py:replan()` | ACTIVE | Replaces failed node with new sub-graph |

**Reality score:** 9/10 — Comprehensive planning layer. Two experimental planners (site, horizon) are wired but secondary. **Note:** `brain/planner/` is a simpler parallel planning implementation — creates only 3-node DAGs vs `core/planner/`'s full state machine. Need consolidation.

---

## 5. EXECUTION

**Canonical future owner:** `core/agents/` (new agent system)

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Agent executor (new) | `core/agents/executor.py` | ACTIVE | make_agent_execute_fn, make_parallel_agent_execute_fn |
| Agent graph | `core/agents/graph.py:AgentExecutionGraph` | ACTIVE | DAG-based agent execution |
| Agent router | `core/agents/router.py:AgentRouter.find_agent_for_goal()` | ACTIVE | Capabilities-based agent selection |
| Base agent | `core/agents/base.py:BaseAgent` | ACTIVE | ABC with can_handle/plan/execute/verify lifecycle |
| Browser agent | `core/agents/browser_agent.py:BrowserAgent` | ACTIVE | Tool-based browser automation agent |
| Build agent | `core/agents/build_agent.py:BuildAgent` | ACTIVE | Build system agent |
| Email agent | `core/agents/email_agent.py:EmailAgent` | ACTIVE | Email operations agent |
| Research agent | `core/agents/research_agent.py:ResearchAgent` | ACTIVE | Research pipeline agent |
| Test agent | `core/agents/test_agent.py:TestAgent` | ACTIVE | Test execution agent |
| Memory agent | `core/agents/memory_agent.py:MemoryAgent` | ACTIVE | Memory management agent |
| Parallel executor | `core/agents/parallel_executor.py:ParallelAgentExecutor` | ACTIVE | Concurrent agent execution |
| Legacy sub-agents | `core/sub_agents/` (13 files) | LEGACY | 10 LLM-prompt agents (Maestro, Nexus, Forge, Oracle, Phantom, Cipher, Herald, Atlas, Scribe, Sentinel). Wrapped by adapters |
| Sub-agent adapters | `core/agents/adapters/` (10 files) | ACTIVE | Bridge between legacy sub-agents and new BaseAgent system |
| Agent runtime | `core/agent_runtime.py:AgentRuntime` | ACTIVE | Multi-round tool-call execution with plan decomposition |
| Agent orchestrator | `core/agent_orchestrator.py:AgentOrchestrator` | ACTIVE | Repository analysis, coding, build orchestration |
| Agent loop | `core/agent_loop.py:stream_agent_loop()` | ACTIVE | SSE streaming entry. Tries RuntimePipeline, falls back to legacy graph |
| Pipeline | `core/pipeline.py:RuntimePipeline` | ACTIVE | Unified runtime: knowledge->planning->strategy->decision->provider->activity->workflow->feedback |
| Legacy agent registry | `core/agent_registry.py` | DEPRECATED | Still imported by work_queue.py and lifespan.py. Emits deprecation warning |
| Agent tools facade | `core/agent_tools.py` | ACTIVE | Re-exports from core/tools/ |
| Agent states shim | `core/agent_states.py` | DEAD | Zero importers. Remove safely |
| Agent prompts | `core/agent_prompts.py` | ACTIVE | System prompt assembly |
| Agent helpers | `core/agent_helpers.py` | ACTIVE | MCP tool cache, tool-call extraction, verifier subagent |
| Brain executor | `brain/executor/executor.py:Executor` | ACTIVE | Unified action executor with tool registration, LLM-based resolution, timeout. Singleton `executor` |
| Brain verifier | `brain/executor/verifier.py:Verifier` | ACTIVE | LLM-based verification of actions, file creations, code outputs. Singleton `verifier` |
| Brain execute with verify | `brain/UnifiedBrain.py:execute_with_verification()` | ACTIVE | Executes action, verifies result, publishes events, stores trace |
| Brain action result | `brain/executor/executor.py:ActionResult` | ACTIVE | Standard result dataclass: success, output, evidence, confidence, error, duration_ms |
| Brain verification result | `brain/executor/verifier.py:VerificationResult` | ACTIVE | Dataclass: verified, confidence, issues, evidence |
| Brain execution context | `brain/execution_context.py:BrainExecutionContext` | ACTIVE | Dataclass for brain execution context: goal, prompt, user_id, session_id |

**Reality score:** 7/10 — Two execution systems coexist (new BaseAgent + legacy SubAgent). Adapter pattern bridges them. agent_states.py is dead. **brain/executor/ is a third execution path** — simpler tool registration without the full agent lifecycle. Three parallel execution systems exist.

---

## 6. WORKFLOW

**Canonical future owner:** `core/workflow/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Workflow engine | `core/workflow/engine.py:WorkflowEngine` | ACTIVE | DAG step execution |
| Workflow models | `core/workflow/models.py` | ACTIVE | WorkflowStatus (10 states), WorkflowStep, StepDefinition |
| Workflow graph | `core/workflow/graph.py:ExecutionGraph` | ACTIVE | DAG execution graph |
| Workflow storage | `core/workflow/storage.py:WorkflowStore` | ACTIVE | SQLite-backed workflow persistence |
| Workflow events | `core/workflow/events.py` | ACTIVE | EventBus, WorkflowEvent |
| Workflow recorder | `core/workflow/recorder.py:WorkflowExecutionRecorder` | ACTIVE | Execution recording |
| Workflow context | `core/workflow/context.py:ExecutionContext` | ACTIVE | Context management |
| Artifact store | `core/workflow/artifact_store.py:ArtifactStore` | ACTIVE | Workflow artifact storage |
| Heartbeat monitor | `core/workflow/heartbeat_monitor.py:HeartbeatMonitor` | ACTIVE | Workflow liveness tracking |
| Recovery | `core/workflow/recovery.py:recover_active_workflows()` | ACTIVE | Active workflow recovery |
| Tracker | `core/workflow/tracker.py:ExecutionTracker` | ACTIVE | Execution progress tracking |
| Calibration | `core/workflow/calibration.py:WorkflowCalibrationEngine` | ACTIVE | Workflow performance calibration |
| Learning models | `core/workflow/learning_models.py` | ACTIVE | Workflow outcome models |
| Learning store | `core/workflow/learning_store.py` | ACTIVE | Workflow history store |
| Long horizon FSM | `core/workflow/long_horizon_fsm.py:LongHorizonFSM` | ACTIVE | 10-state FSM for long-running workflows |
| Workflow routes | `core/routes/workflows.py` | ACTIVE | REST API for workflow CRUD |

**Reality score:** 10/10 — Comprehensive, well-structured workflow layer with persistence, recovery, and monitoring.

---

## 7. SCHEDULER

**Canonical future owner:** `core/scheduler/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Scheduler core | `core/scheduler/scheduler.py` | ACTIVE | Central scheduler |
| Scheduler queue | `core/scheduler/queue.py` | ACTIVE | Task queue management |
| Scheduler models | `core/scheduler/models.py` | ACTIVE | Task/schedule data models |
| Scheduler store | `core/scheduler/store.py` | ACTIVE | Persistent task storage |
| Scheduler worker | `core/scheduler/worker.py` | ACTIVE | Task execution workers |
| Scheduler policies | `core/scheduler/policies.py` | ACTIVE | Scheduling policies |
| Scheduler resources | `core/scheduler/resources.py` | ACTIVE | Resource-aware scheduling |
| Scheduler registry | `core/scheduler/registry.py` | ACTIVE | Task type registry |
| Scheduler executors | `core/scheduler/executors.py` | ACTIVE | Task executors |
| Scheduler decision | `core/scheduler/decision.py` | ACTIVE | Scheduling decision engine |
| Scheduler intelligence | `core/scheduler/intelligence.py` | ACTIVE | ML-based scheduling |
| Scheduler metrics | `core/scheduler/metrics.py` | ACTIVE | Scheduling metrics |
| Scheduler autonomous | `core/scheduler/autonomous.py` | ACTIVE | Autonomous scheduling |
| Scheduler chain | `core/scheduler/chain.py` | ACTIVE | Chained task execution |
| Task scheduler | `core/task_scheduler.py` | ACTIVE | Legacy task scheduling |
| Cron | `core/cron.py` | ACTIVE | Cron-style scheduled jobs |
| Scheduler routes | `core/routes/scheduler.py` | ACTIVE | REST API for schedules |
| Scheduler tools | `core/tools/scheduler_tools.py` | ACTIVE | Tool interface for scheduling |

**Reality score:** 9/10 — Full-featured scheduler with ML-based intelligence and resource awareness.

---

## 8. DESKTOP

**Canonical future owner:** `core/desktop/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Desktop safety | `core/desktop/safety.py:SafetyManager` | ACTIVE | Emergency stop, rate limits, forbidden regions |
| Desktop controller | `core/desktop/controller.py:DesktopController` | ACTIVE | Mouse, keyboard, app launch primitives |
| Desktop replay | `core/desktop/replay.py:ReplayGraph` | ACTIVE | Linked-list action trace recording |
| Screen capture | `core/desktop/screen.py:ScreenCapture` | ACTIVE | Screen/window/region capture via mss+PIL |
| Window controller | `core/desktop/window.py:WindowController` | ACTIVE | Window focus/minimize/maximize/close |
| Workspace state | `core/workspace/desktop_state.py:DesktopState` | ACTIVE | Aggregate snapshot (windows, browser, clipboard, processes) |
| Window detector | `core/workspace/window_detector.py:WindowDetector` | ACTIVE | Active window detection |
| Browser context | `core/workspace/browser_context.py:BrowserContextAwareness` | ACTIVE | Browser tab state awareness |
| Clipboard manager | `core/workspace/clipboard_manager.py:ClipboardManager` | ACTIVE | Text clipboard get/set |
| Process monitor | `core/workspace/process_monitor.py:ProcessMonitor` | ACTIVE | Process listing and system stats |
| PC agent (deprecated) | `pc_agent/computer_agent.py:ComputerAgent` | EXPERIMENTAL/DEPRECATED | Deprecation warning: "will be replaced by core/desktop/" |
| PC agent playbooks | `pc_agent/playbooks.py` | EXPERIMENTAL/DEPRECATED | 10 web automation playbooks |
| PC agent snapshot | `pc_agent/snapshot.py:SystemSnapshot` | EXPERIMENTAL/DEPRECATED | Filesystem snapshot before PC control |
| Desktop control routes | `core/routes/control.py` | ACTIVE | POST /computer |
| PC agent (deprecated) | `pc_agent/computer_agent.py:ComputerAgent` | LEGACY | DeprecationWarning: "will be replaced by core/desktop/" |
| PC agent playbooks | `pc_agent/playbooks.py` | LEGACY | 10 web automation playbooks |
| PC agent snapshot | `pc_agent/snapshot.py:SystemSnapshot` | LEGACY | Filesystem snapshot before PC control |

**Reality score:** 8/10 — core/desktop is the active system. pc_agent/ directory (3 files) is deprecated with explicit warning. Workspace modules are well integrated.

---

## 9. BROWSER

**Canonical future owner:** `core/browser_manager.py` + `core/tools/browser_tools.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Browser manager | `core/browser_manager.py:BrowserManager` | ACTIVE | Playwright lifecycle, stealth injection, session management |
| Browser tools | `core/tools/browser_tools.py` (21 functions) | ACTIVE | Navigate, click, fill, snapshot, screenshot, tabs, etc. |
| Browser FSM | `core/tools/browser_fsm.py:BrowserFSM` | ACTIVE | 10-state deterministic state machine |
| Browser planner | `core/tools/browser_planner.py:BrowserPlanner` | ACTIVE | 1608-line pre/post-plan engine. Domain-specific selectors for 20+ sites |
| Browser research | `core/tools/browser_research.py:do_browser_research()` | ACTIVE | Multi-page research orchestrator |
| Browser tool (deprecated) | `tools/browser_tool.py:JarvisBrowser` | LEGACY | DeprecationWarning. Re-exports BrowserManager |
| Fact extraction | `core/fact_extraction/` (5 files) | ACTIVE | BrowserFactExtractor, BrowserFactStore |
| Browser config | `core/config_schema.py:BrowserConfig` | ACTIVE | Typed config dataclass |

**Reality score:** 9/10 — Sophisticated browser automation with FSM, planning, and research. Legacy browser_tool.py is deprecated.

---

## 10. CODING

**Canonical future owner:** `core/coding/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Repository indexer | `core/coding/repository_indexer.py:RepositoryIndexer` | ACTIVE | SQLite-backed persistent file index. 12 languages |
| Dependency graph | `core/coding/dependency_graph.py:DependencyGraph` | ACTIVE | Fan-in/out, centrality, cycle detection |
| Architecture mapper | `core/coding/architecture_map.py:ArchitectureMapper` | ACTIVE | Layer detection, cross-layer violation analysis |
| Impact analyzer | `core/coding/impact_analyzer.py:ImpactAnalyzer` | ACTIVE | Change impact scoring, risk assessment |
| Change planner | `core/coding/change_planner.py:ChangePlanner` | ACTIVE | Ordered execution phases, risk validation |
| Change simulation | `core/coding/change_simulation.py:ChangeSimulation` | ACTIVE | Pre-edit breakage prediction |
| Refactor safety | `core/coding/refactor_safety.py:RefactorSafetyEngine` | ACTIVE | Safety assessment, layer risk scoring |
| Refactoring engine | `core/coding/refactoring_engine.py:RefactoringEngine` | ACTIVE | Patch generation, validation, rollback |
| Architecture reasoning | `core/coding/architecture_reasoning.py` | ACTIVE | Design scorer, analyzer, tradeoff engine, migration planner |
| Build benchmark | `core/coding/build_benchmark.py` | ACTIVE | Phase 13.1: A/B benchmark comparing build_project vs automated_build |
| Build tools (legacy) | `core/tools/build_tools.py` | ACTIVE/LEGACY | Wraps old AutomationLoop for build_project |
| Automated build | `core/tools/automated_build.py` | ACTIVE | Phase 13.0: Richer build tool with artifact scanning, activity graph, calibration |
| Build routes | `core/build_routes.py` | ACTIVE | 24 FastAPI routes for build lifecycle |
| Brain compiler repair | `brain/compiler_repair_engine.py:CompilerRepairEngine` | ACTIVE | 944-line unified deterministic repair engine. Parses javac/Gradle/AAPT2 errors. 50+ error patterns, category-based repair map |
| Brain repair chaining | `brain/repair_chaining.py:RepairChain` | ACTIVE | Iterative fix→rebuild→detect→fix loop with rollback safety, loop detection, priority-based error selection |
| Brain structural transformer | `brain/structural_transformer.py:StructuralTransformationEngine` | ACTIVE | Type-mismatch, parameter, and API contract repair. 25+ type conversion rules |
| Brain production gate | `brain/production_gate.py:ProductionGate` | ACTIVE | Evaluates benchmark results vs production criteria (build 90%, APK 90%, runtime 60%) |
| Brain real validator | `brain/real_validator.py` (file not found in brain/ — check path) | UNKNOWN | Referenced in cross-module imports |

**Reality score:** 10/10 — Mature, well-layered coding intelligence subsystem. brain/ adds deterministic compiler repair with pattern memory and autonomous fix chaining.

---

## 11. RESEARCH

**Canonical future owner:** `core/research/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Fact models | `core/research/models.py:Fact` | ACTIVE | Core dataclass used by 15+ files |
| Fact extractor | `core/research/extractor.py:FactExtractor` | ACTIVE | Structured fact extraction from text/DOM |
| Fact store | `core/research/storage.py:FactStore` | ACTIVE | SQLite CRUD for facts |
| Fact retriever | `core/research/retriever.py:FactRetriever` | ACTIVE | Topic-aware retrieval |
| Fact reasoner | `core/research/reasoner.py:FactReasoner` | ACTIVE | Cross-source contradiction/agreement/gap analysis |
| Fact synthesizer | `core/research/synthesizer.py:FactSynthesizer` | ACTIVE | Structured report generation |
| Research planner | `core/research/planner.py:ResearchPlanner` | ACTIVE | Question decomposition, iterative refinement |
| Linker | `core/research/linker.py:Linker` | ACTIVE | Entity linking, fact relationship classification |
| Knowledge graph | `core/research/knowledge_graph.py:KnowledgeGraph` | ACTIVE | High-level graph API |
| Graph store | `core/research/graph_store.py:GraphStore` | ACTIVE | SQLite-backed graph persistence |
| Graph models | `core/research/graph_models.py` | ACTIVE | GraphNode, GraphEdge |
| Hypothesis manager | `core/research/hypothesis.py:HypothesisManager` | ACTIVE | Claim-level hypothesis tracking |
| Evidence tracker | `core/research/evidence_tracker.py:EvidenceTracker` | ACTIVE | Bidirectional fact-goal mapping |
| Gap detector | `core/research/gap_detector.py:GapDetector` | ACTIVE | Evidence sufficiency assessment |
| Reflection engine | `core/research/reflection.py:ResearchReflection` | ACTIVE | Post-research pattern learning |
| Reasoning engine | `core/research/reasoning.py:ReasoningEngine` | ACTIVE | Phase 7.5: Bayesian belief-driven reasoning |
| Extraction FSM | `core/research/extraction_fsm.py:ExtractionFSM` | EXPERIMENTAL | Only imported by benchmarks, no production-path imports |
| Deep research tool | `tools/deep_research.py:deep_research()` | ACTIVE | 5-step research pipeline |
| Search tool | `tools/search_tool.py:SearXNGSearch` | ACTIVE | Multi-engine search with DuckDuckGo fallback |
| Search fallback | `tools/search_fallback.py` | ACTIVE | Fallback search chain |
| Crawl4ai tool | `tools/crawl4ai_tool.py:Crawl4AITool` | ACTIVE | Web crawling wrapper |

**Reality score:** 9/10 — Comprehensive research subsystem. extraction_fsm.py is experimental/unused in production.

---

## 12. MEMORY

**Canonical future owner:** `memory/memory_facade.py` (public API) + `core/long_term_memory/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Memory facade | `memory/memory_facade.py:MemoryFacade` | ACTIVE | Unified store/recall API. Singleton: `memory` |
| Tiered memory | `memory/tiered_memory.py:TieredMemory` | ACTIVE | Hot/warm/cold tiered memory |
| Embedding memory | `memory/embedding_memory.py:EmbeddingMemory` | ACTIVE | Ollama+SQLite semantic memory |
| Mem0 adapter | `memory/mem0_adapter.py:Mem0Adapter` | ACTIVE | Cross-session memory via mem0ai |
| Decision memory | `memory/decision_memory.py:DecisionMemory` | ACTIVE | Action->outcome learning. Used by control_loop |
| Preference store | `memory/preferences.py:PreferenceStore` | DEAD | Zero imports across entire codebase |
| JSON memory | `core/memory.py:MemoryManager` | ACTIVE | Legacy JSON file memory. Still widely used |
| Memory-driven router | `core/memory_driven_decisions.py:MemoryDrivenRouter` | ACTIVE | Past-decisions shaping. Used by control_loop |
| Pattern failure memory | `core/pattern_failure_memory.py:PatternFailureMemory` | ACTIVE | Error pattern matching. Heavily used (12+ import sites) |
| Long-term memory adapter | `core/long_term_memory/adapter.py:BehaviorAdapter` | ACTIVE | Knowledge->decision pipeline bridge |
| Long-term consolidator | `core/long_term_memory/consolidator.py:Consolidator` | ACTIVE | Background experience extraction |
| Long-term extractor | `core/long_term_memory/extractor.py:ExperienceExtractor` | ACTIVE | Activity graph->experience conversion |
| Knowledge store | `core/long_term_memory/store.py:KnowledgeStore` | ACTIVE | SQLite knowledge/experience CRUD |
| Knowledge synthesizer | `core/long_term_memory/synthesizer.py:KnowledgeSynthesizer` | ACTIVE | Cross-activity pattern detection |
| Belief system | `core/belief/` (9 files) | ACTIVE | Source tracking, accuracy, freshness, consensus, quality |
| RAG vector | `core/rag_vector.py:VectorRAG` | ACTIVE | ChromaDB hybrid search RAG |
| RAG singleton | `core/rag_singleton.py:get_rag_manager()` | DEAD | Zero imports. Superseded by direct VectorRAG |
| RAG manager (wrapper) | `core/rag_manager.py:RAGManager` | DEAD | Zero imports. Superseded |
| Memory vector | `core/memory_vector.py:MemoryVectorStore` | BROKEN | Non-functional: imports from non-existent `src.chroma_client` and `src.embeddings`. `_healthy` always False |
| Embeddings | `core/embeddings.py:EmbeddingClient` | ACTIVE | HTTP API + FastEmbed fallback |
| Chroma client | `core/chroma_client.py:get_chroma_client()` | ACTIVE | ChromaDB HTTP singleton |
| Evidence generator | `core/evidence/generator.py:EvidenceGenerator` | ACTIVE | 4-source continuous evidence generation |
| Brain memory manager | `brain/memory/memory_manager.py:MemoryManager` | ACTIVE | Orchestrates 4 brain memory types: episodic, semantic, task, decision. Singleton `memory_manager` |
| Brain episodic memory | `brain/memory/episodic.py:EpisodicMemory` | ACTIVE | SQLite-backed goal-driven interaction episodes with actions, context, outcomes |
| Brain semantic memory | `brain/memory/semantic.py:SemanticMemory` | ACTIVE | SQLite-backed fact store with confidence, importance decay, deduplication |
| Brain task memory | `brain/memory/task.py:TaskMemory` | ACTIVE | SQLite-backed execution traces (action, params, observation, success, duration) |
| Brain decision memory | `brain/memory/decision.py:DecisionMemory` | ACTIVE | SQLite-backed decision store: context, decision, alternatives, outcome, lessons |
| Brain memory provider | `brain/memory/base.py:MemoryProvider` | ACTIVE | ABC for all brain memory types |
| Memory fact extraction | `memory/extraction.py:extract_facts()` | ACTIVE | Regex-based subject-predicate-object fact extraction from natural language |
| Memory fact store | `memory/fact_store.py:FactStore` | ACTIVE | SQLite-backed fact storage with embedding support, contradiction detection, consolidation. Singleton via `get_fact_store()` |
| Memory preference profile | `memory/preference_profile.py:PreferenceProfile` | ACTIVE | Builds per-user preference profiles from fact store preference-type facts |
| Memory reranker | `memory/reranker.py:ReRanker` | ACTIVE | Multi-factor memory recall reranker (similarity 0.5, recency 0.3, confidence 0.1, preference 0.1) |

**Reality score:** 6/10 — Multiple overlapping memory systems. 2 dead files (rag_manager, rag_singleton). 1 broken file (memory_vector). PreferenceStore is dead. **Critical overlap:** `brain/memory/` (EpisodicMemory, SemanticMemory, TaskMemory, DecisionMemory) duplicates `memory/` package and `core/activity/storage.py`. `memory/decision_memory.py` vs `brain/memory/decision.py:DecisionMemory` — two separate decision memory implementations with different schemas. `memory/extraction.py` and `memory/fact_store.py` provide fact extraction while `brain/memory/semantic.py:SemanticMemory` does the same.

---

## 13. NOTIFICATIONS

**Canonical future owner:** `notifications/notifier.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Supervisor notifier | `notifications/notifier.py:SupervisorNotifier` | ACTIVE | Email (SMTP), push (ntfy.sh/Pushover), WebSocket, event log. Singleton imported by control_loop, lifespan, supervisor_routes |
| Email monitor | `core/email_monitor.py:EmailMonitor` | ACTIVE | Polls Gmail inbox. Urgency detection. Created in lifespan |
| Alert router | `monitors/alerts.py:AlertRouter` | ACTIVE | Unified alert dispatch: WebSocket, TTS, WhatsApp. Priority levels |

**Reality score:** 8/10 — Notification system is functional but fragmented across notifier, email_monitor, and alert router.

---

## 14. CONFIGURATION

**Canonical future owner:** `core/configuration/service.py:ConfigurationService`

*See Startup section for full details.*

**Reality score:** 6/10 — Four overlapping config systems: JarvisConfig (config_schema), ConfigurationService (configuration/service), Config (config_registry), SettingsStore (settings/store). Dead constants in config.py.

---

## 15. PROVIDERS

**Canonical future owner:** `core/providers/` (execution providers) + `core/model_providers/` (LLM providers)

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| LLM router | `core/llm_router.py:complete()` | ACTIVE | Primary async completion. 40+ import sites |
| LLM core | `core/llm_core.py:stream_llm_with_fallback()` | ACTIVE | Streaming with candidate failover |
| LLM calls | `core/llm_calls.py:llm_call()` | ACTIVE | Synchronous call functions |
| LLM failover | `core/llm_failover.py:FailoverManager` | ACTIVE | Profile-based failover with cooldown |
| LLM providers | `core/llm_providers.py` | ACTIVE | Provider-specific payload builders |
| LLM messages | `core/llm_messages.py:_sanitize_llm_messages()` | ACTIVE | Message cleanup/sanitization |
| LLM state | `core/llm_state.py` | ACTIVE | Host tracking, response cache |
| Model providers (framework) | `core/model_providers/` (9 files) | ACTIVE | OpenAI, Anthropic, Gemini, Groq, Ollama, OpenRouter. Hybrid router |
| Hybrid platform | `core/model_providers/hybrid.py:HybridModelPlatform` | ACTIVE | Local/cloud/hybrid mode switching |
| Model router (framework) | `core/model_providers/router.py:ModelRouter` | ACTIVE | Task-based provider selection with fallback |
| Provider ecosystem | `core/providers/` (20+ files) | ACTIVE | Execution provider framework: desktop, browser, email, workspace, codex, forge, github, messaging, research, deployment |
| Provider registry | `core/providers/registry.py:ProviderRegistry` | ACTIVE | Provider registration and discovery |
| Provider bootstrap | `core/providers/bootstrap.py:bootstrap_providers()` | ACTIVE | Internal+external provider registration |
| Provider feedback | `core/providers/feedback/` (4 files) | ACTIVE | Decision recording, calibration, scoring |
| Provider orchestration | `core/providers/orchestration/` (5 files) | ACTIVE | OrchestrationPlanner, Orchestrator, AdaptEngine |
| Provider SDK | `provider_sdk/` (10 files) | ACTIVE | External provider framework: discovery, registration, lifecycle, loader, manifest v2 |
| Provider SDK loader | `provider_sdk/loader.py` | ACTIVE | Provider discovery and loading from external packages |
| Provider SDK lifecycle | `provider_sdk/lifecycle.py` | ACTIVE | External provider lifecycle management |
| Provider SDK permissions | `provider_sdk/permissions.py` | ACTIVE | Provider permission models |
| Provider SDK quarantine | `provider_sdk/quarantine.py` | ACTIVE | Provider isolation/quarantine |
| Provider SDK stages | `provider_sdk/stages.py` | ACTIVE | Provider execution stages |
| Provider SDK registration | `provider_sdk/registration.py` | ACTIVE | External provider registration |
| Provider SDK manifest | `provider_sdk/manifest.py` / `manifest_v2.py` | ACTIVE | Provider manifest schema (v1 + v2) |
| Provider SDK discovery | `provider_sdk/discovery.py` | ACTIVE | Automated provider discovery |
| Provider SDK adapters | `provider_sdk/adapters/` (4 files) | ACTIVE | MCP, HTTP, gRPC, CLI adapters for external providers |

**Reality score:** 9/10 — Two distinct provider ecosystems (LLM providers + execution providers) + external provider SDK. Both well-structured.

---

## 16. CAPABILITIES

**Canonical future owner:** `core/capability/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Capability models | `core/capability/models.py` | ACTIVE | 20 built-in capabilities |
| Capability registry | `core/capability/registry.py:CapabilityRegistry` | ACTIVE | Register, match, score capabilities |
| Capability graph | `core/capability/graph.py:CapabilityGraph` | ACTIVE | Goal-ability resolution graph |
| Capability composition | `core/capability/composition.py:CompositionEngine` | ACTIVE | Goal->capability->provider composition |
| Capability negotiation | `core/capability/negotiation.py:CapabilityNegotiator` | ACTIVE | Multi-provider negotiation |

**Reality score:** 10/10 — Clean, well-defined capability system with graph-based resolution.

---

## 17. SAFETY

**Canonical future owner:** `core/permission/` + `core/ssrf.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Permission system | `core/permission/` (7 files) | ACTIVE | Models, manager, policy, registry, audit, observer |
| Permission models | `core/permission/models.py` | ACTIVE | 19 permission IDs, RiskLevel, Decision |
| Permission manager | `core/permission/manager.py:PermissionManager` | ACTIVE | Resolution + confirmation |
| Permission policy | `core/permission/policy.py:PolicyEngine` | ACTIVE | STRICT/DEVELOPER/AUTONOMOUS profiles |
| Permission audit | `core/permission/audit.py:PermissionAudit` | ACTIVE | JSONL audit trail |
| Runtime observer | `core/permission/observer.py:RuntimeObserver` | ACTIVE | Violation detection |
| SSRF protection | `core/ssrf.py` | ACTIVE | resolve_and_check, assert_safe_url. Dual-DNS rebinding mitigation |
| URL safety (dead) | `core/url_safety.py:check_outbound_url()` | DEAD | Zero production imports |
| Prompt security | `core/prompt_security.py` | ACTIVE | wrap_untrusted, strip_special_tokens, normalize_homoglyphs |
| Privacy classifier | `core/privacy_classifier.py:PrivacyClassifier` | ACTIVE | LOCAL/HYBRID/CLOUD tiers. Always returns LOCAL by default |
| Sandbox | `core/sandbox/` (3 files) | ACTIVE | Docker sandbox for code execution |
| Safety (desktop) | `core/desktop/safety.py:SafetyManager` | ACTIVE | Desktop action safety guards |
| Tool safety | `core/routing/safety.py:classify_tool()` | ACTIVE | SAFE/CONFIRM/DANGEROUS classification |

**Reality score:** 8/10 — Comprehensive safety architecture. url_safety.py is dead code. Privacy classifier is effectively LOCAL-only.

---

## 18. PERMISSIONS

**Canonical future owner:** `core/authz/` + `core/auth.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Auth manager | `core/auth.py:AuthManager` | ACTIVE | Multi-user auth, bcrypt, TOTP/2FA, session tokens, Firebase |
| FastAPI auth deps | `core/auth.py:verify_token()` | ACTIVE | verify_token, require_scope, require_role |
| AuthZ schema | `core/authz/schema.py` | ACTIVE | Role (5), Scope (20+), AuthContext |
| AuthZ engine | `core/authz/engine.py:PolicyEngine` | ACTIVE | Role-based evaluation with glob matching |
| AuthZ loader | `core/authz/loader.py:PolicyLoader` | ACTIVE | YAML RBAC config loader |
| Permission registry | `core/permission/registry.py:PermissionRegistry` | ACTIVE | Permission registration by provider |

**Reality score:** 9/10 — Full authN/authZ with multi-user support, 2FA, RBAC.

---

## 19. LOGGING

**Canonical future owner:** `core/observability/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| JSON logging | `core/observability/logging.py:JsonFormatter` | ACTIVE | RotatingFileHandler with JSON output |
| Log context | `core/observability/logging.py:LogContext` | ACTIVE | ContextVars for request_id, user_id, session_id |
| Metrics | `core/observability/metrics.py` | ACTIVE | Request counts, LLM latency, tool calls, percentiles |
| Metrics middleware | `core/observability/metrics.py:MetricsMiddleware` | ACTIVE | Starlette middleware |
| Audit log | `core/audit_log.py:AuditLog` | ACTIVE | PII-redacted JSONL audit with buffering |
| Security auditor | `core/security_audit.py:SecurityAuditor` | ACTIVE | Periodic security audit → audit_log + JSON report |
| System logger | `utils/logger.py:SystemLogger` | ACTIVE | Thin logging wrapper |
| Telemetry | `utils/telemetry.py` | ACTIVE | Usage telemetry collection |
| Environment loader | `utils/env_loader.py` | ACTIVE | `.env` file loading and variable resolution |
| Resource monitor | `monitors/resource.py` | ACTIVE | System resource monitoring (CPU, memory, disk) |
| Service health monitor | `monitors/services.py` | ACTIVE | Service health checking |
| Alert router | `monitors/alerts.py:AlertRouter` | ACTIVE | Unified alert dispatch: WebSocket, TTS, WhatsApp. Priority levels |

**Reality score:** 9/10 — Solid observability stack with structured logging, metrics, resource/service monitoring, and alerting.

---

## 20. RECOVERY

**Canonical future owner:** `core/self_healing.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Self-healing framework | `core/self_healing.py:SelfHealing` | ACTIVE | 3-layer: check->heal->recover. 2 registered handlers (ollama, search) |
| Learning loop | `core/self_healing.py:LearningLoop` | ACTIVE | User feedback → rules → prompt suffix |
| Self-diagnosis | `core/self_diagnosis.py:SelfDiagnosis` | ACTIVE | Stuck loops, zero progress, dead agents, resource leaks |
| Doctor | `core/doctor.py:run_doctor()` | ACTIVE | Standalone diagnostic tool. Zero production imports |
| Backup manager | `core/backup.py:BackupManager` | ACTIVE | Tar.gz backup/restore with path traversal protection |
| Checkpoint manager | `core/checkpoint_manager.py:CheckpointManager` | ACTIVE | Per-step checkpoints, rollback, limit enforcement |
| Recovery (workflow) | `core/workflow/recovery.py:recover_active_workflows()` | ACTIVE | Workflow-specific recovery |
| No dedicated recovery module | — | N/A | Recovery scattered across self_healing.py, doctor.py, workflow/recovery.py |

**Reality score:** 6/10 — Recovery is fragmented. Self-healing only handles 2 components. No unified recovery orchestrator.

---

## 21. PLUGIN SYSTEM

**Canonical future owner:** `core/plugins/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Plugin base | `core/plugins/base.py:Plugin` | ACTIVE | Abstract base class with lifecycle hooks |
| Plugin loader | `core/plugins/loader.py` | ACTIVE | Plugin discovery and loading |
| Plugin registry | `core/plugins/registry.py` | ACTIVE | Plugin registration and management |
| Plugin runtime | `core/plugins/runtime.py` | ACTIVE | Runtime plugin lifecycle |
| Plugin API | `core/plugins/api.py` | ACTIVE | Plugin API endpoints |
| Plugin sandbox | `core/plugins/sandbox.py` | ACTIVE | Plugin sandboxing |
| Plugin SSRF | `core/plugins/ssrf.py` | ACTIVE | Plugin SSRF protection |
| Plugin privacy | `core/plugins/privacy.py` | ACTIVE | Plugin privacy controls |
| Plugin events | `core/plugins/events.py` | ACTIVE | Plugin event hooks |
| Plugin automation | `core/plugins/automation.py` | ACTIVE | Automation plugin hooks |
| Plugin voice | `core/plugins/voice.py:VoicePlugin` | ACTIVE | STT/TTS/wake-word plugin hooks |
| Plugin errors | `core/plugins/errors.py` | ACTIVE | Plugin error types |
| Plugin manifest | `core/plugins/manifest.py` | ACTIVE | Plugin manifest schema |
| Plugin dependencies | `core/plugins/dependencies.py` | ACTIVE | Plugin dependency resolution |
| Plugin compatibility | `core/plugins/compatibility.py` | ACTIVE | Plugin compatibility checks |
| Plugin verification | `core/plugins/verification.py` | ACTIVE | Plugin signature verification |
| Plugin hot reload | `core/plugins/hot_reload.py` | ACTIVE | File-watch based hot reload |
| Plugin marketplace | `core/plugins/marketplace.py` | ACTIVE | Plugin marketplace integration |
| Plugin settings store | `core/plugins/settings_store.py` | ACTIVE | Plugin settings persistence |
| Plugin state store | `core/plugins/state_store.py` | ACTIVE | Plugin state persistence |
| Plugin memory | `core/plugins/memory.py` | ACTIVE | Plugin memory access |
| Built-in plugins | `plugins/` (4 files) | ACTIVE | wake_word, PII routing, PC automation, file_tools |
| Plugin SDK | `jarvis_plugin_sdk/` | ACTIVE | Plugin development SDK |

**Reality score:** 10/10 — Mature, comprehensive plugin system with sandboxing, hot-reload, marketplace, and SDK.

---

## 22. VOICE

**Canonical future owner:** `assistant/voice_pipeline.py` + `core/routes/voice.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Voice pipeline | `assistant/voice_pipeline.py:VoiceEngine` | ACTIVE | 1007-line production pipeline: transcribe->think->speak |
| Voice routes | `core/routes/voice.py` | ACTIVE | /stt, /stt/local, /stt/base64, /tts, /voice/test, WS /tts/stream, WS /voice |
| Voice plugin | `core/plugins/voice.py:VoicePlugin` | ACTIVE | Plugin hooks for STT/TTS/wake-word |
| Wake word plugin | `plugins/wake_word_plugin.py` | ACTIVE | Wake word detection plugin |
| Voice config | `core/config_schema.py:VoiceConfig` | ACTIVE | STT/TTS provider and model config |
| STT protocol | `assistant/stt_protocol.py:STTProvider` | ACTIVE | ABC for speech-to-text providers. Registry: `stt_registry` singleton |
| STT init | `assistant/stt.py:init_stt_providers()` | ACTIVE | Registers all STT providers: FasterWhisper (default), Deepgram, Azure |
| TTS protocol | `assistant/tts_protocol.py:TTSProvider` | ACTIVE | ABC for text-to-speech providers. Registry: `tts_registry` singleton |
| TTS core | `assistant/tts.py:JarvisTTS` | ACTIVE | Kokoro-TTS integration with audio caching. Singleton `get_tts()` |
| Wake word detector | `assistant/wake_word.py:WakeWordDetector` | ACTIVE | Two-stage: WebRTC VAD + Faster-Whisper confirmation. Watchdog auto-restart |
| Wake word registry | `assistant/wake_word.py:WakeWordRegistry` | ACTIVE | Manages wake word phrases with phonetic-aware matching (Levenshtein) |
| Voice health monitor | `assistant/voice_pipeline.py:VoiceHealthMonitor` | ACTIVE | Periodic STT/TTS health checks, auto-recovery |
| Voice metrics | `assistant/voice_pipeline.py:VoiceMetrics` | ACTIVE | Per-phase latency tracking (STT, think, TTS, total) |
| FasterWhisper STT | `assistant/providers/faster_whisper.py:FasterWhisperProvider` | ACTIVE | Default STT: local, offline, Faster-Whisper with VAD filter, CUDA/CPU auto-detect |
| Deepgram STT | `assistant/providers/deepgram.py:DeepgramProvider` | ACTIVE | Cloud STT via Deepgram nova-3 API |
| Azure STT | `assistant/providers/azure_speech.py:AzureSpeechProvider` | ACTIVE | Cloud STT via Azure Cognitive Services |
| Kokoro TTS | `assistant/providers/kokoro_tts.py:KokoroTTSProvider` | ACTIVE | Default TTS: wraps JarvisTTS into TTSProvider protocol |
| Edge TTS | `assistant/providers/edge_tts_provider.py:EdgeTTSProvider` | ACTIVE | Cloud TTS via Microsoft Edge online service |
| Legacy voice loop | `assistant/voice_pipeline.py:VoiceLoop` | LEGACY | Backward-compatible wrapper around VoiceEngine |

**Reality score:** 9/10 — Production-grade voice pipeline with protocol-based STT/TTS provider framework, wake word detection, health monitoring. No dedicated `core/voice/` directory.

---

## 23. AUTOMATION

**Canonical future owner:** `core/plugins/automation.py` + `core/scheduler/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Automation plugin | `core/plugins/automation.py` | ACTIVE | Plugin hooks for automation |
| PC automation plugin | `plugins/pc_automation_plugin.py` | ACTIVE | Desktop automation plugin |
| Webhook manager | `core/webhook_manager.py` | ACTIVE | Webhook registration and dispatch |
| MCP manager | `core/mcp_manager.py` | ACTIVE | MCP server management |
| MCP servers | `mcp/` (6 files) | ACTIVE | email_server, memory_server, rag_server, image_gen_server, server |
| PC automation (deprecated) | `automation/pc_automation.py:Parser` | LEGACY | Monolithic NLP command parser for WhatsApp, Instagram, browser, apps, system |
| Messaging automation | `automation/messaging.py:MessagingController` | ACTIVE | Refactored messaging: WhatsAppAutomation, InstagramAutomation via Selenium |
| Call sync server | `automation/call_sync_server.py` | ACTIVE | Windows TCP listener (port 9001): receives call records from Android, desktop notifications, TTS |
| Automation routes | `automation/routes.py` | ACTIVE | FastAPI router exposing automation via `/api/automation/*` |

**Reality score:** 8/10 — Automation infrastructure exists but is less cohesive than other subsystems. pc_automation.py is deprecated in favor of messaging.py and core/desktop.

---

## 24. EVENTBUS

**Canonical future owner:** `core/event_bus.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Core event bus | `core/event_bus.py:EventBus` | ACTIVE | Pub/sub event system |
| Workflow events | `core/workflow/events.py:EventBus` | ACTIVE | Workflow-specific event bus |
| Agent events | `core/agents/events.py:AgentEvent` | ACTIVE | Agent-specific events extending workflow events |
| Plugin events | `core/plugins/events.py` | ACTIVE | Plugin event system |

**Reality score:** 8/10 — Multiple event bus variants. Core event_bus.py is the central pub/sub.

---

## 25. HISTORY (Activity)

**Canonical future owner:** `core/activity/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Activity models | `core/activity/models.py` | ACTIVE | ActivityNode, ActivityEdge, ActivityStatus |
| Activity manager | `core/activity/manager.py:ActivityManager` | ACTIVE | High-level activity CRUD |
| Activity store | `core/activity/storage.py:ActivityStore` | ACTIVE | SQLite-backed persistence (workflow.db) |
| Activity recorder | `core/activity/recorder.py:ActivityRecorder` | ACTIVE | Planner-side recording |
| Activity replay | `core/activity/replay.py:ReplayAssembler` | ACTIVE | DAG-based replay construction |
| Resume engine | `core/activity/resume.py:ResumeEngine` | ACTIVE | Suspended activity resumption |

**Reality score:** 10/10 — Comprehensive activity tracking with DAG replay and resume.

---

## 26. PROJECTS

**Canonical future owner:** `core/project_manager.py` + `core/project_state.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Project manager | `core/project_manager.py:ProjectManager` | ACTIVE | Build queue, prioritization, lifecycle |
| Project state | `core/project_state.py:ProjectState` | ACTIVE | Requirement tracking, completion metrics |
| Cloud project manager | `core/cloud/project_manager.py:ProjectManager` | ACTIVE | Supabase-backed project persistence |
| Workspace manager | `core/workspace_manager.py:WorkspaceManager` | ACTIVE | Project map, build system detection, 16 languages |

**Reality score:** 9/10 — Solid project management with local and cloud backends.

---

## 27. RULES

**Canonical future owner:** `core/governance/` + `core/self_modification/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Governance meta-governor | `governance/MetaGovernor.py` | ACTIVE | Meta-governance rules |
| Governance validator | `governance/GovernanceValidator.py` | ACTIVE | Runtime governance validation |
| Runtime governance layer | `governance/RuntimeGovernanceLayer.py` | ACTIVE | Governance enforcement at runtime |
| Governance work queue | `core/governance/work_queue.py:WorkQueue` | ACTIVE | Priority queue with persistence |
| Governance task router | `core/governance/task_router.py:TaskRouter` | ACTIVE | LLM+rule routing |
| Governance resource monitor | `core/governance/resource_monitor.py:ResourceMonitor` | ACTIVE | Resource-aware throttling |
| Self-modification safety | `core/self_modification/safety.py:SafetyManager` | ACTIVE | Rate limits per session/hour/day |
| No `core/rules/` directory | — | N/A | Rules are in governance/ and self_modification/ |

**Reality score:** 7/10 — No dedicated rules directory. Governance layer exists but is separate from the core codebase.

---

## 28. SELF-MODIFICATION

**Canonical future owner:** `core/self_modification/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Self-modification models | `core/self_modification/models.py` | ACTIVE | Recipe types, modification results, safety limits |
| Self-modification safety | `core/self_modification/safety.py:SafetyManager` | ACTIVE | Enforces max files, lines, restarts |
| Self-modification recipes | `core/self_modification/recipes.py` | ACTIVE | Config, SourceCode, Prompt, Recipe modification types |
| Self-modification planner | `core/self_modification/planner.py:SelfModificationPlanner` | ACTIVE | Prioritizes failing modules |
| Self-modification executor | `core/self_modification/executor.py:SelfModificationExecutor` | ACTIVE | Applies recipes with rollback support |
| Self-modification store | `core/self_modification/store.py:RecipeStore` | ACTIVE | Persistent recipe storage |

**Reality score:** 9/10 — The most powerful subsystem (can modify own source code). Safety limits enforced.

---

## 29. IMPROVEMENT

**Canonical future owner:** `core/improvement/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Improvement models | `core/improvement/models.py` | ACTIVE | Knob, KnobConfig |
| Knob store | `core/improvement/knob_store.py:KnobStore` | ACTIVE | JSON-backed knob persistence |
| Improvement detector | `core/improvement/detector.py:ImprovementDetector` | ACTIVE | Sliding window bottleneck detection |
| Improvement experiment | `core/improvement/experiment.py:ExperimentRunner` | ACTIVE | Stubbed experiment execution |
| Planner detector | `core/improvement/planner_detector.py:PlannerDetector` | ACTIVE | Planning-level issue detection |
| Planner experiment | `core/improvement/planner_experiment.py:PlannerExperiment` | ACTIVE | Logged but not executed |
| Autonomous loop | `core/improvement/autonomous_loop.py:AutonomousLoop` | ACTIVE | Self-improvement cycle orchestration |
| Improvement promoter | `core/improvement/promoter.py:ImprovementPromoter` | ACTIVE | Scores and selects improvements, delegates to generalization |
| Improvement proposals | `core/improvement/proposals.py:ImprovementProposal` | ACTIVE | Proposal persistence |

**Reality score:** 7/10 — Improvement loop exists but experiments are stubbed/logged only. Not fully operational.

---

## 30. GENERALIZATION

**Canonical future owner:** `core/generalization/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Generalization models | `core/generalization/models.py` | ACTIVE | Principle, Strategy, Proposal |
| Principle extractor | `core/generalization/extractor.py:PrincipleExtractor` | ACTIVE | LLM-based principle extraction from experiences |
| Proposal executor | `core/generalization/executor.py:ProposalExecutor` | ACTIVE | Code edit application with rollback |
| Proposal validator | `core/generalization/validator.py:ProposalValidator` | ACTIVE | LLM-based safety/regression analysis |
| Proposal prioritizer | `core/generalization/prioritizer.py:ProposalPrioritizer` | ACTIVE | Impact/urgency scoring |
| Proposal generator | `core/generalization/proposals.py:ProposalGenerator` | ACTIVE | Principle→code patch generation |
| Principle registry | `core/generalization/registry.py:PrincipleRegistry` | ACTIVE | In-memory+JSON principle storage |
| Proposal store | `core/generalization/store.py:ProposalStore` | ACTIVE | File-backed proposal CRUD |
| Causal analyzer | `core/generalization/causal.py:CausalAnalyser` | ACTIVE | Symptom->cause mapping with predefined graph |
| Derived principle engine | `core/generalization/derived.py:DerivedPrincipleEngine` | ACTIVE | Principle composition |

**Reality score:** 8/10 — Well-structured generalization pipeline. Heavy LLM dependency (no deterministic fallback).

---

## 31. STRATEGY

**Canonical future owner:** `core/strategy/` (v1) + `core/strategy/v2/` (v2)

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Strategy models (v1) | `core/strategy/models.py` | ACTIVE | Strategy, Scenario, Decision, EvaluationResult |
| Strategy generator (v1) | `core/strategy/generator.py:StrategyGenerator` | ACTIVE | LLM-based candidate generation |
| Strategy evaluator (v1) | `core/strategy/evaluator.py:StrategyEvaluator` | ACTIVE | Simulation-based evaluation |
| Strategy selector (v1) | `core/strategy/selector.py:StrategySelector` | ACTIVE | Multi-criteria ranking |
| Strategy predictor (v1) | `core/strategy/predictor.py:StrategyPredictor` | ACTIVE | LLM-based outcome prediction |
| Strategy similarity | `core/strategy/similarity.py:StrategySimilarity` | ACTIVE | Deduplication |
| Calibration engine | `core/strategy/calibration.py:CalibrationEngine` | ACTIVE | Historical accuracy tracking |
| Strategy memory adapter | `core/strategy/memory_adapter.py:StrategyMemoryAdapter` | ACTIVE | Bridge to episodic memory |
| Strategy v2 models | `core/strategy/v2/models.py` | ACTIVE | ResourceBudget, Constraint, Portfolio |
| Resource-constrained planner | `core/strategy/v2/planner.py:ResourceConstrainedPlanner` | ACTIVE | Token/time/memory-aware planning |
| Portfolio executor | `core/strategy/v2/executor.py:PortfolioStrategyExecutor` | ACTIVE | Multi-strategy parallel execution |
| Tradeoff analyzer | `core/strategy/v2/tradeoffs.py:TradeoffAnalyzer` | ACTIVE | Pareto-optimal configuration |

**Reality score:** 9/10 — Two generations of strategy system (v1 + v2). v2 adds resource constraints and portfolio execution.

---

## 32. OPPORTUNITY

**Canonical future owner:** `core/opportunity/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Opportunity models | `core/opportunity/models.py` | ACTIVE | Opportunity, Bottleneck, Forecast, RoadmapItem |
| Discovery engine | `core/opportunity/engine.py:DiscoveryEngine` | ACTIVE | Full lifecycle: mine→analyze→forecast→plan→integrate |
| Opportunity miner | `core/opportunity/mining.py:OpportunityMiner` | ACTIVE | Log/metric/error-pattern mining |
| Opportunity graph | `core/opportunity/graph.py:OpportunityGraph` | ACTIVE | Dependency graph with priority propagation |
| Bottleneck analyzer | `core/opportunity/bottlenecks.py:BottleneckAnalyzer` | ACTIVE | Performance bottleneck identification |
| Opportunity forecaster | `core/opportunity/forecasting.py:OpportunityForecaster` | ACTIVE | Trend analysis + regression forecasting |
| Roadmap planner | `core/opportunity/roadmap.py:RoadmapPlanner` | ACTIVE | Critical path analysis for multi-step plans |
| Calibration | `core/opportunity/calibration.py:OpportunityCalibration` | ACTIVE | Historical data validation |
| Opportunity store | `core/opportunity/store.py:OpportunityStore` | ACTIVE | Persistent JSON storage |
| Opportunity routes | `core/routes/opportunities.py` | ACTIVE | REST API for opportunity CRUD |

**Reality score:** 9/10 — End-to-end opportunity discovery pipeline with graph-based planning.

---

## 33. DECISION

**Canonical future owner:** `core/decision/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Decision models | `core/decision/models.py` | ACTIVE | Decision, Evidence, ScoredOption |
| Evidence collector | `core/decision/evidence.py:EvidenceCollector` | ACTIVE | Multi-source evidence (LLM, tools, memory, web) |
| Unified scorer | `core/decision/scoring.py:UnifiedScorer` | ACTIVE | Weighted scoring with configurable criteria |
| Decision bridge | `core/decision/bridge.py:DecisionBridge` | ACTIVE | Cross-system decision integration |

**Reality score:** 8/10 — Clean decision pipeline with multi-source evidence. Bridge enables cross-system integration.

---

## 34. COLLABORATION

**Canonical future owner:** `core/collaboration/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Collaboration models | `core/collaboration/models.py` | ACTIVE | TaskAssignment, AgentCapability, ConsensusVote |
| Collaboration coordinator | `core/collaboration/coordinator.py:CollaborationCoordinator` | ACTIVE | Capability+workload-based task assignment |
| Negotiation manager | `core/collaboration/negotiation.py:NegotiationManager` | ACTIVE | Wraps core/negotiation/engine.py |
| Consensus manager | `core/collaboration/consensus.py:ConsensusManager` | ACTIVE | Accuracy-weighted voting |
| Review manager | `core/collaboration/review.py:ReviewManager` | ACTIVE | Cross-agent work review |

**Reality score:** 8/10 — Multi-agent collaboration with negotiation, consensus, and review.

---

## 35. NEGOTIATION

**Canonical future owner:** `core/negotiation/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Negotiation agents | `core/negotiation/agents.py:NegotiationAgent` | ACTIVE | Role+preference+strategy agents |
| Negotiation engine | `core/negotiation/engine.py:NegotiationEngine` | ACTIVE | Multi-round proposal+preference cycle |
| Negotiation models | `core/negotiation/models.py` | ACTIVE | NegotiationState, NegotiationPreferences |

**Reality score:** 7/10 — Turn-based negotiation. Strategy types: collaborative, competitive, compromise. Used by collaboration system.

---

## 36. EVENTS (EventBus)

*See EventBus section (#24) above.*

---

## 37. SKILLS

**Canonical future owner:** `skills/`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Skills manager | `skills/manager.py` | ACTIVE | Skill management |
| Skills utils | `skills/utils.py` | ACTIVE | Skill utility functions |
| Workflow skills | `skills/` (.md files) | ACTIVE | 4 auto-workflow markdown skills |
| Library skills | `skills/library/` | ACTIVE | Entertainment, finance, knowledge, productivity, system |
| Skills manager | `services/memory/skills.py:SkillsManager` | ACTIVE | Manages skill lifecycle: CRUD, relevance search, categorical indexing. Persists to skills.json |
| Skill format | `services/memory/skill_format.py:Skill` | ACTIVE | Data model + Markdown parser for skill definitions |
| Brain skill acquisition | `brain/skill_acquisition.py:SkillAcquisition` | ACTIVE | Discovers reusable workflows from repeated action patterns via N-gram detection |

**Reality score:** 7/10 — Skills system exists but is less developed than other subsystems. `brain/skill_acquisition.py` provides automatic skill discovery from action traces.

---

## 38. INTEGRATIONS

**Canonical future owner:** `core/integration_manager.py`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Integration manager | `core/integration_manager.py:IntegrationManager` | ACTIVE | Unified BaseIntegration abstraction. Registered: Gmail, Telegram, Discord, Slack, WhatsApp, GitHub, GoogleDrive (stub) |
| External data integrations | `core/integrations/` (5 files) | ACTIVE | News, Sports, Stocks, Timezone, Weather |
| Gmail integration | `integrations/gmail/` | ACTIVE | IMAP/SMTP with attachments, labels, threading |
| WhatsApp integration | `integrations/whatsapp/` (9 files) | ACTIVE | Cloud API + Twilio. Rich media, webhooks, history |
| Channel integrations | `channels/` (7 files) | ACTIVE | Discord, Telegram, Slack, Email, Matrix, IRC |
| Provider SDK | `provider_sdk/` (10 files) | ACTIVE | External provider discovery, registration, lifecycle |

**Reality score:** 9/10 — Extensive integration ecosystem. GoogleDrive is a stub.

---

## 39. BRAIN (Cognitive Core)

**Canonical future owner:** `brain/UnifiedBrain.py` (central orchestrator)

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Unified brain | `brain/UnifiedBrain.py:UnifiedBrain` | ACTIVE | Central cognitive core. Orchestrates reasoning, memory, goals, planning, execution, automation, learning, observers, tools. Singleton `unified_brain` |
| Brain reasoning | `brain/reasoning_engine.py:ReasoningEngine` | ACTIVE | Core LLM reasoning with Chain-of-Thought parsing, fallback, warmup. Singleton `reasoning_engine` |
| Brain cognitive patterns | `brain/cognitive_patterns.py:CognitivePatterns` | ACTIVE | 10 cognitive strategies: plan, critique, reflect, verify, simulate, prioritize, decompose, synthesize, hypothesize, evaluate |
| Brain epistemic tagger | `brain/epistemic_tagger.py:EpistemicTagger` | ACTIVE | Tags responses with [VERIFIED]/[ASSUMED]/[UNCERTAIN]/[RETRIEVED] based on provenance |
| Brain world model | `brain/world_model.py:WorldModel` | ACTIVE | Central situational awareness: tracks entities, resources, goals. Provides structured context for LLM |
| Brain task resolver | `brain/task_resolver.py:TaskResolver` | ACTIVE | Bridges high-level plan nodes to executable tool calls via LLM. Singleton `task_resolver` |
| Brain three-pass pipeline | `brain/UnifiedBrain.py:three_pass()` | ACTIVE | Reason→Critique→Revise three-pass pipeline with plugin hooks |
| Brain reflection | `brain/UnifiedBrain.py:reflect()` | ACTIVE | Reflects on conversation sessions for self-improvement |
| Brain auto-generate goals | `brain/UnifiedBrain.py:auto_generate_goals()` | ACTIVE | Calls GoalGenerator.evaluate_world() for autonomous goal creation |
| Brain learning engine | `brain/learning_engine.py:LearningEngine` | ACTIVE | Reads lessons from DecisionMemory, builds prompt suffix, suppresses/prefers actions based on past outcomes |
| Brain self-improvement | `brain/self_improvement.py:SelfImprovementEngine` | ACTIVE | Propose→Measure→Apply→A/B test→Keep/Revert behavioral intervention |
| Brain skill acquisition | `brain/skill_acquisition.py:SkillAcquisition` | ACTIVE | Discovers reusable workflows from repeated action patterns via N-gram detection |
| Brain prompt optimizer | `brain/prompt_optimizer.py:PromptOptimizer` | ACTIVE | 734-line automated prompt optimization: FailureAnalyzer→PromptGenerator→PromptTester→PromptStore |
| Brain persistence | `brain/persistence.py:ProjectPersistence` | ACTIVE | SQLite-backed multi-day checkpoint/resume for long-running autonomous projects |
| Brain observers | `brain/UnifiedBrain.py:_setup_observers()` | ACTIVE | Registers SystemMonitor, TimeObserver, FileSystemObserver for environment awareness |
| Brain automation loop | `brain/automation/loop.py:AutomationLoop` | ACTIVE | 1234+ line strict autonomous build loop with FailureMemory, ArchitecturalMemory, RequirementTracker, verify_gates |
| Brain execution graph | `brain/planner/task_graph.py:TaskGraph` | ACTIVE | DAG with topological sort, cycle detection, critical path |
| Brain compiler repair | `brain/compiler_repair_engine.py:CompilerRepairEngine` | ACTIVE | 944-line deterministic repair for javac/Gradle/AAPT2 errors |
| Brain repair chain | `brain/repair_chaining.py:RepairChain` | ACTIVE | Iterative fix→rebuild→detect loop with rollback safety |
| Brain production gate | `brain/production_gate.py:ProductionGate` | ACTIVE | Benchmark-based production readiness evaluation |

**Reality score:** 8/10 — brain/ is a parallel cognitive architecture that duplicates many core/ subsystems (planner, executor, memory, automation). UnifiedBrain acts as a second orchestrator alongside core/lifespan and core/pipeline.

---

## 40. CHANNELS (Multi-Platform Messaging)

**Canonical future owner:** `channels/controller.py:ChannelController`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Channel controller | `channels/controller.py:ChannelController` | ACTIVE | Singleton: registers, starts/stops all channels. Unified `send()` API |
| Message processor | `channels/processor.py:process_message()` | ACTIVE | Routes messages through canonical pipeline, emits plugin hooks, enqueues MCP bridge events |
| Base channel plugin | `channels/base.py:ChannelPlugin` | ACTIVE | ABC with ACL (allowlist/blocklist), PairingProtocol for challenge-response device pairing |
| Telegram channel | `channels/telegram_channel.py` | ACTIVE | Telegram bot channel plugin |
| Slack channel | `channels/slack_channel.py` | ACTIVE | Slack bot channel plugin |
| Discord channel | `channels/discord_channel.py` | ACTIVE | Discord bot channel plugin |
| Matrix channel | `channels/matrix_channel.py` | ACTIVE | Matrix protocol channel plugin |
| IRC channel | `channels/irc_channel.py` | ACTIVE | IRC channel plugin |
| Email channel | `channels/email_channel.py` | ACTIVE | Email channel plugin |
| Channel config | `channels/base.py:ChannelConfig` | ACTIVE | Channel configuration dataclass |

**Reality score:** 9/10 — Well-designed channel abstraction with 7 platform implementations. Unified controller lifecycle management.

---

## 41. LEARNING (Student AGI & Pattern Learning)

**Canonical future owner:** `learning/` package

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Training collector | `learning/training_collector.py:TrainingCollector` | ACTIVE | Logs every interaction to SQLite for fine-tuning with auto-labeled accepted/rejected status |
| Pattern engine | `learning/pattern_engine.py:PatternEngine` | ACTIVE | Pure-Python behavioral pattern recognition: frequency analysis, time-series matching, sequence detection |
| Habit tracker | `learning/habit_tracker.py:HabitTracker` | PARTIAL | Stub/placeholder for habit learning |
| Student AGI main | `learning/student_agi/student_agi_main.py` | ACTIVE | Autonomous Student AGI: FastAPI server on port 11436 with teach, ask, feedback, daily lessons, mistakes, progress |
| Student brain | `learning/student_agi/brain/student_brain.py:StudentBrain` | ACTIVE | 913-line core: SQLite knowledge store, step-by-step reasoning, confidence estimation, mistake analysis, emotional state, curiosity engine |
| Jarvis teacher | `learning/student_agi/teacher/jarvis_teacher.py:JarvisTeacher` | ACTIVE | Teaches, quizzes, grades, corrects, encourages the student AGI |
| Student world model | `learning/student_agi/cognition/world_model.py:WorldModel` | ACTIVE | CausalEngine, AnalogyEngine, MetaCognition, ConsistencyChecker for conceptual understanding |
| Student routes | `learning/student_agi/api/student_routes.py` | ACTIVE | Additional API routes for the Student AGI |

**Reality score:** 8/10 — Sophisticated learning system with a complete autonomous Student AGI sub-system. Student AGI is a separate entity taught by JARVIS, not part of the core runtime.

---

## 42. DAEMON (Background Service)

**Canonical future owner:** `daemon/jarvis_service.py:JarvisDaemon`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Jarvis daemon | `daemon/jarvis_service.py:JarvisDaemon` | ACTIVE | Windows background service: heartbeat loop, environment monitoring, stale project cleanup, auto-resume of pending builds |
| PID management | `daemon/jarvis_service.py` | ACTIVE | PID file management and health JSON persistence |
| Windows scheduled task | `daemon/jarvis_service.py:install()`/`uninstall()` | ACTIVE | Creates/removes Windows Scheduled Task via `schtasks` |
| CLI interface | `daemon/jarvis_service.py` | ACTIVE | `python daemon/jarvis_service.py [start|stop|install|uninstall|status]` |

**Reality score:** 7/10 — Functional Windows daemon. No cross-platform support. Tightly coupled to Windows task scheduler.

---

## 43. NETWORK (WebSocket)

**Canonical future owner:** `network/websocket_server.py:ConnectionManager`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Connection manager | `network/websocket_server.py:ConnectionManager` | ACTIVE | Manages WebSocket connections keyed by `device_id:user_id`. Singleton `connection_manager` |
| Message dispatcher | `network/websocket_server.py:handle_message()` | ACTIVE | Processes ping, chat, and echo messages. Chat routes through core.intent_router |

**Reality score:** 6/10 — Minimal WebSocket implementation. Chat routing goes through legacy intent_router. No WS authentication or reconnection.

---

## 44. MCP SERVERS (Standalone)

**Canonical future owner:** `mcp/server.py:MCPServer`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Main MCP server | `mcp/server.py:MCPServer` | ACTIVE | Central MCP server: registers 12+ tools (web_search, browser_navigate, computer, memory_search, send_message, etc.), WebSocket bridge, event queue with approval |
| RAG MCP server | `mcp/rag_server.py` | ACTIVE | MCP server for RAG document management: list indexed files, add/remove directories |
| Memory MCP server | `mcp/memory_server.py` | ACTIVE | MCP server for memory CRUD: list, add, edit, delete, search with vector store |
| Email MCP server | `mcp/email_server.py` | ACTIVE | 1278+ line MCP server for email management: list/send/reply/archive/delete across multiple IMAP accounts |
| Image gen MCP server | `mcp/image_gen_server.py` | ACTIVE | MCP server for image generation via OpenAI-compatible APIs |
| MCP common utils | `mcp/_common.py` | ACTIVE | Shared constants and truncate helper for MCP servers |

**Reality score:** 8/10 — Standalone MCP servers with JSON-RPC 2.0. Each server can run independently. Email server is the most feature-rich.

---

## 45. HYBRID MODELS

**Canonical future owner:** `models/hybrid_models.py:HybridModelManager`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Hybrid model manager | `models/hybrid_models.py:HybridModelManager` | ACTIVE | Orchestrates multiple LLM providers with automatic fallback: Ollama→Codex CLI→Claude→Copilot. Singleton `hybrid_manager` |
| Task-type routing | `models/hybrid_models.py` | ACTIVE | Task-type-specific model routing (planning→deepseek-r1, coding→qwen2.5-coder, vision→moondream) |
| Performance tracking | `models/hybrid_models.py` | ACTIVE | Per-provider performance tracking and confidence estimation |

**Reality score:** 6/10 — Overlaps with core/llm_router and core/llm_failover. Provides a simpler fallback chain but duplicates LLM routing logic.

---

## 46. CONFIG ASSETS

**Canonical future owner:** `config/` directory

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Quality constitution | `config/quality_constitution.json` | ACTIVE | Quality constitution rules/guidelines for output grading |
| Role definitions | `config/roles.yaml` | ACTIVE | Role definitions in YAML for RBAC |

**Reality score:** 7/10 — Static config assets. Not a Python package. Consumed by governance and quality systems.

---

## 47. REMINDERS

**Canonical future owner:** `reminders/manager.py:ReminderManager`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Reminder manager | `reminders/manager.py:ReminderManager` | ACTIVE | Background polling loop (30s), SQLAlchemy-backed due reminder checking, TTS injection for voice alerts |

**Reality score:** 7/10 — Simple background polling implementation. Tightly coupled to AsyncSession and TTS.

---

## 48. NOTES

**Canonical future owner:** `notes/activity_tracker.py:NotesManager`

| Component | File(s) | Status | Details |
|-----------|---------|--------|---------|
| Notes manager | `notes/activity_tracker.py:NotesManager` | ACTIVE | SQLAlchemy CRUD for user notes, tags, activity, daily summaries via core.database models |

**Reality score:** 7/10 — Simple CRUD notes manager integrated with the async ORM.

---

## CROSS-CUTTING ISSUES

### Dead Files (Zero Production Imports)
| File | Responsibility | Notes |
|------|----------------|-------|
| `core/agent_states.py` | Execution | Shim re-exporting from graph/state. Remove safely |
| `core/rag_manager.py` | Memory | Zero imports. Superseded by direct VectorRAG |
| `core/rag_singleton.py` | Memory | Zero imports. Superseded |
| `memory/preferences.py` (PreferenceStore) | Memory | Zero imports |
| `core/url_safety.py` | Safety | Zero imports. Duplicates ssrf.py |

### Broken Code
| File | Responsibility | Issue |
|------|----------------|-------|
| `core/memory_vector.py` | Memory | Imports from non-existent `src.chroma_client` and `src.embeddings`. `_healthy` always False |
| `core/benchmark/perf_baseline.py` | Benchmark | Imports non-existent `mark_setup_state` from `core.setup.detector` (inside try block) |

### Deprecated Code (Explicit DeprecationWarning)
| File | Responsibility | Notes |
|------|----------------|-------|
| `pc_agent/computer_agent.py:ComputerAgent` | Desktop | Explicit deprecation: "will be replaced by core/desktop/" |
| `pc_agent/playbooks.py` | Desktop | Deprecated alongside computer_agent |
| `pc_agent/snapshot.py:SystemSnapshot` | Desktop | Deprecated alongside computer_agent |
| `automation/pc_automation.py` | Automation | Monolithic engine — deprecated in favor of messaging.py and core/desktop |
| `core/memory.py:MemoryManager` | Memory | DeprecationWarning: "use memory.memory_facade.MemoryFacade" |
| `core/model_router.py` | LLM | Backward-compat shim for llm_router |
| `tools/browser_tool.py:JarvisBrowser` | Browser | DeprecationWarning: "re-exports BrowserManager" |
| `governance/resource_monitor.py` | Monitoring | DeprecationWarning: "use monitors/resource.py" |
| `core/environment_monitor.py` | Monitoring | DeprecationWarning |

### Duplicate/Overlapping Systems
| Area | Files | Issue |
|------|-------|-------|
| Configuration | config.py, config_schema.py, config_registry.py, configuration/service.py, settings/store.py | 5 overlapping config systems |
| Request routing | intent_router.py (legacy) vs routing/request_classifier.py (modern) | Two parallel classification paths |
| Agent execution | sub_agents/ (legacy) + adapters vs agents/ (new) | Dual execution systems bridged by adapters |
| **Brain executor** | `brain/executor/` | **Third execution path** — simpler tool registration without full agent lifecycle |
| Diagnostics | core/diagnostics.py (standalone) vs core/diagnostics/ (package) | Two different build_diagnostic_report implementations |
| SSRF | core/ssrf.py vs core/url_safety.py | Two SSRF protection files with different philosophies |
| Event bus | core/event_bus.py, workflow/events.py, agents/events.py, plugins/events.py | Multiple event bus variants |
| Resource monitoring | monitors/resource.py, governance/resource_monitor.py, core/environment_monitor.py | Overlapping resource monitors |
| **Planning** | `core/planner/` (full state machine) vs `brain/planner/` (simple 3-node DAG) | Two parallel planning systems with different complexity |
| **Memory (brain/memory)** | `brain/memory/memory_manager.py` + 4 sub-memories | Duplicates `memory/` package (MemoryFacade, TieredMemory, EmbeddingMemory, Mem0Adapter) |
| **Decision memory** | `memory/decision_memory.py` vs `brain/memory/decision.py:DecisionMemory` | Two separate decision memory implementations with different schemas and persistence |
| **LLM routing** | `core/llm_router.py` (LiteLLM, 8 groups) vs `models/hybrid_models.py:HybridModelManager` (simple fallback) | Two LLM routing systems |
| **Automation** | `brain/automation/loop.py:AutomationLoop` (autonomous build loop) vs `core/control_loop.py:ControlLoop` (core build loop) | Two build-loop implementations |
| **Channels vs routers** | `channels/processor.py:process_message()` (canonical pipeline) vs `routers/chat.py:chat_handler()` (legacy direct handler) | Two message processing paths |
| **Fact extraction** | `memory/extraction.py:extract_facts()` (regex-based) vs `brain/memory/semantic.py:SemanticMemory` (embedding-based) | Two fact extraction/storage approaches |
| **Orchestrators** | `core/lifespan.py` (startup orchestrator) vs `brain/UnifiedBrain.py` (cognitive orchestrator) | Two system orchestrators with different scope |

### Key Architectural Observations
1. **Centralized lifespan** — `core/lifespan.py` is the single orchestration point with ~42 startup phases
2. **Brain as cognitive core** — `brain/UnifiedBrain.py` is a parallel orchestrator that duplicates many core/ subsystems (planner, executor, memory, automation) with its own event wiring and observer system
3. **Activity graph as spine** — Activity system (store/manager/recorder) serves as the common persistence backbone
4. **Provider abstraction** — Two clean provider abstractions (LLM model_providers + execution providers) with registration and routing
5. **Self-improvement chain** — improvement/detector -> generalization/extractor -> proposals -> executor forms a feedback loop
6. **Phase numbering** — Code comments reference Phase numbers (Phase 7.5, 8.1, 10, 13.0, 13.1, 14, 15, 17-24) indicating phased development
7. **Three execution paths** — `core/agents/` (new BaseAgent system), `brain/executor/` (simple tool executor), and legacy sub_agents (now migrated) — three parallel execution systems
8. **Six memory packages** — `memory/` (MemoryFacade), `brain/memory/` (MemoryManager), `core/memory.py` (legacy JSON), `core/long_term_memory/` (KnowledgeStore), `core/activity/storage.py` (ActivityStore), `core/rag_vector.py` (VectorRAG) — six memory systems with overlapping responsibilities
9. **Two orchestrators** — `core/lifespan.py` (startup/HTTP) and `brain/UnifiedBrain.py` (cognitive/autonomous) co-exist with no clear boundary between them
10. **Channels architecture** — `channels/processor.py:process_message()` is the canonical message routing pipeline, but `routers/chat.py:chat_handler()` still bypasses it for direct HTTP requests
11. **No migration path** — No documented process for migrating from legacy to new systems

---

## ROADMAP — 8-Phase Consolidation Plan

> This roadmap was derived from the audit findings above. It is the recommended execution order. Each phase depends on the previous.

### MIGRATION LIFECYCLE (cross-cutting — applies to all phases)

Every legacy→canonical transition follows this sequence:

```
Legacy → Adapter → Dual Run → Validation → Deprecation Warning → Removal → Tests
```

Each phase below lists the subsystems that need this lifecycle applied.

---

### PHASE 0 — Remove Dead Code (1–2 days) ✅ COMPLETED

**Goal:** Delete everything the audit confirmed as dead or broken.

| Action | File(s) | Risk | Status |
|--------|---------|------|--------|
| Delete dead file | `core/agent_states.py` | LOW — zero importers | ✅ |
| Delete dead file | `core/rag_manager.py` | LOW — zero importers | ✅ |
| Delete dead file | `core/rag_singleton.py` | LOW — zero importers | ✅ |
| Delete dead file | `memory/preferences.py` | LOW — zero importers | ✅ |
| Delete dead file | `core/url_safety.py` | LOW — zero importers | ✅ |
| Fix broken imports | `core/memory_vector.py` — change `src.*` → `core.*` | LOW — currently non-functional | ✅ |
| Fix broken imports | `core/benchmark/perf_baseline.py` — remove import of non-existent `mark_setup_state` | LOW — inside try block | ✅ |
| Remove deprecated shim | `tools/browser_tool.py` — redirect imports to `core.browser_manager` | LOW — emits DeprecationWarning | ✅ |
| Remove deprecated shim | `core/model_router.py` — redirect imports to `core.llm_router` | MEDIUM — 7 import sites | ✅ |

**Canonical owner:** Cleanup lead

---

### PHASE 1 — Canonical Architecture (2–3 weeks)

**Goal:** Every subsystem has exactly ONE canonical owner. Eliminate all overlapping implementations.

**Sub-phase 1e completed:** Diagnostics, Event Bus, Resource Monitors, Memory, Agent Execution consolidated. Sub-agents migrated to core/agents/_legacy/.

**Sub-phase 1f completed:** Full deep audit of brain/, memory/, assistant/, tools/, services/, channels/, learning/, daemon/, mcp/, network/, automation/, providers/, plugins/, integrations/, config/, models/. 12 new subsystems documented. 15 new duplicate/overlapping systems identified.

| Subsystem | Current State | Canonical Owner | Action |
|-----------|--------------|-----------------|--------|
| **Configuration** | 5 systems: config.py, config_schema.py, config_registry.py, configuration/service.py, settings/store.py | `core/configuration/service.py:ConfigurationService` | Migrate all consumers to ConfigurationService. Delete config.py constants, deprecate config_registry.py, fold config_schema into service |
| **Request Routing** | 2 paths: intent_router (legacy 750-line rule-based) vs routing/request_classifier (modern) | `core/routing/request_classifier.py` | Kill intent_router's `_rule_based()`, migrate callers to classify_request(), delete intent_router.py |
| **Agent Execution** | 2 layers: sub_agents/ (10 legacy LLM agents) vs agents/ (new BaseAgent system) | `core/agents/` | ✅ COMPLETED — `core/sub_agents/` deleted. SubAgent base + AgentResult moved to `core/agents/_sub_agent_base.py`. AgentRegistry moved to `core/agents/registry.py`. 9 agent implementations moved to `core/agents/_legacy/`. `do_sessions_spawn` moved to `core/tools/sub_agent_spawn.py`. MaestroAgent removed (no adapter existed). All 12 importers (adapters, api routes, spawning manager, forge provider, tests) updated. |
| **Event Bus** | 4 variants: core/event_bus.py, workflow/events.py, agents/events.py, plugins/events.py | `core/event_bus.py` | ✅ COMPLETED — All event bus logic merged into `core/event_bus.py`. `brain/events/event_bus.py` and `core/workflow/events.py` are now re-export shims. WebSocket broadcast added to canonical bus. |
| **Resource Monitoring** | 3 monitors: monitors/resource.py, governance/resource_monitor.py, environment_monitor.py | `monitors/` package | ✅ COMPLETED — `monitors/resource.py` expanded to cover governance API (get_snapshot, should_throttle, should_reject, 5-tier recommend_concurrency, pct/count field aliases). `governance/resource_monitor.py` converted to backward-compat shim with DeprecationWarning. `core/environment_monitor.py` now emits DeprecationWarning. `monitors/__init__.py` exports `resource_monitor` singleton. |
| **SSRF** | 2 files: ssrf.py (strict, active) vs url_safety.py (permissive, dead) | `core/ssrf.py` | Already complete — url_safety.py removed in Phase 0 |
| **Diagnostics** | 2 files: core/diagnostics.py (standalone, dead) vs core/diagnostics/ (package, active) | `core/diagnostics/` package | ✅ COMPLETED — Standalone `core/diagnostics.py` deleted. All functionality merged into `core/diagnostics/report.py`. |
| **Memory** | Multiple facades: memory/memory_facade.py, core/memory.py, memory/tiered_memory.py, memory/embedding_memory.py, memory/mem0_adapter.py | `memory/memory_facade.py` | ✅ COMPLETED — `core/memory.py:MemoryManager` emits DeprecationWarning. `tiered_memory`, `embedding_memory`, `mem0_adapter` already have zero direct production imports (only consumed by the facade). Utility functions (tokenize, jaccard_similarity, get_text_similarity) remain without warning. `core/rag_manager.py` removed in Phase 0. |
| **Brain Memory** | `brain/memory/` (MemoryManager + 4 sub-memories) duplicates `memory/` package | `memory/memory_facade.py` | NEW — `brain/memory/` has EpisodicMemory, SemanticMemory, TaskMemory, DecisionMemory that overlap with memory/ and core/activity/. Must consolidate 6 memory packages into one. |
| **Brain Planner** | `brain/planner/` (simple 3-node DAG) duplicates `core/planner/` (full state machine) | `core/planner/` | NEW — `brain/planner/planner.py:Planner` only creates 3-node DAGs. Should be replaced by core/planner calls or merged. |
| **Brain Executor** | `brain/executor/` (Executor + Verifier) is a third execution path | `core/agents/` | NEW — brain/executor provides simpler tool registration without agent lifecycle. Should consolidate into core/agents/ or core/tools/. |
| **Brain Automation** | `brain/automation/loop.py:AutomationLoop` (1234-line autonomous build loop) overlaps with `core/control_loop.py:ControlLoop` | `core/control_loop.py` | NEW — Two parallel build-loop implementations with different architectures. Need unification. |
| **Hybrid Models** | `models/hybrid_models.py:HybridModelManager` duplicates `core/llm_router.py` | `core/llm_router.py` | NEW — HybridModelManager provides simpler fallback chain but duplicates LLM routing. Should be deprecated in favor of llm_router. |
| **Decision Memory** | `memory/decision_memory.py` vs `brain/memory/decision.py:DecisionMemory` — two implementations | `memory/memory_facade.py` | NEW — Different schemas and persistence mechanisms for the same concept. Need consolidation. |

**Canonical owner:** Architecture lead

---

### PHASE 2 — Universal Activity Layer (2–3 weeks)

**Goal:** Every subsystem emits ActivityNode. ActivityStore becomes the universal backbone for replay, resume, memory, analytics, debugging, and monitoring.

| Subsystem | Emission Point | Backend |
|-----------|---------------|---------|
| Planner | `core/planner/` → `ActivityManager.create_activity()` | `core/activity/storage.py:ActivityStore` |
| Workflow | `core/workflow/engine.py` → ActivityNode per step | ActivityStore |
| Browser | `core/tools/browser_tools.py` → ActivityNode per action | ActivityStore |
| Desktop | `core/desktop/controller.py` → ActivityNode per DesktopAction | ActivityStore |
| Coding | `core/coding/change_planner.py` → ActivityNode per change | ActivityStore |
| Research | `core/research/extractor.py` → ActivityNode per extraction | ActivityStore |
| Build | `core/tools/automated_build.py` → ActivityNode per phase | ActivityStore |
| Voice | `assistant/voice_pipeline.py` → ActivityNode per utterance | ActivityStore |
| Scheduler | `core/scheduler/` → ActivityNode per task execution | ActivityStore |

**Consumers of ActivityStore after wiring:**

```
ActivityStore
  ├── ReplayAssembler — debug any execution
  ├── ResumeEngine — resume interrupted work
  ├── MemoryFacade — learn from past activities
  ├── AnalyticsPlanner — performance analysis
  ├── Diagnostics — execution tracing
  ├── Monitoring — real-time activity tracking
  └── ImprovementDetector — pattern mining
```

**Canonical owner:** Activity team

---

### PHASE 3 — Unified Reasoning Engine (2–3 weeks)

**Goal:** One canonical pipeline replaces ad-hoc LLM calls across subsystems.

```
Request
  ↓
Intent (routing/request_classifier)
  ↓
Goal (goal_interpreter + capability/composition)
  ↓
Capability (capability/graph + capability/negotiation)
  ↓
Planner (planner/state_machine + templates)
  ↓
Strategy (strategy/v2/planner + portfolio)
  ↓
Decision (decision/evidence + decision/scoring)
  ↓
Execution (agents/executor + providers/router)
  ↓
Verification (planner/health + refactor_safety)
  ↓
Memory (long_term_memory + belief)
  ↓
Learning (improvement + generalization)
```

| Current Ad-hoc Path | Replacement |
|--------------------|-------------|
| `agent_runtime.run_task()` → direct `complete()` call | Pipeline dispatches to Strategy→Decision→Execution |
| `browser_planner._llm_chose_browser_tool()` → inline LLM | Pipeline Goal→Capability→Planner selects tool |
| `research/reasoner.py` → direct LLM | Pipeline Strategy→Decision→Evidence collection |
| `coding/impact_analyzer` → standalone analysis | Pipeline Capability→Planner→Strategy |

**Pipeline orchestrator:** Build a new `core/pipeline/orchestrator.py` that routes each request through the canonical stages. The existing `core/pipeline.py:RuntimePipeline` is the starting point.

**Canonical owner:** Reasoning team

---

### PHASE 4 — Universal Memory (1–2 weeks)

**Goal:** One `MemoryFacade` API backed by all memory tiers. No module imports memory sub-components directly.

| Memory Type | Current File(s) | Unified API |
|-------------|-----------------|-------------|
| Episodic | `core/activity/storage.py:ActivityStore` | `MemoryFacade.recall(type="episodic")` |
| Semantic | `memory/embedding_memory.py:EmbeddingMemory` | `MemoryFacade.recall(type="semantic")` |
| Vector | `core/rag_vector.py:VectorRAG` | `MemoryFacade.search(type="vector")` |
| Decisions | `memory/decision_memory.py:DecisionMemory` | `MemoryFacade.recall(type="decision")` |
| Experiences | `core/long_term_memory/store.py:KnowledgeStore` | `MemoryFacade.recall(type="experience")` |
| Beliefs | `core/belief/store.py:BeliefStore` | `MemoryFacade.recall(type="belief")` |
| Preferences | `memory/preferences.py:PreferenceStore` | (DEAD — remove) |
| Working | `core/session.py:SessionManager` | `MemoryFacade.recall(type="working")` |
| Long-term | `core/long_term_memory/consolidator.py:Consolidator` | `MemoryFacade.consolidate()` |

**Consolidation target:** `memory/memory_facade.py:MemoryFacade` becomes the SINGLE import for all memory operations. Direct imports of `tiered_memory`, `embedding_memory`, `mem0_adapter`, `KnowledgeStore`, `BeliefStore`, etc., are deprecated.

**Canonical owner:** Memory team

---

### PHASE 5 — Autonomous Loop (2–3 weeks)

**Goal:** Connect existing subsystems into a continuous Observe→Detect→Plan→Execute→Verify→Learn→Improve→Repeat loop.

```
Scheduler
  ↓ (triggers)
Observe — monitors/resource.py, monitors/services.py, monitors/alerts.py
  ↓ (feeds)
Research — core/research/ (gap detection, opportunity mining)
  ↓ (produces)
Opportunity — core/opportunity/ (engine→graph→forecast→roadmap)
  ↓ (selects)
Planner — core/planner/ (state_machine→templates→strategies)
  ↓ (commits)
Decision — core/decision/ (evidence→scoring)
  ↓ (executes)
Execution — core/agents/ → core/providers/
  ↓ (validates)
Verification — core/planner/health + core/coding/refactor_safety
  ↓ (stores)
Memory — core/long_term_memory/consolidator + core/belief/
  ↓ (detects patterns)
Improvement — core/improvement/detector + promoter
  ↓ (extracts principles)
Generalization — core/generalization/extractor + validator
  ↓ (repeats)
Scheduler — schedule next observation
```

**What already exists:** Every box in this pipeline is implemented. The missing piece is the wiring — a loop orchestrator that chains them together.

**What to build:** `core/autonomous/orchestrator.py` — reads scheduler triggers, routes through the loop, handles failures, reports progress.

**Canonical owner:** Autonomous team

---

### PHASE 6 — Runtime & Distribution (6A–6F, completed)

**Goal:** Complete the runtime platform with security, tenancy, distribution, and
distributed graph execution.

| Sprint | Focus | Status |
|---|---|---|
| 6A | Identity models & propagation (User, Session, Identity propagation) | ✅ |
| 6B | Tenant boundaries & multi-tenancy (TenantResolution stage, tenant isolation) | ✅ |
| 6C | Resource access & authorization (ResourceScope, Authorization, Permission grants) | ✅ |
| 6D | RuntimeContext v1 (frozen runtime object model, canonical pipeline 19 stages) | ✅ |
| 6E | Distribution layer (WorkerRegistry, Transport, WorkerEndpoint, InProcess/HTTP) | ✅ |
| 6F | Distributed Graph (DAG execution, scheduler, checkpoint, recovery, architecture rules 43–47) | ✅ |

**Key outputs:** `core/distribution/`, `core/identity/`, `core/pipeline/` (19-stage canonical pipeline),
`docs/architecture/ADR-008-runtime-v1.md`, architecture rules 1–47.

**Marketplace / Ecosystem plans deferred to Phase 9.**

---

> **Roadmap update (runtime-v1):** Phase 7 was originally planned as Enterprise.
> After completion of Runtime v1 (Identity, Multi-tenancy, Distribution, Distributed Graph),
> the roadmap was reordered. Intelligence Platform now precedes Enterprise because it builds
> directly on the completed runtime architecture. Enterprise capabilities move to Phase 8
> without loss of scope. Universal Graph moves to Phase 9.

### PHASE 7 — Intelligence Platform (4–6 weeks)

**Goal:** Transform the runtime into a system that can reason, compare strategies,
learn from outcomes, and explain every decision.

**Canonical spec:** `docs/architecture/ADR-009-intelligence-platform.md`

| Sprint | Focus | Type | Dependencies |
|---|---|---|---|
| 7.0 | Consolidation audit & frozen contracts | Inventory | None |
| 7.1 | Reasoning integration (ReasoningEngine, EvidenceTracker, FactReasoner) | Integration | Sprint 0 |
| 7.2 | Knowledge graph integration (KnowledgeGraph, GraphStore) | Integration | Sprint 0 |
| 7.3 | Multi-strategy planner (strategy generation, comparison, ranking) | New build | Sprint 1 |
| 7.4 | Reflection integration (ResearchReflection) | Integration | Sprint 0 |
| 7.5 | Learning engine (merge DecisionMemory + brain/learning_engine) | Merge + new | Sprint 4 |
| 7.6 | Policy optimization (thresholds, weights, retry limits) | New build | Sprint 5 |
| 7.7 | Explainability (unified explanation artifact) | New build | Sprints 1+2+3 |
| 7.8 | Intelligence metrics (reasoning_depth, evidence_count, etc.) | New build | Sprint 7 |
| 7.9 | Architecture rules 48–55 | Enforcement | Sprint 8 |
| 7.10 | Deterministic replay & regression tests | New build | Sprint 9 |

**Existing assets reused:** `core/research/reasoning.py`, `reasoner.py`, `evidence_tracker.py`,
`knowledge_graph.py`, `graph_store.py`, `reflection.py`, `synthesizer.py`, `planner.py`.

**Pipeline insertion:** Knowledge → Reasoning → Planner → Reflection → Learning → Explainability
(6 new or replaced stages in the 23-stage pipeline).

---

### PHASE 8 — Enterprise Platform (4–6 weeks)

**Goal:** Multi-user, multi-team operation with shared state.

| Feature | Current State | Target |
|---------|--------------|--------|
| Organizations | ❌ | Org-scoped projects, memory, workflows |
| Teams | ❌ | Team workspaces with membership |
| Permissions | ✅ Single-user RBAC | Org-level RBAC with inheritable policies |
| Shared Memory | ❌ | Cross-user memory with access controls |
| Distributed Agents | ❌ | Remote agent workers, cloud orchestration |
| Remote Execution | ❌ | Execute on remote machines via provider SDK |

**Prerequisites:** Phase 1 (config canonical), Phase 7 (intelligence pipeline)

**Canonical owner:** Enterprise team

---

### PHASE 9 — Universal Graph & Marketplace (4–6 weeks each)

**Goal (Graph):** One graph database unifying all current graph types.

| Current Graph | File(s) | Status |
|-------------|---------|--------|
| Activity Graph | `core/activity/storage.py` | ACTIVE — SQLite |
| Knowledge Graph | `core/research/graph_store.py` + `knowledge_graph.py` | ACTIVE — SQLite |
| Dependency Graph | `core/coding/dependency_graph.py` | ACTIVE — in-memory+SQLite |
| Capability Graph | `core/capability/graph.py` | ACTIVE — in-memory |
| Opportunity Graph | `core/opportunity/graph.py` | ACTIVE — JSON |
| Workflow Graph | `core/workflow/graph.py:ExecutionGraph` | ACTIVE — in-memory |
| Browser FSM Graph | `core/tools/browser_fsm.py:BrowserFSM` | ACTIVE — in-memory |

**Unified data model:**

```
Project → Goal → Plan → Activity → Decision → Evidence
                                         → Memory
                                         → Capability
                                         → Agent
                                         → Tool
                                         → Workflow
                                         → Repository
                                         → File
                                         → Function
```

**Implementation strategy:**
1. Define a single `GraphNode` and `GraphEdge` schema that covers all current graph types
2. Migrate `ActivityStore` to the unified schema (it's the most mature)
3. Migrate remaining graphs one by one
4. Build a single `GraphDB` class with relationship traversal, path finding, and subgraph extraction
5. Replace all existing graph implementations with `GraphDB`

**Goal (Marketplace):** Expand the existing plugin marketplace into a full App Store:
Plugins, Agents, Skills, Workflows, MCP Servers, Prompt Packs, Integrations,
Capability Packs, Tool Providers, Templates, Themes, Models.

**Canonical owner:** Graph team (cross-cutting) / Marketplace team

---

### SUMMARY — Execution Order

```
Phase 0: Remove Dead Code          ██░░░░░░░░░░░░░░  1–2 days      ✅ COMPLETED
Phase 1: Canonical Architecture    ██████████░░░░░░  2–3 weeks     🔄 IN PROGRESS (1e✅ 1f✅)
Phase 2: Universal Activity Layer  ████████████░░░░  2–3 weeks
Phase 3: Unified Reasoning Engine  ██████████████░░  2–3 weeks
Phase 4: Universal Memory          ██████████████░░  2–3 weeks     (scope expanded: 6→1 consolidation)
Phase 5: Autonomous Loop           ████████████████  2–3 weeks
Phase 6: Runtime & Distribution    ████████████████  3–4 weeks     6A–6F (Identity → Distributed Graph)
Phase 7: Intelligence Platform     ████████████████  4–6 weeks     ADR-009
Phase 8: Enterprise Platform       ████████████████  4–6 weeks
Phase 9: Universal Graph / Marketplace ████████████  4–6 weeks each

MIGRATION LIFECYCLE                ░░░░░░░░░░░░░░░░  Ongoing
```

**Total estimated effort:** 6–9 months with a focused team (reordered per runtime-v1 checkpoint).

**Phase 1 remaining work (15 new consolidation targets):**
- `brain/memory/` (6 memory packages → 1)
- `brain/planner/` (merge into core/planner/)
- `brain/executor/` (merge into core/agents/ or core/tools/)
- `brain/automation/loop.py` (merge with core/control_loop.py)
- `models/hybrid_models.py` (deprecate in favor of core/llm_router.py)
- `memory/decision_memory.py` vs `brain/memory/decision.py` (consolidate)
- `routers/chat.py` (route through channels/processor.py)
- Core orchestrator boundary: `core/lifespan.py` vs `brain/UnifiedBrain.py`

**The golden rule:** No new features until Phase 1 is complete. Every feature built on a fragmented architecture creates more migration debt.
