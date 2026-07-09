# 03 — Capability Audit

> **Phase 3 of Source-of-Truth Audit.**  
> Every capability inventoried end-to-end: purpose, entry points, providers, dependencies, permissions, health, reachability, usage across all UIs, and callers.  
> READ ONLY — no code modifications.

---

## Table of Contents

1. [Desktop](#1-desktop)
2. [Browser](#2-browser)
3. [Coding](#3-coding)
4. [Research](#4-research)
5. [Automation](#5-automation)
6. [Memory](#6-memory)
7. [Voice](#7-voice)
8. [Notifications](#8-notifications)
9. [Email](#9-email)
10. [Projects](#10-projects)
11. [Build](#11-build)
12. [Search](#12-search)
13. [Filesystem](#13-filesystem)
14. [Terminal](#14-terminal)
15. [Vision](#15-vision)
16. [Speech](#16-speech)
17. [Scheduling](#17-scheduling)

---

## 1. Desktop

| Field | Value |
|-------|-------|
| **Purpose** | Control the local desktop — mouse, keyboard, screen capture, window management |
| **Canonical Definition** | `core/capability/models.py:129` — `Capability(id="desktop", category="automation")` |
| **Provider** | `DesktopProvider` at `core/providers/adapters/desktop_provider.py:21` — `provider_id="desktop"` |
| **Provider Health** | Checks `pyautogui.size()` at `desktop_provider.py:48` — returns HEALTHY, DEGRADED, or DOWN |
| **Provider Priority** | 10 (registered in `bootstrap.py:33`) |
| **Entry Points** | `desktop_provider.handle_tool()` dispatches 16+ actions: `mouse_move`, `mouse_click`, `mouse_double_click`, `mouse_scroll`, `mouse_drag`, `keyboard_type`, `keyboard_press`, `keyboard_hotkey`, `capture_screen`, `capture_window`, `capture_region`, `window_focus/minimize/maximize/restore/close` |
| **Dependencies** | `pyautogui`, `core.desktop.controller`, `core.desktop.screen`, `core.desktop.window` |
| **Permissions** | `desktop.window.read`, `desktop.mouse.move`, `desktop.mouse.click`, `desktop.keyboard.type`, `desktop.screen.capture` (defined at `models.py:133-140`) |
| **Reachable** | ✅ Conditionally — DEGRADED if `pyautogui` fails or platform lacks GUI |
| **Used** | Via `handle_tool()` dispatch in agent graph; permission block category `"desktop"` at `core/permission/policy.py:32` |
| **Registered** | ✅ `ProviderRegistry` via `bootstrap_providers()` at `core/providers/bootstrap.py:33` |
| **Production Usage** | Agent graph tool calls (`computer` tool maps here), `execute_action("pc_control")` |
| **Agent Usage** | Via `computer` tool in `TOOL_TAGS`; mapped to `desktop` capability in graph nodes |
| **CLI** | `jarvis advanced` → PC automation commands |
| **Web** | No direct web endpoints; used via agent loop |
| **TUI** | No direct TUI support |
| **Reality Score** | 7/10 — functional but critically depends on `pyautogui` (Windows-only reliable); health check is real |
| **Callers** | `core/main.py:execute_action("pc_control")` → `automation/pc_automation.py`; agent graph `tool_call_node` → `handle_tool()` dispatch |
| **Future Canonical Location** | `core/capability/desktop/` with dedicated module |

---

## 2. Browser

| Field | Value |
|-------|-------|
| **Purpose** | Automate web browsing — navigate, click, fill forms, extract data, take screenshots |
| **Canonical Definition** | `core/capability/models.py:49` — `Capability(id="browser", category="automation")` |
| **Provider** | `BrowserProvider` at `core/providers/adapters/browser_provider.py:42` — `provider_id="browser"` |
| **Provider Health** | Calls `do_browser_health()` from `core/tools/browser_tools` at `browser_provider.py:69` — returns HEALTHY if browser alive, else DOWN |
| **Provider Priority** | 10 (registered in `bootstrap.py:25`) |
| **Entry Points** | `browser_provider.handle_tool()` dispatches 21 browser tools: `navigate`, `click`, `fill`, `press`, `snapshot`, `screenshot`, `evaluate`, `find`, `get_url`, `get_title`, `current_state`, `get_history`, `list_tabs`, `switch_tab`, `new_tab`, `close_tab`, `wait_visible`, `wait_text`, `wait_interactive`, `shadow_query`, `health` |
| **Dependencies** | `core/tools/browser_tools.py` (Playwright-based), `core/tools/browser_planner.py` (FSM-based) |
| **Permissions** | `network.http` (defined at `models.py:53`) |
| **Reachable** | ✅ Conditionally — depends on Playwright being installed and browser binary available |
| **Used** | 24 `browser_*` tools in `TOOL_TAGS` (all `ALWAYS_AVAILABLE`); invoked by agent graph RAG tool selection |
| **Registered** | ✅ `ProviderRegistry` via `bootstrap_providers()` at `core/providers/bootstrap.py:25` |
| **Production Usage** | Direct agent tool calls; also via `core/main.py:execute_action("open_url")` which uses `webbrowser.open()` directly (bypasses provider) |
| **Agent Usage** | Heavy — `BrowserPlanner.pre_plan()` injects `browser_snapshot` after navigate; `BrowserPlanner.post_plan()` chains follow-up actions |
| **CLI** | No direct CLI; `jarvis chat` can invoke via agent |
| **Web** | No direct web endpoints; `request_classifier.py` routes ACTION_BROWSER sub-types |
| **TUI** | No direct TUI support |
| **Reality Score** | 8/10 — well-implemented with Playwright; real health check; active production usage |
| **Callers** | Agent graph `plan_node` → `BrowserPlanner.pre_plan()`; `tool_call_node` → `execute_tool_block()`; `core/pipeline/stages/planner.py:48` checks `if "browser" in requirements`; `core/pipeline/stages/reasoner.py:61` appends `"browser"`; `core/pipeline.py:48-49` `infer_capabilities()` maps search/browse/navigate → `"browser"` |
| **Future Canonical Location** | `core/capability/browser/` with dedicated module |

---

## 3. Coding

| Field | Value |
|-------|-------|
| **Purpose** | Write, edit, debug, refactor, test, and generate code across multiple languages |
| **Canonical Definition** | `core/capability/models.py:41` — `Capability(id="coding", category="development")` |
| **Providers** | **ForgeProvider** (`core/providers/adapters/forge.py:19`, priority=10), **ClaudeCodeProvider** (`core/providers/adapters/claude_code.py:24`, priority=50, conditional), **CodexProvider** (`core/providers/adapters/codex.py:24`, priority=60, conditional) |
| **Forge Health** | Always returns HEALTHY at `forge.py:51` — **no real health check** |
| **ClaudeCode Health** | Runs `claude --version` at `claude_code.py:50` |
| **Codex Health** | Runs `codex --version` at `codex.py:45` |
| **Entry Points** | `ForgeProvider.handle_tool()` dispatches 12 tool types: `bash`, `python`, `write_file`, `edit_file`, `read_file`, `glob`, `grep`, `build_project`, `repair_project`, `run_tests`, `create_document`, `update_document` |
| **Dependencies** | `core/tools/execution.py`, `core/graph/` (LangGraph loop), LLM backends through `core/llm_router` |
| **Permissions** | `filesystem.read`, `filesystem.write` (defined at `models.py:44-45`) |
| **Reachable** | ✅ Forge always reachable; ClaudeCode/Codex only if CLI installed |
| **Used** | Core of every agent interaction; inferred from goal keywords (`infer_capabilities()` at `core/pipeline.py:46`) |
| **Registered** | ✅ Forge via `bootstrap.py:24`; ClaudeCode/Codex conditionally via `bootstrap.py:41-53` |
| **Production Usage** | Primary capability — virtually every agentic request touches coding |
| **Agent Usage** | `core/agents/router.py:75` maps `"coding"` → `"forge"` default agent |
| **CLI** | `jarvis code` — multi-step coding; `jarvis build` — build automation |
| **Web** | `POST /api/agent/stream` → `stream_agent_loop`; `POST /api/chat` → canonical pipeline |
| **TUI** | Textual TUI via WebSocket to agent loop |
| **Reality Score** | 8/10 — comprehensive implementation; Forge health check is fake (always HEALTHY) but active usage is high |
| **Callers** | `core/pipeline.py:46` — `infer_capabilities()` maps 6 keyword groups; `core/pipeline/stages/capability_selection.py:50` maps `"write_code"` → `["coding"]`; `core/agents/router.py:75,136,166` — agent routing; `core/configuration/service.py:18` — config mapping; `core/capability/graph.py:46,51,66,72` — subgraph templates; `core/improvement/models.py:21` — self-improvement; `core/providers/router.py:239,323` — default fallback capability |
| **Future Canonical Location** | `core/capability/coding/` with dedicated module |

---

## 4. Research

| Field | Value |
|-------|-------|
| **Purpose** | Gather, synthesize, and analyze information from web searches and documents |
| **Canonical Definition** | `core/capability/models.py:97` — `Capability(id="research", category="knowledge")` |
| **Provider** | `ResearchProvider` at `core/providers/adapters/research_provider.py:18` — `provider_id="research"` |
| **Provider Health** | Checks `FactStore.count_facts()` at `research_provider.py:44` — HEALTHY if store responds, otherwise DOWN |
| **Provider Priority** | 10 (registered in `bootstrap.py:26`) |
| **Entry Points** | `ResearchProvider.execute()` at `research_provider.py:77` dispatches: `_quick_research()` (single browser query) or `_full_research()` (planner + multi-query + synthesis) |
| **Dependencies** | `core/research/storage/` (FactStore), `core/research/planner/`, `core/research/synthesizer/`, `core/tools/browser_research.py` |
| **Permissions** | `network.http` (defined at `models.py:100`) |
| **Reachable** | ✅ Conditionally — depends on research storage modules |
| **Used** | Default fallback in `infer_capabilities()` at `core/pipeline.py:59` (if no keywords matched → `["research"]`) |
| **Registered** | ✅ `ProviderRegistry` via `bootstrap_providers()` at `core/providers/bootstrap.py:26` |
| **Production Usage** | Agent tool calls `trigger_research`, `manage_research`; classified requests without clear intent default to research |
| **Agent Usage** | `core/agents/router.py:69` maps `"research"` → `"research"` agent; `core/agents/capabilities.py:5` maps research keywords |
| **CLI** | `jarvis advanced research`; `jarvis understand` for codebase research |
| **Web** | `api/research_routes.py` — independent `/research` API prefix |
| **TUI** | Via agent WebSocket |
| **Reality Score** | 7/10 — solid implementation with quick/full modes; real health check; broadest fallback in system |
| **Callers** | `core/pipeline.py:50-51` — fallback at line 59; `core/pipeline/stages/capability_selection.py:48,52,53` — search_web/research/analyze → research; `core/capability/graph.py:55-62,79,83` — research → documentation; `brain/tools/tool_registry.py:97` — `do_trigger_research` registration; `core/routing/request_classifier.py` — ACTION_BROWSER → research; `core/main.py:718` — `execute_action("web_search")` |
| **Future Canonical Location** | `core/capability/research/` with dedicated module |

---

## 5. Automation

| Field | Value |
|-------|-------|
| **Purpose** | Execute multi-step workflows, scheduled tasks, background pipelines, and orchestration |
| **Canonical Definition** | `core/capability/models.py:197` — `Capability(id="automation", category="infrastructure")` |
| **Provider** | `AutomationProvider` at `core/providers/adapters/automation_provider.py:20` — `provider_id="automation"` |
| **Provider Health** | Checks `WorkflowEngine()` instantiation at `automation_provider.py:46` — HEALTHY if engine responds, else DOWN |
| **Provider Priority** | 10 (registered in `bootstrap.py:27`) |
| **Entry Points** | `AutomationProvider.execute()` at `automation_provider.py:70` — runs `WorkflowEngine.start_workflow()` with `StepDefinition` list |
| **Dependencies** | `core/workflow/engine.py`, `core/workflow/models.py` |
| **Permissions** | `filesystem.read`, `filesystem.write`, `network.http` (defined at `models.py:200-204`) |
| **Reachable** | ✅ Conditionally — depends on WorkflowEngine being importable |
| **Used** | RuntimePipeline Phase A.6 (Workflow Execution at `core/pipeline.py:264`) |
| **Registered** | ✅ `ProviderRegistry` via `bootstrap_providers()` at `core/providers/bootstrap.py:27` |
| **Production Usage** | Background task execution, scheduled workflows, activity scheduler executors |
| **Agent Usage** | Via `scheduler_*` tools (10 scheduler tools in `TOOL_TAGS`, all `ALWAYS_AVAILABLE`); `workflow_*` tools (5 tools) |
| **CLI** | `jarvis advanced automation` |
| **Web** | `automation/routes.py` — `/api/automation` prefix |
| **TUI** | No direct TUI support |
| **Reality Score** | 6/10 — functional but complex; WorkflowEngine and AutomationProvider duplicate concept; Real health check |
| **Callers** | `core/pipeline.py:56-57` — `infer_capabilities()` maps schedule/automate → "automation"; `core/scheduler/decision.py:125` — activity component mapping; `core/llm_router.py:72,82` — model mapping |
| **Future Canonical Location** | `core/capability/automation/` with dedicated module |

---

## 6. Memory

| Field | Value |
|-------|-------|
| **Purpose** | Store, retrieve, consolidate, and recall information across sessions — tiered memory, embeddings, preferences, facts |
| **Canonical Definition** | Not in `core/capability/models.py` — memory is a cross-cutting concern, not a capability in the builtin set |
| **Providers** | No dedicated `ExecutionProvider` for memory; memory is handled by **pipeline stages** and **dedicated subsystems** |
| **Pipeline Stages** | `MemoryStage` at `core/pipeline/stages/memory.py` — stage 17/19 in canonical pipeline; `ContextRetrievalStage` at `core/pipeline/stages/context_retrieval.py` — stage 9/19 |
| **Subsystems** | `core/long_term_memory/` (Consolidator, BehaviorAdapter, Store, Extractor, Synthesizer, Models); `memory/` (TieredMemory, MemoryFacade, EmbeddingMemory, DecisionMemory, FactStore, PreferenceProfile, Mem0Adapter); `brain/memory/` |
| **Dependencies** | ChromaDB (embeddings), SQLite (fact store), Mem0 (optional adapter) |
| **Permissions** | `memory:write` scope at `core/tools/execution.py` line 2630 — `manage_memory` tool is ADMIN-only |
| **Reachable** | ✅ Always — all subsystems lazy-imported |
| **Used** | Every pipeline execution (stage 17); Phase A.8 in `RuntimePipeline` (Knowledge Injection via `BehaviorAdapter`); Phase A.9 (Learning Feedback via `Consolidator`) |
| **Registered** | Not as a provider; registered as pipeline stage via `DEFAULT_STAGES` at `core/pipeline/stages/__init__.py:62` |
| **Production Usage** | `manage_memory` tool (CRUD); automatic consolidation every 120s (in pipeline) or background loop (in lifespan) |
| **Agent Usage** | `manage_memory` tool is `ALWAYS_AVAILABLE`; memory context injected into prompts via `BehaviorAdapter.for_planner()` |
| **CLI** | No direct CLI |
| **Web** | `api/memory_routes.py` — memory REST API |
| **TUI** | No direct TUI support |
| **Reality Score** | 5/10 — **DRIFT**: 3 competing memory systems (`core/long_term_memory/`, `memory/`, `brain/memory/`) with overlapping responsibilities; no unified provider abstraction; `MemoryStage` in canonical pipeline vs `BehaviorAdapter` in legacy pipeline |
| **Callers** | `core/pipeline.py:164-170` — `BehaviorAdapter.for_planner()` in Phase A.8; `core/pipeline.py:457-467` — `Consolidator` in Phase A.9; `core/lifespan.py:836-843` — background consolidator loop; pipeline stage 17/19 |
| **Future Canonical Location** | `core/capability/memory/` with unified MemoryProvider, deprecating 3-way split |

---

## 7. Voice

| Field | Value |
|-------|-------|
| **Purpose** | Process voice input (STT) and produce spoken output (TTS) through the voice pipeline |
| **Canonical Definition** | `core/capability/models.py:165` — `Capability(id="voice", category="interaction", tags=["voice", "audio", "speech", "wake_word"])` |
| **Provider** | No dedicated `ExecutionProvider` — voice is handled by `VoiceEngine` at `assistant/voice_pipeline.py:307` |
| **Engine Health** | `VoiceHealthMonitor` at `voice_pipeline.py:262` — periodic STT/TTS health checks |
| **Entry Points** | `VoiceEngine.process_audio()` at `voice_pipeline.py:421` (full duplex); `VoiceEngine.transcribe()` at `voice_pipeline.py:392` (STT only); `VoiceEngine.think()` at `voice_pipeline.py:403` (via `voice_adapter`); `VoiceEngine.speak()` at `voice_pipeline.py:414` (TTS only) |
| **Dependencies** | `assistant/stt.py` (FasterWhisper default, Deepgram/AzureSpeech optional), `assistant/tts.py` (Kokoro-TTS default), `core/audio_emotion.py` (emotion detection), `sounddevice`, `soundfile`, `webrtcvad` |
| **Permissions** | None defined in capability model |
| **Reachable** | ✅ Always — STT/TTS providers lazy-loaded; auto-recovery on failure |
| **Used** | `VoiceLoop` started in lifespan (`core/lifespan.py:442-448`); 3 modes: wake-word, continuous, push-to-talk |
| **Registered** | Not as a provider; registered as `app.state.voice_loop` at `core/lifespan.py:443` |
| **Production Usage** | Active voice loop with per-phase latency metrics (STT, think, TTS, total); rolling 1000-sample metrics window |
| **Agent Usage** | Not used by agent; voice has its own independent pipeline (`voice_adapter` → `process_message`) |
| **CLI** | No direct CLI |
| **Web** | `core/routes/voice.py` — voice API routes |
| **TUI** | No direct TUI support |
| **Reality Score** | 9/10 — well-implemented production-grade voice engine with auto-recovery, device management, VAD, emotion detection, health monitoring, and per-phase latency tracking |
| **Callers** | `VoiceEngine.process_audio()` → `VoiceEngine.think()` → `voice_adapter()` at `core/pipeline/adapters/voice_adapter.py:24`; `PluginEventBus.emit("on_voice_command")` at `voice_pipeline.py:432` |
| **Future Canonical Location** | `core/capability/voice/` — already largely self-contained; add `ExecutionProvider` wrapper |

---

## 8. Notifications

| Field | Value |
|-------|-------|
| **Purpose** | Send push notifications, desktop alerts, and message digests through multiple channels |
| **Canonical Definition** | `core/capability/models.py:113` — `Capability(id="notifications", category="communication")` |
| **Providers** | No dedicated `ExecutionProvider` for notifications; handled by `MessagingProvider` at `core/providers/adapters/messaging_provider.py:18` (capabilities include `"notification"`) and `SupervisorNotifier` at `notifications/notifier.py:28` |
| **Health** | MessagingProvider health checks email_server + channel_controller channels at `messaging_provider.py:45` |
| **Entry Points** | `MessagingProvider.handle_tool()` for notification/message sending; `notifier.py:notify()` for push notifications (ntfy.sh/Pushover/digest) |
| **Dependencies** | ntfy.sh or Pushover credentials, email server, channel controller |
| **Permissions** | None defined in capability model |
| **Reachable** | ✅ Conditionally — DEGRADED if no channels configured |
| **Used** | `event_bus.py` — event broadcast; `channels/processor.py` — MCP enqueue; `AlertRouter` at lifespan |
| **Registered** | Indirectly via `MessagingProvider` at `bootstrap.py:28` |
| **Production Usage** | Alert routing (broadcast, speak, WhatsApp); email monitoring alert callbacks; supervisor notifications |
| **Agent Usage** | Via `messaging` capability routing |
| **CLI** | No direct CLI |
| **Web** | No direct web endpoints; pushed via WebSocket |
| **TUI** | No direct TUI support |
| **Reality Score** | 6/10 — functional but fragmented: `MessagingProvider`, `SupervisorNotifier`, `AlertRouter`, `PluginEventBus` all handle notifications differently |
| **Callers** | `core/lifespan.py:300` — `AlertRouter` construction; `notifications/notifier.py:notify()` — Pushover/ntfy; `core/pipeline/stages/capability_selection.py:57` — send_message → `["messaging", "notifications"]` |
| **Future Canonical Location** | `core/capability/notifications/` — consolidate MessagingProvider + Notifier + AlertRouter |

---

## 9. Email

| Field | Value |
|-------|-------|
| **Purpose** | Send, receive, compose, manage, and triage email messages |
| **Canonical Definition** | `core/capability/models.py:141` — `Capability(id="email", category="communication")` |
| **Providers** | `EmailProvider` at `core/providers/adapters/email_provider.py:18` — `provider_id="email"`; also via `MessagingProvider` (`"send_email"` in capability names) |
| **Provider Health** | Checks `mcp.email_server.email_server is not None` at `email_provider.py:41` — DOWN if MCP missing, DEGRADED if unconfigured |
| **Provider Priority** | 10 (registered in `bootstrap.py:32`) |
| **Entry Points** | `EmailProvider.handle_tool()` — 3 email tool names; MCP email server tools (10 tools at `execution.py:2666`: `list_email_accounts`, `send_email`, `list_emails`, `read_email`, `reply_to_email`, `bulk_email`, `delete_email`, `archive_email`, `mark_email_read`, `email_send`) |
| **Dependencies** | `mcp/email_server.py` (IMAP/SMTP), `core/email_monitor.py` (background polling), `api/email_routes.py` |
| **Permissions** | `network.smtp` (defined at `models.py:144`); email tools are ADMIN-only |
| **Reachable** | ✅ Conditionally — DOWN if MCP email server unavailable; DEGRADED if unconfigured |
| **Used** | Background monitoring (120s interval at lifespan), REST API, agent tools |
| **Registered** | ✅ `ProviderRegistry` via `bootstrap_providers()` at `core/providers/bootstrap.py:32`; MCP email server tools also registered |
| **Production Usage** | `send_email` (ALWAYS_AVAILABLE), `list_emails`/`read_email`/`reply_to_email` (ASSISTANT_ALWAYS_AVAILABLE) |
| **Agent Usage** | 10+ MCP email tools; `email_send` / `email_send_email` in TOOL_TAGS |
| **CLI** | No direct CLI |
| **Web** | `api/email_routes.py` — `/email/status`, `/email/inbox`, `/email/draft`, `/email/send`; `core/email_monitor.py` — background poll |
| **TUI** | No direct TUI support |
| **Reality Score** | 7/10 — dual path (EmailProvider + MCP email server); real health check; active monitoring; ADMIN-only gating is correct |
| **Callers** | `core/lifespan.py:339-356` — EmailMonitor background task; `api/email_routes.py` — REST endpoints; `core/pipeline/stages/capability_selection.py` — intent mapping |
| **Future Canonical Location** | `core/capability/email/` — consolidate EmailProvider + MCP email tools |

---

## 10. Projects

| Field | Value |
|-------|-------|
| **Purpose** | Manage multiple software projects with queues, priorities, checkpoint/resume, and lifecycle management |
| **Canonical Definition** | Not in `core/capability/models.py` — project management is a cross-cutting orchestration concern |
| **Provider** | `ProjectManager` at `core/project_manager.py:47` — not a formal `ExecutionProvider` |
| **Health** | `ProjectManager` queue processor started at `core/lifespan.py:515-517` |
| **Entry Points** | `ProjectManager.enqueue()` at `project_manager.py:120`; `ProjectManager.work()` at `project_manager.py:160`; automatic queue processing via `process_queue()` background task |
| **Dependencies** | `core/supervisor_agent.py` (SupervisorAgent for goal decomposition), CLI agents (opencode, aider, codex, gemini, shell) |
| **Permissions** | None defined — `SupervisorAgent` has no capability-gated permissions |
| **Reachable** | ✅ Always — singleton at `core/project_manager.py:255` |
| **Used** | Build system, multi-step goals, supervisor agent |
| **Registered** | As `app.state.build_queue` at lifecycle; not in any provider registry |
| **Production Usage** | Build pipeline (`/api/build/start` → enqueue), supervisor agent orchestration |
| **Agent Usage** | `SupervisorAgent.start_build()` → `ProjectManager.enqueue()` |
| **CLI** | `jarvis build <path>` → `cmd_build` |
| **Web** | `core/build_routes.py` — `/api/build/*`; `core/plan_routes.py` — agent orchestrator |
| **TUI** | No direct TUI support |
| **Reality Score** | 5/10 — **DRIFT**: `ProjectManager` and `SupervisorAgent` overlap heavily; neither is a registered `ExecutionProvider`; no capability-gated permissions; no health check beyond "started" |
| **Callers** | `core/lifespan.py:515` — queue processor start; `core/build_routes.py` — `/api/build/start` enqueue; `cli_commands.cmd_build` — CLI entry |
| **Future Canonical Location** | `core/capability/projects/` with `ProjectExecutionProvider` wrapper |

---

## 11. Build

| Field | Value |
|-------|-------|
| **Purpose** | Build, repair, test, and validate software projects autonomously |
| **Canonical Definition** | Not in `core/capability/models.py` as a standalone capability — build is a composition of `coding` → `testing` → `deployment` (defined in `core/capability/graph.py:44-54`) |
| **Providers** | `ForgeProvider` (`build_project`, `repair_project`, `run_tools`); `SupervisorAgent` task templates for scaffold/frontend/backend/database/auth |
| **Health** | No direct build health check; relies on Forge health (always HEALTHY) |
| **Entry Points** | `build_project` tool at `core/tools/execution.py:2626` (ALWAYS_AVAILABLE); `repair_project` at line 2627; `run_tests` at line 2628; `runtime_validate` at line 2629; `automated_build` at line 2625 |
| **Dependencies** | `ForgeProvider`, `SupervisorAgent`, `ProjectManager`, build tools, test frameworks |
| **Permissions** | None specific to build |
| **Reachable** | ✅ Always — Forge always installed and healthy |
| **Used** | Agent graph tool calls; supervisor agent build plans; `/api/build/start` REST endpoint |
| **Registered** | Tools are always registered in TOOL_TAGS; build routes at `core/build_routes.py` |
| **Production Usage** | Multi-agent build pipeline with auto-repair on failure; supervisor agent build mode |
| **Agent Usage** | Heavy — `build_project`, `repair_project`, `run_tests`, `runtime_validate` all ALWAYS_AVAILABLE |
| **CLI** | `jarvis build <path>` — build with auto-repair; `jarvis code` — full coding pipeline |
| **Web** | `core/build_routes.py` — `/api/build/start`, `/api/build/status`, `/api/build/cancel`, `/api/build/list` |
| **TUI** | No direct TUI support |
| **Reality Score** | 7/10 — well-integrated build pipeline with auto-repair; tools are ALWAYS_AVAILABLE in graph; no dedicated capability model for build as a standalone concept |
| **Callers** | `core/pipeline.py:52-53` — `infer_capabilities("deployment")` overlaps; `core/capability/graph.py:44-54` — build subgraph template; `core/main.py:731` — `execute_action("build")` → `supervisor.start_build()`; `core/build_routes.py:44` — `/api/build/start` |
| **Future Canonical Location** | `core/capability/build/` — formalize as a composed capability |

---

## 12. Search

| Field | Value |
|-------|-------|
| **Purpose** | Search the web and codebase for information |
| **Canonical Definition** | Not in `core/capability/models.py` as standalone — search is subsumed by `research` and `browser` capabilities |
| **Providers** | No dedicated `ExecutionProvider` for search; handled by `BrowserProvider` (`"search"` in capability names) and `ResearchProvider` |
| **Implementations** | `tools/search_tool.py:29` — `SearXNGSearch` (primary, configurable endpoint), `DuckDuckGoFallback` (fallback); `semantic_search` tool at `core/tools/execution.py:2562` (codebase search); `web_search` tool at `core/tools/execution.py:403` (ALWAYS_AVAILABLE) |
| **Dependencies** | `searxng` (optional), `httpx`/`requests`, DuckDuckGo (no API key needed) |
| **Permissions** | `network.http` (via research/browser capabilities) |
| **Reachable** | ✅ Always — DuckDuckGo fallback ensures search works even without SearXNG |
| **Used** | Agent graph `web_search` tool (ALWAYS_AVAILABLE); `semantic_search` for codebase (ALWAYS_AVAILABLE) |
| **Registered** | As tools in TOOL_TAGS, not as a provider |
| **Production Usage** | `SearchDecisionGate` at `search_tool.py:120` determines if search is needed; `multi_hop()` for iterative gap-driven research |
| **Agent Usage** | `web_search` and `semantic_search` are both `ALWAYS_AVAILABLE` in graph |
| **CLI** | `jarvis code` or `jarvis understand` may trigger codebase search |
| **Web** | Via REST/WebSocket agent loop |
| **TUI** | Via agent WebSocket |
| **Reality Score** | 7/10 — robust implementation with fallback chain and gap-driven multi-hop; no formal capability registration as standalone |
| **Callers** | `core/main.py:718` — `execute_action("web_search")` → `tools/search_tool.search()`; `core/pipeline/stages/capability_selection.py:48` — `"search_web": ["research", "browser"]`; agent graph tool selection |
| **Future Canonical Location** | `core/capability/search/` — formalize as sub-capability of research |

---

## 13. Filesystem

| Field | Value |
|-------|-------|
| **Purpose** | Read, write, edit, delete, list, and search files on the local filesystem |
| **Canonical Definition** | `core/capability/models.py:121` — `Capability(id="filesystem", category="infrastructure")` |
| **Providers** | No dedicated `ExecutionProvider` for filesystem; handled by tools directly in `core/tools/execution.py` and via `ForgeProvider.handle_tool()` dispatch |
| **Entry Points** | 11 filesystem tools in `TOOL_TAGS`: `read_file`, `write_file`, `append_file`, `delete_file`, `list_folder` (via MCP or direct fallback); `edit_file`, `undo_edit_file`, `batch_edit_file` (direct handlers); `watch_file` (file watching); `semantic_search` (codebase search) |
| **Dependencies** | None beyond Python stdlib |
| **Permissions** | `filesystem.read`, `filesystem.write` (defined at `models.py:124-125`); write/delete are `needs_confirmation=True`, `tools:execute:medium` at `core/tools/defaults.py` |
| **Reachable** | ✅ Always — no external dependencies |
| **Used** | Every agent interaction reads/writes files |
| **Registered** | Tools in TOOL_TAGS via `core/tools/_constants.py`; file_tools_plugin also registers 5 tools via `plugins/file_tools_plugin.py` |
| **Production Usage** | All `read_file`/`write_file`/`edit_file` are ALWAYS_AVAILABLE in graph |
| **Agent Usage** | Core agent tools — injected in every graph execution |
| **CLI** | `jarvis code` — file operations as part of coding |
| **Web** | Via agent endpoints |
| **TUI** | Via agent WebSocket |
| **Reality Score** | 8/10 — well-implemented with path confinement, confirmation gates, and RBAC; dual tool path (MCP + direct fallback + Forge adapter + plugin) creates some redundancy |
| **Callers** | `core/pipeline/stages/capability_selection.py:62-63` — `"read_file": ["filesystem"]`, `"write_file": ["filesystem"]`; agent graph tool selection; `ForgeProvider.handle_tool()` dispatch |
| **Future Canonical Location** | `core/capability/filesystem/` with dedicated `FilesystemProvider` consolidating 4 tool paths |

---

## 14. Terminal

| Field | Value |
|-------|-------|
| **Purpose** | Execute shell commands, persistent shell sessions, and process management |
| **Canonical Definition** | `core/capability/models.py:157` — `Capability(id="terminal", category="infrastructure")` |
| **Providers** | No dedicated `ExecutionProvider` for terminal; handled by tools directly in `core/tools/execution.py` |
| **Entry Points** | `bash` tool (expert handler), `python` tool (expert handler), `shell`/`shell_command` (persistent shell via `WinShell`/`UnixShell`), `close_shell` (session cleanup) |
| **Dependencies** | `asyncio.subprocess`, `ptyprocess` (Unix), `winpty` (Windows optional) |
| **Permissions** | `bash`/`python`/`shell` are ADMIN-only; `needs_confirmation=True` at `core/tools/defaults.py` with `tools:execute:high` risk level |
| **Reachable** | ✅ Always — subprocess module is stdlib |
| **Used** | Every agent interaction that needs shell execution |
| **Registered** | Tools in TOOL_TAGS via `core/tools/_constants.py:21-27` |
| **Production Usage** | Shell execution in agent graph; `bash` is ALWAYS_AVAILABLE; `python` is ALWAYS_AVAILABLE |
| **Agent Usage** | Core agent tools — injected in every graph execution; `pause_node` pauses before effectful commands when `pause_before_effectful` enabled |
| **CLI** | No direct terminal CLI (jarvis runs shell commands as part of coding) |
| **Web** | `core/routes/terminal.py` — `/ws/terminal` WebSocket for persistent shell |
| **TUI** | No direct TUI support |
| **Reality Score** | 8/10 — well-implemented with persistent shell, confirmation gates, RBAC; no dedicated provider but tools are mature |
| **Callers** | Agent graph `tool_call_node` → `execute_tool_block()` → `bash`/`python`/`shell` handlers; `core/pipeline/stages/capability_selection.py:58` — `"run_command": ["terminal"]` |
| **Future Canonical Location** | `core/capability/terminal/` with `TerminalProvider` wrapper |

---

## 15. Vision

| Field | Value |
|-------|-------|
| **Purpose** | Capture and analyze screen content, answer questions about visual scenes |
| **Canonical Definition** | `core/capability/models.py:57` — `Capability(id="vision", category="intelligence")` |
| **Providers** | No dedicated `ExecutionProvider` for vision; handled by REST API endpoints |
| **Dependencies** | `mss` (screen capture), LLM with vision capabilities (via LLM router) |
| **Permissions** | None defined in capability model |
| **Entry Points** | `core/routes/vision.py:18` — `/api/vision/screen` (capture + describe), `/api/vision/analyze` (QA over screen) |
| **Reachable** | ✅ Always — `mss` is pure Python, screen capture always works |
| **Used** | Screen understanding REST API |
| **Registered** | As FastAPI routes at `core/main.py:766` via `core/routes/vision.py` |
| **Production Usage** | Screen analysis for desktop context; vision_browser tool for browser screenshots |
| **Agent Usage** | `vision_browser` tool in TOOL_TAGS; `core/pipeline/stages/capability_selection.py:53` — `"analyze": ["research", "vision"]` |
| **CLI** | No direct CLI |
| **Web** | `POST /api/vision/screen`, `POST /api/vision/analyze` |
| **TUI** | No direct TUI support |
| **Reality Score** | 5/10 — **DORMANT**: Minimal implementation (2 endpoints); no `ExecutionProvider`; no health check; vision capability depends on LLM having vision support (not guaranteed) |
| **Callers** | `api/vision_routes.py` (optional, loaded at `core/main.py:237`); `core/routes/vision.py` (direct load at `core/main.py:766`); `core/pipeline/stages/capability_selection.py:53` |
| **Future Canonical Location** | `core/capability/vision/` with `VisionProvider` |

---

## 16. Speech

| Field | Value |
|-------|-------|
| **Purpose** | Convert speech to text (STT) and text to speech (TTS) |
| **Canonical Definition** | `core/capability/models.py:173` — `Capability(id="speech", category="interaction", tags=["voice", "audio", "stt", "tts"])` |
| **Provider** | No dedicated `ExecutionProvider` for speech; handled by `assistant/stt.py` (STT) and `assistant/tts.py` (TTS) |
| **STT Providers** | `FasterWhisperProvider` (default, local), `DeepgramProvider` (cloud, optional), `AzureSpeechProvider` (cloud, optional) — registered at `assistant/stt.py:38-50` |
| **TTS Providers** | `KokoroTTSProvider` (default, local at `assistant/providers/kokoro_tts.py`), `EdgeTTSProvider` (online, optional at `assistant/providers/edge_tts_provider.py`) — handled by `assistant/tts.py:27` `JarvisTTS` |
| **Health** | STT: via `VoiceHealthMonitor`; TTS: via `JarvisTTS` lazy init |
| **Entry Points** | `VoiceEngine.transcribe()` at `voice_pipeline.py:392`; `VoiceEngine.speak()` at `voice_pipeline.py:414`; direct `stt.transcribe()` / `tts.synthesize()` |
| **Dependencies** | `faster-whisper` (STT), `kokoro` (TTS), `sounddevice`, `soundfile` |
| **Permissions** | None defined in capability model |
| **Reachable** | ✅ Always — FasterWhisper + Kokoro are local, always available |
| **Used** | VoiceEngine full pipeline; direct synthetic calls from `core/lifespan.py:260-283` (reminder TTS) |
| **Registered** | In `stt_registry` and `tts` singleton; not in ProviderRegistry |
| **Production Usage** | Voice commands, system announcements, reminder TTS |
| **Agent Usage** | Not used by agent directly |
| **CLI** | No direct CLI |
| **Web** | `core/routes/voice.py` — voice API |
| **TUI** | No direct TUI support |
| **Reality Score** | 8/10 — comprehensive STT/TTS with multiple providers; auto-recovery; caching; real health monitoring through VoiceEngine |
| **Callers** | `VoiceEngine.process_audio()` → `transcribe()` + `speak()`; `core/lifespan.py:276` — `_TTSWrapper` for reminders; `core/lifespan.py:298` — `AlertRouter` speak function |
| **Future Canonical Location** | `core/capability/speech/` — already self-contained, add `ExecutionProvider` |

---

## 17. Scheduling

| Field | Value |
|-------|-------|
| **Purpose** | Schedule, queue, execute, and manage recurring or one-shot tasks, activities, and workflows |
| **Canonical Definition** | Not in `core/capability/models.py` as standalone — scheduling overlaps with `automation` capability |
| **Subsystems** | **4 scheduling systems coexist** with overlapping responsibilities: |
| **Scheduler 1** | `core/scheduler/` — `Scheduler` (tick-based, 5s interval), `AutonomousScheduler` (AI-driven), `DecisionEngine` (what to run), `SchedulerQueue`, `SchedulerRegistry` with 5 executors (research, build, repair, email, benchmark), `SchedulerStore`, `SchedulerMetrics`, `Policies` |
| **Scheduler 2** | `core/cron/scheduler.py` — Traditional cron-like scheduler, started at `core/lifespan.py:707-714` |
| **Scheduler 3** | `reminders/manager.py` — Reminder-specific scheduler, loaded at `core/lifespan.py:249-253` with TTS injection |
| **Scheduler 4** | `core/governance/work_queue.py` — Governance work queue, started at `core/lifespan.py:619-625` |
| **Dependencies** | SQLite (persistence), asyncio (event loop) |
| **Permissions** | `scheduler_*` tools are ADMIN-only |
| **Reachable** | ✅ All 4 always reachable |
| **Used** | Background task execution, cron jobs, reminders, governance work items |
| **Registered** | As lifecycle objects at `core/lifespan.py` lines 707 (cron), 717 (activity scheduler), 249 (reminders), 619 (governance) |
| **Production Usage** | 10 `scheduler_*` tools in TOOL_TAGS (all ALWAYS_AVAILABLE); cron jobs; activity scheduler executors; reminder management |
| **Agent Usage** | `manage_tasks` tool (ADMIN-only); scheduler tools via agent graph |
| **CLI** | `jarvis advanced scheduling` |
| **Web** | `core/routes/scheduler.py` — scheduler REST API |
| **TUI** | No direct TUI support |
| **Reality Score** | 4/10 — **DRIFT**: 4 competing scheduling systems with no unified abstraction; `core/scheduler/` is the most complete but overlaps with cron; reminders are separate; governance is separate; no single capability provider |
| **Callers** | `core/lifespan.py:707` — cron start; `core/lifespan.py:717` — activity scheduler start; `core/lifespan.py:249` — reminders load; `core/lifespan.py:619` — governance work queue start; `core/pipeline.py:56-57` — `infer_capabilities()` maps schedule/automate/cron → "automation" |
| **Future Canonical Location** | `core/capability/scheduling/` — unify 4 schedulers into single `SchedulingProvider` |

---

## Summary Matrix

| Capability | Reality | Provider | Health Check | Registered | Agent Tools | Dedicated API | CLI |
|------------|---------|----------|-------------|------------|-------------|---------------|-----|
| Desktop | 7/10 | DesktopProvider | ✅ Real (pyautogui) | ✅ bootstrap | `computer` | No | `advanced` |
| Browser | 8/10 | BrowserProvider | ✅ Real (playwright) | ✅ bootstrap | 24 `browser_*` | No | Via agent |
| Coding | 8/10 | Forge/ClaudeCode/Codex | ❌ Forge fake | ✅ bootstrap | 12 tool types | No | `code`, `build` |
| Research | 7/10 | ResearchProvider | ✅ Real (FactStore) | ✅ bootstrap | `trigger_research` | `/research` | `understand` |
| Automation | 6/10 | AutomationProvider | ✅ Real (WorkflowEngine) | ✅ bootstrap | 10 `scheduler_*` | `/api/automation` | `advanced` |
| Memory | 5/10 | ❌ None (3-way split) | ❌ No provider | ❌ Stage only | `manage_memory` | `/api/memory` | No |
| Voice | 9/10 | ❌ None (VoiceEngine) | ✅ VoiceHealthMonitor | ❌ app.state | None | `/voice` | No |
| Notifications | 6/10 | MessagingProvider | ✅ Real | ✅ bootstrap | None | No | No |
| Email | 7/10 | EmailProvider (+MCP) | ✅ Real | ✅ bootstrap | 10 MCP email tools | `/email/*` | No |
| Projects | 5/10 | ❌ None (ProjectManager) | ❌ No health | ❌ app.state | None | `/api/build/*` | `build` |
| Build | 7/10 | ForgeProvider | ❌ Forge fake | Via Forge | `build_project` +3 | `/api/build/*` | `build` |
| Search | 7/10 | ❌ None (tools only) | ❌ No provider | ❌ Tools only | `web_search` | No | Via agent |
| Filesystem | 8/10 | ❌ None (tools + plugin) | ❌ No provider | ❌ Tools + plugin | 11 file tools | No | Via agent |
| Terminal | 8/10 | ❌ None (tools only) | ❌ No provider | ❌ Tools only | `bash`/`python`/`shell` | `/ws/terminal` | No |
| Vision | 5/10 | ❌ None (REST only) | ❌ No health | ❌ Routes only | `vision_browser` | `/api/vision/*` | No |
| Speech | 8/10 | ❌ None (stt/tts module) | ✅ VoiceHealthMonitor | ❌ Module only | None | `/voice` | No |
| Scheduling | 4/10 | ❌ None (4-way split) | ❌ No provider | ❌ 4 lifecycle objects | 10 `scheduler_*` | `/scheduler` | `advanced` |

### Key Findings

1. **9 of 17 capabilities have no `ExecutionProvider`** — Memory, Voice, Projects, Search, Filesystem, Terminal, Vision, Speech, Scheduling rely on tools, modules, or REST endpoints instead.

2. **4 scheduling systems coexist** (`core/scheduler/`, `core/cron/`, `reminders/`, `governance/`) with zero unification — worst DRIFT in the system.

3. **ForgeProvider health check is fake** — always returns HEALTHY with no real verification. ClaudeCode and Codex have real health checks (CLI version probes).

4. **Memory has a 3-way split** between `core/long_term_memory/`, `memory/`, and `brain/memory/` — confirmed as DRIFT in Phase 1f.

5. **Voice and Speech are the highest-scoring capabilities** (9/10 and 8/10) — well-implemented with real health monitors, auto-recovery, and per-phase metrics.

6. **Filesystem has 4 tool dispatch paths** — MCP server, direct fallback in `execution.py`, `ForgeProvider.handle_tool()`, and `file_tools_plugin` — all doing the same thing.

7. **The `core/capability/` package exists** with models, registry, graph, composition, and negotiation — but only 10 of 20 built-in capabilities are actually mapped to providers. The infrastructure is ready for unification.

### Recommended Actions (Phase 4)

1. Create `ExecutionProvider` wrappers for Memory, Voice, Projects, Search, Filesystem, Terminal, Vision, Speech, Scheduling.
2. Fix ForgeProvider health check to actually verify the forge agent is reachable.
3. Unify 4 scheduling systems under `core/capability/scheduling/`.
4. Consolidate Memory 3-way split under `core/capability/memory/`.
5. Consolidate Filesystem 4 dispatch paths under `core/capability/filesystem/`.
6. Add capability-gated permissions for all capabilities that lack them (Voice, Speech, Notifications, Projects, Build, Scheduling).
