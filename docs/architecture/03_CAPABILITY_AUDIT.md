# CAPABILITY AUDIT — MJ Architecture

**Generated:** 2026-07-18  
**Scope:** Full capability audit of MJ codebase (READ ONLY)  
**Principle:** Every capability has ONE canonical provider owner.

---

## Capability Inventory

| Capability | Canonical Provider | Status | Reality Score |
|------------|-------------------|--------|---------------|
| **coding** | OllamaProvider (`core/providers/adapters/ollama_provider.py`) | ACTIVE | 9/10 |
| **browser** | BrowserProvider (`core/providers/adapters/browser_provider.py`) | ACTIVE | 9/10 |
| **research** | ResearchProvider (`core/providers/adapters/research_provider.py`) | ACTIVE | 9/10 |
| **automation** | AutomationProvider (`core/providers/adapters/automation_provider.py`) | ACTIVE | 8/10 |
| **messaging** | MessagingProvider | ACTIVE | 7/10 |
| **deployment** | DeploymentProvider | ACTIVE | 7/10 |
| **workspace** | WorkspaceProvider | ACTIVE | 7/10 |
| **github** | GitHubProvider | ACTIVE | 7/10 |
| **email** | EmailProvider | ACTIVE | 7/10 |
| **desktop** | DesktopProvider | ACTIVE | 8/10 |
| **ollama** | OllamaProvider | ACTIVE | 9/10 |
| **claude_code** | ClaudeCodeProvider | ACTIVE | 7/10 |
| **codex** | CodexProvider | ACTIVE | 7/10 |
| **forge** | ForgeProvider | ACTIVE | 8/10 |
| **browser (legacy)** | BrowserProvider (deprecated path) | LEGACY | 3/10 |
| **research (legacy)** | ResearchProvider (deprecated path) | LEGACY | 3/10 |
| **deployment (legacy)** | DeploymentProvider (deprecated path) | LEGACY | 3/10 |
| **forensics** | — | MISSING | 0/10 |
| **forensics:disk** | — | MISSING | 0/10 |
| **forensics:memory** | — | MISSING | 0/10 |
| **forensics:network** | — | MISSING | 0/10 |

---

## Detailed Capability Audit

---

### 1. DESKTOP

**Purpose:** Desktop automation — mouse, keyboard, window, screen capture, app launching.

**Entry Point:** `core/providers/adapters/desktop_provider.py:DesktopProvider`

**Provider:** `DesktopProvider` (`core/providers/adapters/desktop_provider.py`)

**Dependencies:**
- `core.desktop.controller:DesktopController` (singleton `desktop_controller`)
- `core.desktop.screen:ScreenCapture` (singleton `screen_capture`)
- `core.desktop.window:WindowController` (singleton `window_controller`)
- `core.desktop.safety:SafetyManager` (singleton `safety_manager`)

**Permissions Required:**
```python
permissions = (
    "desktop.window.read", "desktop.mouse.move",
    "desktop.mouse.click", "desktop.keyboard.type",
    "desktop.screen.capture",
)
```

**Health Check:** Verifies `pyautogui.size()` works (pyautogui import + screen size).

**Registered Capabilities:** `desktop` (features: mouse_move, mouse_click, mouse_double_click, mouse_scroll, mouse_drag, keyboard_type, keyboard_press, keyboard_hotkey, screen_capture, window_capture, region_capture, window_focus, window_minimize, window_maximize, window_restore, window_close, open_app, open_url)

**Health Check:** Verifies `pyautogui.size()` works.

**Registered Capabilities:** `desktop`

**Reachable:** Yes — registered in `core/providers/bootstrap.py:register_internal_providers()`

**Used By:** 
- Pipeline via `CapabilitySelectionStage` → `ProviderRouter.select("desktop")`
- `automation/pc_automation.py` (legacy, deprecated)
- `core/plugins/automation.py:PCAutomationPlugin` (plugin wrapper)

**Agent Usage:** Via `ProviderRouter.select("desktop")` → `DesktopProvider.execute()`

**CLI:** Not directly exposed

**Web:** Via pipeline → `ProviderRouter.select("desktop")`

**TUI:** Not directly exposed

**Reality Score:** 8/10 — Solid implementation, but legacy `automation/pc_automation.py` duplicates functionality.

