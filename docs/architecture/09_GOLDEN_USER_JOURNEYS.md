# Phase 9: Golden User Journeys

**Status**: READ ONLY — no code was modified.  
**Date**: 2026-07-15  
**Scope**: Three complete end-to-end user journeys traced with every arrow annotated.

---

## Legend

Each arrow uses this format:

```
STEP NAME
  File: path/file.py:line     — Function or class
  DB:   table_name            — Database table touched
  Evt:  EVENT_NAME             — Event fired on EventBus
  Cap:  capability_tag         — Capability resolved
  Perm: permission_check       — Permission/authorization gate
  Fail: failure_mode           — What breaks here and what happens
  Reality: N/10               — How connected/complete this step is
```

**Broken arrows** are marked with `⚠ BROKEN` — these are paths that are disconnected, contain dead code, or have critical gaps.

---

## Journey 1: Install → Setup → Chat → Build Calculator → Progress → APK → Inbox → History → Resume

```
User acquires code
  │
  ▼
install.py / jarvis.py
  │
  ├──→ Detector (Python/Git/Ollama/Playwright/Docker/Hardware)
  │
  ├──→ SetupEngine.run_full_setup()
  │
  ├──→ Chat (POST /api/chat)
  │
  ├──→ Pipeline (23 stages)
  │
  ├──→ Agent Router → BuildAgent
  │
  ├──→ ControlLoop.run_build()
  │
  ├──→ Progress Tracker + WebSocket
  │
  ├──→ APK output (⚠ BROKEN)
  │
  ├──→ Inbox notification
  │
  ├──→ History persistence
  │
  └──→ Resume tomorrow
```

### Arrow 1: User runs install script

```
USER RUNS: python install.py  OR  python jarvis.py
  File: install.py:27          — main() — one-liner remote installer
  File: jarvis.py:254          — main() — CLI entry point with wizard
  DB:   (none — no DB yet)
  Evt:  (none — EventBus not initialized)
  Cap:  (none)
  Perm: (none — runs with user's OS permissions)
  Fail: Python < 3.10 → sys.exit(1)
        Git not found → sys.exit(1)
  Reality: 8/10  — Well-connected, but one-liner install.py is separate from jarvis.py setup wizard
```

### Arrow 2: First-run detection

```
FIRST-RUN CHECK
  File: jarvis.py:270           — main() checks ~/.jarvis/data/.setup_complete
  DB:   (none — JSON marker file)
  Evt:  (none)
  Cap:  (none)
  Perm: Filesystem read access to ~/.jarvis/
  Fail: Marker file corrupted → re-runs setup
  Reality: 7/10  — JSON file state, not in DB; no migration path if schema changes
```

### Arrow 3: CLI Setup Wizard

```
CLI SETUP WIZARD
  File: jarvis.py:274           — _run_cli_setup() → SetupEngine.run_full_setup()
  File: core/setup/engine.py:192 — SetupEngine.run_full_setup()
  DB:   (none)
  Evt:  (none — no events during setup)
  Cap:  (none)
  Perm: (none)
  Fail: CTRL+C → phase set to FAILED, state saved as IN_PROGRESS (resumable)
  Reality: 8/10  — Interactive CLI with checkpoints, but no EventBus integration
```

### Arrow 4: Detect hardware & software

```
DETECT ALL COMPONENTS
  File: core/setup/detector.py:272   — detect_all()
  File: core/setup/detector.py:53    — detect_python()  → sys.version_info >= (3,10)
  File: core/setup/detector.py:63    — detect_git()     → subprocess.run(["git","--version"])
  File: core/setup/detector.py:75    — detect_ollama_installed() → shutil.which("ollama")
  File: core/setup/detector.py:82    — detect_ollama_running()  → HTTP GET /api/tags
  File: core/setup/detector.py:93    — detect_ollama_models()   → list installed models
  File: core/setup/detector.py:115   — detect_playwright()      → import check
  File: core/setup/detector.py:136   — detect_docker()          → subprocess.run(["docker","info"])
  File: core/setup/detector.py:150   — detect_config()          → checks setup_complete marker
  File: core/setup/detector.py:173   — detect_api_keys()        → checks env vars
  File: core/setup/detector.py:186   — detect_hardware()        → psutil + nvidia-smi
  File: core/setup/detector.py:225   — recommend_model()        → picks model from catalogue
  DB:   (none — all in-memory)
  Evt:  (none)
  Cap:  (none)
  Perm: (none — runs nvidia-smi, subprocess)
  Fail: Hardware detection fails → returns partial results
        Ollama not found → prompts user to install
  Reality: 9/10  — Thorough multi-component detection with recommendations
```

### Arrow 5: Install Ollama

```
ENSURE OLLAMA INSTALLED & RUNNING
  File: core/setup/engine.py:114    — ensure_ollama() → installer.ensure_ollama_running()
  File: core/setup/installer.py:66  — ensure_ollama_running() → subprocess.Popen(["ollama","serve"])
  DB:   (none)
  Evt:  (none)
  Cap:  (none)
  Perm: (none — starts OS process)
  Fail: Ollama binary not found → InstallResult(success=False)
        Ollama start timeout → InstallResult(success=False)
  Reality: 8/10  — Auto-starts Ollama, timeout handling
```

### Arrow 6: Pull LLM model

