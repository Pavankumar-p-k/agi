# SOURCE OF TRUTH — MJ Architecture Constitution

**Generated:** 2026-07-18  
**Scope:** Full codebase audit (READ ONLY)  
**Principle:** Every major responsibility has ONE canonical owner.

---

## Responsibility Index

| # | Responsibility | Canonical Owner | Status |
|---|----------------|-----------------|--------|
| 1 | Startup | `core/lifespan.py:lifespan()` | ACTIVE |
| 2 | Request Processing | `core/pipeline/pipeline.py:Pipeline.execute()` | ACTIVE |
| 3 | Goal Understanding | `core/pipeline/stages/intent.py:IntentStage` | ACTIVE |
| 4 | Planning | `core/planner/executor.py:PlannerExecutor` | ACTIVE |
| 5 | Execution | `core/tools/executor.py:ToolExecutor` + `core/pipeline/stages/execution.py:ExecutionStage` | ACTIVE |
| 6 | Workflow | `core/workflow/engine.py:WorkflowEngine` | ACTIVE |
| 7 | Scheduler | `core/scheduler/scheduler.py:Scheduler` + `core/cron.py:scheduler` | ACTIVE |
| 8 | Desktop | `core/desktop/controller.py:DesktopController` | ACTIVE |
| 9 | Browser | `core/tools/browser_tools.py` + `browser_fsm.py` + `browser_planner.py` | ACTIVE |
| 10 | Coding | `core/coding/` + `core/tools/implementations.py` | ACTIVE |
| 11 | Research | `core/research/` | ACTIVE |
| 12 | Memory | `memory/memory_facade.py:MemoryFacade` | ACTIVE |
| 13 | Notifications | `notifications/notifier.py:SupervisorNotifier` | ACTIVE |
| 14 | Configuration | `core/configuration/service.py:ConfigurationService` | ACTIVE |
| 15 | Providers | `core/providers/router.py:ProviderRouter` + `core/providers/registry.py:ProviderRegistry` | ACTIVE |
| 16 | Capabilities | `core/capability/registry.py:CapabilityRegistry` | ACTIVE |
| 17 | Safety | `core/desktop/safety.py:SafetyManager` | ACTIVE |
| 18 | Permissions | `core/permission/manager.py:PermissionManager` | ACTIVE |
| 19 | Logging | `core/observability/logging.py` + `utils/logger.py` | ACTIVE |
| 20 | Recovery | `core/workflow/recovery.py` + `core/self_healing.py` | ACTIVE |
| 21 | Plugin System | `core/plugins/loader.py:PluginLoader` + `core/plugins/registry.py:PluginRegistry` | ACTIVE |
| 22 | Voice | `assistant/voice_pipeline.py:VoiceLoop` | ACTIVE |
| 23 | Automation | `automation/pc_automation.py` + `core/plugins/automation.py:PCAutomationPlugin` | ACTIVE |
| 24 | EventBus | `core/event_bus.py:EventBus` (`global_event_bus`) | ACTIVE |
| 25 | History | `core/history/service.py:HistoryService` | ACTIVE |
| 26 | Projects | `core/project_manager.py:ProjectManager` | ACTIVE |
| 27 | Rules | `core/governance/` | ACTIVE |

---

## Detailed Responsibility Audit

---

### 1. STARTUP
**Canonical Owner:** `core/lifespan.py:lifespan()` (async context manager for FastAPI)

**Implementations:**
- **ACTIVE:** `core/lifespan.py` — 945 lines, orchestrates 30+ subsystem initializations in sequence:
  - DB init (`core/database.py:init_db()`)
  - Auth (`core/auth.py:AuthManager`)
  - Firebase (`core/auth.py:init_firebase()`)
  - Reminders (`reminders/manager.py:reminder_manager`)
  - TTS injection (`assistant/tts.py:get_tts()`)
  - Monitoring (`monitors/`: `ResourceMonitor`, `AlertRouter`, `ServiceHealthChecker`)
  - LLM Failover (`core/llm_failover.py:CooldownProbe`)
  - Email Monitor (`core/email_monitor.py:EmailMonitor`)
  - Audio Emotion (`core/audio_emotion.py:emotion_detector`)
  - Scene Generator (`tools/scene_generator.py:scene_generator`)
  - Agent Registry (`core/agent_registry.py`)
  - Ollama background poll
  - Reasoning warmup (`brain/reasoning_engine.py:reasoning_engine.warmup()`)
  - Voice Loop (`assistant/voice_pipeline.py:VoiceLoop`)
  - AutoDream (`core/dreaming.py:DreamingLoop`)
  - Self-healing (`core/self_healing.py:learning_loop`, `self_healing`)
  - Quality Grader (`core/quality_grader.py:QualityGrader`, `ConstitutionalMemory`)
  - Prompt Optimizer (`brain/prompt_optimizer.py:PromptOptimizer`)
  - Project Manager queue (`core/project_manager.py:project_manager`)
  - Plugin System (`core/plugins/loader.py:PluginLoader`, builtin plugins)
  - Provider Ecosystem (`core/providers/bootstrap.py:bootstrap_providers()`)
  - Skills loader (`core/plugins/loader.py:get_plugin_loader()`)
  - Governance work queue (`core/governance/work_queue.py`)
  - Audit Log (`core/audit_log.py:audit_log`)
  - RBAC (`core/authz/loader.py:policy_loader`)
  - Channels (`channels/controller.py:channel_controller`)
  - MCP (`mcp/mcp_server.py:mcp_server`, `core/gateway/bridge.py:mcp_bridge`)
  - Cron (`core/cron.py:scheduler`)
  - Activity Scheduler (`core/scheduler/scheduler.py:Scheduler`)
  - Backup (`core/backup.py:backup_manager`)
  - Security Auditor (`core/security_audit.py:security_auditor`)
  - Skills (`skills/skill_manager.py:skill_manager`)
  - Commitments (`core/commitments.py:commitment_store`)
  - Proactive Monitor (`core/proactive_monitor.py:init_proactive_monitor()`)
  - Workflow Engine + Recovery + Heartbeat (`core/workflow/engine.py`, `recovery.py`, `HeartbeatMonitor`)
  - Knowledge Consolidator (`core/long_term_memory/consolidator.py:Consolidator`)