**Future Canonical Location:** `core/providers/adapters/desktop_provider.py` (already canonical)

---

### 2. BROWSER

**Purpose:** Web browsing, navigation, search, form filling, clicking, screenshots, tab management.

**Entry Point:** `core/providers/adapters/browser_provider.py:BrowserProvider`

**Provider:** `BrowserProvider` (`core/providers/adapters/browser_provider.py`)

**Dependencies:**
- `core.tools.browser_planner:BrowserPlanner` (FSM-based planning)
- `core.tools.browser_tools` (low-level Playwright operations)
- `core.tools.browser_research` (research workflows)

**Permissions Required:** `("network.http",)`

**Registered Capabilities:** `browser`, `web`, `search`, `navigate`, `browse`

**Health Check:** Calls `core.tools.browser_tools.do_browser_health()`

**Registered Capabilities:** `browser`, `web`, `search`, `navigate`, `browse`

**Reachable:** Yes — registered in `core/providers/bootstrap.py:register_internal_providers()`

**Used By:**
- Pipeline via `CapabilitySelectionStage` → `ProviderRouter.select("browser")`
- `core/tools/browser_research.py` (research workflows)
- `core/tools/browser_planner.py` (planning)

**Agent Usage:** Via `ProviderRouter.select("browser")` → `BrowserProvider.execute()`

**CLI:** Not directly exposed

**Web:** Via pipeline → `ProviderRouter.select("browser")`

**TUI:** Not directly exposed

**Reality Score:** 9/10 — Comprehensive, but legacy `core/tools/browser_fsm.py` + `browser_planner.py` + `browser_tools.py` are fragmented.

**Future Canonical Location:** `core/providers/adapters/browser_provider.py` (already canonical, but internal tools fragmented)

---

### 3. CODING

**Purpose:** Code generation, editing, refactoring, building, testing, scaffolding.

**Entry Point:** Multiple providers:
- `ForgeProvider` (`core/providers/adapters/forge.py`) — primary
- `OllamaProvider` (`core/providers/adapters/ollama_provider.py`) — fallback

**Providers:**
1. **ForgeProvider** (`core/providers/adapters/forge.py`) — primary
   - Uses `core.agents.adapters.forge_adapter.ForgeSubAgent`
   - Capabilities: `coding`, `codegen`, `generate code`, `implement`, `refactor`, `debug code`, `build`, `compile`, `create`, `develop`, `make`, `test`, `testing`, `validate`, `verify`, `check`
   - Languages: Python, Java, Kotlin, JavaScript, TypeScript, Rust, Go
   - Frameworks: Android, Spring, React, Django, Flask, FastAPI
   - Features: scaffold, modify, repair, test_generation

2. **OllamaProvider** — fallback for coding
   - Capabilities: `code`, `coding`, `generate code`
   - Models: qwen2.5-coder, qwen2.5, etc.

**Health Check:** `ForgeProvider` — always HEALTHY (local); `OllamaProvider` — checks Ollama API.

**Registered Capabilities:** `code`, `coding`, `codegen`, `generate code`, `implement`, `refactor`, `debug code`, `build`, `compile`, `create`, `develop`, `make`, `test`, `testing`, `validate`, `verify`, `check`

**Reachable:** Yes — registered in `core/providers/bootstrap.py`

**Used By:** Pipeline via `CapabilitySelectionStage` → `ProviderRouter.select("code")`

**Agent Usage:** Via `ProviderRouter.select("code")` → `ForgeProvider` (primary) or `OllamaProvider` (fallback)

**CLI:** `jarvis code "task"` → `cmd_code` → `stream_agent_loop` → pipeline → `ProviderRouter.select("code")`

**Web:** Via pipeline → `ProviderRouter.select("code")`

**TUI:** Build panel → `build_service` → `forge`

**Reality Score:** 8/10 — Forge is primary, Ollama fallback, but capability naming inconsistent (`code` vs `coding` vs `codegen`).

**Future Canonical Location:** `core/providers/adapters/forge.py` (primary), consolidate `code`/`coding`/`codegen`.

---

### 4. RESEARCH

**Purpose:** Web research, fact extraction, synthesis, report generation.

**Entry Point:** `core/providers/adapters/research_provider.py:ResearchProvider`