```
PULL OLLAMA MODEL
  File: core/setup/engine.py:130    — pull_model() → installer.pull_ollama_model()
  File: core/setup/installer.py:51  — pull_ollama_model() → subprocess.run(["ollama","pull", model_id])
  DB:   (none)
  Evt:  (none)
  Cap:  (none)
  Perm: Network access to Ollama registry
  Fail: Model pull timed out → InstallResult(success=False)
        Disk full → subprocess error
  Reality: 7/10  — Blocks setup until download completes; no SSE progress reported
```

### Arrow 7: Install Playwright

```
INSTALL PLAYWRIGHT BROWSER
  File: core/setup/engine.py:122    — install_playwright() → installer.install_playwright()
  File: core/setup/installer.py:21  — install_playwright() → pip install + subprocess playwright install
  DB:   (none)
  Evt:  (none)
  Cap:  (none)
  Perm: (none)
  Fail: Playwright install fails → InstallResult(success=False)
  Reality: 7/10  — Functional but no progress reporting
```

### Arrow 8: Configure API keys & default model

```
CONFIGURE SETTINGS
  File: core/setup/engine.py:141    — configure() → configurator.configure_api_keys()
  File: core/setup/configurator.py:69 — configure_api_keys() → prompts user for keys
  File: core/setup/configurator.py:37 — save_settings() → writes ~/.jarvis/data/settings.json
  File: core/setup/configurator.py:105 — mark_setup_complete() → writes ~/.jarvis/data/.setup_complete
  DB:   (none — JSON files only)
  Evt:  (none)
  Cap:  (none)
  Perm: Filesystem write to ~/.jarvis/
  Fail: JSON corrupt → returns {} on read — silent fallback
  Reality: 6/10  — API keys stored in plaintext JSON; no encryption
```

### Arrow 9: Initialize database

```
DATABASE INIT (server startup)
  File: core/database.py:46        — init_db() → Alembic upgrade head
  File: core/database.py:69        — User model
  File: core/database.py:86        — Note model
  File: core/database.py:101       — Reminder model
  File: core/database.py:116       — Activity model
  File: core/database.py:129       — DailySummary model
  File: core/database.py:142       — KnownFace model
  File: core/database.py:159       — ChatHistory model
  File: core/database.py:171       — ConnectedDevice model
  File: core/database.py:183       — JarvisSkill model
  File: core/database.py:193       — ExecutionLog model
  File: core/database.py:209       — SubagentRun model
  DB:   data/app.db — 11 async SQLAlchemy tables
  Evt:  (none)
  Cap:  (none)
  Perm: Filesystem write to CWD
  Fail: Alembic migration fails → server won't start
  Reality: 8/10  — Alembic-managed migrations; deferred to server start (not install)
```

### Arrow 10: User sends chat message

```
⚠ ARROW BEGINS: POST /api/chat
  File: core/routes/chat.py:32     — chat_route()
  DB:   users table — read via verify_token
  Evt:  (none at route level)
  Cap:  (none at route level)
  Perm: verify_token() — FastAPI dependency auth
  Fail: 401 if token invalid
        400 if bad request body
  Reality: 10/10 — Production-grade FastAPI endpoint
```

### Arrow 11: Middleware stack

```
FASTAPI MIDDLEWARE (in order)
  1. CORS
     File: core/main.py:162        — CORSMiddleware
  2. Security Headers
     File: core/main.py:170        — SecurityHeadersMiddleware (from core/middleware.py)
  3. Rate Limiter
     File: core/main.py:178        — rate_limit_middleware()
     File: core/rate_limiter.py     — SlidingWindowRateLimiter (120 req / 60s)
     Fail: 429 rate_limit_exceeded
  4. Session Auth
     File: core/main.py:198        — session_auth_middleware()
     File: core/auth.py             — AuthManager.validate_token()
     DB:   users/sessions table
     Fail: 401 unauthorized
     Reality: 7/10 — bypassed in DEV_MODE
  5. Plugin Hook
     File: core/main.py:206        — plugin_hook_middleware()
  6. Request ID
     File: core/main.py:224        — RequestIDMiddleware
  7. Metrics
     File: core/main.py:226        — MetricsMiddleware
```

### Arrow 12: REST adapter → Pipeline

```
REST ADAPTER → PIPELINE
  File: core/pipeline/adapters/rest_adapter.py:17  — rest_adapter()
  File: core/pipeline/pipeline.py:67               — process_message()
  DB:   (none)
  Evt:  (none — events come from pipeline stages)
  Cap:  (none)
  Perm: (none — auth already done in middleware)
  Fail: Pipeline execution error → Response.error set
  Reality: 9/10  — Clean transport abstraction
```

### Arrow 13: Pipeline execution (23 stages)

