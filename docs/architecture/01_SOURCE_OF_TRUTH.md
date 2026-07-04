# SOURCE OF TRUTH — MJ Constitution

> Audit date: 2026-07-04
> Phase: Phase 1b complete — Diagnostics consolidated, Event Bus consolidated.
> Methodology: grep import analysis, file-by-file read, dependency tracing.

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

**Reality score:** 9/10 — Cohesive pipeline. goal_interpreter is the primary entry, capability graph handles resolution.

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

**Reality score:** 9/10 — Comprehensive planning layer. Two experimental planners (site, horizon) are wired but secondary.

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

**Reality score:** 7/10 — Two execution systems coexist (new BaseAgent + legacy SubAgent). Adapter pattern bridges them. agent_states.py is dead.

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

**Reality score:** 8/10 — core/desktop is the active system. pc_agent is deprecated with explicit warning. Workspace modules are well integrated.

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

**Reality score:** 10/10 — Mature, well-layered coding intelligence subsystem. Phase structure clear.

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

**Reality score:** 7/10 — Multiple overlapping memory systems. 2 dead files (rag_manager, rag_singleton). 1 broken file (memory_vector). PreferenceStore is dead.

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

**Reality score:** 9/10 — Two distinct provider ecosystems (LLM providers + execution providers). Both well-structured.

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

**Reality score:** 9/10 — Solid observability stack with structured logging, metrics, and audit.

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

**Reality score:** 9/10 — Production-grade voice pipeline. No dedicated `core/voice/` directory (functionality spread across routes, plugins, assistant).

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

**Reality score:** 8/10 — Automation infrastructure exists but is less cohesive than other subsystems.

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

**Reality score:** 7/10 — Skills system exists but is less developed than other subsystems.

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

### Duplicate/Overlapping Systems
| Area | Files | Issue |
|------|-------|-------|
| Configuration | config.py, config_schema.py, config_registry.py, configuration/service.py, settings/store.py | 5 overlapping config systems |
| Request routing | intent_router.py (legacy) vs routing/request_classifier.py (modern) | Two parallel classification paths |
| Agent execution | sub_agents/ (legacy) + adapters vs agents/ (new) | Dual execution systems bridged by adapters |
| Diagnostics | core/diagnostics.py (standalone) vs core/diagnostics/ (package) | Two different build_diagnostic_report implementations |
| SSRF | core/ssrf.py vs core/url_safety.py | Two SSRF protection files with different philosophies |
| Event bus | core/event_bus.py, workflow/events.py, agents/events.py, plugins/events.py | Multiple event bus variants |
| Resource monitoring | monitors/resource.py, governance/resource_monitor.py, core/environment_monitor.py | Overlapping resource monitors |

### Key Architectural Observations
1. **Centralized lifespan** — `core/lifespan.py` is the single orchestration point with 42 startup phases
2. **Activity graph as spine** — Activity system (store/manager/recorder) serves as the common persistence backbone
3. **Provider abstraction** — Two clean provider abstractions (LLM model_providers + execution providers) with registration and routing
4. **Self-improvement chain** — improvement/detector -> generalization/extractor -> proposals -> executor forms a feedback loop
5. **Phase numbering** — Code comments reference Phase numbers (Phase 7.5, 8.1, 10, 13.0, 13.1, 14, 15, 17-24) indicating phased development
6. **No migration path** — No documented process for migrating from legacy to new systems

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

### PHASE 1 — Canonical Architecture (1–2 weeks)

**Goal:** Every subsystem has exactly ONE canonical owner. Eliminate all overlapping implementations.