**Provider:** `ResearchProvider` (`core/providers/adapters/research_provider.py`)

**Dependencies:**
- `core.research.planner:ResearchPlanner`
- `core.research.storage:FactStore`
- `core.research.synthesizer:FactSynthesizer`
- `core.tools.browser_research:do_browser_research`
- `core.tools.browser_planner:BrowserPlanner`
- `core.fact_extraction.bridge:bridge_batch`

**Health Check:** Verifies `FactStore.count_facts()` works.

**Registered Capabilities:** `research`, `find`, `learn`, `investigate`, `explore`, `analysis`

**Modes:**
- `quick` — `do_browser_research()` with 1 iteration
- `full` — full planner → queries → browser research → fact extraction → synthesis

**Health Check:** Verifies `FactStore.count_facts()` works.

**Reachable:** Yes — registered in `core/providers/bootstrap.py`

**Used By:** Pipeline via `CapabilitySelectionStage` → `ProviderRouter.select("research")`

**Agent Usage:** Via `ProviderRouter.select("research")`

**CLI:** Not directly exposed

**Web:** Via pipeline → `ProviderRouter.select("research")`

**TUI:** Not directly exposed

**Reality Score:** 9/10 — Well-structured, but dual `_quick_research`/`_full_research` paths.

**Future Canonical Location:** `core/providers/adapters/research_provider.py` (already canonical)

---

### 5. AUTOMATION

**Purpose:** Workflow automation, scheduling, orchestration.

**Entry Point:** `core/providers/adapters/automation_provider.py:AutomationProvider`

**Provider:** `AutomationProvider` (`core/providers/adapters/automation_provider.py`)

**Registered Capabilities:** `automation`, `workflow`, `schedule`, `background`, `pipeline`, `orchestration`

**Health Check:** Returns HEALTHY (no external deps)

**Reachable:** Yes — registered in `core/providers/bootstrap.py`

**Used By:** Pipeline via `CapabilitySelectionStage` → `ProviderRouter.select("automation")`

**Agent Usage:** Via `ProviderRouter.select("automation")`

**CLI:** Not directly exposed

**Web:** Via pipeline → `ProviderRouter.select("automation")`

**TUI:** Not directly exposed

**Reality Score:** 8/10 — Capability registered but implementation minimal (no actual automation engine).

**Future Canonical Location:** `core/providers/adapters/automation_provider.py` — needs implementation.

---

### 6. MEMORY

**Purpose:** Unified store/recall across episodic, semantic, task, decision, vector memory.

**Entry Point:** `memory/memory_facade.py:MemoryFacade` (singleton `memory`)

**Owner:** `MemoryFacade` (`memory/memory_facade.py`)

**Backends:**
1. **Episodic:** `memory/episodic_store.py:EpisodicStore` — goal/action/result episodes
2. **Semantic:** `memory/semantic_store.py:SemanticStore` — facts with confidence
3. **Task:** `memory/task_store.py:TaskStore` — action traces (success/failure/duration)
3. **Decision:** `memory/decision_store.py:DecisionStore` — architecture decisions + lessons
4. **Vector:** `memory/vector_store.py` — ChromaDB collections
5. **Tiered:** `memory/tiered_memory.py:tiered_memory` — hot/warm/cold tiering
6. **Mem0:** `memory/mem0_adapter.py:mem0_memory` — mem0 integration

**Health Check:** N/A (facade, no single health)

**Reachable:** Yes — singleton `memory` imported everywhere.

**Used By:**
- Pipeline `MemoryStage` → `memory.store()`, `memory.recall()`
- `brain/UnifiedBrain.py` → `_canonical_memory` alias
- `core/pipeline/stages/memory.py:MemoryStage`
- `core/execution/manager.py:ExecutionManager.record_trace()`
- `core/workflow/engine.py` → `ActivityRecorder`
- `core/pipeline/stages/memory.py:MemoryStage`

**Agent Usage:** Via `memory.store()`, `memory.recall()`, `memory.store_fact()`, etc.

**CLI:** Not directly exposed

**Web:** Via pipeline stages

**TUI:** Not directly exposed

**Reality Score:** 9/10 — Unified facade, 5 backends, but `tiered_memory` and `mem0` overlap.

