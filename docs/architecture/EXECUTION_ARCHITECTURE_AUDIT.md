# Execution Architecture Audit

> **Forensic READ-ONLY analysis.**  
> Every execution path traced. Every bypass cataloged. Every provider audited.  
> This is the audit to run before making the Capability Registry the heart of JARVIS.

---

## Cross-Reference Refinement (Post-All-Audits)

> This section was added after completing all 9 other architecture audit documents. It cross-references findings from later audits that affect execution.

### Key Findings Affecting Execution

| Finding | Source Audit | Impact on Execution |
|---------|-------------|---------------------|
| **tool_factory.py is thread-hostile** | DEPENDENCY_GRAPH_AUDIT.md | `_initialized` + `_tools` global state races under concurrent pipeline execution. **Critical** — must fix before multi-request. |
| **RateLimitStage is a no-op** | REQUEST_PIPELINE_AUDIT.md | No rate limiting for non-HTTP execution paths (MCP, WebSocket, internal). |
| **MemoryDrivenRouter is separate from MemoryFacade** | MEMORY_ARCHITECTURE_AUDIT.md | Agent routing decisions are split between `decision_memory.py` (System A, JSON) and `brain/memory/decision.py` (System B, SQLite). Execution path uses System A only. |
| **3 planner systems produce 3 different plan formats** | PLANNER_ARCHITECTURE_AUDIT.md | Execution must handle `SubGoal` tree (core), `TaskGraph` DAG (brain), and flat dict (pipeline) — three incompatible input formats. |
| **WorkflowEngine is the single execution orchestrator** | WORKFLOW_ARCHITECTURE_AUDIT.md | All multi-step execution should use `WorkflowEngine`, but `execute_tool_block()` is called directly from many places, bypassing workflow lifecycle. |
| **is_authorized_to_execute() + 36-tool blocklist** | IDENTITY_PERMISSION_AUDIT.md | Dual authorization mechanism — PolicyEngine scopes + legacy blocklist. Blocklist bypasses scope system. |
| **execute_tool_block() uses hardcoded tool dispatch** | DEPENDENCY_GRAPH_AUDIT.md | 3,024-line function with ~100 inline handlers. No pluggability, no capability gating. |
| **27+ SQLite databases with no connection pooling** | STORAGE_ARCHITECTURE_AUDIT.md | Each `sqlite3.connect()` call in execution opens a new file handle. No pooling, no centralized management. |
| **CapabilitySelectionStage exists but uses hardcoded dict** | REQUEST_PIPELINE_AUDIT.md | Stage 13 of pipeline is wired but bypasses CapabilityRegistry. Registry is initialized but never queried. |

### Target Architecture Connections

The Target Architecture (TARGET_ARCHITECTURE.md) makes these specific commitments for execution:

1. **Pipeline is the only request path** — remove RuntimePipeline and all direct-graph execution bypasses
2. **CapabilityRegistry is the central authority** — replaces hardcoded dict in CapabilitySelectionStage and tool dispatch in `execute_tool_block()`
3. **WorkflowEngine handles all multi-step execution** — LongHorizonFSM integrates, `execute_tool_block()` becomes workflow step executor
4. **ExecutionProviders own tool dispatch** — decompose the 3,024-line function into per-capability provider classes
5. **Single Authorizer for all security checks** — `is_authorized_to_execute()` + PermissionManager + tool blocklist unified

### Changes from Original Audit

| Original Recommendation | Refined Recommendation | Reason |
|------------------------|----------------------|--------|
| Wire CapabilitySelectionStage (stage 13) | **Same** — confirmed by pipeline audit | Pipeline stage exists but is dead code |
| Fix `infer_capabilities()` | **Same** — confirmed by pipeline audit | Primary bypass from execution to capabilities |
| Add ExecutionProviders for 9 missing capabilities | **Split into phases** — Phase 1: thread safety + rate limiting. Phase 2-4: memory, planner, capability unification. Phase 7: workflow enhancements. | Later audits revealed higher-priority blocking issues |
| Remove 3,024-line bypass | **Defer** to Phase 7 | Blocked by memory, planner, and capability unification |
| Providers own execution | **Defer** to Phase 7 | Requires ExecutionProvider infrastructure first |

---

## Table of Contents