```
PIPELINE.EXECUTE() — 23 STAGES
  File: core/pipeline/pipeline.py:187  — Pipeline.execute()

  Stage  1 — Receive
    File: core/pipeline/stages/receive.py:14     — ReceiveStage.execute()
    Cap:  (none)
  Stage  2 — Load Context
    File: core/pipeline/stages/load_context.py:19 — LoadContextStage.execute()
  Stage  3 — Authentication
    File: core/pipeline/stages/auth.py:34         — AuthenticationStage.execute()
    DB:   users table
    Perm: IdentityService.authenticate_session()
    Fail: 401 → pipeline aborts
  Stage  4 — Tenant Resolution
    (pre-built, referenced)
  Stage  5 — Authorization
    File: core/pipeline/stages/authorization.py   — AuthorizationStage
    Perm: PolicyEngine.evaluate(scope, resource)
    Fail: 403 → pipeline aborts
  Stage  6 — Resource Access
    (pre-built, referenced)
  Stage  7 — Rate Limit
    File: core/pipeline/stages/rate_limit.py      — RateLimitStage
    Perm: Per-profile limits (30-120 req/min)
    Fail: 429 → pipeline aborts
  Stage  8 — Intent
    File: core/pipeline/stages/intent.py:23       — IntentStage.execute()
    Cap:  intent resolution
  Stage  9 — Context Retrieval
    File: core/pipeline/stages/context_retrieval.py:18  — ContextRetrievalStage.execute()
    DB:   ai_os_memory.db (Chroma/SQLite vector store)
    Cap:  memory recall
    Fail: Empty memories returned → continues silently
  Stage 10 — Knowledge
    (pre-built, referenced)
  Stage 11 — Reasoning
    File: core/pipeline/stages/reasoning/stage.py:44  — ReasoningStage.execute()
    Cap:  reasoning, evidence collection, contradiction detection
  Stage 12 — Planner
    (pre-built, referenced)
  Stage 13 — Plan Validator
    (pre-built, referenced)
  Stage 14 — Capability Selection
    File: core/pipeline/stages/capability_selection.py:36  — CapabilitySelectionStage.execute()
    Cap:  capability resolution via registry
    Perm: Risk profile filter
  Stage 15 — Execution
    File: core/pipeline/stages/execution.py:242  — ExecutionStage.execute()
    Cap:  LLM completion via LiteLLMProvider / OllamaFallbackProvider
    DB:   execution_logs table (optional)
  Stage 16 — Verification
    (pre-built, referenced)
  Stage 17 — Epistemic Tagging
    (pre-built, referenced)
  Stage 18 — Reflection
    (pre-built, referenced)
  Stage 19 — Learning
    (pre-built, referenced)
  Stage 20 — Policy Optimization
    (pre-built, referenced)
  Stage 21 — Memory
    File: core/pipeline/stages/memory.py:33      — MemoryStage.execute()
    DB:   ai_os_memory.db, fact_store
    Cap:  fact extraction, contradiction detection
  Stage 22 — Metrics
    (pre-built, referenced)
  Stage 23 — Explainability
    (pre-built, referenced)
  Stage 24 — Formatter
    File: core/pipeline/stages/formatter.py:19   — FormatterStage.execute()

  Reality: 9/10 — Well-architected 23-stage pipeline with retry, timeout, cancellation, observability
  Gap: Several stages (10, 12, 13, 16-20, 22-23) are referenced but their implementations act as pass-throughs
```

### Arrow 14: LLM model selection

```
LLM MODEL SELECTION
  File: core/llm_router.py:283     — complete()
  File: core/llm_router.py:532     — route_request()
  File: core/llm_router.py:507     — route_role_for_text()
  File: core/llm_router.py:149     — group_for_role()
  File: core/llm_router.py:152     — model_for_role()
  DB:   (none)
  Evt:  Plugin hooks: before_model_resolve, llm_input, model_call_started, llm_output, model_call_ended
  Cap:  LLM completion
  Fail: Ollama unreachable → failover to cloud or Err(LLMError)
        All providers fail → ProviderResult(text="", error="All providers failed")
  Reality: 8/10  — Multi-stage resolution: env var → config → defaults → failover
```

### Arrow 15: Response formatting

```
RESPONSE FORMATTING
  File: core/pipeline/stages/formatter.py:19  — FormatterStage.execute()
  File: core/pipeline/adapters/rest_adapter.py:56 — converts Response to dict
  DB:   (none)
  Evt:  (none)
  Cap:  (none)
  Reality: 10/10 — Clean Response type with formatted dict output
```

### Arrow 16: Persist chat to history

```
PERSIST CHAT HISTORY
  File: core/routes/chat.py:52     — _persist_chat()
  DB:   chat_history table — INSERT user row + INSERT assistant row
  Evt:  (none — direct DB write, no EventBus notification)
  Cap:  (none)
  Fail: DB constraint violation → logged, chat still delivered
  Reality: 8/10 — Functional but no EventBus event fired for history write
```

### Arrow 17: Agent routing → BuildAgent

```
AGENT ROUTING (for "build a calculator app")
  File: core/agents/router.py:78   — find_agent_for_goal()
  File: core/agents/base.py:46     — BaseAgent.can_handle() — keyword substring match
  File: core/agents/build_agent.py:14 — BuildAgent.capabilities = ["build","compile","create","develop","make","apk","package"]
  DB:   (none)
  Evt:  (none)
  Cap:  ["build", "compile", "create", "develop", "make", "apk", "package"]
  Fail: No agent matches → falls back to generic LLM
  Reality: 8/10  — Simple keyword-based routing works but is fragile
```

### Arrow 18: BuildAgent execution

```
BUILDAGENT EXECUTE
  File: core/agents/build_agent.py:16  — execute()
  File: core/tools/build_tools.py:48   — do_build_project()
  DB:   (none)
  Evt:  Progress callbacks via _emit_progress()
  Cap:  build, compile
  Perm: (none checked)
  Fail: execute_tool_block fails → returns {"exit_code": non-zero}
        AutomationLoop not initialized → build fails
  Reality: 7/10  — Bridges to AutomationLoop; silent failures possible
```