**Legacy/Dead:** None found. Single canonical entry point.

---

### 2. REQUEST PROCESSING
**Canonical Owner:** `core/pipeline/pipeline.py:Pipeline.execute()` → 19-stage pipeline (ADR-006 order)

**Stages (in order):**
1. `ReceiveStage` (`core/pipeline/stages/receive.py`)
2. `LoadContextStage` (`core/pipeline/stages/load_context.py`)
3. `AuthenticationStage` (`core/pipeline/stages/auth.py`)
4. `TenantResolutionStage` (`core/pipeline/stages/tenant_resolution.py`)
5. `AuthorizationStage` (`core/pipeline/stages/authorization.py`)
6. `ResourceAccessStage` (`core/pipeline/stages/resource_access.py`)
7. `RateLimitStage` (`core/pipeline/stages/rate_limit.py`)
8. `IntentStage` (`core/pipeline/stages/intent.py`)
9. `ContextRetrievalStage` (`core/pipeline/stages/context_retrieval.py`)
10. `KnowledgeStage` (`core/pipeline/stages/knowledge.py`)
11. `ReasoningStage` (`core/pipeline/stages/reasoning.py`)
12. `PlannerStage` (`core/pipeline/stages/planner.py`)
13. `PlanValidatorStage` (`core/pipeline/stages/plan_validator.py`)
14. `CapabilitySelectionStage` (`core/pipeline/stages/capability_selection.py`)
15. `ExecutionStage` (`core/pipeline/stages/execution.py`)
16. `VerificationStage` (`core/pipeline/stages/verification.py`)
17. `EpistemicTaggingStage` (`core/pipeline/stages/epistemic.py`)
18. `ReflectionStage` (`core/pipeline/stages/reflection.py`)
19. `LearningStage` (`core/pipeline/stages/learning.py`)
20. `PolicyOptimizationStage` (`core/pipeline/stages/policy_optimization.py`)
21. `MemoryStage` (`core/pipeline/stages/memory.py`)
22. `NotificationStage` (`core/pipeline/stages/notification.py`)
23. `MetricsStage` (`core/pipeline/stages/metrics.py`)
24. `ExplainabilityStage` (`core/pipeline/stages/explainability/`)
25. `FormatterStage` (`core/pipeline/stages/formatter.py`)

**Entry Point:** `core/pipeline/pipeline.py:process_message(request, services)` → creates `PipelineContext` → executes pipeline → returns `Response`

**Transport Adapters (all delegate to pipeline):**
- **REST:** `core/pipeline/adapters/rest_adapter.py:rest_adapter()` → called from `core/routes/chat.py`
- **WebSocket:** `core/pipeline/adapters/websocket_adapter.py:ws_adapter()` / `stream_via_pipeline()` → called from `core/routes/chat.py:websocket_router`
- **Channel:** `core/pipeline/adapters/channel_adapter.py:channel_adapter()` → called from `channels/processor.py`
- **Voice:** `core/pipeline/adapters/voice_adapter.py` (TTS/STT pipeline integration)

**Legacy Fallback:** `core/agent_loop.py:stream_agent_loop()` has `_disable_pipeline` flag that falls back to `core/graph:build_default_graph()` (LangGraph-based). Fallback counter tracked via `_fallback_count`.

---

### 3. GOAL UNDERSTANDING
**Canonical Owner:** `core/pipeline/stages/intent.py:IntentStage`

**Implementations:**
- **ACTIVE:** `IntentStage.execute(ctx)` — uses `core/llm_router.py:resolve_model()` + LLM call to classify intent, extracts entities, maps to capabilities
- **CONNECTED:** `brain/UnifiedBrain.py:reason()` — three-pass reasoning (reason → critique → revise) for deeper understanding
- **PARTIAL:** `core/routing/request_classifier.py` — legacy request classification (pre-pipeline)

**Evidence:** `core/pipeline/stages/intent.py` imports `core.llm_router`, `core.prompts`, classifies `ctx.raw_input` into structured intent with `capability`, `entities`, `confidence`.

---

### 4. PLANNING
**Canonical Owner:** `core/planner/executor.py:PlannerExecutor` (deterministic, template-based)

**Implementations:**
- **ACTIVE:** `PlannerExecutor`:
  - `create_plan(goal)` → classifies goal → selects template → builds `ExecutionPlan` with steps
  - `decompose_goal(goal)` → uses `GoalDecomposer` (`core/planner/decomposer.py`) → returns `SubGoal` tree
  - `create_decomposed_plan(goal)` → creates plans for each leaf sub-goal
  - `record_step(plan_id, tool_name, success)` — tracks pending/completed/failed steps
  - `check_early_termination(plan_id, completed_tools)` — detects missing required steps
  - `inject_task(plan_id, step_name, overrides)` — enforces execution of required steps bypassing LLM
- **ACTIVE:** `core/planner/decomposer.py:GoalDecomposer` — LLM-based hierarchical decomposition
- **ACTIVE:** `core/planner/dag.py:TaskGraph`, `TaskNode` — DAG representation
- **ACTIVE:** `core/planner/strategies.py` — planning strategies (sequential, parallel, adaptive)
- **CONNECTED:** `core/pipeline/stages/planner.py:PlannerStage` — pipeline integration, calls `PlannerExecutor`
- **LEGACY:** `brain/UnifiedBrain.py:plan_goal()` — uses `core.planner.decomposer` + `core.planner.executor.PlannerExecutor` (duplicate path)

**Templates:** `core/planner/templates.py` — defines `TEMPLATES` mapping goal patterns to required/optional steps (research, build, test, validate, email, apk, notify).

---