**Future Canonical Location:** `memory/memory_facade.py` (already canonical)

---

### 7. VOICE

**Purpose:** Wake word → STT → LLM → TTS pipeline.

**Entry Point:** `assistant/voice_pipeline.py:VoiceLoop` (singleton via `core/lifespan.py`)

**Pipeline:** Wake Word → STT → LLM → TTS → Speaker

**Components:**
- **Wake Word:** `assistant/wake_word.py` — WebRTC VAD + Faster-Whisper
- **STT:** `assistant/stt.py` — `STTProtocol`, providers: `faster_whisper`, `deepgram`
- **TTS:** `assistant/tts.py` — `TTSProtocol`, providers: `edge_tts`, `kokoro_tts`, `azure_speech`
- **VoiceLoop:** `assistant/voice_pipeline.py:VoiceLoop` — orchestrates wake→STT→LLM→TTS

**Providers:** `faster_whisper`, `deepgram` (STT); `edge_tts`, `kokoro_tts`, `azure_speech` (TTS)

**Health Check:** STT/TTS provider availability.

**Reachable:** Yes — started in `core/lifespan.py` via `VoiceLoop().start()`

**Used By:** `assistant/voice_pipeline.py:VoiceLoop` → `core/lifespan.py` starts on startup.

**Agent Usage:** Wake word → STT → pipeline → TTS → speaker.

**CLI:** Not directly exposed.

**Web:** Not directly exposed (voice is local).

**TUI:** Not directly exposed.

**Reality Score:** 8/10 — Clean pipeline, but STT/TTS providers not unified under provider registry.

**Future Canonical Location:** `assistant/voice_pipeline.py:VoiceLoop` (already canonical).

---

### 8. NOTIFICATIONS

**Purpose:** Push notifications, email digests, WebSocket updates.

**Entry Point:** `notifications/notifier.py:SupervisorNotifier` (singleton `notifier`)

**Owner:** `SupervisorNotifier` (`notifications/notifier.py`)

**Channels:**
- Event log write (`~/.jarvis/projects/{project}/events.jsonl`)
- Email (SMTP) for `build_completed`, `task_failed`
- Push: ntfy.sh + Pushover for `build_completed`, `build_started`, `task_failed`
- WebSocket client registry (`register_ws`, `unregister_ws`)

**Health Check:** N/A (passive)

**Reachable:** Yes — wired in `core/lifespan.py`: `supervisor.on_notify(notifier.notify)`

**Used By:** `core/lifespan.py` wires `supervisor.on_notify(notifier.notify)`

**Agent Usage:** Via `supervisor.on_notify()` → `notifier.notify()`

**CLI:** Not directly exposed.

**Web:** Via pipeline → `NotificationStage` → `SupervisorNotifier`.

**TUI:** Not directly exposed.

**Reality Score:** 8/10 — Clean, but channels hardcoded.

**Future Canonical Location:** `notifications/notifier.py` (already canonical).

---

### 9. EMAIL

**Purpose:** Send/receive emails.

**Entry Point:** `core/providers/adapters/email_provider.py:EmailProvider`

**Provider:** `EmailProvider` (`core/providers/adapters/email_provider.py`)

**Capabilities:** `email`, `send_email`, `compose_email`, `email_attachments`

**Health Check:** Returns DOWN (no SMTP configured by default).

**Reachable:** Yes — registered in `core/providers/bootstrap.py`.

**Used By:** Pipeline via `ProviderRouter.select("email")`.

**Agent Usage:** Via `ProviderRouter.select("email")`.

**CLI:** Not directly exposed.

**Web:** Via pipeline → `ProviderRouter.select("email")`.

**TUI:** Not directly exposed.

**Reality Score:** 6/10 — Provider exists but health check fails without SMTP config.

**Future Canonical Location:** `core/providers/adapters/email_provider.py`.

---

### 10. PROJECTS

**Purpose:** Project lifecycle, build queue, state management.

**Entry Point:** `core/project_manager.py:ProjectManager` (singleton `project_manager`)

**Owner:** `ProjectManager` (`core/project_manager.py`)

**Components:**
- `core/project_state.py:ProjectState` — state management
- `core/build/service.py:build_service` — build orchestration
- `core/routes/build/operations_router.py` — REST API