### Arrow 19: ControlLoop build execution

```
CONTROLLOOP RUN BUILD
  File: core/legacy/control_loop.py:164  — run_build()
  File: core/goal_interpreter.py:49      — interpret_goal() → LLM parses goal
  File: core/legacy/control_loop.py:823  — _execute_plan()
  DB:   (none for interpretation)
        ProjectState saved as JSON: ~/.jarvis/projects/{name}/state.json
  Evt:  build_started, goal_interpreted, plan_created, build_complete, validation_complete, retry
        All via notifier.notify() and ExecutionManager.publish_progress()
  Cap:  LLM available for goal interpretation
  Perm: budget_controller.check_budget()
  Fail: Budget exhausted → abort
        LLM unavailable → interpret fails
        Goal too ambiguous → ambiguity check triggers clarification
  Reality: 8/10  — Multi-strategy execution with retry, validation, fix loop
  Gap: Uses legacy ControlLoop (deprecated), not newer WorkflowEngine
```

### Arrow 20: Provider selection for build

```
PROVIDER SELECTION (evidence-based)
  File: core/providers/router.py:108    — ProviderRouter.select(capability)
  File: core/providers/router.py:116    — registry.get_providers_for_capability("coding")
  File: core/providers/router.py:149    — _score() — 8-dimension weighted scoring
  File: core/providers/adapters/forge.py:26 — ForgeProvider capabilities
  DB:   provider_memory (~/.jarvis/provider_settings/registry.json)
        BenchmarkStore
  Evt:  DecisionRecorder.record_decision()
  Cap:  coding, build, compile
  Perm: Budget check, health check, enable/disable check, memory skip check
  Fail: No providers for capability → returns None
        All providers unhealthy → returns None
  Reality: 9/10  — Most sophisticated selection system in the codebase
```

### Arrow 21: Subprocess build execution

```
SUBPROCESS EXECUTION (shell commands / launcher)
  File: core/agent_launcher.py:190      — launch(agent="shell")
  File: core/agent_launcher.py:236      — asyncio.create_subprocess_exec(*shlex.split(cmd_str))
  File: core/providers/adapters/forge.py:99 — ForgeSubAgent.run(goal)
  DB:   (none)
  Evt:  Progress via callback
  Cap:  shell execution
  Perm: Filesystem access to workspace directory
  Fail: Command not found → subprocess error
        Timeout → asyncio.TimeoutError
        Rate-limited → API key rotation from vault
  Reality: 9/10  — Robust subprocess management with timeouts, rate-limit handling, key rotation
```

### Arrow 22: Progress tracking (WebSocket)

```
⚠ ARROW: PROGRESS TRACKING
  File: core/workflow/tracker.py:94     — ExecutionTracker (IN-MEMORY ONLY — not persisted)
  File: core/workflow/graph.py           — ExecutionGraph (tree of ExecutionNode)
  File: core/routes/progress.py:214     — WebSocket /api/progress/ws/{session_id}
  File: core/event_bus.py:139            — _broadcast() — sends to registered WebSockets
  DB:   (none — ExecutionGraph is in-memory, LOST ON RESTART)
  Evt:  GOAL_CREATED, NODE_CREATED, NODE_COMPLETED, NODE_FAILED, etc.
  Cap:  (none)
  Fail: WebSocket disconnected → events lost (no reconnection queue)
  Reality: 6/10  ⚠ BROKEN — ExecutionTracker stores graphs in memory only.
        On server restart, all in-flight progress tracking is lost.
        ActivityGraph (activity_manager/store) IS persisted to SQLite — but not connected to ExecutionTracker.
```

### Arrow 23: APK generation

```
⚠ BROKEN ARROW: APK GENERATION
  The codebase has NO production APK generation pipeline.
  APK references exist only in:
    File: benchmarks/parallel_workflow_benchmark.py:88  — mocked: open("app-debug.apk","wb").write(b"fake apk")
    File: benchmarks/real_repo_recovery.py:211          — gradle assembleDebug command
  No:
    - Dedicated APK build tool
    - Android SDK integration
    - /api/download/apk endpoint
    - Artifact delivery mechanism
  Reality: 2/10  ⚠ BROKEN — Path is mocked in benchmarks, not production.
        If Gradle runs successfully, the APK lands on filesystem but has no delivery path.
```

### Arrow 24: Inbox notification

```
INBOX NOTIFICATION
  File: core/inbox/store.py:107     — InboxStore._subscribe_to_events()
  File: core/inbox/store.py:39      — InboxItem model
  DB:   inbox_items table in data/system.db
  Evt:  Subscribed to: GOAL_COMPLETED, GOAL_FAILED, NEED_INPUT, WARNING, ERROR, MILESTONE, NODE_FAILED, NODE_SKIPPED
  Cap:  (none — event-driven)
  Perm: (none — internal)
  Fail: EventBus not connected to build events → no inbox created
        DB write fails → notification lost
  Reality: 9/10  — Well-connected; subscribes to goal/workflow events and auto-creates inbox items
```

### Arrow 25: Inbox delivery