### 5. EXECUTION
**Canonical Owner:** `core/tools/executor.py:ToolExecutor` + `core/pipeline/stages/execution.py:ExecutionStage`

**Implementations:**
- **ACTIVE:** `ToolExecutor.execute(block, session_id, ...)` — wraps `core.tools.execution.handlers:execute_tool_block()` with `ExecutionManager` lifecycle (start/progress/completed/failed events + memory trace recording)
- **ACTIVE:** `ExecutionStage.execute(ctx)` — pipeline stage, uses `ToolExecutor`, handles tool blocks from `ctx.formatted_response`
- **ACTIVE:** `core/tools/execution/handlers.py:execute_tool_block()` — 68K lines, massive dispatch to 100+ tool handlers:
  - `direct_tools.py` — shell, fs, grep, glob, task, todo, http, python, etc.
  - `edit_tools.py` — edit_file, edit_file_text, replace, etc.
  - `formatting.py` — format, lint, typecheck
  - `mcp.py` — MCP tool calls
  - `subprocess.py` — subprocess execution
  - `security.py` — SSRF protection, path validation
  - `plugins.py` — plugin tool execution
- **CONNECTED:** `brain/UnifiedBrain.py:executor` → `brain/executor.py:Executor` (singleton `_executor_singleton`) — legacy unified executor, registers project tools
- **LEGACY:** `core/agent_executor.py`, `core/agent_launcher.py` — old agent loop executors

---

### 6. WORKFLOW
**Canonical Owner:** `core/workflow/engine.py:WorkflowEngine`

**Implementations:**
- **ACTIVE:** `WorkflowEngine`:
  - `execute_workflow(workflow_type, input_data, ...)` — runs FSM-based workflows
  - `recover_active_workflows()` — crash recovery on startup
  - Compensation/rollback support (`compensate()`)
  - Idempotency keys
- **ACTIVE:** `core/workflow/long_horizon_fsm.py:LongHorizonFSM` — multi-day workflow state machine
- **ACTIVE:** `core/workflow/recovery.py` — `recover_workflow()`, `compensate_workflow()`
- **ACTIVE:** `core/workflow/heartbeat_monitor.py:HeartbeatMonitor` — detects stale workflows
- **ACTIVE:** `core/workflow/tracker.py:WorkflowTracker` — progress tracking
- **ACTIVE:** `core/workflow/storage.py` — persistence layer
- **CONNECTED:** `core/pipeline/stages/notification.py` — workflow event notifications
- **LEGACY:** `core/workflow/calibration.py` — workflow calibration (experimental)

---

### 7. SCHEDULER
**Canonical Owner:** `core/scheduler/scheduler.py:Scheduler` (activity scheduler) + `core/cron.py:scheduler` (cron)

**Implementations:**
- **ACTIVE:** `core/scheduler/scheduler.py:Scheduler` — tick-based (5s default), registry of executors:
  - `research_executor`, `build_executor`, `repair_executor`, `email_executor`, `benchmark_executor`
  - `core/scheduler/registry.py:SchedulerRegistry` — registers executors by name
  - `core/scheduler/autonomous.py` — autonomous scheduling decisions
  - `core/scheduler/intelligence.py` — scheduling intelligence
  - `core/scheduler/queue.py` — priority queue
  - `core/scheduler/worker.py` — worker pool
- **ACTIVE:** `core/cron.py:scheduler` — cron-style recurring jobs (`add(name, schedule, func, params)`)
- **CONNECTED:** `core/lifespan.py` starts both schedulers on startup
- **LEGACY:** `core/scheduler/pipeline_executor.py` — pipeline-specific executor

---

### 8. DESKTOP
**Canonical Owner:** `core/desktop/controller.py:DesktopController` (singleton `desktop_controller`)

**Implementations:**
- **ACTIVE:** `DesktopController` — pyautogui wrapper with safety checks:
  - Mouse: `move_mouse`, `click`, `double_click`, `scroll`, `drag`
  - Keyboard: `type_text`, `press_key`, `hotkey`
  - App/URL: `launch_app`, `open_url`
  - All actions emit `desktop.*` events to `global_event_bus`
  - Replay recording via `core/desktop/replay.py:desktop_replay`
- **ACTIVE:** `core/desktop/safety.py:SafetyManager` (singleton `safety_manager`) — pre-action validation:
  - Emergency stop
  - Forbidden screen regions
  - Mouse speed limits (2000 px/s)
  - Typing rate limits (30 char/s)
  - Screenshot rate (10/min), click rate (60/min)
  - Cooldown enforcement (50ms)
  - Audit logging
- **ACTIVE:** `core/desktop/window.py` — window management (focus, minimize, maximize, restore, close)
- **ACTIVE:** `core/desktop/screen.py` — screen capture
- **LEGACY:** `automation/pc_automation.py` — Open Interpreter integration (separate path)

---

### 9. BROWSER
**Canonical Owner:** `core/tools/browser_tools.py` + `core/tools/browser_fsm.py` + `core/tools/browser_planner.py`

**Implementations:**
- **ACTIVE:** `core/tools/browser_tools.py` — 37K lines, Playwright-based:
  - `browser_navigate`, `browser_click`, `browser_type`, `browser_scroll`, `browser_screenshot`, `browser_extract`, `browser_wait`, `browser_eval`
  - Session management, multi-tab, frame handling
- **ACTIVE:** `core/tools/browser_fsm.py` — `BrowserFSM` state machine for complex browser tasks
- **ACTIVE:** `core/tools/browser_planner.py` — `BrowserPlanner` — LLM-driven browser action planning (67K lines)
- **ACTIVE:** `core/tools/browser_research.py` — `BrowserResearch` — automated research via browser
- **CONNECTED:** `core/pipeline/stages/execution.py` executes browser tools via `ToolExecutor`
- **LEGACY:** `core/agents/browser_agent.py` — agent-based browser control (pre-tools)

---

### 10. CODING
**Canonical Owner:** `core/coding/` + `core/tools/implementations.py`