| Subsystem | Current State | Canonical Owner | Action |
|-----------|--------------|-----------------|--------|
| **Configuration** | 5 systems: config.py, config_schema.py, config_registry.py, configuration/service.py, settings/store.py | `core/configuration/service.py:ConfigurationService` | Migrate all consumers to ConfigurationService. Delete config.py constants, deprecate config_registry.py, fold config_schema into service |
| **Request Routing** | 2 paths: intent_router (legacy 750-line rule-based) vs routing/request_classifier (modern) | `core/routing/request_classifier.py` | Kill intent_router's `_rule_based()`, migrate callers to classify_request(), delete intent_router.py |
| **Agent Execution** | 2 layers: sub_agents/ (10 legacy LLM agents) vs agents/ (new BaseAgent system) | `core/agents/` | Delete sub_agents/ directory. Adapters already bridge. Remove Maestro (no adapter exists) |
| **Event Bus** | 4 variants: core/event_bus.py, workflow/events.py, agents/events.py, plugins/events.py | `core/event_bus.py` | ✅ COMPLETED — All event bus logic merged into `core/event_bus.py`. `brain/events/event_bus.py` and `core/workflow/events.py` are now re-export shims. WebSocket broadcast added to canonical bus. |
| **Resource Monitoring** | 3 monitors: monitors/resource.py, governance/resource_monitor.py, environment_monitor.py | `monitors/` package | ✅ COMPLETED — `monitors/resource.py` expanded to cover governance API (get_snapshot, should_throttle, should_reject, 5-tier recommend_concurrency, pct/count field aliases). `governance/resource_monitor.py` converted to backward-compat shim with DeprecationWarning. `core/environment_monitor.py` now emits DeprecationWarning. `monitors/__init__.py` exports `resource_monitor` singleton. |
| **SSRF** | 2 files: ssrf.py (strict, active) vs url_safety.py (permissive, dead) | `core/ssrf.py` | Already complete — url_safety.py removed in Phase 0 |
| **Diagnostics** | 2 files: core/diagnostics.py (standalone, dead) vs core/diagnostics/ (package, active) | `core/diagnostics/` package | ✅ COMPLETED — Standalone `core/diagnostics.py` deleted. All functionality merged into `core/diagnostics/report.py`. |
| **Memory** | Multiple facades: memory/memory_facade.py, core/memory.py, memory/tiered_memory.py, memory/embedding_memory.py, memory/mem0_adapter.py | `memory/memory_facade.py` | ✅ COMPLETED — `core/memory.py:MemoryManager` emits DeprecationWarning. `tiered_memory`, `embedding_memory`, `mem0_adapter` already have zero direct production imports (only consumed by the facade). Utility functions (tokenize, jaccard_similarity, get_text_similarity) remain without warning. `core/rag_manager.py` removed in Phase 0. |

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

### PHASE 6 — Marketplace (3–4 weeks)

**Goal:** Expand the existing plugin marketplace into a full App Store for the JARVIS ecosystem.

| Artifact Type | Current Support | Marketplace Target |
|--------------|-----------------|-------------------|
| Plugins | ✅ `core/plugins/marketplace.py` | Install, version, dependency resolution |
| Agents | ❌ | Publish BaseAgent subclasses as packages |
| Skills | ❌ `skills/library/` (local only) | Remote skill registries |
| Workflows | ❌ | Workflow template registry |
| MCP Servers | ❌ | MCP server discovery and installation |
| Prompt Packs | ❌ | Shared system prompt collections |
| Integrations | ❌ | One-click integration installation |
| Capability Packs | ❌ | Bundled capability sets |
| Tool Providers | ❌ | Provider registration from remote |
| Templates | ❌ | Project/site/workflow templates |
| Themes | ❌ | UI theme packs |
| Models | ❌ | Model registry + one-click pull |

**Canonical owner:** Marketplace team

---

### PHASE 7 — Enterprise (4–6 weeks)

**Goal:** Multi-user, multi-team operation with shared state.

| Feature | Current State | Target |
|---------|--------------|--------|
| Organizations | ❌ | Org-scoped projects, memory, workflows |
| Teams | ❌ | Team workspaces with membership |
| Permissions | ✅ Single-user RBAC | Org-level RBAC with inheritable policies |
| Shared Memory | ❌ | Cross-user memory with access controls |
| Distributed Agents | ❌ | Remote agent workers, cloud orchestration |
| Remote Execution | ❌ | Execute on remote machines via provider SDK |

**Prerequisites:** Phase 1 (config canonical), Phase 7 (graph database)

**Canonical owner:** Enterprise team

---

### PHASE 8 — Universal Graph (4–6 weeks)

**Goal:** One graph database unifying all current graph types.

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

**Canonical owner:** Graph team (cross-cutting)

---

### SUMMARY — Execution Order

```
Phase 0: Remove Dead Code          ██░░░░░░░░░░░░░░  1–2 days
Phase 1: Canonical Architecture    ████████░░░░░░░░  1–2 weeks
Phase 2: Universal Activity Layer  ████████████░░░░  2–3 weeks
Phase 3: Unified Reasoning Engine  ██████████████░░  2–3 weeks
Phase 4: Universal Memory          ██████████████░░  1–2 weeks
Phase 5: Autonomous Loop           ████████████████  2–3 weeks
Phase 6: Marketplace               ████████████████  3–4 weeks
Phase 7: Enterprise                ████████████████  4–6 weeks
Phase 8: Universal Graph           ████████████████  4–6 weeks

MIGRATION LIFECYCLE                ░░░░░░░░░░░░░░░░  Ongoing
```

**Total estimated effort:** 4–6 months with a focused team.

**The golden rule:** No new features until Phase 1 is complete. Every feature built on a fragmented architecture creates more migration debt.