```
INBOX API + WEBSOCKET
  File: core/routes/inbox.py        — REST endpoints (list, mark-read, add, delete)
  File: core/routes/inbox.py:117    — WebSocket /api/inbox/ws — real-time delivery
  DB:   inbox_items table
  Evt:  inbox_new — broadcast via WebSocket on POST /api/inbox/add
  Fail: WebSocket disconnect → user misses real-time notification
  Reality: 9/10  — Complete SQLite-backed inbox with REST + WebSocket
```

### Arrow 26: History persistence

```
HISTORY — THREE PARALLEL SYSTEMS
  1. Chat History
     File: core/routes/chat.py:52     — _persist_chat()
     DB:   chat_history table in data/app.db (SQLAlchemy)
  2. Activity Graph
     File: core/activity/storage.py:27 — ActivityStore
     DB:   activity_nodes + activity_edges in data/system.db
  3. Project State
     File: core/project_state.py:55    — ProjectState
     File: JSON files at ~/.jarvis/projects/{name}/state.json
  4. Orchestration
     File: core/providers/orchestration/store.py — OrchestrationStore
     DB:   orchestration_plans + orchestration_steps in ~/.jarvis/orchestration.db
  Evt:  WORKFLOW_STARTED, STEP_COMPLETED, WORKFLOW_COMPLETED, etc.
  Reality: 9/10  — Multiple redundant persistence layers (chat, activity graph, project state, orchestration)
```

### Arrow 27: Resume tomorrow

```
RESUME TOMORROW
  ResumeEngine (activity-based):
    File: core/activity/resume.py:85   — ResumeEngine.find_resume_point()
    File: core/activity/resume.py:196  — mark_resumed()
    DB:   activity_nodes + activity_edges
    Cap:  (none)
    Fail: Activity in terminal status → cannot resume

  ControlLoop (build-based):
    File: core/legacy/control_loop.py:278  — resume_build()
    File: core/legacy/control_loop.py:298  — run_pending() — scans ~/.jarvis/projects/
    File: core/project_state.py             — ProjectState.load()
    Fail: State file corrupted → cannot resume

  CheckpointManager (file-level):
    File: core/checkpoint_manager.py       — CheckpointManager.rollback()
    DB:   ~/.jarvis/checkpoints/{project}/ — file snapshots

  WorkflowEngine (workflow-based):
    File: core/workflow/engine.py:149      — resume_workflow()
    File: core/workflow/recovery.py:16     — recover_active_workflows()
    DB:   workflow_instances, workflow_steps
    Evt:  WORKFLOW_RECOVERED

  AgentState (per-round):
    File: core/session_db.py:87            — save_snapshot()
    DB:   agent_state_snapshots table

  Reality: 8/10  — Multiple resume mechanisms at different layers;
        but ExecutionTracker (progress WebSocket) is in-memory and lost on restart
```

---

## Journey 2: Research → Write Report → Generate PDF → Save → Resume

```
User: "Research machine learning"
  │
  ├──→ Chat → Pipeline (23 stages)
  │
  ├──→ trigger_research tool
  │
  ├──→ deep_research() — 5 steps
  │     ├── Plan → LLM generates sub-questions
  │     ├── Search → SearXNG / DuckDuckGo
  │     ├── Fetch → aiohttp HTML fetch
  │     ├── Extract → LLM extracts facts per chunk
  │     └── Synthesize → LLM produces structured JSON
  │
  ├──→ Write Report → document_tools
  │
  ├──→ Generate PDF ⚠ BROKEN
  │
  ├──→ Save → multiple stores
  │
  └──→ Resume ⚠ PARTIAL
```

### Arrow 1: Research request enters pipeline

```
RESEARCH REQUEST
  File: core/tools/cookbook_tools.py:1157 — do_trigger_research()
  File: core/tools/schemas_research.py:18   — trigger_research schema
  File: api/research_routes.py:27           — start_research() (FastAPI)
  DB:   (none at entry)
  Evt:  "ui_event": "research_started" — via HTTP response
  Cap:  research
  Perm: Internal tool token (_internal_headers())
  Fail: Missing topic → HTTP 400
  Reality: 9/10  — Clean tool→API bridge
```

### Arrow 2: deep_research pipeline

```
DEEP RESEARCH — 5 STEPS
  File: tools/deep_research.py:25     — deep_research()

  Step 1 — PLAN
    File: tools/deep_research.py:62   — LLM generates 3-5 sub-questions
    File: core/llm_router.py:283      — complete() — LLM call
    Cap:  analysis LLM group
    Fail: LLM error → returns partial sub-questions

  Step 2 — SEARCH
    File: tools/deep_research.py:86   — search_engine.search()
    File: tools/search_tool.py         — SearXNGSearch.search()
    File: tools/search_tool.py         — DuckDuckGoFallback (SearXNG unavailable)
    Cap:  web search
    Fail: SearXNG down → DuckDuckGo fallback
          No sources found → "No sources found"
    Reality: 8/10  — Multi-engine with fallback

  Step 3 — FETCH
    File: tools/deep_research.py:124  — aiohttp fetch (3 concurrent)
    Cap:  network access
    Fail: HTTP 404/403 → page skipped, continues
    Reality: 8/10  — Batched concurrent fetches with error tolerance

  Step 4 — EXTRACT
    File: tools/deep_research.py:149  — HTML strip + chunk → LLM extract facts
    File: core/llm_router.py:283      — complete() per chunk
    Cap:  analysis LLM group
    Fail: LLM error → chunk skipped
    Reality: 7/10  — Chunked extraction, but no cross-source dedup

  Step 5 — SYNTHESIZE
    File: tools/deep_research.py:193  — LLM produces JSON: {summary, key_findings, confidence}
    File: core/research/synthesizer.py:40  — FactSynthesizer.synthesize() (exists but not called by deep_research)
    Cap:  analysis LLM group
    Fail: LLM JSON parse error → fallback to raw text
    Reality: 6/10  ⚠ BROKEN — deep_research() does its own ad-hoc synthesis.
        FactSynthesizer exists in core/research/ but is NOT connected to deep_research.
        Two parallel research systems: tools-level (deep_research.py) and core-level (core/research/).
```