**Implementations:**
- **ACTIVE:** `core/coding/`:
  - `repository_indexer.py` — codebase indexing
  - `dependency_graph.py` — import/dep analysis
  - `impact_analyzer.py` — change impact analysis
  - `change_planner.py` — plans code changes
  - `change_simulation.py` — simulates changes
  - `refactoring_engine.py` — automated refactoring
  - `refactor_safety.py` — safety checks
  - `architecture_map.py`, `architecture_reasoning.py` — architecture analysis
  - `build_benchmark.py` — build performance
- **ACTIVE:** `core/tools/implementations.py` — 58K lines, code implementation tools:
  - `write_file`, `edit_file_text`, `create_directory`, `run_command`, `compile_java`, `run_tests`, `build_project`
  - Language-specific: Python, TypeScript, Java, Go, Rust, etc.
  - Framework-aware: React, FastAPI, Django, Spring, etc.
- **CONNECTED:** `core/tools/cookbook_tools.py` — 67K lines, pattern-based code generation
- **CONNECTED:** `core/tools/build_tools.py` — build orchestration

---

### 11. RESEARCH
**Canonical Owner:** `core/research/` — `ResearchPlanner`, `Retriever`, `Synthesizer`

**Implementations:**
- **ACTIVE:** `core/research/planner.py:ResearchPlanner` — plans research strategy
- **ACTIVE:** `core/research/retriever.py:Retriever` — multi-source retrieval (web, docs, code)
- **ACTIVE:** `core/research/synthesizer.py:Synthesizer` — synthesizes findings
- **ACTIVE:** `core/research/extractor.py` — content extraction
- **ACTIVE:** `core/research/evidence_tracker.py` — tracks evidence/provenance
- **ACTIVE:** `core/research/gap_detector.py` — detects knowledge gaps
- **ACTIVE:** `core/research/reasoner.py` — research-specific reasoning
- **ACTIVE:** `core/research/knowledge_graph.py` — builds knowledge graphs
- **ACTIVE:** `core/research/graph_store.py` — graph persistence
- **ACTIVE:** `core/research/hypothesis.py` — hypothesis generation/testing
- **ACTIVE:** `core/tools/deep_research.py` — deep research tool (entry point)
- **CONNECTED:** `core/pipeline/stages/knowledge.py:KnowledgeStage` — pipeline integration

---

### 12. MEMORY
**Canonical Owner:** `memory/memory_facade.py:MemoryFacade` (singleton `memory`)

**Implementations:**
- **ACTIVE:** `MemoryFacade` — unified interface over 5 backends:
  - **Episodic:** `memory/episodic_store.py:EpisodicStore` — goal/action/result episodes
  - **Semantic:** `memory/semantic_store.py:SemanticStore` — facts with confidence
  - **Task:** `memory/task_store.py:TaskStore` — action traces (success/failure/duration)
  - **Decision:** `memory/decision_store.py:DecisionStore` — architecture decisions + lessons
  - **Vector:** `memory/vector_store.py` — ChromaDB collections
- **ACTIVE:** `memory/tiered_memory.py:tiered_memory` — hot/warm/cold tiering (used by `MemoryFacade.store()`)
- **ACTIVE:** `memory/mem0_adapter.py:mem0_memory` — mem0 integration (used by tiered)
- **ACTIVE:** `memory/embedding_memory.py` — embedding-based recall
- **ACTIVE:** `memory/extraction.py` — fact extraction from conversations
- **ACTIVE:** `memory/preference_profile.py` — user preference learning
- **ACTIVE:** `memory/reranker.py` — cross-encoder reranking
- **CONNECTED:** `brain/UnifiedBrain.py` uses `_canonical_memory` (alias to `memory`) for all memory ops
- **CONNECTED:** `core/pipeline/stages/memory.py:MemoryStage` — pipeline integration

---

### 13. NOTIFICATIONS
**Canonical Owner:** `notifications/notifier.py:SupervisorNotifier` (singleton `notifier`)

**Implementations:**
- **ACTIVE:** `SupervisorNotifier.notify(project, event, data)`:
  - Event log write (`~/.jarvis/projects/{project}/events.jsonl`)
  - Email (SMTP) for `build_completed`, `task_failed`
  - Push: ntfy.sh + Pushover for `build_completed`, `build_started`, `task_failed`
  - WebSocket client registry (`register_ws`, `unregister_ws`)
- **CONNECTED:** `core/lifespan.py` wires `supervisor.on_notify(notifier.notify)`
- **LEGACY:** `core/email_monitor.py` — inbound email monitoring (separate)

---

### 14. CONFIGURATION
**Canonical Owner:** `core/configuration/service.py:ConfigurationService` (singleton `configuration`)

**Implementations:**
- **ACTIVE:** `ConfigurationService`:
  - Resolution chain: overrides → env vars → config.yaml → settings.json → SettingsStore → registry defaults
  - `load(config_yaml, settings_json)` — loads from multiple sources
  - `get(key)`, `set(key, value, persist)`, `reset(key)`
  - Capability-based model resolution (`resolve(capability)`) → routes to ollama/openai/anthropic
  - Provider management (`get_providers()`, `set_provider_enabled()`, `set_routing()`)
  - Encrypted secrets (`~/.jarvis/api_keys.json`, `oauth_tokens.json`)
  - Change listeners (`on_change(key, callback)`) + event bus emission (`config.changed`)
  - API dict export with secret masking
- **DEPRECATED:** `core/config.py` — shim with `__getattr__` delegation to `ConfigurationService`
- **REGISTRY:** `core/config_registry.py` — defines config schema (types, defaults, UI hints, env var mappings)
- **SCHEMA:** `core/config_schema.py:jarvis_config` — Pydantic models for validation

---

### 15. PROVIDERS
**Canonical Owner:** `core/providers/router.py:ProviderRouter` (singleton `provider_router`) + `core/providers/registry.py:ProviderRegistry` (singleton `provider_registry`)