1. [Every Execution Path](#1-every-execution-path)
2. [Execution Table](#2-execution-table)
3. [Bypass Report](#3-bypass-report)
4. [ExecutionProvider Audit](#4-executionprovider-audit)
5. [Scheduling Audit](#5-scheduling-audit)
6. [Capability Registry Audit](#6-capability-registry-audit)
7. [Provider Architecture Audit](#7-provider-architecture-audit)
8. [Event Architecture Audit](#8-event-architecture-audit)
9. [Reality Scores](#9-reality-scores)
10. [Final Architecture Conclusions](#10-final-architecture-conclusions)

---

## 1. Every Execution Path

### 1.1 Coding

**Path A — Canonical Pipeline (POST /api/chat)**
```
Client → POST /api/chat
  → middleware[rate_limit → session_auth → plugin_hook → RequestID → Metrics]
  → core/routes/chat.py:33 chat_route()
  → core/pipeline/adapters/rest_adapter.py:17 rest_adapter()
    → Request(text, transport="rest", ...)
    → core/pipeline/pipeline.py:67 process_message(request)
      → PipelineContext created (line 89-111)
      → get_identity_service().create_context() (line 100)
      → ResourceScope (line 106-111)
      → Pipeline.execute(ctx) (line 112)
        → 19 stages in order (stages/__init__.py:44-64):
          1. receive         — validate input
          2. load_context    — session context
          3. authentication  — verify identity
          4. tenant_resolution
          5. authorization   — RBAC
          6. resource_access — resource scope
          7. rate_limit
          8. intent          — classify intent
          9. context_retrieval — memory context
          10. reasoner       — LLM reasoning (via llm_router)
          11. planner        — generate plan
          12. plan_validator
          13. capability_selection — **Dead: not wired** (see §6)
          14. execution ← **Dead: not wired** (see §6)
          15. verification
          16. epistemic
          17. memory
          18. metrics
          19. formatter
      → Response(text, error, metadata) (line 123-128)
  → _persist_chat() (chat.py:52) → ChatHistory SQLite
  → JSON response
```

**Path B — Agent Stream (POST /api/agent/stream)**
```
Client → POST /api/agent/stream
  → middleware[rate_limit → session_auth → plugin_hook → RequestID → Metrics]
  → core/routes/chat.py:88 agent_stream()
  → core/agent_loop.py:34 stream_agent_loop()
    → if _disable_pipeline=False:
      → RuntimePipeline() (pipeline.py:73)
      → RuntimePipeline.execute() (pipeline.py:109)
        → infer_capabilities(goal) ← **BYPASS** (hardcoded keywords)
        → Phase A.8: Knowledge Injection (BehaviorAdapter.for_planner)
        → Phase A.1: Planning (PlannerExecutor.create_plan)
        → Phase A.2: Strategy (StrategyGenerator → StrategySelector)
        → Phase A.3+A.4: Decision (DecisionEvidence → UnifiedDecisionModel)
        → Phase A.5: Provider (ProviderRouter.select) ← **BYPASS** (direct router)
        → Phase A.7: Activity Recording (ActivityManager)
        → Phase A.6: Workflow (WorkflowEngine.start_workflow)
        → build_default_graph().execute(state + pipeline_context)
          → graph/nodes.py: setup_node → think_node → route_node → tool_call_node
            → tool_call_node → _execute_one_tool() (nodes.py:785)
              → handle_tool() on provider OR execute_tool_block() ← **BYPASS**
        → Post: Provider Memory Feedback → CalibrationEngine
        → Post: Learning Feedback (Consolidator)
      → SSE events: delta, tool_start, tool_output, agent_step, metrics, [DONE]
    → else/exception:
      → graph.execute(state) ← **LEGACY BYPASS** (direct graph, no pipeline)
```

**Path C — Agent Graph (direct, legacy)**
```
  → build_default_graph() (graph/__init__.py)
  → graph.execute(state)
    → setup_node (nodes.py:118)
      → loads MCP manager
      → selects relevant tools via ToolIndex (RAG)
      → builds system prompt with tool schemas
    → think_node (nodes.py:345)
      → calls LLM with FUNCTION_TOOL_SCHEMAS
    → route_node (nodes.py:604)
      → parses LLM response → ToolBlock objects
    → plan_node (nodes.py:77)
      → BrowserPlanner.pre_plan() — injects browser_snapshot after navigate
    → tool_call_node (nodes.py:901)
      → _resolve_tool_blocks() → for each block → _execute_one_tool()
        → if ctx.provider.handle_tool() exists: call it
        → else: execute_tool_block(name, content) ← **CENTRAL BYPASS**
          → CORE_MAPPING check (read_file/write_file/bash etc → ActionEngine)
          → _MCP_TOOL_MAP check (bash/python/read_file etc → MCP server)
          → 100+ _hdl_* handlers (browser, shell, document, scheduler, etc.)
    → finish_node
```

### 1.2 Browser

```
  tool_call_node → _execute_one_tool()
  → execute_tool_block("browser_navigate", args) (execution.py:2601)
  → _hdl_browser_navigate() (execution.py:1826)
  → do_browser_navigate() (browser_tools.py:102)
    → _validate_url() — blocks dangerous schemes
    → BrowserManager.instance() (browser_manager.py:88)
      → _ensure(session_id) → ensure_browser_alive() (browser_manager.py:235)
        → async_playwright().start() (browser_manager.py:169)
        → chromium.launch() with stealth args (browser_manager.py:171)
      → ensure_context_alive() (browser_manager.py:245)
      → ensure_page_alive() (browser_manager.py:254)
    → page.goto(url) (browser_tools.py:111)
    → page.title() (browser_tools.py:117)
    → _action_result() → return dict
  → event_bus._broadcast() ← **NO events emitted from browser execution**
  → UI receives tool_output SSE event
```

**BYPASS: No capability_registry, no provider_router, no pipeline check.** The browser handler imports `do_browser_navigate` directly from `core/tools/browser_tools.py`.

### 1.3 Desktop

```
  tool_call_node → _execute_one_tool()
  → execute_tool_block("computer", args) (execution.py)
  → (handled via ForgeProvider.handle_tool or direct dispatch)
  → DesktopProvider._dispatch() (desktop_provider.py:95)
    → DesktopController (core/desktop/controller.py:31)
      → SafetyManager.check() (controller.py:46)
      → pyautogui.moveTo() / click() / typewrite() / hotkey() etc
      → OR core/desktop/screen.py — ScreenCapture via mss
      → OR core/desktop/window.py — WindowController
  → return ExecutionResult
```

**BYPASS: DesktopProvider exists in ProviderRegistry but is never called through capability resolution.** The agent graph calls `handle_tool()` directly on a provider instance obtained from pipeline context — but that context was populated by `infer_capabilities()` → `provider_router.select()`, not through CapabilityRegistry.

### 1.4 Research

```
  tool_call_node → execute_tool_block("trigger_research", args)
  → _hdl_trigger_research() (execution.py:1733)
  → do_trigger_research() (cookbook_tools.py:1157)
    → POST to {COOKBOOK_BASE}/api/research/start (httpx)
    → OR directly:
      → SearXNGSearch.search() (search_tool.py:119)
        → SearXNG API (search_tool.py:120-137)
        → Fallback: DuckDuckGoFallback.search() (search_tool.py:141)
      → scrape_top() (search_tool.py:158)
        → Crawl4AI (search_tool.py:162)
        → Fallback: trafilatura (search_tool.py:178)
      → multi_hop() (search_tool.py:188)
        → iterative gap-driven search with Ollama LLM refinement
  → return research results
```

**BYPASS: ResearchProvider exists but the `trigger_research` tool bypasses it entirely.** The tool handler calls `do_trigger_research()` directly from `cookbook_tools.py`, not through ResearchProvider.

### 1.5 Voice

```
  Microphone → audio bytes
  → VoiceEngine.process_audio(audio_bytes) (voice_pipeline.py:421)
    → LatencyTracker.start()
    → emotion_detector.analyze(audio_bytes) (voice_pipeline.py:424)
    → transcribe(audio_bytes) → self.stt.transcribe() (voice_pipeline.py:392)
      → FasterWhisper STT (assistant/stt.py)
      → PluginEventBus.emit("on_voice_command", text=transcribed) (line 432)
    → think(transcribed, emotion) (voice_pipeline.py:440)
      → voice_adapter(text, ...) (adapters/voice_adapter.py:24)
        → Request(text, transport="voice", ...)
        → process_message(request) ← **ENTERS CANONICAL PIPELINE**
          → 19 stages → Pipeline.execute()
        → Response.text
    → speak(response) → self.tts.synthesize(text) (voice_pipeline.py:414)
      → Kokoro KPipeline (tts.py:45)
      → numpy concatenation → soundfile WAV
    → LatencyTracker.record(stt_ms, think_ms, tts_ms, total_ms)
  → audio bytes out
```

**PATH BYPASSES CapabilityRegistry entirely.** The canonical pipeline's `process_message()` is reached, but the pipeline's capability_selection and execution stages are dead code. The pipeline relies on LLM reasoning, not capability resolution.

### 1.6 Email

```
  tool_call_node → execute_tool_block("send_email", args)
  → BARE_EMAIL_TOOLS check (execution.py:2666)
  → rename to "mcp__email__send_email"
  → not in _TOOL_HANDLERS → falls to tool.startswith("mcp__") (execution.py:2787)
  → mcp.call_tool("mcp__email__send_email", args) (execution.py:2798)
  → mcp/email_server.py → @server.call_tool()
    → _send_email() (email_server.py:813)
      → _resolve_send_config() — SMTP config
      → EmailMessage() → headers, body, attachments
      → _smtp_connect() → smtplib.SMTP_SSL() or starttls()
      → conn.send_message()
      → IMAP append() to Sent folder
  → return {"sent": True, ...}
```

**BYPASS: EmailProvider exists but `send_email` routes through MCP server, not through EmailProvider.** The EmailProvider adapter (`core/providers/adapters/email_provider.py`) delegates to the same `mcp.email_server._send_email()` — it exists but is never the primary path.

### 1.7 Memory

```
  tool_call_node → execute_tool_block("manage_memory", args)
  → _hdl_manage_memory() (execution.py:2114)
  → do_manage_memory() (chat_tools.py:31)
    → MemoryManager (core/memory.py)
      → memory.json file persistence
      → MemoryVectorStore (cosine similarity)
    → action:
      add:   MemoryManager.add_entry() → save to memory.json
      search: MemoryManager.get_relevant_memories()
      delete: delete from in-memory → save
```

**BYPASS: No MemoryProvider exists.** There are 3 competing memory subsystems (`core/long_term_memory/`, `memory/`, `brain/memory/`) but the `manage_memory` tool uses a simple JSON-file-based MemoryManager. MemoryStage in canonical pipeline exists but is dead code.

### 1.8 Filesystem

```
  tool_call_node → _execute_one_tool()
  → execute_tool_block("read_file", args) (execution.py:1413)
  → CORE_MAPPING → action_engine.execute("read_file", params) (execution.py:1461)
  → ActionEngine.read_file(path) (action_engine.py:66)
  → _execute_native("read_file", path) (action_engine.py:96)
  → _direct_fallback("read_file", content) (execution.py:519)
    → Path confinement: _resolve_tool_path() (execution.py:633)
      → sensitive deny list (.ssh, .gnupg...)
      → allowlist check (DATA_DIR, /tmp, extra_roots)
    → open(path, encoding="utf-8").read() via asyncio.to_thread()
    → Line parsing + line numbers
  → OR MCP alternative: mcp.call_tool("mcp__filesystem__read_file", args)
```

**FOUR DISPATCH PATHS:** MCP server → `_call_mcp_tool()` → `_direct_fallback()`, `ForgeProvider.handle_tool()` → `execute_tool_block()`, `ActionEngine._execute_native()`, and `file_tools_plugin` registration. All do the same thing.

### 1.9 Terminal

```
  tool_call_node → _execute_one_tool()
  → execute_tool_block("bash", content) (execution.py:1413)
  → CORE_MAPPING → action_engine.execute("run_command", params) (execution.py:1461)
  → ActionEngine.run_command(command) (action_engine.py:81)
  → _execute_native("bash", command) (action_engine.py:96)
  → _direct_fallback("bash", content) (execution.py:552)
    → Sandbox check: docker sandbox OR direct execution
    → Direct:
      Win: create_subprocess_exec("cmd", "/c", ...)
      Unix: create_subprocess_exec("/bin/sh", "-c", ...)
    → Streaming: _run_subprocess_streaming() reads stdout/stderr line-by-line
    → Progress callback every 2s with tail of output
    → Timeout: 1 hour default
  → {"output": ..., "exit_code": ...}
```

### 1.10 Notifications

```
  Discord message → discord_channel.py:on_message()
  → Access control check
  → channels/processor.py:23 process_message(text, "discord", ...)
  → channel_adapter(text, "discord", ...) (adapters/channel_adapter.py:18)
    → Request(text, transport="discord", ...)
    → process_message(request) ← **CANONICAL PIPELINE**
    → Response.text
  → _emit_hooks() (processor.py:36)
    → PluginEventBus.instance().emit("on_channel_message", ...)
    → mcp_server.enqueue_event("message", ...) — bidir MCP bridge
  → message.reply(response_text)
```

### 1.11 Automation (automated_build)

```
  tool_call_node → execute_tool_block("automated_build", args)
  → _hdl_automated_build() (execution.py:2385)
  → do_automated_build() (automated_build.py:360)
    → Phase 1: planning — GoalManager.create()
    → Phase 2: building — AutomationLoop._build_project()
    → Phase 3: packaging — scan for APK/AAB/logs
    → Post: ActivityStore.create_node() per phase
    → Post: CalibrationStore.record() — strategy learning
    → Post: ExperienceExtractor → KnowledgeStore
  → BuildExecutionRecord
```

### 1.12 Scheduling

```
  tool_call_node → execute_tool_block("scheduler_submit", args)
  → _hdl_scheduler_submit() (execution.py:2440)
  → do_scheduler_submit() (scheduler_tools.py:74)
    → Scheduler instance
    → SchedulerQueue.submit() → ScheduledActivity
  → Scheduler tick loop (every 5s):
    → refresh activities from store + ActivityGraph
    → clean finished workers
    → fill slots with best-scored ready activities (chain-aware)
    → launch each as async worker → SchedulerExecutor
      → research_executor → do_browser_research()
      → build_executor → do_build_project()
      → repair_executor → do_repair_project()
      → email_executor → _call_mcp_tool("mcp__email__send_email")
      → benchmark_executor → run_benchmark()
      → default_executor → execute_tool_block()
```

### 1.13 Projects

```
  POST /api/build/start
  → core/build_routes.py:44 start_build()
    → project_manager.enqueue(req.goal) (project_manager.py)
    → ProjectQueue → ControlLoop (control_loop.py)
    → SupervisorAgent.achieve_goal_or_subgoal() (supervisor_agent.py)
      → goal decomposition → task templates
      → CLI agent launch (opencode/aider/codex etc)
      → monitor progress → retry/adapt
    → ProjectState.save()
  → GET /api/build/status/{name} returns progress
```

### 1.14 Vision

```
  POST /api/vision/screen
  → core/routes/vision.py:25 vision_screen()
  → VisionAgent() (vision_agent.py:166)
    → _capture() → mss.mss() screenshot
    → _describe(state) → Ollama Moondream vision model via httpx
  → {"description": ..., "b64": ..., "width": ..., "height": ...}
```

### 1.15 Build

```
  tool_call_node → execute_tool_block("build_project", args)
  → _hdl_build_project() (execution.py:2007)
  → do_build_project() (build_tools.py:43)
  → _register_build_artifacts() → scan for APK/AAB/log/html
  → {"success": ..., "status": ..., "execution_id": ...}
```

---

## 2. Execution Table

| # | Capability | Entry Points | Execution Path | ExecutionProvider? | CapRegistry? | Scheduler? | Tool? | REST? | Status |
|---|-----------|-------------|---------------|-------------------|-------------|-----------|-------|-------|--------|
| 1 | **Coding** | CLI, POST /api/chat, POST /api/agent/stream, WS | stream_agent_loop → RuntimePipeline → graph → execute_tool_block | ForgeProvider (priority 10) | **NO** — uses `infer_capabilities()` | Via workflow | `bash`, `python`, `write_file` etc | `/api/chat`, `/api/agent/stream` | **Production** |
| 2 | **Browser** | Agent tool `browser_navigate`, REST automation | execute_tool_block → _hdl_browser_navigate → do_browser_navigate → Playwright | BrowserProvider (priority 10) | **NO** | Via scheduler executors | 24 `browser_*` tools | `automation/routes.py` | **Production** |
| 3 | **Desktop** | Agent tool `computer`, REST PC control | execute_tool_block → DesktopProvider._dispatch → DesktopController → pyautogui | DesktopProvider (priority 10) | **NO** | No | `computer` tool | `core/routes/control.py` | **Production** |
| 4 | **Research** | Agent tool `trigger_research`, CLI `understand` | execute_tool_block → do_trigger_research → SearXNG/DuckDuckGo → multi_hop | ResearchProvider (priority 10) | **NO** — `infer_capabilities()` fallback | research_executor | `trigger_research`, `web_search` | `/api/research/*` | **Production** |
| 5 | **Voice** | Microphone → VoiceEngine | VoiceEngine.process_audio → voice_adapter → process_message → pipeline | **NONE** | **NO** — bypasses all registries | No | None | `/voice` routes | **Production** |
| 6 | **Email** | Agent tool `send_email`, MCP tools | execute_tool_block → mcp.call_tool → email_server._send_email → smtplib | EmailProvider (priority 10) | **NO** | email_executor | 10 MCP email tools | `/email/*` | **Production** |
| 7 | **Memory** | Agent tool `manage_memory` | execute_tool_block → do_manage_memory → MemoryManager → memory.json | **NONE** (3-way subsystem) | **NO** | No | `manage_memory` | `/api/memory/*` | **Production** |
| 8 | **Filesystem** | Agent tool `read_file`/`write_file` etc | execute_tool_block → ActionEngine → _direct_fallback → open() | **NONE** (4 dispatch paths) | **NO** | No | 11 file tools | Via agent | **Production** |
| 9 | **Terminal** | Agent tool `bash`/`python`/`shell` | execute_tool_block → ActionEngine → _direct_fallback → subprocess | **NONE** | **NO** | No | `bash`, `python`, `shell` | `/ws/terminal` | **Production** |
| 10 | **Notifications** | Channel messages (Discord/Telegram) | channel_plugin → process_message → channel_adapter → pipeline | MessagingProvider (priority 10) | **NO** — pipeline bypasses | No | None | Via channels | **Production** |
| 11 | **Automation** | Agent tool `automated_build` | execute_tool_block → do_automated_build → AutomationLoop | AutomationProvider (priority 10) | **NO** | Via scheduler | `automated_build` | `/api/automation/*` | **Production** |
| 12 | **Scheduling** | Agent tool `scheduler_submit` | execute_tool_block → do_scheduler_submit → SchedulerQueue → tick → executor | **NONE** (4 schedulers coexist) | **NO** | **IS THE SCHEDULER** | 10 `scheduler_*` tools | `/scheduler` routes | **Production** |
| 13 | **Projects** | POST /api/build/start | build_routes → ProjectManager → SupervisorAgent → CLI agents | **NONE** | **NO** | Via project_manager queue | None | `/api/build/*` | **Production** |
| 14 | **Vision** | POST /api/vision/screen | vision_agent → mss screenshot → Ollama Moondream | **NONE** | **NO** | No | `vision_browser` tool | `/api/vision/*` | **Production** |
| 15 | **Build** | Agent tool `build_project` | execute_tool_block → do_build_project → build_tools | **NONE** (via ForgeProvider) | **NO** | build_executor | `build_project`, `repair_project` etc | `/api/build/*` | **Production** |
| 16 | **Speech** | VoiceEngine.speak() | tts.synthesize → Kokoro KPipeline → soundfile | **NONE** | **NO** | No | None | `/voice` routes | **Production** |
| 17 | **Search** | Agent tool `web_search` | execute_tool_block → mcp call OR _direct_fallback → SearXNG → DuckDuckGo | **NONE** (via BrowserProvider) | **NO** | Via research_executor | `web_search`, `web_fetch` | Via agent | **Production** |

### Key Finding

**Every single capability bypasses the CapabilityRegistry in its execution path.** Zero capabilities actually go through `capability_registry.get_providers()` or `capability_graph.resolve_goal()` during execution. The CapabilityRegistry is queried in exactly one production path: `core/agents/router.py:90` for `get_providers_for_task()`, which is used for agent routing, not for execution.

---

## 3. Bypass Report

### Category A: Architecture Violations (Must Fix)

| # | Bypass | File | What Happens Instead | Severity |
|---|--------|------|---------------------|----------|
| B1 | `infer_capabilities()` | `core/pipeline.py:38-60` | Hardcoded keyword → capability mapping, duplicates CapabilityRegistry | **CRITICAL** |
| B2 | `provider_router.select()` direct | `core/pipeline.py:228` | Selects providers without going through CapabilityRegistry | **HIGH** |
| B3 | `execute_tool_block()` | `core/tools/execution.py:1413` | Central tool dispatcher, ~3K lines, no capability check | **CRITICAL** |
| B4 | 100+ `_hdl_*` handlers | `execution.py:1472-3024` | Direct tool handler closures, no capability gating | **CRITICAL** |
| B5 | `ActionEngine` | `core/action_engine.py:20-147` | Parallel execution layer, no registry awareness | **HIGH** |
| B6 | `execute_action()` | `core/main.py:689-761` | Hardcoded intent → action routing, 11+ intents | **HIGH** |
| B7 | `automation/routes.py` | 12+ REST endpoints | Direct calls to pc_automation, WhatsApp, Instagram, browser | **CRITICAL** |
| B8 | `WorkflowEngine._execute_step()` | `core/workflow/engine.py:372` | Calls `execute_tool_block()` directly | **HIGH** |
| B9 | All 5 concrete agents | `browser_agent.py`, `research_agent.py` etc | Each calls `execute_tool_block()` directly | **HIGH** |
| B10 | `ExecutionStage._build_executor()` | `stages/execution.py:189` | Canonical pipeline's own execution stage bypasses cap registry | **HIGH** |
| B11 | Provider bootstrap | `bootstrap.py:24-33` | Registers providers but NOT their capabilities in CapabilityRegistry | **HIGH** |
| B12 | `CapabilitySelectionStage` | `stages/capability_selection.py:46` | Hardcoded intent→cap dict as primary, reg as fallback | **MEDIUM** |

### Category B: Legacy Bypasses (Should Fix)

| # | Bypass | File | What Happens Instead | Severity |
|---|--------|------|---------------------|----------|
| B13 | `stream_agent_loop()` legacy fallback | `agent_loop.py:102-126` | Direct `graph.execute(state)`, whole pipeline bypassed | **HIGH** |
| B14 | `agent_resume()` | `routes/chat.py:217` | Loads checkpoint → `graph.execute(state)` directly | **MEDIUM** |
| B15 | `core/routes/control.py` | `computer_control()` | `computer_agent.execute_natural_language()` directly | **HIGH** |
| B16 | `core/build_routes.py` | `start_build()` | Direct `project_manager.enqueue()`, no capability check | **HIGH** |

### Category C: Transitive Bypasses (Calls execute_tool_block directly)

| # | Bypass | File | Line | Severity |
|---|--------|------|------|----------|
| B17 | Governance WorkQueue | `work_queue.py` | 306 | MEDIUM |
| B18 | PlannerExecutor | `planner/executor.py` | 298 | MEDIUM |
| B19 | Scheduler executors | `scheduler/executors.py` | 177 | MEDIUM |
| B20 | Benchmark runner | `benchmark/runner.py` | 350 | LOW |

### Bypass Counts

| Category | Count |
|----------|-------|
| **Critical** (must fix) | 5 |
| **High** (should fix) | 10 |
| **Medium** (fix when refactoring) | 5 |
| **Low** (test infra) | 1 |
| **Total bypasses** | ~40 distinct code paths |
| **Files calling `execute_tool_block()` directly** | ~30 |
| **REST endpoints bypassing cap registry** | ~40+ |

---

## 4. ExecutionProvider Audit

### 4.1 Provider Summary

| # | Provider | ID | Created | Registered By | Priority | Health Check | Health Real? | Prod Users | Dead? |
|---|----------|----|---------|-------------|----------|-------------|-------------|-----------|-------|
| P1 | ForgeProvider | `forge` | Direct instance | bootstrap.py:24 | 10 | `return HEALTHY` | **FAKE** | pipeline.py:228, agents/router.py | No |
| P2 | BrowserProvider | `browser` | Direct instance | bootstrap.py:25 | 10 | `do_browser_health()` | **REAL** | pipeline.py:228 | No |
| P3 | ResearchProvider | `research` | Direct instance | bootstrap.py:26 | 10 | `FactStore.count_facts()` | **REAL** | pipeline.py:228 | No |
| P4 | AutomationProvider | `automation` | Direct instance | bootstrap.py:27 | 10 | `WorkflowEngine()` | **REAL** | pipeline.py:228 | No |
| P5 | MessagingProvider | `messaging` | Direct instance | bootstrap.py:28 | 10 | email + channel check | **REAL** | pipeline.py:228 | No |
| P6 | DeploymentProvider | `deployment` | Direct instance | bootstrap.py:29 | 10 | docker/git which | **REAL** | pipeline.py:228 | No |
| P7 | WorkspaceProvider | `workspace` | Direct instance | bootstrap.py:30 | 10 | `DesktopState.snapshot()` | **REAL** | pipeline.py:228 | No |
| P8 | GitHubProvider | `github` | Direct instance | bootstrap.py:31 | 10 | `git --version` | **REAL** | pipeline.py:228 | No |
| P9 | EmailProvider | `email` | Direct instance | bootstrap.py:32 | 10 | mcp email server check | **REAL** | pipeline.py:228 | No |
| P10 | DesktopProvider | `desktop` | Direct instance | bootstrap.py:33 | 10 | `pyautogui.size()` | **REAL** | pipeline.py:228 | No |
| P11 | ClaudeCodeProvider | `claude_code` | Direct instance | bootstrap.py:41 | 50 | `claude --version` | **REAL** | agents/router.py | Conditional |
| P12 | CodexProvider | `codex` | Direct instance | bootstrap.py:48 | 60 | `codex --version` | **REAL** | agents/router.py | Conditional |

### 4.2 Who Actually Calls Providers

| Caller | File | Line | What It Calls | Frequency |
|--------|------|------|-------------|-----------|
| `RuntimePipeline.execute()` | `pipeline.py` | 228 | `self._provider_router.select()` | Every agent stream request |
| `AgentRouter.select_provider()` | `agents/router.py` | 136 | `provider_router.select_with_fallback()` | Every agent route |
| `Orchestrator._select_provider()` | `orchestration/orchestrator.py` | 338 | `self._router.select()` | Every orchestration step |
| `CapabilityNegotiator.resolve()` | `capability/negotiation.py` | 82 | `provider_router.select_with_fallback()` | **DEAD CODE** (composition is test-only) |

### 4.3 Provider Routing Call Chain

```
  RuntimePipeline.execute() (pipeline.py:199)
    → capabilities = infer_capabilities(goal) ← **hardcoded, no registry**
    → for cap in capabilities:
      → task_ctx = {"capability": cap, "goal": goal, ...}
      → p = self._provider_router.select(cap, task=task_ctx, record_decision=True)
        → candidates = provider_registry.get_providers_for_capability(capability)
        → Filter: enabled, budget, skip-list, health
        → Score: 7 dimensions + calibration adjustment
        → _score_dimensions():
          → historical_success ← provider_memory.get_performance_score()
          → benchmark_quality ← benchmark_store
          → health ← provider.cached_health()
          → latency ← provider_memory latency stats
          → cost ← provider capabilities metadata
          → budget ← provider_budget.can_use() ← **always True** (record_spend never called)
          → offline_availability ← provider config
        → calibration_adjustment ← calibrator.get_adjustment()
        → Record decision: recorder.record_decision() ← **active**
      → if p: selected_capability = cap; break
    → pipeline_context["provider"] = provider
    → graph.execute(state + pipeline_context)
      → tool_call_node → _execute_one_tool()
        → ctx.get("provider").handle_tool() ← **direct provider dispatch**
```

### 4.4 Provider Memory Activity

| Function | Production Calls | Test Calls | Status |
|----------|----------------|------------|--------|
| `provider_memory.record()` | 2 (pipeline.py:430, nodes.py:780) | 1 | **ACTIVE** |
| `provider_memory.get_performance_score()` | 1 (router.py:259) | 4 | **ACTIVE** — influences scoring |
| `provider_memory.should_skip()` | 2 (router.py:131,196) | 0 | **ACTIVE** — gates failed providers |
| `provider_memory.get_top_providers()` | 0 | 0 | **DEAD CODE** |
| `provider_memory.get_distribution()` | 0 | 0 | **DEAD CODE** |
| `provider_memory.get_expected_score()` | 0 | 0 | **DEAD CODE** |

### 4.5 Feedback/Calibration Loop Activity

| Function | Production Calls | Status |
|----------|----------------|--------|
| `recorder.record_decision()` | 1 (router.py:167, when `record_decision=True`) | **ACTIVE** |
| `recorder.record_outcome()` | 2 (pipeline.py:440, orchestrator.py:310) | **ACTIVE** |
| `calibrator.update_from_outcomes()` | 2 (pipeline.py:449, orchestrator.py:216) | **ACTIVE** |
| `calibrator.get_adjustment()` | 3 (router.py:241,246,326) | **ACTIVE** — influences scoring |

### 4.6 Budget Activity

| Function | Production Calls | Status |
|----------|----------------|--------|
| `provider_budget.can_use()` | 2 (router.py:127,194) | **ACTIVE** but always returns True |
| `provider_budget.record_spend()` | 0 | **DEAD CODE** |

### 4.7 Key Provider Findings

1. **ForgeProvider health is fake** — always returns `HEALTHY`. No real probe.
2. **Budget is a no-op** — `can_use()` is checked but `record_spend()` is never called, so the gate is always open.
3. **Provider memory IS active** — success rates influence the `historical_success` scoring dimension.
4. **Provider routing IS active** — `select()` is called from 2 production paths.
5. **But routing is used only for LLM tool dispatch** — providers don't actually execute capabilities; they wrap tools that call `execute_tool_block()`.
6. **`get_top_providers()` is dead code** — abandoned. So is `get_distribution()` and `get_expected_score()`.

---

## 5. Scheduling Audit

### 5.1 All Schedulers & Background Workers

| # | Scheduler | File | Created | Started By | Interval | Events? | Score | Replaceable? |
|---|-----------|------|---------|------------|---------|---------|-------|-------------|
| S1 | Activity Scheduler | `core/scheduler/scheduler.py` | lifespan.py:739 | `await start()` | 5s tick | **NO** | 7/10 | Yes |
| S2 | AutonomousScheduler | `core/scheduler/autonomous.py` | **NOT STARTED** | — | — | — | 6/10 | Orphaned |
| S3 | Cron Scheduler | `core/cron.py:169` | Module singleton | `await start()` | 60s poll | **NO** | 6/10 | Yes |
| S4 | Reminders Manager | `reminders/manager.py:90` | Module singleton | `load_and_schedule_all()` | 30s sleep | **NO** | 5/10 | Yes |
| S5 | Governance WorkQueue | `core/governance/work_queue.py:353` | Module singleton | `start()` | Background loop | **NO** | 7/10 | Yes |
| S6 | Consolidator | `core/long_term_memory/consolidator.py` | lifespan.py:846 | `create_task(_run())` | Background | **NO** | 6/10 | Yes |
| S7 | DreamingLoop | `core/dreaming.py` | lifespan.py:458 | `create_task(scheduler())` | Hourly (2AM) | **NO** | 6/10 | Yes |
| S8 | Ollama Poll | lifespan.py:418 | Inline | `create_task()` | One-shot (30 retries) | **NO** | 7/10 | Yes |
| S9 | Orphan Recovery | `core/spawning/orphan.py` | lifespan.py:232 | `create_task()` | One-shot | **NO** | 5/10 | Yes |
| S10 | ProactiveMonitor | `core/proactive_monitor.py` | lifespan.py:793 | `create_task()` | One-shot | **NO** | 5/10 | Yes |
| S11 | Workflow Recovery | `core/workflow/engine.py` | lifespan.py:807 | `create_task()` | One-shot | **NO** | 7/10 | Yes |
| S12 | ServiceHealthChecker | `monitors/health.py` | lifespan.py:308 | `await start()` | 30s | **NO** | 8/10 | Yes |
| S13 | EmailMonitor | `core/email_monitor.py` | lifespan.py:356 | `await start()` | 120s | **NO** | 7/10 | Yes |
| S14 | HeartbeatMonitor | `core/workflow/engine.py` | lifespan.py:828 | `await start()` | 10s | **NO** | 7/10 | Yes |
| S15 | FailoverProbe | `core/llm_failover.py` | lifespan.py:335 | `await start()` | Conditional | **NO** | 8/10 | Yes |
| S16 | Channels | `channels/controller.py` | lifespan.py:670 | `create_task()` | One-shot | PluginEventBus | 7/10 | Yes |
| S17 | Marketplace Refresh | `core/plugins/marketplace.py` | lifespan.py:612 | `create_task()` | One-shot | **NO** | 6/10 | Yes |
| S18 | Project Manager Queue | `core/project_manager.py` | lifespan.py:522 | `create_task()` | Background | **NO** | 6/10 | Yes |
| S19 | Voice Loop | `assistant/voice_pipeline.py` | lifespan.py:447 | `start()` | Background | `on_voice_command` | 9/10 | Yes |

### 5.2 Scheduling DRIFT Analysis

**4 scheduling systems coexist with overlapping responsibilities:**

| System | File | Purpose | Unique Features | Overlaps With |
|--------|------|---------|-----------------|---------------|
| `core/scheduler/` | Full module | Activity scheduling with executors | Chain manager, intelligence scoring, worker pool | cron, reminders |
| `core/cron.py` | Singleton | Traditional cron jobs | Cron expressions, persistent jobs | scheduler, reminders |
| `reminders/manager.py` | Singleton | User reminder polling | TTS injection, database polling | cron, scheduler |
| `governance/work_queue.py` | Singleton | Governance task queue | Priority queue (1/5/10), task router, throttling | scheduler |

**Who can be deleted:**

| Scheduler | Can Delete? | Can Become Plugin? |
|-----------|-------------|-------------------|
| Activity Scheduler | No — primary execution engine | Partially — registry could be plugin |
| AutonomousScheduler | **YES** — never started, dead code | Yes — opportunity discovery plugin |
| Cron Scheduler | **YES** — only 2 jobs (backup, remind) | Yes — jobs as plugins |
| Reminders Manager | **YES** — 30s polling, no events | Yes — reminder event generator |
| Governance WorkQueue | **YES** — routing should be unified | Yes — governance policy plugin |

---

## 6. Capability Registry Audit

### 6.1 What's Inside `core/capability/`

| File | Purpose | Production Usage | Status |
|------|---------|-----------------|--------|
| `models.py` | 20 built-in `Capability` dataclasses | Used by `capability_selection.py` (dead) + `registry.py` | **Partially used** |
| `registry.py` | `CapabilityRegistry` with `get_providers()`, `match_goal()`, `get_providers_for_task()` | 1 production caller: `agents/router.py:90` | **Sparsely used** |
| `graph.py` | `CapabilityGraph.resolve_goal()` with 4 templates (build, research, publish, browse) | Called by composition + negotiation (both test-only) | **DEAD CODE** |
| `composition.py` | `CompositionEngine.compose()` — build execution plan with permissions + negotiation | 0 production callers | **DEAD CODE** |
| `negotiation.py` | `CapabilityNegotiator.resolve()` — score and select provider for capability node | 0 production callers (transitive through composition) | **DEAD CODE** |

### 6.2 What Actually Uses `capability_registry`

| File | Line | Function | Production? |
|------|------|----------|-------------|
| `core/providers/bootstrap.py` | 95 | `register_capability()` (for v2 plugins only) | Yes |
| `core/providers/bootstrap.py` | 169,191 | `all_capabilities()` (health check) | Yes |
| `core/agents/router.py` | 90 | `get_providers_for_task(goal)` — agent routing | **Yes** |
| `core/capability/graph.py` | 122 | `match_goal()` — cache check | Only called by dead code |
| `core/capability/negotiation.py` | 221,223 | `get()` — provider lookup | Only called by dead code |
| `core/permission/registry.py` | 35 | `get(capability_id)` — permission resolution | Yes |
| `core/pipeline/stages/capability_selection.py` | 39 | `get()` — as fallback | **Stage is dead code** |
| `provider_sdk/registration.py` | 44,73 | `register_capability()` | Optional SDK |

### 6.3 Verdict

| Question | Answer |
|----------|--------|
| Metadata only? | **Mostly.** 20 capability definitions exist but only 10 have providers mapped. |
| Execution engine? | **No.** Zero capabilities execute through CapabilityRegistry. |
| Planning engine? | **No.** CompositionEngine is dead code. CapabilityGraph is dead code. |
| Plugin registry? | **No.** PluginRegistry is in `core/plugins/`, separate system. |
| Dead? | **Partially.** `registry.py` has 1 real caller. Everything else is dead or test-only. |
| Future system? | **The infrastructure is ready** — models, registry, graph, composition, negotiation all exist. They just aren't wired into any execution path. |

---

## 7. Provider Architecture Audit

### 7.1 Is This a Runtime Backbone or Model Router?

| Aspect | Current Reality |
|--------|----------------|
| **Registration** | 12 providers registered, 10 always-on, 2 conditional |
| **Capability mapping** | Each provider declares `capability_names` → `_capability_index` maps cap → [providers] |
| **Resolution** | `provider_router.select(capability, task)` — weighted scoring + calibration |
| **Execution** | Providers' `handle_tool()` dispatches to `execute_tool_block()` |
| **Health** | 11/12 real health checks; 1 fake (Forge) |
| **Scoring** | 7 dimensions (historical_success, benchmark, health, latency, cost, budget, offline) + calibration |
| **Decision recording** | Active — router records decisions, pipeline records outcomes, calibration adjusts scores |
| **Budget** | Checked but never recorded → always passes |

### 7.2 What Providers Actually Do

Providers are **LLM tool dispatchers with scoring wrappers**. When `handle_tool()` is called, they all do the same thing: call into `execute_tool_block()` or `do_*()` functions from `core.tools.*`. The provider abstraction adds:

1. **Health checking** — 11/12 providers have real health probes
2. **Scoring/Ranking** — 7-dimension weighted scoring enables intelligent selection
3. **Feedback loop** — decisions + outcomes are recorded, calibrations adjust future scoring
4. **Budget gating** — theoretically limits spending (currently a no-op)
5. **Failure skipping** — `should_skip()` gates failing providers

### 7.3 Verdict

**Providers are model routers with health checking, NOT a runtime execution backbone.** They select the best provider for a capability, but the actual execution happens through `execute_tool_block()` which sits entirely outside the provider system.

---

## 8. Event Architecture Audit

### 8.1 What Events Flow

| System | Events Published | Via | Subscribers |
|--------|-----------------|-----|-------------|
| **Pipeline** | `StreamEvent` (stage_start, stage_end, pipeline_end) | `stream_pipeline()` async generator | WebSocket adapter only |
| **Workflow** | `GOAL_CREATED`, `GOAL_COMPLETED`, `GOAL_FAILED`, `NODE_CREATED`, `NODE_UPDATED`, `NODE_COMPLETED`, `NODE_FAILED`, `NODE_SKIPPED`, `WARNING`, `ERROR`, `MILESTONE`, `NEED_INPUT`, `CONFIDENCE_UPDATED`, `ESTIMATE_UPDATED` | `emit_event()` → `get_bus().emit()` → `global_event_bus.publish()` | InboxStore, UnifiedBrain, WebSocket broadcast |
| **Brain** | `goal.created`, `goal.completed`, `goal.failed`, `task.completed`, `task.failed`, `system.disk_low` | `self.events.publish()` | UnifiedBrain |
| **Voice** | `on_voice_command` | `PluginEventBus.instance().emit()` | Plugin hooks |
| **Channels** | `on_channel_message` | `PluginEventBus.instance().emit()` | Plugin hooks + MCP bridge |
| **Memory** | `on_memory_recall` | `PluginEventBus.instance().emit()` | Plugin hooks |
| **Settings** | `settings.changed` | `self.event_bus.publish()` | Settings listeners |
| **Documents** | `document_created`, `document_edited` | `fire_event()` | EventBus history |
| **Observations** | `observation.observed` | `core/observation/hub` | EventBus |

### 8.2 What Does NOT Publish Events

| System | Missing Event Types | Impact |
|--------|-------------------|--------|
| **Schedulers** (all 4) | Activity started/completed/failed | UI cannot see scheduled task progress |
| **Tool execution** | Tool started/completed/failed | UI cannot see tool execution status |
| **Provider routing** | Provider selected/fallback | No routing decisions visible |
| **Agent graph** | Think/route/plan/tool_call | Only SSE output, no EventBus |
| **Channel execution** | Per-pipeline-stage | Only WS adapter sees StreamEvents |

### 8.3 WebSocket Broadcast

```
  EventBus.publish(event)
    → _broadcast(event_data)
      → for ws in _ws_all: ws.send_text(json)
      → for ws in _ws_by_session[session_id]: ws.send_text(json)
```

**WebSocket registration:**
- `core/routes/progress.py:222` — `bus.register_ws(ws, session_id=session_id)` — per-session
- `core/event_bus.py:113-116` — `register_ws()` adds to `_ws_all` + `_ws_by_session`

**Who receives what:** Every WebSocket registered via `register_ws()` receives ALL events broadcast by `_broadcast()`. This includes goal lifecycle events, node events, warnings, errors, milestones. There is no per-capability filtering.

### 8.4 StreamEvent Gap

**StreamEvents NEVER reach EventBus.** The pipeline's `stream_pipeline()` yields `StreamEvent` as an async generator. The WebSocket adapter consumes them and sends WS messages. But they are NOT forwarded to `global_event_bus.publish()`. This means:
- `stage_start`/`stage_end` events are only visible to the WebSocket adapter caller
- InboxStore cannot see pipeline stages
- History (ring buffer) does not capture pipeline lifecycle

### 8.5 Scheduler Event Gap

**No scheduler publishes events.** All 4 schedulers execute silently. Activity lifecycle (started, completed, failed, retried) has zero EventBus presence. The `core/workflow/tracker.py` does emit `GOAL_COMPLETED` etc., but this is triggered by workflow engine, not by the schedulers.

### 8.6 Event Architecture Verdict

| Question | Answer |
|----------|--------|
| Does execution publish progress? | **Partially.** Workflow tracker publishes goal/node events. But schedulers and tool execution don't. |
| Does UI receive it? | **Yes** — WebSocket broadcast delivers all EventBus events. But StreamEvents (pipeline stages) go through a separate path. |
| Does Inbox receive it? | **Yes** — InboxStore subscribes to 8 event types. |
| Does History receive it? | **No** — only EventBus in-memory ring buffer (100 entries). No persistent History module. |
| **Overall** | **FRAGMENTED** — two parallel event systems (EventBus + StreamEvents), schedulers are silent, tool execution is silent. |

---

## 9. Reality Scores

| # | Capability | Design | Impl | Registry | Execution | Planner | Provider | UI | Production | **Overall** |
|---|-----------|--------|------|----------|-----------|---------|----------|-----|-----------|------------|
| 1 | **Coding** | 8 | 8 | 0 | 8 | 7 | 7 | 7 | 10 | **6.9** |
| 2 | **Browser** | 8 | 9 | 0 | 8 | 6 | 8 | 7 | 9 | **6.9** |
| 3 | **Desktop** | 7 | 7 | 0 | 7 | 4 | 7 | 5 | 7 | **5.6** |
| 4 | **Research** | 7 | 8 | 0 | 7 | 6 | 7 | 6 | 8 | **6.1** |
| 5 | **Voice** | 9 | 9 | 0 | 8 | 4 | 0 | 7 | 9 | **5.8** |
| 6 | **Email** | 7 | 7 | 0 | 7 | 4 | 7 | 5 | 8 | **5.6** |
| 7 | **Memory** | 5 | 5 | 0 | 5 | 4 | 0 | 5 | 6 | **3.8** |
| 8 | **Filesystem** | 7 | 8 | 0 | 8 | 4 | 0 | 7 | 10 | **5.6** |
| 9 | **Terminal** | 8 | 9 | 0 | 8 | 4 | 0 | 7 | 10 | **5.8** |
| 10 | **Notifications** | 6 | 6 | 0 | 6 | 4 | 6 | 6 | 8 | **5.3** |
| 11 | **Automation** | 6 | 6 | 0 | 6 | 5 | 6 | 5 | 7 | **5.1** |
| 12 | **Scheduling** | 4 | 5 | 0 | 5 | 4 | 0 | 5 | 7 | **3.8** |
| 13 | **Projects** | 5 | 5 | 0 | 5 | 5 | 0 | 5 | 6 | **4.0** |
| 14 | **Vision** | 5 | 5 | 0 | 5 | 3 | 0 | 5 | 5 | **3.5** |
| 15 | **Build** | 7 | 7 | 0 | 7 | 5 | 7 | 5 | 8 | **5.8** |
| 16 | **Speech** | 8 | 8 | 0 | 8 | 3 | 0 | 6 | 9 | **5.3** |
| 17 | **Search** | 7 | 8 | 0 | 8 | 5 | 0 | 6 | 9 | **5.4** |

**Scoring Notes:**
- **Registry** = 0 for all — zero capabilities execute through the CapabilityRegistry
- **Voice/Speech** score high on implementation (9) but zero on Registry because they bypass completely
- **Coding/Browser** score highest overall due to production stability despite architecture bypass
- **Memory/Scheduling/Vision** score lowest — fragmented implementations, dead code, no unified design

---

## 10. Final Architecture Conclusions

### 10.1 What Survives Unchanged

| System | Reason |
|--------|--------|
| **`core/tools/browser_tools.py`** | Mature Playwright-based browser automation with FSM planner |
| **`assistant/voice_pipeline.py`** | Production-grade voice engine with auto-recovery, metrics, health monitoring |
| **`assistant/stt.py` + `assistant/tts.py`** | Solid STT/TTS with multiple providers |
| **`core/event_bus.py`** | Well-designed async event bus with pattern subscription, WebSocket broadcast |
| **`core/tools/search_tool.py`** | Robust search with SearXNG → DuckDuckGo fallback, multi-hop refinement |
| **`tools/security.py` + permission gates** | RBAC, tool authorization, path confinement, confirmation gates |
| **`core/workflow/engine.py`** | Durable workflow engine with heartbeat, recovery, compensation |
| **`core/providers/memory.py`** | Bayesian evidence-based provider memory — actively influences routing |
| **`core/providers/feedback/`** | Active feedback loop: decisions → outcomes → calibration → scoring |

### 10.2 What Becomes Wrappers

| System | Wraps | Into |
|--------|-------|------|
| **`core/tools/execution.py`** | ~100+ tool handlers | `CapabilityProvider` base class — each tool group becomes a provider |
| **`core/action_engine.py`** | 6 core actions (read/write/bash etc) | `FilesystemProvider` + `TerminalProvider` |
| **`core/providers/adapters/*.py`** | 10 existing provider adapters | `ExecutionProvider` (they already implement this) |
| **`channels/processor.py`** | Channel message routing | Add capability resolution before pipeline entry |
| **`core/build_routes.py`** | Build system | Wrap in `BuildExecutionProvider` |
| **`core/email_monitor.py`** | Background email monitoring | Wrap in `EmailMonitorProvider` |

### 10.3 What Becomes Adapters

| System | Adapter For | Into |
|--------|------------|------|
| **`core/pipeline/adapters/*.py`** | Transport-specific input | Already are adapters — keep as-is |
| **`channels/discord_channel.py` etc** | Platform-specific messaging | Already are channel adapters — add capability resolution |
| **`core/tools/execution.py:_direct_fallback()`** | Direct tool execution | `DefaultExecutionProvider` |
| **`core/tools/execution.py:_call_mcp_tool()`** | MCP tool routing | `MCPExecutionProvider` |
| **`core/providers/bootstrap.py`** | Provider init | Already is an adapter — wire through CapabilityRegistry |

### 10.4 What Becomes Plugins

| System | As Plugin | Priority |
|--------|-----------|----------|
| **`pc_automation_plugin.py`** | Desktop capability plugin | High |
| **`pii_routing_plugin.py`** | Privacy/routing override plugin | High |
| **`wake_word_plugin.py`** | Voice wake word plugin | Medium |
| **`file_tools_plugin.py`** | Filesystem tools plugin | Medium |
| **`reminders/manager.py`** | Reminder scheduler plugin | Medium |
| **`core/cron.py`** | Cron job scheduler plugin | Medium |
| **`core/providers/adapters/claude_code.py`** | Claude Code external provider | Won't change |
| **`core/providers/adapters/codex.py`** | Codex external provider | Won't change |

### 10.5 What Becomes the Backbone

| System | Role | Current Status |
|--------|------|----------------|
| **`core/capability/registry.py`** | Capability resolution backbone | **Exists but unused** — upgrade from metadata to execution layer |
| **`core/capability/graph.py`** | Capability dependency planning | **Exists but dead code** — wire into execution |
| **`core/pipeline/pipeline.py`** (canonical) | 19-stage request pipeline | **Active** — add capability-selection stage wiring |
| **`core/pipeline/pipeline.py`** (legacy RuntimePipeline) | Agent execution | **DRIFT** — migrate to canonical pipeline |
| **`core/providers/router.py`** | Provider selection with scoring | **Active** — keep as-is, becomes sub-layer of CapabilityRegistry |
| **`core/providers/registry.py`** | Provider registration | **Active** — keep as-is, becomes sub-layer |

### 10.6 What Becomes Deprecated

| System | Deprecation Reason | Replacement |
|--------|-------------------|-------------|
| **`core/pipeline.py` (legacy RuntimePipeline)** | Duplicates canonical pipeline | `core/pipeline/pipeline.py` + `stream_pipeline()` |
| **`core/capability/composition.py`** | Dead code, never used | Move logic into graph + negotiator |
| **`core/capability/negotiation.py`** | Dead code, never used | Move logic into ProviderRouter |
| **`core/agent_loop.py` legacy fallback** | Direct graph execution bypass | Remove — all paths go through pipeline |
| **`core/main.py:execute_action()`** | Hardcoded intent routing | Remove — use canonical pipeline |
| **`core/agent_runtime.py`** | Standalone agent runtime, no callers | Remove |
| **`automation/routes.py`** | 12+ REST endpoints outside architecture | Migrate to capability-gated providers |
| **`core/cron.py`** | 2-hardcoded-job cron, redundant with scheduler | Replace with scheduler plugin |
| **`reminders/manager.py`** | 30s polling, no events, redundant | Replace with scheduler plugin |
| **`core/governance/work_queue.py`** | Parallel queueing system | Merge into unified scheduler |
| **`core/scheduler/autonomous.py`** | Never started, dead code | Activate or remove |
| **`core/scheduler/metrics.py`** | Never instantiated, dead code | Wire into scheduler or remove |
| **`core/providers/budget.py`** | No-op (record_spend never called) | Fix or remove |

### 10.7 The One-Question Answer

> **How does execution actually happen today, and how do we make the Capability Registry become the single execution layer?**

**Today's reality:** Execution flows through a single 3,024-line function called `execute_tool_block()` in `core/tools/execution.py`. It dispatches ~100+ tool types via inline handlers. The Capability Registry, ProviderRouter, and ExecutionProviders sit on top as a **scoring/selection layer for LLM routing** — they decide *which* provider should handle a request, but that provider then calls the same `execute_tool_block()` that everything else calls. The registry adds metadata and scoring, not execution.

**To make CapabilityRegistry the execution layer:**

1. **Replace `execute_tool_block()`** — decompose its ~100 handlers into `ExecutionProvider` subclasses (one per capability domain). Each provider owns its tool dispatch.

2. **Wire `CapabilitySelectionStage`** — it exists in `core/pipeline/stages/` but is dead code. Wire it into the canonical pipeline's active stage list in `stages/__init__.py`.

3. **Wire `ExecutionStage`** — it also exists but is dead code. Wire it to use the CapabilityRegistry to resolve execution providers.

4. **Fix `infer_capabilities()`** — replace with `capability_registry.match_goal()`. This closes the primary bypass.

5. **Unify the 3 pipeline paths** — canonical pipeline (for REST/WS/voice/channel), legacy RuntimePipeline (for agent stream), and direct graph (for fallback/resume) all do the same thing through different code. Unify under canonical pipeline with capability-gated execution.

6. **Add ExecutionProviders for the 9 capabilities that lack them** — Memory, Voice, Projects, Search, Filesystem, Terminal, Vision, Speech, Scheduling.

7. **Make providers own execution** — today providers' `handle_tool()` delegates to `execute_tool_block()`. Instead, make each provider implement `execute()` directly, owning the tool dispatch for its capability domain.

8. **Remove the 3,024-line bypass** — once all tools are encapsulated in capability providers, `execute_tool_block()` becomes a small router that maps tool names to their owning provider's `execute()` method.

The infrastructure already exists. The models are defined. The registry is initialized. The scoring system works. The feedback loop is active. **What's missing is the wiring** — the 10% of connections that would make the 90% of design actually execute.