### Arrow 3: Research result storage

```
RESULT STORAGE
  File: core/tools/cookbook_tools.py:1087 — do_manage_research()
  DB:   (filesystem) data/deep_research/{session_id}.json
        (SQLite) research_facts table in data/workflow.db
        (SQLite) kg_nodes + kg_edges tables in data/workflow.db
  Cap:  (none)
  Reality: 8/10  — Persisted to both filesystem and SQLite
```

### Arrow 4: Write report (document system)

```
WRITE REPORT — DOCUMENT TOOLS
  File: core/tools/document_tools.py:267   — do_create_document()
  File: core/tools/document_tools.py:336   — do_update_document()
  File: core/tools/document_tools.py:811   — do_edit_document()
  DB:   documents + document_versions tables in data/app.db
  Evt:  document_created, document_edited via fire_event()
  Cap:  documents tool group
  Fail: Missing session → error
        FIND/REPLACE block not matched → edit fails
  Reality: 9/10  — Full document system with versioning, FIND/REPLACE, unified diff support
```

### Arrow 5: Generate PDF

```
⚠ BROKEN ARROW: GENERATE PDF
  File: core/personal_docs.py:18    — extract_pdf_text() — READS PDFs only
  File: core/document_processor.py:116 — _read_pdf() — READS PDFs only (uses pdfplumber)

  NO PDF GENERATION CAPABILITY EXISTS:
    - No reportlab, fpdf, weasyprint, pdfkit, or similar library
    - No PDF generation function anywhere in the codebase
    - Documents are stored as Markdown/text in SQLite

  Reality: 1/10  ⚠ BROKEN — System reads PDFs but cannot generate them.
        A user asking "generate a PDF report" gets an error or a Markdown file.
```

### Arrow 6: Save (multiple layers)

```
SAVE — MULTIPLE PERSISTENCE LAYERS
  Research result: data/deep_research/{session_id}.json
  Facts:           research_facts table (SQLite)
  Knowledge Graph: kg_nodes + kg_edges tables (SQLite)
  Document:        documents + document_versions tables (SQLite)
  Session:         ~/.jarvis/sessions/{session_id}.json
  AgentState:      agent_state_snapshots table (SQLite) — per round
  Workflow:        workflow_instances + workflow_steps + workflow_events + workflow_contexts + workflow_artifacts

  Reality: 9/10  — Multiple redundant persistence layers
```

### Arrow 7: Resume research

```
⚠ PARTIAL ARROW: RESUME RESEARCH
  WorkflowEngine.resume_workflow():       YES — persistent workflow resume
    File: core/workflow/engine.py:149
  Recovery.recover_active_workflows():    YES — auto-recovery on startup
    File: core/workflow/recovery.py:16
  AgentState snapshots:                   YES — per-round persistence
    File: core/session_db.py:87

  deep_research() itself:                 NO — runs as single async function
    File: tools/deep_research.py:25       — No checkpointing mid-research
    File: api/research_routes.py:25       — _jobs dict is IN-MEMORY (lost on restart)
    File: core/tools/cookbook_tools.py:1157 — trigger_research has no resume operation

  Reality: 5/10  ⚠ PARTIAL — Workflow-level resume works, but research-level resume is impossible.
        A 30-minute research job interrupted at minute 29 must start from scratch.
```

---

## Journey 3: Desktop Automation → Open App → Move Mouse → Browser → Finish

```
User: "Open Chrome and search for cats"
  │
  ├──→ /api/vision/run (VisionAgent)
  │     OR /computer (pc_agent legacy)
  │     OR /api/chat (ActionEngine)
  │
  ├──→ Capture screenshot
  │
  ├──→ Vision model describes screen
  │
  ├──→ LLM plans steps
  │
  ├──→ Open App (Chrome)
  │
  ├──→ Move mouse to URL bar
  │
  ├──→ Type URL
  │
  ├──→ Browser navigation
  │
  └──→ Finish / verify
```

### Arrow 1: Entry point (3 parallel paths)

```
THREE ENTRY PATHS (coexist, not unified)

  Path A: /api/vision/run (Modern — VisionAgent)
    File: core/routes/vision.py:125     — run_task()
    File: core/vision_agent.py:177      — VisionAgent.run()
    DB:   (none)
    Evt:  (none)
    Cap:  vision_browser
    Perm: verify_token
    Fail: Empty instruction → returns error
    Reality: 7/10

  Path B: /computer (Legacy — pc_agent)
    File: core/routes/control.py:25     — computer_control()
    File: pc_agent/computer_agent.py:161 — execute_natural_language()
    DB:   pc_agent_logs table
    Evt:  (none)
    Cap:  desktop automation
    Perm: verify_token + GovernanceValidator
    Reality: 5/10  — Marked DEPRECATED/EXPERIMENTAL in source

  Path C: /api/chat → ActionEngine
    File: core/action_engine.py:30      — ActionEngine.process()
    File: core/desktop/controller.py     — DesktopController
    DB:   (none)
    Evt:  (none)
    Cap:  desktop
    Reality: 6/10  — Thin wrapper around DesktopController
```