**Implementations:**
- **ACTIVE:** `ProviderRegistry`:
  - `register(provider, priority)`, `unregister()`, `enable()`, `disable()`, `set_priority()`
  - Capability index: `get_providers_for_capability(capability)`
  - Persistence to `~/.jarvis/provider_settings/registry.json`
- **ACTIVE:** `ProviderRouter.select(capability, task, workflow_id, prefer_offline, record_decision)`:
  - Filters: enabled, budget, memory skip, health
  - Evidence-based scoring (7 dimensions): historical_success, benchmark_quality, health, latency, cost, budget, offline_availability
  - Weights configurable via `_DEFAULT_WEIGHTS`
  - Calibration adjustment from `core/providers/feedback/calibrator.py:CalibrationEngine`
  - Decision recording via `core/providers/feedback/recorder.py:DecisionRecorder`
  - Fallback chain via `select_with_fallback()`
- **ACTIVE:** `core/providers/base.py:ExecutionProvider` — abstract base with `capabilities()`, `estimate_latency()`, `estimate_cost()`, `cached_health()`
- **ACTIVE:** `core/providers/memory.py:ProviderMemory` — performance tracking (Bayesian success rates)
- **ACTIVE:** `core/providers/budget.py:ProviderBudgetManager` — cost budgets per provider/workflow
- **ACTIVE:** `core/providers/bootstrap.py:bootstrap_providers()` — registers builtin providers (Ollama, OpenAI, Anthropic, etc.)
- **ADAPTERS:** `provider_sdk/adapters/` — MCP, HTTP, gRPC, CLI adapters for external providers

---

### 16. CAPABILITIES
**Canonical Owner:** `core/capability/registry.py:CapabilityRegistry`

**Implementations:**
- **ACTIVE:** `core/capability/registry.py` — `CapabilityRegistry` (singleton via `core.capability`)
- **ACTIVE:** `core/capability/graph.py:CapabilityGraph` — dependency graph
- **ACTIVE:** `core/capability/models.py` — capability definitions
- **ACTIVE:** `core/capability/negotiation.py` — capability negotiation
- **ACTIVE:** `core/capability/composition.py` — capability composition
- **CONNECTED:** `core/pipeline/stages/capability_selection.py:CapabilitySelectionStage` — selects providers for capabilities
- **CONNECTED:** `core/providers/router.py` uses capabilities for routing

---

### 17. SAFETY
**Canonical Owner:** `core/desktop/safety.py:SafetyManager` (singleton `safety_manager`)

**Implementations:**
- **ACTIVE:** `SafetyManager.check(action_type, details)` → `SafetyDecision`:
  - Emergency stop gate
  - Cooldown enforcement (50ms)
  - Mouse: forbidden regions, speed limit (2000 px/s)
  - Keyboard: typing rate (30 char/s), max length (500)
  - Screenshot rate (10/min), click rate (60/min)
  - Audit log (`_audit_log`), history (`_history`)
- **ACTIVE:** `core/control/kill_switch.py:kill_switch` — global kill switch (`check()`, `engage()`, `release()`)
- **ACTIVE:** `core/permission/manager.py:PermissionManager` — permission policies
- **ACTIVE:** `core/governance/task_router.py` — governance validation for actions
- **CONNECTED:** `DesktopController` calls `safety_manager.check()` before every action
- **CONNECTED:** `core/plugins/automation.py` — plugin safety hooks

---

### 18. PERMISSIONS
**Canonical Owner:** `core/permission/manager.py:PermissionManager`

**Implementations:**
- **ACTIVE:** `PermissionManager`:
  - `check(permission, context)` → `PermissionDecision`
  - Policy registry (`core/permission/registry.py`)
  - Audit logging (`core/permission/audit.py`)
  - Observer pattern (`core/permission/observer.py`)
- **ACTIVE:** `core/permission/policy.py` — policy definitions
- **ACTIVE:** `core/permission/models.py` — permission models
- **CONNECTED:** `core/authz/loader.py:policy_loader` — RBAC policies
- **CONNECTED:** `core/pipeline/stages/authorization.py:AuthorizationStage` — pipeline integration

---

### 19. LOGGING
**Canonical Owner:** `core/observability/logging.py` + `utils/logger.py`

**Implementations:**
- **ACTIVE:** `core/observability/logging.py` — structured logging setup, JSON formatter, log levels
- **ACTIVE:** `utils/logger.py` — `get_logger(name)` singleton pattern
- **ACTIVE:** `core/main.py` — root logger config (rotating file handler, stdout, `JARVIS_LOG_LEVEL`)
- **ACTIVE:** `core/lifespan.py` — logs every subsystem startup with `[LIFESPAN]` prefix
- **ACTIVE:** `core/event_bus.py` — logs event dispatch (`logger.debug("[EventBus] subscribed...")`)
- **CONNECTED:** All modules use `logging.getLogger(__name__)`

---

### 20. RECOVERY
**Canonical Owner:** `core/workflow/recovery.py` + `core/self_healing.py`

**Implementations:**
- **ACTIVE:** `core/workflow/recovery.py` — `recover_workflow()`, `compensate_workflow()`, `recover_active_workflows()`
- **ACTIVE:** `core/workflow/engine.py:WorkflowEngine.recover_active_workflows()` — called on startup
- **ACTIVE:** `core/self_healing.py:self_healing` — `SelfHealing` class with error pattern detection
- **ACTIVE:** `core/self_healing.py:learning_loop` — continuous learning from failures
- **ACTIVE:** `core/spawning/orphan.py:orphan_recovery.recover()` — subagent orphan recovery
- **ACTIVE:** `core/scheduler/autonomous.py` — autonomous recovery decisions
- **CONNECTED:** `core/lifespan.py` starts workflow recovery + heartbeat monitor
- **LEGACY:** `core/backup.py:backup_manager` — backup/restore (separate)

---

### 21. PLUGIN SYSTEM
**Canonical Owner:** `core/plugins/loader.py:PluginLoader` (singleton `get_plugin_loader()`) + `core/plugins/registry.py:PluginRegistry` (singleton `plugin_registry`)