**Health Check:** N/A (manager, not provider).

**Reachable:** Yes — singleton `project_manager` used in `core/lifespan.py` and `core/routes/build/`.

**Used By:** `core/lifespan.py` starts `project_manager.process_queue()`, `core/routes/build/operations_router.py`.

**Agent Usage:** Via `build_service.queue_build()`, `build_service.cancel()`, etc.

**CLI:** `jarvis build "goal"` → `cmd_build` → `build_service.queue_build()`.

**Web:** `POST /api/build` → `core/routes/build/operations_router.py`.

**TUI:** `jarvis_tui.py` BuildPanel → `build_service.list_all()`.

**Reality Score:** 9/10 — Well-structured, separate build service.

**Future Canonical Location:** `core/project_manager.py` + `core/build/service.py` (already canonical).

---

### 11. BUILD

**Purpose:** Autonomous build with auto-repair.

**Entry Point:** `core/build/service.py:build_service` + `core/tools/automated_build.py`

**Owner:** `build_service` (`core/build/service.py`)

**Components:**
- `core/tools/automated_build.py` — build + auto-repair loop
- `core/tools/build_tools.py` — build orchestration
- `core/tools/implementations.py` — `build_project`, `compile_java`, `run_tests`
- `core/tools/cookbook_tools.py` — pattern-based code generation

**Health Check:** N/A.

**Reachable:** Yes — `build_service` singleton.

**Used By:** `core/lifespan.py` starts `build_service.process_queue()`.

**Agent Usage:** Via `build_service.queue_build()`, `resume()`, `cancel()`.

**CLI:** `jarvis build "goal"` → `cmd_build` → `build_service.queue_build()`.

**Web:** `POST /api/build` → `core/routes/build/operations_router.py`.

**TUI:** BuildPanel → `build_service.list_all()`.

**Reality Score:** 9/10 — Well-structured, auto-repair loop.

**Future Canonical Location:** `core/build/service.py` + `core/tools/automated_build.py` (already canonical).

---

### 12. SEARCH

**Purpose:** Web search, code search, semantic search.

**Entry Points:**
- **Web Search:** `core/tools/browser_tools.py` → `do_browser_search()`, `do_browser_fill()`, etc.
- **Code Search:** `core/tools/index.py` → `get_tool_index()` + `search_codebase()`
- **Semantic Search:** `memory/memory_facade.py` → `memory.search_all()`, `memory.search_vectors()`
- **Web Search Tool:** `core/tools/search_tool.py:search()` → falls back to `search_fallback.py`

**Providers:**
- **Browser:** `BrowserProvider` (capability `browser`, `web`, `search`, `navigate`, `browse`)
- **Research:** `ResearchProvider` (capability `research`, `find`, `search`)
- **Memory:** `MemoryFacade.search_vectors()`, `memory.recall()`

**Health Check:** Browser health via `BrowserProvider.health()`.

**Reachable:** Yes — via pipeline stages `ContextRetrievalStage` + `KnowledgeStage`.

**Used By:** Pipeline stages `ContextRetrievalStage` + `KnowledgeStage`.

**Agent Usage:** Via pipeline stages.

**CLI:** `jarvis chat "search for..."` → pipeline.

**Web:** Via pipeline.

**TUI:** Via pipeline.

**Reality Score:** 8/10 — Multiple search paths, but unified under pipeline.

**Future Canonical Location:** `core/tools/search_tool.py` + pipeline stages (already canonical).

---

### 13. FILESYSTEM

**Purpose:** File read/write/list/delete/search.

**Entry Point:** `core/tools/implementations.py` — `read_file`, `write_file`, `edit_file_text`, `create_directory`, `list_directory`, `delete_file`, `run_command`, `compile_java`, `run_tests`, `build_project`.

**Also:** `core/tools/execution/handlers.py` — `edit_file`, `edit_file_text`, `replace`, etc.

**Provider:** None (direct tool execution via `execute_tool_block()`).

**Health Check:** N/A.

**Reachable:** Yes — direct tool execution via `execute_tool_block()`.

**Used By:** Pipeline `ExecutionStage` → `ToolExecutor` → `execute_tool_block()`.

**Agent Usage:** Via pipeline `ExecutionStage` → `ToolExecutor`.