### Arrow 2: VisionAgent — capture screen

```
CAPTURE SCREEN
  File: core/vision_agent.py:233     — _capture()
  File: mss.mss()                     — MSS library (multi-platform screenshot)
  File: core/desktop/controller.py    — DesktopController.screenshot() (alternative path)
  Perm: SafetyManager.check(SCREEN_CAPTURE) — rate limit: 10 screenshots/min
  Fail: MSS fails → pyautogui.screenshot() fallback
        Rate limited → SafetyDecision(allowed=False) — no exception, caller must check
  Reality: 8/10  — Dual capture methods, rate-limited
```

### Arrow 3: Vision model describes screen

```
VISION MODEL DESCRIBES SCREEN
  File: core/vision_agent.py:245     — _describe()
  File: core/vision_agent.py:433     — _llava() — calls Ollama /api/generate
  File: core/vision_agent.py:443     — VISION_MODEL from config, fallback moondream:latest
  DB:   (none)
  Cap:  vision
  Fail: Ollama not running → exception
        Vision model not installed → fallback chain: moondream:latest → llava:7b → llava
  Reality: 7/10  — Vision model with fallback chain; temperature 0.1 fixed
```

### Arrow 4: LLM plans steps

```
PLAN STEPS
  File: core/vision_agent.py:276     — _plan()
  File: core/llm_router.py            — planning LLM call (Gemma4 via Ollama)
  Response: JSON array of steps: [{action, params}, ...]
  Cap:  planning
  Fail: LLM returns invalid JSON → parse error → step execution aborted
  Reality: 7/10  — Structured planning with JSON output
```

### Arrow 5: Open App

```
OPEN APP
  VisionAgent path:
    File: core/vision_agent.py:301   — _exec(action="open_app")
    File: core/vision_agent.py:305   — CMDS dict (hardcoded app→command mappings)
    File: core/vision_agent.py:322   — subprocess.Popen(["cmd","/c", ...], shell=False)
    Perm: (none — no SafetyManager.check() call)
    Reality: 6/10

  DesktopController path:
    File: core/desktop/controller.py:199 — launch_app()
    File: core/desktop/controller.py:204 — shutil.which() + candidates dict
    File: core/desktop/controller.py:214 — subprocess.Popen(exe, shell=True)  ⚠ HIGH RISK
    Perm: (none — NO SafetyManager.check() call in launch_app)
    Reality: 4/10  ⚠ BROKEN — shell=True on Windows; no safety gate before execution

  pc_agent path:
    File: pc_agent/computer_agent.py:127 — open_app()
    File: pc_agent/computer_agent.py:133 — subprocess.Popen([resolved], shell=False)
    File: pc_agent/computer_agent.py:61  — _resolve_app_path() — checks APP_MAP, shutil.which(), Windows dirs
    Reality: 7/10  — Safer than DesktopController (shell=False)
```

### Arrow 6: Move mouse to element

```
MOVE MOUSE TO ELEMENT
  1. Find element coordinates via vision:
     File: core/vision_agent.py:249   — _find() — vision model returns {x, y}
     File: core/vision_agent.py:258   — coordinates scaled 2x to full resolution
     Fail: Element not found → Exception: "'{target}' not found on screen"
     Reality: 7/10  — Vision-based coordinate prediction; assumes 50% screenshot resolution

  2. Move mouse via DesktopController:
     File: core/desktop/controller.py:45 — move_mouse(x, y, duration)
     File: core/desktop/safety.py:121    — SafetyManager.check(MOUSE_MOVE, {...})
     Perm: SafetyManager gates:
           Gate 1: Emergency stop — blocks ALL if active
           Gate 2: Cooldown — 50ms min between actions
           Gate 4: Mouse speed — max 2000 px/sec
     Reality: 8/10

  3. Click:
     File: core/desktop/controller.py:61 — click(x, y, button)
     File: core/desktop/safety.py:121    — SafetyManager.check(MOUSE_CLICK, {...})
     Perm: Gate 6: Click rate — max 60 clicks/min
           Gate 3: Forbidden regions — blocked screen areas
     Fail: Safety reject → DesktopAction(success=False, error) — no exception
     Reality: 9/10

  PyAutoGUI failsafe:
    File: core/vision_agent.py:50     — pyautogui.FAILSAFE = True
    File: core/vision_agent.py:51     — pyautogui.PAUSE = 0.35
    Mouse to corner (0,0) → FailSafeException → emergency stop
```

### Arrow 7: Browser interaction