**Implementations:**
- **ACTIVE:** `PluginLoader.load_all(path)` — scans for `plugin.json`/`skill.json`, loads manifests, installs deps, imports entry module, calls `setup(registry)`
- **ACTIVE:** `PluginRegistry` — `register(manifest, module)`, `unregister()`, `load_all(state)`, `unload_all()`, `run_hook(hook_name, **data)`
- **ACTIVE:** `core/plugins/base.py:Plugin` — base class with hook decorators (`@hook("on_request")`)
- **ACTIVE:** `core/plugins/manifest.py:PluginManifest` — schema validation
- **ACTIVE:** `core/plugins/dependencies.py:dependency_resolver` — pip install from manifest `requires`
- **ACTIVE:** `core/plugins/compatibility.py:compatibility_checker` — version compatibility
- **ACTIVE:** `core/plugins/hot_reload.py` — file watcher for hot reload
- **ACTIVE:** `core/plugins/watchdog.py:PluginWatchdog` — health checks
- **ACTIVE:** `core/plugins/verification.py:manifest_verifier` — manifest integrity verification
- **ACTIVE:** `core/plugins/marketplace.py:plugin_marketplace` — plugin index refresh
- **BUILTIN PLUGINS** (registered in `core/lifespan.py`):
  - `WakeWordPlugin` — wake word detection
  - `PIIRoutingPlugin` — PII detection → local routing
  - `PCAutomationPlugin` — PC automation with governance
  - `MemoryPlugin` — tiered memory hooks
  - `FileToolsPlugin` — filesystem tools
- **CONNECTED:** `core/pipeline/pipeline.py:Pipeline.hooks` — `HookRegistry` for pipeline-stage hooks
- **LEGACY:** `core/plugins/automation.py` — old automation plugin interface

---

### 22. VOICE
**Canonical Owner:** `assistant/voice_pipeline.py:VoiceLoop` (singleton via `core/lifespan.py`)

**Implementations:**
- **ACTIVE:** `VoiceLoop` — wake word + STT + TTS pipeline:
  - `assistant/wake_word.py` — WebRTC VAD + Faster-Whisper wake word
  - `assistant/stt.py` — `STTProtocol`, providers: `faster_whisper`, `deepgram`
  - `assistant/tts.py` — `TTSProtocol`, providers: `edge_tts`, `kokoro_tts`, `azure_speech`
  - `assistant/providers/` — provider implementations
- **ACTIVE:** `core/desktop/controller.py` — voice-triggered desktop actions
- **CONNECTED:** `core/lifespan.py` starts `VoiceLoop` on startup
- **CONNECTED:** `core/plugins/base.py:WakeWordPlugin` — plugin wrapper
- **LEGACY:** `assistant/edge_tts_module.py` — old Edge TTS wrapper

---

### 23. AUTOMATION
**Canonical Owner:** `automation/pc_automation.py` + `core/plugins/automation.py:PCAutomationPlugin`

**Implementations:**
- **ACTIVE:** `automation/pc_automation.py:PCAutomation` — Open Interpreter integration:
  - `execute(command)` — runs OI with governance validation
  - `messaging.py` — cross-platform messaging (WhatsApp, SMS, etc.)
  - `call_sync_server.py` — call handling
- **ACTIVE:** `core/plugins/automation.py:PCAutomationPlugin` — plugin wrapper with hooks: `on_execute`, `on_governance_check`
- **ACTIVE:** `core/desktop/controller.py:DesktopController` — low-level OS automation
- **CONNECTED:** `core/lifespan.py` registers `PCAutomationPlugin`
- **LEGACY:** `automation/routes.py` — HTTP routes for automation

---

### 24. EVENTBUS
**Canonical Owner:** `core/event_bus.py:EventBus` (singleton `global_event_bus`)

**Implementations:**
- **ACTIVE:** `EventBus`:
  - Pattern subscription (exact, wildcard *, multi **)
  - Priority ordering
  - Async + sync publish
  - Streaming queue subscribers
  - In-memory event history ring buffer (100)
  - Dispatch stats
  - WebSocket broadcast (session-scoped + global)
  - Tenant-aware routing (`resource_scope.tenant_id`)
  - Namespace isolation (`system`, `plugin`, `workflow`)
- **ACTIVE:** `core/event_bus.py` — System event types:
  - Config: `CONFIG_CHANGED`, `CONFIG_RELOADED`, `CONFIG_VALIDATION_ERROR`
  - RAG: `RAG_DOCUMENTS_RETRIEVED`, `RAG_DOCUMENT_SCORED`, `RAG_RELEVANCE_FEEDBACK`
  - Workflow: `WORKFLOW_IDEMPOTENCY_HIT`
  - Memory: `MEMORY_FACT_CONFLICT`, `MEMORY_INDEX_UPDATED`
  - Database: `DATABASE_CONNECTION_POOLED`
- **ACTIVE:** `core/event_bus.py` — Workflow event types (legacy compat):
  - `WORKFLOW_STARTED`, `WORKFLOW_RESUMED`, `STEP_STARTED`, `STEP_COMPLETED`, `STEP_FAILED`, `WORKFLOW_COMPLETED`, `WORKFLOW_FAILED`, `WORKFLOW_CANCELLED`, `WORKFLOW_RECOVERED`, `COMPENSATION_STARTED`, `COMPENSATION_STEP_STARTED`, `COMPENSATION_STEP_COMPLETED`, `COMPENSATION_STEP_FAILED`, `WORKFLOW_COMPENSATED`, `COMPENSATION_FAILED`, `IDEMPOTENCY_HIT`
  - Goal: `GOAL_CREATED`, `GOAL_UPDATED`, `GOAL_COMPLETED`, `GOAL_FAILED`
  - Node: `NODE_CREATED`, `NODE_UPDATED`, `NODE_COMPLETED`, `NODE_FAILED`, `NODE_SKIPPED`
  - Artifact: `ARTIFACT_CREATED`
  - Meta: `CONFIDENCE_UPDATED`, `ESTIMATE_UPDATED`, `NEED_INPUT`, `WARNING`, `ERROR`, `MILESTONE`, `FOCUS_CHANGED`