**CLI:** `jarvis code "edit file..."` → pipeline.

**Web:** Via pipeline.

**TUI:** Via pipeline.

**Reality Score:** 9/10 — Direct tool execution, no provider indirection needed.

**Future Canonical Location:** `core/tools/implementations.py` (already canonical).

---

### 14. TERMINAL

**Purpose:** Shell command execution, persistent shells.

**Entry Point:** `core/tools/implementations.py` → `run_command()`, `persistent_shell.py`

**Also:** `core/tools/execution/handlers.py` → `bash` tool, `python` tool.

**Provider:** None (direct tool execution).

**Health Check:** N/A.

**Reachable:** Yes — `execute_tool_block()` handles `bash`, `python`, `run_command`.

**Used By:** Pipeline `ExecutionStage` → `ToolExecutor`.

**Agent Usage:** Via pipeline.

**CLI:** `jarvis code "run pytest"` → pipeline.

**Web:** Via pipeline.

**TUI:** Via pipeline.

**Reality Score:** 9/10 — Direct execution, well-integrated.

**Future Canonical Location:** `core/tools/implementations.py` (already canonical).

---

### 15. VISION

**Purpose:** Image understanding, OCR, screen analysis.

**Entry Point:** `OllamaProvider` (capability `vision`) + `VisionProvider` (if exists).

**Providers:**
1. **OllamaProvider** — capability `vision`, uses `moondream:latest` model.
2. **BrowserProvider** — `vision` capability via browser screenshots + analysis.

**Health Check:** OllamaProvider checks `/api/tags`; Vision model availability depends on model installed.

**Reachable:** Yes — `ProviderRouter.select("vision")` → `OllamaProvider`.

**Used By:** Pipeline `CapabilitySelectionStage` → `ProviderRouter.select("vision")`.

**Agent Usage:** Via `ProviderRouter.select("vision")`.

**CLI:** Not directly exposed.

**Web:** Via pipeline.

**TUI:** Not directly exposed.

**Reality Score:** 7/10 — Only Ollama provider, no dedicated vision provider.

**Future Canonical Location:** Need dedicated `VisionProvider` adapter.

---

### 16. SPEECH

**Purpose:** STT (speech-to-text) + TTS (text-to-speech).

**Entry Point:** `assistant/voice_pipeline.py` → `VoiceLoop`.

**Components:**
- **STT:** `assistant/stt.py` — `STTProtocol`, providers: `faster_whisper`, `deepgram`
- **TTS:** `assistant/tts.py` — `TTSProtocol`, providers: `edge_tts`, `kokoro_tts`, `azure_speech`
- **Wake Word:** `assistant/wake_word.py` — WebRTC VAD + Faster-Whisper

**Providers:** STT/TTS providers registered in `assistant/providers/`.

**Health Check:** STT/TTS provider availability.

**Reachable:** Yes — `VoiceLoop` started in `core/lifespan.py`.

**Used By:** `assistant/voice_pipeline.py:VoiceLoop` → `core/lifespan.py`.

**Agent Usage:** Wake word → STT → pipeline → TTS → speaker.

**CLI:** Not directly exposed.

**Web:** Not directly exposed.

**TUI:** Not directly exposed.

**Reality Score:** 8/10 — Clean pipeline, but providers not under `ProviderRegistry`.

**Future Canonical Location:** `assistant/voice_pipeline.py:VoiceLoop` (already canonical), but providers should register with `ProviderRegistry`.

---

### 17. SCHEDULING

**Purpose:** Recurring jobs, cron, autonomous activity scheduling.

**Entry Points:**
1. **Cron:** `core/cron.py:scheduler` — cron-style recurring jobs (`add(name, schedule, func, params)`).
2. **Activity Scheduler:** `core/scheduler/scheduler.py:Scheduler` — tick-based activity scheduler with worker pool.

**Components:**
- **Cron Scheduler:** `core/cron.py:scheduler` — `add(name, schedule, func, params)`, background task.
- **Activity Scheduler:** `core/scheduler/scheduler.py:Scheduler` — tick-based (5s), worker pool (3), executors: `research_executor`, `build_executor`, `repair_executor`, `email_executor`, `benchmark_executor`.

**Health Check:** N/A.

**Reachable:** Yes — started in `core/lifespan.py`.