```
BROWSER INTERACTION — TWO PATHS

  Path A: Desktop-based (pyautogui) — VisionAgent
    File: core/vision_agent.py:333   — _exec(action="navigate") — ctrl+l, type url, enter
    File: core/vision_agent.py:341   — _exec(action="click") — vision-find + pyautogui.click
    Perm: (none — browser is a desktop app at this level)
    Reality: 6/10  — Fragile: depends on screen coordinates, keyboard shortcuts

  Path B: Playwright-based (Managed Browser) — BrowserProvider
    File: core/browser_manager.py:159   — BrowserManager.start()
    File: core/tools/browser_tools.py:102 — do_browser_navigate()
    File: core/tools/browser_tools.py:127 — do_browser_find()
    File: core/tools/browser_tools.py:149 — do_browser_find_interactive()
    File: core/tools/browser_tools.py:249 — do_browser_click()
    File: core/tools/browser_tools.py:281 — do_browser_fill()
    File: core/tools/browser_tools.py:389 — do_browser_snapshot()
    File: core/tools/browser_tools.py:492 — do_browser_screenshot()
    File: core/tools/browser_tools.py:525 — do_browser_evaluate(js)  ⚠ UNRESTRICTED JS EXECUTION
    File: core/tools/browser_planner.py    — BrowserPlanner.pre_plan() + post_plan()
    File: core/tools/browser_fsm.py        — BrowserFSM (START→NAVIGATE→SEARCH→...→COMPLETE/FAIL)
    File: core/providers/adapters/browser_provider.py — BrowserProvider

    URL Validation:
      File: core/tools/browser_tools.py:13 — Validates against dangerous schemes
      Blocked: file://, chrome://, javascript:, data:, blob:, about:, extensions://
      Perm: is_admin bypass

    Fail: Navigation timeout → fallback to domcontentloaded
          Bot challenge → auto-bypass (browser_planner.py:1268)
          Overlay intercept → auto-retry with force=True
          Fill failure → 4 fallback strategies
    Reality: 8/10  — Sophisticated Playwright-based browser management with stealth, FSM, fallback strategies
```

### Arrow 8: Task completion

```
TASK COMPLETION

  VisionAgent:
    File: core/vision_agent.py:218   — task.status = "done", t_end = time.time()
    File: core/vision_agent.py:220   — _summarize() → natural language result
    File: core/vision_agent.py:423   — "Task '{instruction}' finished {done}/{len(steps)} steps in {secs}s"
    Fail: Task failed → status = "failed", error captured
    Reality: 8/10

  BrowserFSM:
    File: core/tools/browser_fsm.py:317 — is_terminal() checks for COMPLETE or FAIL
    File: core/tools/browser_planner.py:124 — breaks loop if terminal state
    Reality: 9/10

  Result Reporting:
    File: core/routes/vision.py:135   — Returns _task_dict() with status, result, steps
    File: core/routes/control.py:29   — Returns raw dict from execute_natural_language()
    DB:   DesktopActions recorded in ReplayGraph (in-memory)
    Evt:  (none — no EventBus events for desktop actions)
    Reality: 6/10  ⚠ No EventBus events fired for desktop automation completion
```

---

## Cross-Cutting Summary

### Broken Arrows (must fix)

| ID | Journey | Arrow | Issue | Severity |
|----|---------|-------|-------|----------|
| B1 | 1 | APK generation | No production APK pipeline — only mocked in benchmarks | HIGH |
| B2 | 1 | Progress tracker | ExecutionGraph is in-memory only — lost on restart | HIGH |
| B3 | 2 | Generate PDF | Zero PDF generation capability anywhere in codebase | HIGH |
| B4 | 2 | Research resume | deep_research() runs as single async function with no checkpointing; _jobs dict is in-memory | MEDIUM |
| B5 | 2 | Research synthesis | deep_research() does ad-hoc synthesis; FactSynthesizer exists but is not connected | MEDIUM |
| B6 | 3 | DesktopController launch_app | shell=True on Windows; no SafetyManager gate | HIGH |
| B7 | 3 | Desktop EventBus integration | No EventBus events fired for desktop automation lifecycle | MEDIUM |

### Architecture Debt

| Issue | Affected Journeys | Count |
|-------|-------------------|-------|
| In-memory state lost on restart | 1 (progress), 2 (research jobs) | 2 |
| Parallel implementations for same function | 2 (research), 3 (desktop entry) | 2 |
| No EventBus integration for whole journey | 1 (install), 3 (desktop) | 2 |
| Safety gates bypassed in some paths | 3 (launch_app) | 1 |
| Secrets stored in plaintext | 1 (settings), all (API keys) | All |

### Health Scores by Journey

| Journey | Score | Key Strength | Key Weakness |
|---------|-------|-------------|--------------|
| Install → Setup → Chat → Build → APK → Resume | 7.5/10 | Chat pipeline is production-grade (10/10) | APK path is mocked; progress tracker in-memory |
| Research → Report → PDF → Resume | 6.0/10 | Document system is robust (9/10) | Zero PDF generation; research can't resume mid-flight |
| Desktop → Open → Mouse → Browser → Finish | 6.5/10 | SafetyManager is comprehensive (9/10) | launch_app has shell=True; 3 parallel entry paths |

### Architecture Decisions Required

1. **Unified artifact delivery** — APK, PDF, and other generated files need a consistent storage + download path
2. **Persistent progress** — ExecutionTracker must write to SQLite (ActivityStore already does)
3. **Research checkpointing** — deep_research needs per-step checkpointing for resume
4. **Desktop EventBus integration** — All desktop actions should fire lifecycle events
5. **Single desktop entry point** — Merge VisionAgent / pc_agent / ActionEngine into one
6. **Safety gate for launch_app** — Must go through SafetyManager like every other desktop action

---

*End of Phase 9 — READ ONLY audit. No code was modified.*