- **ACTIVE:** `core/event_bus.py` — Build event types: `BUILD_STARTED`, `BUILD_COMPLETED`, `BUILD_FAILED`, `BUILD_FIX_REQUESTED`
- **ACTIVE:** `core/event_bus.py` — Execution trace/decision: `EXECUTION_TRACE`, `EXECUTION_DECISION`, `EXECUTION_PROGRESS`
- **LEGACY:** `core/event_bus.py:PluginEventBus` — adapter routing plugin events through canonical bus + plugin hooks (deprecated, use `global_event_bus` with `namespace="plugin"`)
- **LEGACY:** `core/event_bus.py:get_bus()`, `emit_event()` — legacy workflow compat

---

### 25. HISTORY
**Canonical Owner:** `core/history/service.py:HistoryService`

**Implementations:**
- **ACTIVE:** `core/history/service.py` — `HistoryService` for activity/event persistence
- **CONNECTED:** `core/pipeline/stages/notification.py` — event notifications
- **LEGACY:** Multiple scattered history implementations (not unified)

---

### 26. PROJECTS
**Canonical Owner:** `core/project_manager.py:ProjectManager`

**Implementations:**
- **ACTIVE:** `core/project_manager.py:ProjectManager` — project lifecycle, queue processing
- **ACTIVE:** `core/project_state.py:ProjectState` — project state management
- **CONNECTED:** `core/lifespan.py` starts `project_manager.process_queue()`
- **CONNECTED:** `core/build/service.py:build_service` — build project management

---

### 27. RULES
**Canonical Owner:** `core/governance/`

**Implementations:**
- **ACTIVE:** `core/governance/task_router.py` — task routing with governance validation
- **ACTIVE:** `core/governance/work_queue.py` — prioritized work queue
- **ACTIVE:** `core/governance/resource_monitor.py` — resource monitoring
- **ACTIVE:** `core/governance/cli_commands.py` — governance CLI
- **CONNECTED:** `core/authz/loader.py:policy_loader` — RBAC policies
- **CONNECTED:** `core/permission/manager.py` — permission enforcement
- **CONNECTED:** `core/pipeline/stages/authorization.py` — pipeline integration

---

## Cross-Cutting Concerns

### Transport Adapters (all delegate to canonical pipeline)
| Transport | Adapter | Entry Point |
|-----------|---------|-------------|
| REST | `core/pipeline/adapters/rest_adapter.py:rest_adapter()` | `core/routes/chat.py` |
| WebSocket | `core/pipeline/adapters/websocket_adapter.py:ws_adapter()` / `stream_via_pipeline()` | `core/routes/chat.py:websocket_router` |
| Channel (Discord/Telegram/Slack/Matrix/IRC) | `core/pipeline/adapters/channel_adapter.py:channel_adapter()` | `channels/processor.py` |
| Voice | `core/pipeline/adapters/voice_adapter.py` | `assistant/voice_pipeline.py` |
| CLI | `core/pipeline/adapters/` (via `jarvis_cli.py`) | `jarvis_cli.py` |
| MCP | `mcp/mcp_server.py` | `mcp/mcp_server.py` |

### Legacy Paths (fallback only)
| Path | Trigger | Status |
|------|---------|--------|
| `core/agent_loop.py:stream_agent_loop()` | `_disable_pipeline=True` or pipeline exception | FALLBACK |
| `core/graph:build_default_graph()` | Legacy agent loop fallback | FALLBACK |
| `brain/UnifiedBrain.py` | Direct brain API calls | CONNECTED |
| `automation/pc_automation.py` | Open Interpreter path | CONNECTED |

### Deprecated/Shim Modules
| Module | Replaced By | Status |
|--------|-------------|--------|
| `core/config.py` | `core/configuration/service.py` | DEPRECATED (shim) |
| `core/plugins/automation.py` | `core/plugins/base.py` + `PCAutomationPlugin` | LEGACY |
| `core/event_bus.py:PluginEventBus` | `global_event_bus` + `namespace="plugin"` | DEPRECATED |
| `core/event_bus.py:get_bus()` | `global_event_bus` | LEGACY |

---

## Reality Scores

| Responsibility | Score | Notes |
|----------------|-------|-------|
| Startup | 100% | Single canonical lifespan, 30+ subsystems |
| Request Processing | 95% | Pipeline is canonical; legacy fallback exists |
| Goal Understanding | 90% | IntentStage is canonical; UnifiedBrain duplicates |
| Planning | 85% | PlannerExecutor is canonical; UnifiedBrain duplicates |
| Execution | 90% | ToolExecutor canonical; legacy executors exist |
| Workflow | 95% | WorkflowEngine canonical; calibration experimental |
| Scheduler | 90% | Two schedulers (activity + cron) both active |
| Desktop | 95% | Controller + SafetyManager canonical |
| Browser | 90% | Tools canonical; browser_agent legacy |
| Coding | 95% | coding/ + implementations.py canonical |
| Research | 95% | research/ canonical; pipeline integrated |
| Memory | 95% | Facade over 5 backends |
| Notifications | 90% | SupervisorNotifier canonical |
| Configuration | 95% | ConfigurationService canonical; config.py deprecated |
| Providers | 95% | Router + Registry canonical; bootstrap active |
| Capabilities | 90% | Registry canonical; graph/composition active |
| Safety | 95% | SafetyManager + kill_switch canonical |
| Permissions | 85% | Manager + RBAC + Pipeline stage |
| Logging | 95% | Structured, multiple entry points |
| Recovery | 85% | Workflow + Self-healing + Orphan |
| Plugin System | 95% | Loader + Registry + Manifests |
| Voice | 90% | VoiceLoop canonical; providers active |
| Automation | 85% | PCAutomation + Plugin + Desktop split |
| EventBus | 100% | Single canonical bus |
| History | 70% | HistoryService + ActivityManager split |
| Projects | 90% | ProjectManager canonical |
| Rules | 75% | Governance split across files |