**Used By:** `core/lifespan.py` starts both schedulers.

**Agent Usage:** Indirect via scheduled tasks.

**CLI:** Not directly exposed.

**Web:** Not directly exposed.

**TUI:** Not directly exposed.

**Reality Score:** 8/10 — Two schedulers, slightly overlapping.

**Future Canonical Location:** Consolidate into single `Scheduler` with cron + activity modes.

---

## Cross-Capability Summary

| Capability | Provider | Status | Reality Score | Future Location |
|------------|----------|--------|---------------|-----------------|
| coding | ForgeProvider / OllamaProvider | ACTIVE | 8/10 | core/coding/ |
| browser | BrowserProvider | ACTIVE | 9/10 | core/providers/adapters/browser_provider.py |
| research | ResearchProvider | ACTIVE | 9/10 | core/providers/adapters/research_provider.py |
| automation | AutomationProvider | ACTIVE | 8/10 | core/providers/adapters/automation_provider.py |
| desktop | DesktopProvider | ACTIVE | 8/10 | core/providers/adapters/desktop_provider.py |
| ollama | OllamaProvider | ACTIVE | 9/10 | core/providers/adapters/ollama_provider.py |
| forge | ForgeProvider | ACTIVE | 8/10 | core/providers/adapters/forge.py |
| research (legacy) | ResearchProvider | LEGACY | 3/10 | — |
| browser (legacy) | BrowserProvider | LEGACY | 3/10 | — |
| deployment | DeploymentProvider | ACTIVE | 7/10 | core/providers/adapters/deployment_provider.py |
| email | EmailProvider | ACTIVE | 6/10 | core/providers/adapters/email_provider.py |
| desktop | DesktopProvider | ACTIVE | 8/10 | core/providers/adapters/desktop_provider.py |
| ollama | OllamaProvider | ACTIVE | 9/10 | core/providers/adapters/ollama_provider.py |
| forge | ForgeProvider | ACTIVE | 8/10 | core/providers/adapters/forge.py |
| research | ResearchProvider | ACTIVE | 9/10 | core/providers/adapters/research_provider.py |
| automation | AutomationProvider | ACTIVE | 8/10 | core/providers/adapters/automation_provider.py |
| memory | MemoryFacade | ACTIVE | 9/10 | memory/memory_facade.py |
| voice | VoiceLoop | ACTIVE | 8/10 | assistant/voice_pipeline.py |
| notifications | SupervisorNotifier | ACTIVE | 8/10 | notifications/notifier.py |
| email | EmailProvider | ACTIVE | 6/10 | core/providers/adapters/email_provider.py |
| projects | ProjectManager | ACTIVE | 9/10 | core/project_manager.py |
| build | build_service | ACTIVE | 9/10 | core/build/service.py |
| search | Multi (Browser/Research/Memory) | ACTIVE | 8/10 | core/tools/search_tool.py |
| filesystem | Direct tools | ACTIVE | 9/10 | core/tools/implementations.py |
| terminal | Direct tools | ACTIVE | 9/10 | core/tools/implementations.py |
| vision | OllamaProvider | ACTIVE | 7/10 | needs VisionProvider |
| speech | VoiceLoop | ACTIVE | 8/10 | assistant/voice_pipeline.py |
| scheduling | Scheduler + Cron | ACTIVE | 8/10 | core/scheduler/ + core/cron.py |

---

## Missing Capabilities (Gaps)

| Capability | Status | Needed? |
|------------|--------|---------|
| forensics | MISSING | Yes |
| forensics:disk | MISSING | Yes |
| forensics:memory | MISSING | Yes |
| forensics:network | MISSING | Yes |
| backup | MISSING | Yes |
| restore | MISSING | Yes |
| monitoring | MISSING | Partial (monitors/) |
| alerting | MISSING | Partial (notifications) |
| logging | PARTIAL | Partial (observability/logging.py) |
| metrics | PARTIAL | Partial (observability/metrics.py) |
| tracing | MISSING | Yes |
| profiling | MISSING | Yes |
| debugging | PARTIAL | Partial (debugger.py) |
| packaging | MISSING | Yes |
| distribution | MISSING | Yes |
| containerization | MISSING | Yes |
| orchestration | PARTIAL | Partial (automation) |
| secrets | PARTIAL | Partial (secret_storage.py) |
| key_management | MISSING | Yes |
| certificates | MISSING | Yes |
| identity | PARTIAL | Partial (auth.py) |
| authorization | PARTIAL | Partial (authz/) |
| audit | PARTIAL | Partial (audit_log.py) |
| compliance | MISSING | Yes |

---

## Canonical Locations Summary

| Capability | Canonical Location |
|------------|-------------------|
| Pipeline | `core/pipeline/pipeline.py` |
| Request Processing | `core/pipeline/pipeline.py:process_message()` |
| Planning | `core/planner/executor.py:PlannerExecutor` |
| Execution | `core/tools/executor.py:ToolExecutor` |
| Workflow | `core/workflow/engine.py:WorkflowEngine` |
| Scheduler | `core/scheduler/scheduler.py:Scheduler` |
| Desktop | `core/desktop/controller.py:DesktopController` |
| Browser | `core/providers/adapters/browser_provider.py` |
| Coding | `core/providers/adapters/forge.py` (primary) |
| Research | `core/providers/adapters/research_provider.py` |
| Memory | `memory/memory_facade.py:MemoryFacade` |
| Notifications | `notifications/notifier.py:SupervisorNotifier` |
| Configuration | `core/configuration/service.py:ConfigurationService` |
| Providers | `core/providers/router.py:ProviderRouter` |
| Capabilities | `core/capability/registry.py:CapabilityRegistry` |
| Safety | `core/desktop/safety.py:SafetyManager` + `core/control/kill_switch.py` |
| Permissions | `core/permission/manager.py:PermissionManager` |
| Logging | `core/observability/logging.py` + `utils/logger.py` |
| Recovery | `core/workflow/recovery.py` + `core/self_healing.py` |
| Plugin System | `core/plugins/loader.py:PluginLoader` + `core/plugins/registry.py:PluginRegistry` |
| Voice | `assistant/voice_pipeline.py:VoiceLoop` |
| Automation | `core/plugins/automation.py:PCAutomationPlugin` |
| EventBus | `core/event_bus.py:global_event_bus` |
| History | `core/history/service.py:HistoryService` |
| Projects | `core/project_manager.py:ProjectManager` |
| Rules | `core/governance/` |

---

## Reality Score Summary

| Score | Count | Capabilities |
|-------|-------|--------------|
| 9-10/10 | 8 | desktop, browser, ollama, forge, research, memory, build, projects |
| 8/10 | 7 | coding, automation, desktop, voice, notifications, scheduling, voice |
| 7/10 | 3 | vision, email, claude_code, codex |
| 6/10 | 2 | email, automation |
| 5/10 | 0 | — |
| <5/10 | 0 | — |
| MISSING | 15+ | forensics, backup, monitoring, alerting, tracing, profiling, packaging, distribution, containerization, orchestration, secrets, keys, certificates, identity, authorization, audit, compliance, backup, restore, monitoring, alerting, logging, metrics, tracing, profiling, debugging, packaging, distribution, containerization, orchestration |

---

## Recommendations

1. **Consolidate Browser** — Merge `browser_tools.py`, `browser_fsm.py`, `browser_planner.py` into single `browser_provider.py`.

2. **Unify Coding** — Move `core/tools/implementations.py` + `cookbook_tools.py` + `build_tools.py` into `core/coding/`.

3. **Remove Legacy** — Delete `core/graph/`, `core/agent_loop.py` fallback, `core/llm_calls.py`, `automation/pc_automation.py`, `api/agent_routes.py`.

4. **Add VisionProvider** — Create dedicated `VisionProvider` adapter.

5. **Unify Speech** — Register STT/TTS providers with `ProviderRegistry`.

6. **Consolidate Schedulers** — Merge `core/cron.py` + `core/scheduler/scheduler.py`.

7. **Register Voice Providers** — Register STT/TTS providers with `ProviderRegistry`.

8. **Unify Event Systems** — Replace `WorkflowEvent` with `EventBus` events.

9. **Add Missing Capabilities** — Prioritize: forensics, backup/restore, monitoring, alerting, tracing, packaging, distribution, containerization, secrets management, key management, certificates, compliance.

---

*End of Capability Audit*