---

## Canonical Future Owners (Consolidation Targets)

| Responsibility | Current | Target | Rationale |
|----------------|---------|--------|-----------|
| Request Processing | Pipeline (19 stages) | **Pipeline** | Already canonical |
| Planning | `PlannerExecutor` + `GoalDecomposer` | **PlannerExecutor** | Deterministic, template-based |
| Execution | `ToolExecutor` + `ExecutionStage` | **ToolExecutor** | Single wrapper with lifecycle |
| Memory | `MemoryFacade` (5 backends) | **MemoryFacade** | Already unified |
| Providers | `ProviderRouter` + `ProviderRegistry` | **ProviderRouter** | Evidence-based selection |
| Desktop | `DesktopController` + `SafetyManager` | **DesktopController** | Safety as internal concern |
| Browser | 3 browser_* modules | **browser_tools.py** | Consolidate FSM/Planner into tools |
| Coding | `core/coding/` + `implementations.py` | **core/coding/** | Move tools into coding/ |
| Research | `core/research/` | **core/research/** | Already cohesive |
| Voice | `VoiceLoop` + providers | **VoiceLoop** | Already unified |
| Plugins | `PluginLoader` + `PluginRegistry` | **PluginRegistry** | Loader as internal detail |

---

## Reality Scores

| Responsibility | Score | Notes |
|----------------|-------|-------|
| Startup | 10/10 | Single lifespan, comprehensive |
| Request Processing | 9/10 | Pipeline canonical, legacy fallback exists |
| Goal Understanding | 8/10 | Pipeline stage + brain duplicate |
| Planning | 9/10 | PlannerExecutor canonical, brain duplicate |
| Execution | 8/10 | ToolExecutor canonical, brain executor duplicate |
| Workflow | 9/10 | WorkflowEngine canonical |
| Scheduler | 8/10 | Two schedulers (activity + cron) |
| Desktop | 10/10 | Controller + Safety unified |
| Browser | 6/10 | 3 modules, not consolidated |
| Coding | 7/10 | Split between coding/ and tools/ |
| Research | 9/10 | Cohesive research/ module |
| Memory | 9/10 | Facade over 5 backends |
| Notifications | 9/10 | Single notifier |
| Configuration | 9/10 | Service canonical, config.py deprecated |
| Providers | 9/10 | Router + Registry clear separation |
| Capabilities | 8/10 | Registry + Graph + Pipeline stage |
| Safety | 9/10 | SafetyManager comprehensive |
| Permissions | 8/10 | Manager + RBAC + Pipeline stage |
| Logging | 8/10 | Structured, multiple entry points |
| Recovery | 8/10 | Workflow + Self-healing + Orphan |
| Plugin System | 9/10 | Loader + Registry + Manifests |
| Voice | 8/10 | VoiceLoop + providers |
| Automation | 7/10 | PCAutomation + Plugin + Desktop split |
| EventBus | 10/10 | Single canonical bus |
| History | 7/10 | HistoryService + ActivityManager split |
| Projects | 9/10 | ProjectManager canonical |
| Rules | 7/10 | Governance split across files |

---

## Canonical Future Owners (Consolidation Targets)

| Responsibility | Current | Target | Rationale |
|----------------|---------|--------|-----------|
| Request Processing | Pipeline (19 stages) | **Pipeline** | Already canonical |
| Planning | `PlannerExecutor` + `GoalDecomposer` | **PlannerExecutor** | Deterministic, template-based |
| Execution | `ToolExecutor` + `ExecutionStage` | **ToolExecutor** | Single wrapper with lifecycle |
| Memory | `MemoryFacade` (5 backends) | **MemoryFacade** | Already unified |
| Providers | `ProviderRouter` + `ProviderRegistry` | **ProviderRouter** | Evidence-based selection |
| Desktop | `DesktopController` + `SafetyManager` | **DesktopController** | Safety as internal concern |
| Browser | 3 browser_* modules | **browser_tools.py** | Consolidate FSM/Planner into tools |
| Coding | `core/coding/` + `implementations.py` | **core/coding/** | Move tools into coding/ |
| Research | `core/research/` | **core/research/** | Already cohesive |
| Voice | `VoiceLoop` + providers | **VoiceLoop** | Already unified |
| Plugins | `PluginLoader` + `PluginRegistry` | **PluginRegistry** | Loader as internal detail |

---

## Action Items (For Constitution)

1. **DELETE** `automation/pc_automation.py` and `automation/routes.py` — 100% duplicate
2. **DELETE** `core/graph/` (StateGraph) — DORMANT fallback, Pipeline is canonical
3. **DELETE** `core/agent_loop.py` fallback path — Pipeline is primary
4. **DELETE** `api/agent_routes.py` — legacy graph endpoint
5. **CONSOLIDATE** `core/tools/browser_tools.py` + `browser_fsm.py` + `browser_planner.py` → single `browser_tools.py`
4. **CONSOLIDATE** `core/coding/` + `core/tools/implementations.py` → `core/coding/`
5. **CONSOLIDATE** `core/tools/cookbook_tools.py` + `build_tools.py` → `core/coding/`
5. **CONSOLIDATE** `core/desktop/controller.py` + `core/desktop/safety.py` → single module
6. **CONSOLIDATE** `brain/UnifiedBrain.py` methods → Pipeline stages (Intent/Planner/Execution/Memory)
7. **DELETE** `core/config.py` shim — use `ConfigurationService` directly
8. **DELETE** `core/event_bus.py:PluginEventBus` — deprecated
9. **DELETE** `core/event_bus.py:get_bus()` / `emit_event()` — legacy
10. **CONSOLIDATE** `WorkflowEvent` → `EventBus` events (unify event systems)

---

*End of SOURCE OF TRUTH Audit*