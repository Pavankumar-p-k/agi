# 03 — Universal Capability Audit

> **Phase 3 of Source-of-Truth Audit.**  
> Every capability traced from definition to execution.  
> Status: **DRIFT** / **DUPLICATE** / **CORRECT** / **DORMANT** with Reality Score.

---

## Table of Contents

1. [Desktop](#1-desktop)
2. [Browser](#2-browser)
3. [Coding](#3-coding)
4. [Build](#4-build)
5. [Research](#5-research)
6. [Memory](#6-memory)
7. [Voice](#7-voice)
8. [Speech](#8-speech)
9. [Notifications](#9-notifications)
10. [Email](#10-email)
11. [Search](#11-search)
12. [Filesystem](#12-filesystem)
13. [Terminal](#13-terminal)
14. [Vision](#14-vision)
15. [Scheduling](#15-scheduling)
16. [Projects](#16-projects)
17. [Automation](#17-automation)

---

## 1. Desktop

| Field | Value |
|-------|-------|
| **Purpose** | Automate local PC: mouse, keyboard, screenshots, window management, app launching |
| **Entry Point** | `core/desktop/controller.py:31` `DesktopController` — `move_mouse()`, `click()`, `type_text()`, `press_key()`, `hotkey()`, `open_url()`, `launch_app()` |
| **Entry Point** | `core/desktop/screen.py:42` `ScreenCapture` — `capture_screen()`, `capture_window()`, `capture_region()` |
| **Entry Point** | `core/desktop/window.py:37` `WindowController` — `focus()`, `minimize()`, `maximize()`, `restore()`, `close()` |
| **Entry Point** | `core/desktop/safety.py:121` `SafetyManager.check()` — gates every action |
| **Entry Point** | `core/vision_agent.py:177` `VisionAgent.run()` — alternative vision-based desktop control |
| **Provider** | `DesktopProvider` (`core/providers/adapters/desktop_provider.py:21`) — wraps DesktopController + ScreenCapture + WindowController. `provider_id: "desktop"`. Registered in `bootstrap.py:23,33`. |
| **Dependencies** | `pyautogui`, `mss`, `PIL`, `pygetwindow`, `webbrowser` |
| **Permissions** | `SafetyManager`: emergency stop, forbidden regions, mouse speed limit (2000 px/s), typing rate limit (30 char/s), typing length limit (500 chars), screenshot rate limit (10/min), click rate limit (60/min), cooldown (0.05s), active window validation |
| **Health** | `DesktopProvider.health()` at `provider.py:48` — calls `pyautogui.size()` |
| **Reachable** | REST `POST /computer` (`core/routes/control.py:24`), MCP `computer` tool (`mcp/server.py:326`), `VisionAgent`, `ComputerAgent` |
| **Used** | `VisionAgent` (direct pyautogui, bypasses DesktopProvider), `ComputerAgent` (pc_agent), `mcp/server.py` fallback, `core/routes/control.py` |
| **Registered** | ❌ NOT in `implementations.py`. ❌ NOT in `tool_registry (brain)`. ❌ NOT in `handlers.py`. MCP `computer` uses `pc_agent/ComputerAgent`, NOT `DesktopController`. |
| **Production Usage** | Medium — `VisionAgent` active but bypasses safety layer. `DesktopProvider` exists but is not wired into tool dispatch. |
| **Agent Usage** | `VisionAgent` (direct), `ComputerAgent` (experimental/pc_agent) |
| **CLI** | None |
| **Web** | `POST /computer` (`core/routes/control.py:24`) |
| **TUI** | None |
| **Callers** | `core/desktop/controller.py`, `screen.py`, `window.py`, `safety.py`, `replay.py`; `providers/adapters/desktop_provider.py`; `core/vision_agent.py`; `pc_agent/computer_agent.py`; `mcp/server.py`; `core/routes/control.py` |
| **Reality Score** | 4/10 |
| **Status** | `DRIFT` — three competing implementations (`core/desktop/`, `pc_agent/`, `VisionAgent`). `VisionAgent` bypasses SafetyManager. Provider not wired into tool dispatch. |
| **Future Canonical** | `core/desktop/controller.py` `DesktopController` — consolidate all desktop control, deprecate `pc_agent/` and `VisionAgent` fallback |

---

## 2. Browser

| Field | Value |
|-------|-------|
| **Purpose** | Full browser automation: navigate, click, fill, snapshot, screenshot, tab management, shadow DOM, JavaScript evaluation, multi-page research |
| **Entry Point** | `core/tools/browser_tools.py` — 22 functions: `do_browser_navigate()` (line 102), `do_browser_click()` (249), `do_browser_fill()` (281), `do_browser_snapshot()` (389), `do_browser_screenshot()` (492), `do_browser_evaluate()` (525), `do_browser_find()` (127), `do_browser_find_interactive()` (149), `do_browser_press()` (343), `do_browser_get_url()` (472), `do_browser_get_title()` (482), `do_browser_current_state()` (505), `do_browser_get_history()` (537), `do_browser_list_tabs()` (551), `do_browser_switch_tab()` (560), `do_browser_new_tab()` (575), `do_browser_close_tab()` (590), `do_browser_wait_visible()` (604), `do_browser_wait_text()` (620), `do_browser_wait_interactive()` (636), `do_browser_shadow_query()` (682), `do_browser_health()` (726) |
| **Entry Point** | `core/browser_manager.py:154` `BrowserManager.instance()` — Playwright session lifecycle |
| **Entry Point** | `core/tools/browser_planner.py:1031` `BrowserPlanner.pre_plan()` — intelligent pre/post planning with 9 rules |
| **Entry Point** | `core/tools/browser_fsm.py:289` `BrowserFSM` — deterministic state machine alternative |
| **Entry Point** | `core/tools/browser_research.py:32` `do_browser_research()` — multi-page research pipeline |
| **Entry Point** | `core/agents/browser_agent.py:16` `BrowserAgent.execute()` — agent wrapper |
| **Provider** | `BrowserProvider` (`core/providers/adapters/browser_provider.py:42`). `provider_id: "browser"`. Registered in `bootstrap.py:15,25`. |
| **Dependencies** | `playwright` (async), `base64`, `json`. Session storage: `data/browser_sessions/` JSON files. |
| **Permissions** | URL validation (`_validate_url` at `browser_tools.py:13`): blocks `file://`, `chrome://`, `edge://`, `about:`, `javascript:`, `data:` for non-admin. `PolicyEngine` for tool availability. `check_rbac` / `check_approval` in `authorization.py`. No `SafetyManager`. |
| **Health** | `BrowserProvider.health()` (`provider.py:69`) + `do_browser_health()` (`browser_tools.py:726`) — verifies Playwright connection |
| **Reachable** | REST `POST /api/browser` (`core/routes/operations.py:586`), `POST /browser/open` etc. (`automation/routes.py:113-145`), MCP `browser_navigate` (`mcp/server.py:314`), `BrowserAgent`, `ResearchAgent`, pipeline stages |
| **Used** | Extensive — `handlers.py` dispatches all 22 tools, `research_provider.py` uses `do_browser_research`, `browser_planner.py` injects tool blocks, `scheduler/registry.py` registers research task, 25+ acceptance tests |
| **Registered** | ✅ 22 tools in `implementations.py` (`__all__` lines 79-102, 151-172). ✅ in `TOOL_TAGS` (`_constants.py:49-57`). ✅ in `handlers.py` (line 594+). MCP: `browser_navigate` only. ❌ NOT in `tool_registry (brain)`. |
| **Production Usage** | High — heavily tested (25+ acceptance scenarios), used by ResearchProvider, BrowserAgent, and research pipeline |
| **Agent Usage** | `BrowserAgent` (navigate+snapshot), `ResearchAgent` (via `do_browser_research` + `ResearchProvider`) |
| **CLI** | None |
| **Web** | `POST /api/browser` (`operations.py:586`), `POST /browser/open/google/youtube/maps` (`automation/routes.py`), MCP WS bridge |
| **TUI** | None |
| **Callers** | 18+ files: `browser_tools.py`, `browser_planner.py`, `browser_fsm.py`, `browser_research.py`, `implementations.py`, `_constants.py`, `index.py`, `handlers.py`, `browser_provider.py`, `research_provider.py`, `browser_agent.py`, `browser_manager.py`, `scheduler/registry.py`, `mcp/server.py`, `automation/routes.py`, `operations.py`, tests |
| **Reality Score** | 9/10 |
| **Status** | `CORRECT` — single architecture, 22 tools, planner+FSM, provider adapter, extensive tests |
| **Future Canonical** | `core/browser_manager.py` (session lifecycle) + `core/tools/browser_tools.py` (atomic operations) |

---

## 3. Coding (Editing + Providers)

| Field | Value |
|-------|-------|
| **Purpose** | Code file editing (find/replace, unified diff, batch, refactor, undo) + code generation via 3 providers (Forge, Claude Code, Codex) |
| **Entry Point** | `core/tools/execution/edit_tools.py:25` `do_edit_file()` — find/replace edits with backup |
| **Entry Point** | `core/tools/execution/edit_tools.py:196` `do_refactor()` — code refactoring |
| **Entry Point** | `core/tools/execution/edit_tools.py:276` `do_undo_edit_file()` — undo last edit |
| **Entry Point** | `core/tools/execution/edit_tools.py:307` `do_batch_edit_file()` — glob-pattern batch edits |
| **Entry Point** | `core/providers/adapters/forge.py:92` `ForgeProvider.execute()` — internal coding agent |
| **Entry Point** | `core/providers/adapters/claude_code.py:84` `ClaudeCodeProvider.execute()` — external Claude CLI |
| **Entry Point** | `core/providers/adapters/codex.py:79` `CodexProvider.execute()` — external Codex CLI |
| **Provider** | Three providers: `ForgeProvider` (`forge`, priority 10), `ClaudeCodeProvider` (`claude_code`, priority 50), `CodexProvider` (`codex`, priority 60). All registered in `bootstrap.py:14-48`. All three claim `coding`, `codegen`, `implement`, `refactor`, `debug`, `test` capabilities. |
| **Dependencies** | `difflib`, `hashlib`, `ast`, `ruff` (Python auto-format), `prettier` (JS/TS/CSS/JSON), `subprocess` (Claude/Codex CLIs), `core/agents/_legacy/forge/ForgeAgent` |
| **Permissions** | Path allowlist (`_resolve_tool_path` in `security.py`): restricts to `DATA_DIR`, `/tmp`, configured roots. Blocks `.ssh`, `.gnupg`, `.gitconfig`, `.env`, `.netrc`, `authorized_keys`, `id_rsa`. `PolicyEngine` for tool availability. `check_rbac` / `check_approval`. |
| **Health** | `ForgeProvider.health()` — always HEALTHY (no-op). `ClaudeCodeProvider.health()` — runs `claude --version`. `CodexProvider.health()` — runs `codex --version`. |
| **Reachable** | Via `execute_tool_block` from any agent/pipeline. REST: None directly. MCP: Not registered. Agent: all agents can call. CLI: None. |
| **Used** | `handlers.py` dispatches all 4 edit tools (lines 327-339). `tool_registry (brain)` registers `edit_file` (line 80). `index.py` lists them. `schemas.py` and `schemas_document.py` define schemas. |
| **Registered** | ❌ Edit tools NOT exported from `implementations.py` (only `do_edit_document` from document_tools is). ✅ `edit_file`, `undo_edit_file`, `batch_edit_file`, `refactor` in `TOOL_TAGS` (`_constants.py:23,45-46`). ✅ `edit_file` in `tool_registry (brain)`. ✅ Dispatch entries in `handlers.py`. ❌ NOT in MCP. |
| **Production Usage** | High — edit tools are core capability. ForgeProvider is the primary coding provider. Claude Code and Codex are fallback (require external CLIs). |
| **Agent Usage** | All agents can call edit tools via `execute_tool_block`. `BuildAgent` uses file operations. |
| **CLI** | None |
| **Web** | None directly (accessed via tool dispatch) |
| **TUI** | None |
| **Callers** | `edit_tools.py`, `handlers.py`, `implementations.py`, `_constants.py`, `index.py`, `parsing.py`, `tool_registry (brain)`, `forge.py`, `claude_code.py`, `codex.py`, `schemas.py`, `schemas_document.py`, tests |
| **Reality Score** | 7/10 |
| **Status** | `DUPLICATE` — edit tools not in `implementations.py` (only document tools). Three coding providers overlap on same capabilities. Forge is internal default; Claude Code and Codex are preferred when available (router selects). |
| **Future Canonical** | `core/tools/execution/edit_tools.py` for editing. `core/providers/adapters/forge.py` as default coding provider. Register edit tools in `implementations.py`. |

---

## 4. Build

| Field | Value |
|-------|-------|
| **Purpose** | Autonomous software build pipeline: plan → generate → verify gates → build (error classification + targeted repair) → test → verify → runtime validation → completion tracking |
| **Entry Point** | `brain/automation/loop.py:1111` `AutomationLoop._build_project()` — core engine with 8 phases |
| **Entry Point** | `brain/automation/loop.py:430` `classify_error()` — 27-pattern regex error classification |
| **Entry Point** | `brain/automation/loop.py:474` `apply_fix()` — applies classified fixes (add_import, create_file, fix_manifest, etc.) |
| **Entry Point** | `brain/automation/loop.py:608` `verify_gates()` — static verification checks |
| **Entry Point** | `core/tools/build_tools.py:48` `do_build_project()` — simpler wrapper |
| **Entry Point** | `core/tools/automated_build.py:364` `do_automated_build()` — newer wrapper with ActivityGraph + CalibrationStore + KnowledgeStore |
| **Entry Point** | `core/tools/build_tools.py:71` `do_repair_project()` — targeted repair |
| **Entry Point** | `core/tools/build_tools.py:88` `do_run_tests()` — test execution |
| **Entry Point** | `core/tools/build_tools.py:106` `do_runtime_validate()` — runtime validation |
| **Entry Point** | `core/agents/build_agent.py:16` `BuildAgent.execute()` — agent wrapper |
| **Entry Point** | `core/agents/test_agent.py:16` `TestAgent.execute()` — test agent wrapper |
| **Provider** | `AutomationProvider` (`core/providers/adapters/automation_provider.py:20`). `provider_id: "automation"`. Registered in `bootstrap.py:16,26`. |
| **Dependencies** | `ast`, `re`, `subprocess`, `shutil`, `fnmatch`, `hashlib`, `brain/automation/loop.py` (AutomationLoop, FailureMemory, ArchitecturalMemory, RequirementTracker), `core/planner/` (Plan, UnifiedStore), `core/activity/*`, `core/long_term_memory/*`, `core/belief/*`, `core/llm_router` |
| **Permissions** | Path allowlists via `_resolve_tool_path`. `PolicyEngine` for tool availability. Gradle/gradlew detection validates build tools exist. Error classification does not check permissions. |
| **Health** | `AutomationProvider.health()` at `provider.py:46` — tries to instantiate `WorkflowEngine` |
| **Reachable** | REST `POST /build/overnight` (`core/routes/cowork.py:110`), `GET /status/{build_id}` (`supervisor_routes.py:74`), `POST /cancel/{build_id}` (`supervisor_routes.py:98`), `BuildAgent`, `TestAgent`, pipeline stages |
| **Used** | `handlers.py` dispatches `do_build_project` (line 787) + `do_automated_build` (line 1159). `build_agent.py` calls `build_project`. `test_agent.py` calls `run_tests` + `runtime_validate`. 6 benchmark files mock `do_build_project`. |
| **Registered** | ✅ 5 tools in `implementations.py` (lines 103-109, 173): `do_build_project`, `do_repair_project`, `do_run_tests`, `do_runtime_validate`, `cancel_build`. ✅ in `TOOL_TAGS` (`_constants.py:64`). ✅ in `handlers.py`. ❌ NOT in `tool_registry (brain)`. ❌ NOT in MCP. |
| **Production Usage** | High — AutomationLoop is the core build engine with 10 MAX_REPAIR_ATTEMPTS, 27 error patterns, FailureMemory, ArchitecturalMemory, plan evolution. 6 benchmarks depend on it. `do_automated_build` is newer with richer post-execution recording. |
| **Agent Usage** | `BuildAgent` (`do_build_project`), `TestAgent` (`do_run_tests` + `do_runtime_validate`) |
| **CLI** | None |
| **Web** | `POST /build/overnight` (`cowork.py:110`), `GET /status/{id}` (`supervisor_routes.py:74`), `POST /cancel/{id}` (`supervisor_routes.py:98`) |
| **TUI** | None |
| **Callers** | `loop.py`, `project_tool.py`, `build_tools.py`, `automated_build.py`, `implementations.py`, `_constants.py`, `handlers.py`, `build_agent.py`, `test_agent.py`, `cowork.py`, `supervisor_routes.py`, `build_benchmark.py`, `automation_provider.py`, 6 benchmark files |
| **Reality Score** | 7/10 |
| **Status** | `DUPLICATE` — dual wrapper layer (`build_tools.py` vs `automated_build.py`) around same `AutomationLoop` engine. Both ACTIVE. `automated_build.py` is newer/richer. |
| **Future Canonical** | `core/tools/automated_build.py` `do_automated_build` — deprecate `build_tools.py`. Core engine remains `brain/automation/loop.py` `AutomationLoop`. |

---

## 5. Research

| Field | Value |
|-------|-------|
| **Purpose** | End-to-end research pipeline: plan → search/extract → store facts → reason → detect gaps → synthesize reports → reflect on quality. Knowledge graph, hypothesis management, evidence tracking. |
| **Entry Point** | `core/research/planner.py:120` `ResearchPlanner` — creates research plans from questions |
| **Entry Point** | `core/research/extractor.py` `FactExtractor` — text → structured facts |
| **Entry Point** | `core/research/storage.py` `FactStore` — SQLite-backed fact persistence |
| **Entry Point** | `core/research/retriever.py` `FactRetriever` — topic-aware fact retrieval |
| **Entry Point** | `core/research/reasoner.py` `FactReasoner` — cross-source contradiction detection, gap analysis |
| **Entry Point** | `core/research/reasoning.py` `ReasoningEngine` — belief-driven research with Bayesian confidence |
| **Entry Point** | `core/research/synthesizer.py` `FactSynthesizer` — structured report generation |
| **Entry Point** | `core/research/gap_detector.py` `GapDetector` — evidence gap analysis |
| **Entry Point** | `core/research/evidence_tracker.py` `EvidenceTracker` — fact↔goal coverage mapping |
| **Entry Point** | `core/research/hypothesis.py` `HypothesisManager` — claim-level hypothesis testing |
| **Entry Point** | `core/research/reflection.py` `ResearchReflection` — quality reflection with pattern learning |
| **Entry Point** | `core/research/knowledge_graph.py` `KnowledgeGraph` — high-level graph API |
| **Entry Point** | `core/research/graph_store.py` `GraphStore` — SQLite-backed knowledge graph (`kg_nodes`/`kg_edges`) |
| **Entry Point** | `core/research/linker.py` `Linker` — entity extraction + fact relationship classification |
| **Entry Point** | `core/research/extraction_fsm.py` `ExtractionFSM` — **UNUSED** 10-state extraction state machine |
| **Entry Point** | `core/agents/research_agent.py:12` `ResearchAgent` — agent wrapper (simplified: browser navigate + fetch) |
| **Entry Point** | `core/tools/browser_research.py:32` `do_browser_research()` — bridges browser tools with research pipeline |
| **Provider** | `ResearchProvider` (`core/providers/adapters/research_provider.py:18`). `provider_id: "research"`. Capabilities: `research, find, learn, investigate, explore, analysis`. Registered in `bootstrap.py`. |
| **Dependencies** | `core.research.*` (21 files), `core.fact_extraction.*`, `core.llm_router`. No external libraries beyond stdlib. Database: FactStore (SQLite), ChromaDB (optional). |
| **Permissions** | `is_authorized_to_execute` in `security.py` — research tools require `TOOLS_EXECUTE_LOW` (not in NON_ADMIN_BLOCKED_TOOLS). |
| **Health** | `ResearchProvider.health()` at `provider.py:44` — checks `FactStore.count_facts()` |
| **Reachable** | REST: `core/routes/research.py:23` (`/api/research/facts, /search, /contradictions`), `api/research_routes.py:21` (`/research/run, /status/{job_id}, /list`). Agent: `ResearchAgent`. Tool: `do_browser_research`. Provider: `ResearchProvider`. MCP: Not directly. CLI: None. |
| **Used** | `research_agent.py`, `cookbook_tools.py` (`do_trigger_research`, `do_manage_research`), `api/research_routes.py`, `core/routes/research.py`, `tools/deep_research.py` |
| **Registered** | ✅ `do_manage_research`, `do_trigger_research` in `implementations.py` (from `cookbook_tools`). ✅ Research tools in `TOOL_TAGS`. ❌ NOT in MCP. |
| **Production Usage** | High — active pipeline. `deep_research()` called from `api/research_routes.py`. `ResearchAgent` registered in agent graph. |
| **Agent Usage** | `ResearchAgent` (simplified: navigate + fetch). `NexusAdapter` (deep research via agent adapters). |
| **CLI** | None |
| **Web** | `POST /research/run`, `GET /research/status/{job_id}`, `GET /research/list`, `GET /api/research/facts`, `POST /api/research/search`, `GET /api/research/contradictions`, `POST /api/research/store`, `GET /api/research/sessions` |
| **TUI** | Not directly |
| **Callers** | 30+ files import from `core.research.*` |
| **Reality Score** | 8/10 |
| **Status** | `CORRECT` — rich pipeline, well-organized 21-file package. `ResearchAgent` is simplified bypass (navigate+fetch only). `extraction_fsm.py` is UNUSED. |
| **Future Canonical** | `core/research/` — full pipeline. Unify `ResearchAgent` to use same pipeline. Remove `extraction_fsm.py`. |

---

## 6. Memory

| Field | Value |
|-------|-------|
| **Purpose** | Multi-backend persistent memory: episodic (SQLite), semantic (SQLite), task (SQLite), decision (SQLite + JSON), facts (SQLite), vector (ChromaDB), tiered (hot/warm/cold), mem0, CRUD JSON store, preference profiles, re-ranking, similarity |
| **Entry Point** | `memory/memory_facade.py:27` `MemoryFacade` (singleton `memory`) — unified interface with lazy backends |
| **Entry Point** | `memory/crud_store.py:28` `CrudStore` — JSON-file CRUD |
| **Entry Point** | `memory/episodic_store.py:24` `EpisodicStore` — SQLite |
| **Entry Point** | `memory/semantic_store.py:24` `SemanticStore` — SQLite |
| **Entry Point** | `memory/task_store.py:22` `TaskStore` — SQLite |
| **Entry Point** | `memory/decision_store.py:24` `DecisionStore` — SQLite |
| **Entry Point** | `memory/fact_store.py:20` `FactStore` — SQLite |
| **Entry Point** | `memory/decision_memory.py:27` `DecisionMemory` — JSON file |
| **Entry Point** | `memory/vector_store.py:19` `get_chroma_collection()` — unified ChromaDB access |
| **Entry Point** | `memory/preference_profile.py:20` `PreferenceProfile` — preference aggregation |
| **Entry Point** | `memory/reranker.py:10` `ReRanker` — multi-factor search re-ranking |
| **Entry Point** | `core/agents/memory_agent.py:13` `MemoryAgent` — agent wrapper |
| **Entry Point** | `core/memory_driven_decisions.py:22` `MemoryDrivenRouter` — runtime agent selection |
| **Entry Point** | `mcp/memory_server.py:33` `MCPServer` — MCP CRUD memory tool |
| **Provider** | ❌ No dedicated `ExecutionProvider` for memory. Accessed via `memory.memory_facade.memory` singleton directly. |
| **Dependencies** | `chromadb`, `numpy`, `sqlite3`, `mem0` (optional), `Pillow`. DB files: `data/memory.db` (SQLite — episodic, semantic, task, decision, fact), `data/memory.json` (CrudStore), `data/chroma/` (ChromaDB), `~/.jarvis/decision_memory.json`, `ai_os_memory.db` (intermittent fact_store usage). |
| **Permissions** | `manage_memory` in `NON_ADMIN_BLOCKED_TOOLS` (`security.py:28`). RBAC checked via `check_rbac`. |
| **Health** | No dedicated health check. Graceful degradation on access failure. |
| **Reachable** | REST: `api/memory_routes.py:15` (`/api/memory` — list, stats, per-user, delete). MCP: `mcp/memory_server.py` (`manage_memory` tool). Agent: `MemoryAgent`. Tool: `do_manage_memory` in `implementations.py` (via `chat_tools`). Facade: `memory.memory_facade.memory` (used throughout). |
| **Used** | 40+ files import from `memory.*`. Key consumers: `UnifiedBrain`, `world_model`, `pipeline/memory.py` stage, `api/memory_routes.py`, `mcp/memory_server.py`, `core/memory_driven_decisions.py`, `learning_engine`, `skill_acquisition`, `self_improvement`. |
| **Registered** | ✅ `do_manage_memory` in `implementations.py:111` (from `chat_tools`). ✅ `manage_memory` MCP tool in `mcp/memory_server.py:56`. ❌ NOT as ExecutionProvider. |
| **Production Usage** | High — `MemoryFacade` is the primary memory access point throughout the codebase. |
| **Agent Usage** | `MemoryAgent` (capabilities: `memory, remember, learn, pattern, store, recall`) |
| **CLI** | None |
| **Web** | `GET /api/memory` (list), `GET /api/memory/stats`, `GET /api/memory/{user_id}`, `DELETE /api/memory/{user_id}` |
| **TUI** | Memory stats could feed into TUI monitoring |
| **Callers** | 40+ files across `core/`, `brain/`, `plugins/`, `mcp/`, `api/` |
| **Reality Score** | 6/10 |
| **Status** | `DRIFT` — `decision_memory.py` (JSON) and `decision_store.py` (SQLite) are two separate implementations with different schemas and different callers. `fact_store.py` uses both `data/memory.db` and `ai_os_memory.db` inconsistently. CrudStore is a third flat-file store. MemoryFacade hides complexity but does not resolve fragmentation. |
| **Future Canonical** | `memory/memory_facade.py` `MemoryFacade` — single API. Consolidate `decision_memory` into `decision_store`. Unify `fact_store` database path. |

---

## 7. Voice

| Field | Value |
|-------|-------|
| **Purpose** | Full voice pipeline: mic → VAD → Wake Word → STT → LLM → TTS → speaker. Three modes: wake-word, continuous (VAD), push-to-talk. |
| **Entry Point** | `assistant/voice_pipeline.py:421` `VoiceEngine.process_audio()` — full pipeline: emotion → STT → think → TTS |
| **Entry Point** | `assistant/voice_pipeline.py` `VoiceEngine.think()` — text → `voice_adapter()` → canonical pipeline |
| **Entry Point** | `assistant/wake_word.py` `WakeWordDetector` — two-stage VAD + whisper confirmation |
| **Entry Point** | `assistant/stt.py:57` `get_stt()` — STT provider factory |
| **Entry Point** | `assistant/tts.py:27` `JarvisTTS` / `get_tts()` — TTS engine |
| **Entry Point** | `core/pipeline/adapters/voice_adapter.py:24` `voice_adapter()` — bridges voice to canonical pipeline |
| **Entry Point** | `core/routes/voice.py` — REST + WS voice endpoints |
| **Entry Point** | `assistant/stt_protocol.py` `STTProvider` ABC — FasterWhisper, Deepgram, Azure Speech |
| **Entry Point** | `assistant/tts_protocol.py` `TTSProvider` ABC — Kokoro, EdgeTTS |
| **Provider** | ❌ No dedicated `ExecutionProvider` for voice. Voice is a pipeline transport, not a tool. |
| **Dependencies** | `torch`, `kokoro`, `faster-whisper`, `soundfile`, `numpy`, `edge-tts`, `webrtcvad`, `sounddevice`, `pyaudio`. Deepgram/Azure SDKs (optional). |
| **Permissions** | `verify_token` on voice REST routes (`core/routes/voice.py`). No special RBAC (considered low-risk). |
| **Health** | `VoiceEngine` built-in periodic health. `STTProvider.health()` per provider. |
| **Reachable** | REST: `core/routes/voice.py` (`/stt`, `/stt/local`, `/stt/base64`, `/tts`, `/api/tts/chatterbox`). Pipeline: `voice_adapter()` → `process_message()`. Plugin: `wake_word_plugin.py`. |
| **Used** | `core/routes/voice.py`, `assistant/voice_pipeline.py`, `plugins/wake_word_plugin.py`, `core/pipeline/adapters/voice_adapter.py`, test files |
| **Registered** | ❌ Not registered as a tool (voice is a transport, not a tool). |
| **Production Usage** | High — voice pipeline initialized at startup. Voice routes available. STT supports 3 providers, TTS supports 2 providers. |
| **Agent Usage** | Not directly (voice commands go through pipeline → LLM, not through agents) |
| **CLI** | None |
| **Web** | `POST /stt`, `/stt/local`, `/stt/base64`, `/tts`, `/api/tts/chatterbox` |
| **TUI** | Voice metrics (latency, success rate) could display in TUI |
| **Callers** | 15+ files |
| **Reality Score** | 9/10 |
| **Status** | `CORRECT` — single pipeline, pluggable STT/TTS providers via registry, clean adapter into canonical pipeline |
| **Future Canonical** | `assistant/voice_pipeline.py` `VoiceEngine` — owns the voice pipeline lifecycle |

---

## 8. Speech

| Field | Value |
|-------|-------|
| **Purpose** | Standalone speech synthesis (TTS) and recognition (STT) utilities — lower-level APIs than Voice pipeline |
| **Entry Point** | `assistant/tts.py:27` `JarvisTTS` / `get_tts()` — text → audio |
| **Entry Point** | `assistant/stt.py:57` `get_stt()` — audio → text |
| **Entry Point** | `assistant/edge_tts_module.py` `EdgeTTS` — Edge TTS wrapper |
| **Entry Point** | `core/audio_emotion.py` `AudioEmotionDetector` — emotion from audio |
| **Provider** | ❌ No dedicated ExecutionProvider (same as Voice — transport, not tool) |
| **Dependencies** | Same as Voice |
| **Permissions** | Same as Voice |
| **Health** | `STTProvider.health()` per provider, `JarvisTTS._ensure_model()` |
| **Reachable** | Same REST endpoints as Voice |
| **Used** | `core/routes/voice.py`, `assistant/voice_pipeline.py`, `plugins/wake_word_plugin.py` |
| **Registered** | ❌ Not tools |
| **Production Usage** | High — same as Voice |
| **Agent Usage** | Not directly |
| **CLI** | None |
| **Web** | Same as Voice |
| **TUI** | None |
| **Callers** | Same as Voice |
| **Reality Score** | 9/10 |
| **Status** | `CORRECT` — same pipeline as Voice, logically grouped |
| **Future Canonical** | Merge with Voice under `assistant/` — Speech is a sub-component of Voice |

---

## 9. Notifications

| Field | Value |
|-------|-------|
| **Purpose** | Multi-channel notification: push (ntfy.sh, Pushover), email (SMTP), WebSocket broadcast, JSONL event log |
| **Entry Point** | `notifications/notifier.py:28` `SupervisorNotifier` — build event notifications |
| **Entry Point** | `monitors/alerts.py:44` `AlertRouter` — monitor alert routing (WS, TTS, WhatsApp) |
| **Entry Point** | `core/event_bus.py:139` `_broadcast()` — WebSocket event push |
| **Provider** | ❌ No dedicated ExecutionProvider |
| **Dependencies** | `smtplib`, `httpx`, `json`. External: SMTP server, ntfy.sh, Pushover API. |
| **Permissions** | None (fire-and-forget). Email credentials from env vars. |
| **Health** | No dedicated health check |
| **Reachable** | Internal only — triggered by events/alerts from build pipeline and monitors. Not exposed as REST endpoints. |
| **Used** | `notifications/notifier.py` (build events), `monitors/alerts.py` (system alerts), `core/event_bus.py` (all events → WS broadcast) |
| **Registered** | ❌ Not registered as tools |
| **Production Usage** | Low — `SupervisorNotifier` only triggered by build events. `AlertRouter` routing functions default to `None` (not wired). |
| **Agent Usage** | Not available to agents |
| **CLI** | None |
| **Web** | WebSocket only (EventBus pushes events to connected WS clients) |
| **TUI** | Could feed into activity monitor |
| **Callers** | `notifier.py`, `alerts.py`, `event_bus.py` |
| **Reality Score** | 3/10 |
| **Status** | `DUPLICATE` — `SupervisorNotifier` and `AlertRouter` overlap. Neither is fully wired. No TTS bridge. No central notification service. |
| **Future Canonical** | NEW — consolidate into `core/notifications/` package with single routing API + TTS bridge |

---

## 10. Email

| Field | Value |
|-------|-------|
| **Purpose** | Multi-account email: fetch (IMAP), send (SMTP), draft, triage, search, attachments |
| **Entry Point** | `channels/email_channel.py:27` `EmailChannel` — channel-based email |
| **Entry Point** | `mcp/email_server.py:47` `EmailServer` — MCP server with list/read/draft/send |
| **Entry Point** | `core/providers/adapters/email_provider.py:18` `EmailProvider` — ExecutionProvider |
| **Entry Point** | `core/agents/email_agent.py:12` `EmailAgent` — agent wrapper |
| **Entry Point** | `api/email_routes.py:19` — REST API |
| **Provider** | `EmailProvider` (`core/providers/adapters/email_provider.py:18`). `provider_id: "email"`. Capabilities: `email, send_email, compose_email, email_attachments`. Registered in `bootstrap.py`. |
| **Dependencies** | `imaplib`, `smtplib`, `email`, `sqlite3`, `httpx`. DB: `data/app.db` (email_accounts table). External: IMAP/SMTP servers. |
| **Permissions** | `send_email`, `reply_to_email`, `list_emails`, `read_email`, `resolve_contact`, `manage_contact` in `NON_ADMIN_BLOCKED_TOOLS` (`security.py:31`). Requires `TOOLS_EXECUTE_HIGH`. RBAC via `check_rbac`. |
| **Health** | `EmailProvider.health()` at `provider.py:41` — checks `mcp.email_server` importable and not None. `EmailChannel._is_configured()` checks env vars. |
| **Reachable** | REST: `api/email_routes.py:19` (`/email/status, /inbox, /draft, /send`). MCP: `mcp/email_server.py`. Agent: `EmailAgent`. Channel: `EmailChannel`. Provider: `EmailProvider`. |
| **Used** | `api/email_routes.py`, `mcp/email_server.py`, `core/agents/email_agent.py`, `core/tools/chat_tools.py`, tests |
| **Registered** | ✅ Email tools in `TOOL_TAGS`. ✅ MCP server `"email"`. ✅ `EmailProvider` as ExecutionProvider. ❌ NOT directly in `implementations.py` (routed through MCP). |
| **Production Usage** | Medium — email MCP server runs with multi-account support. REST API active. |
| **Agent Usage** | `EmailAgent` (capabilities: `email, mail, send, deliver, notify`) |
| **CLI** | None |
| **Web** | `GET /email/status`, `GET /email/inbox`, `POST /email/draft`, `POST /email/send` |
| **TUI** | None |
| **Callers** | 10+ files |
| **Reality Score** | 7/10 |
| **Status** | `CORRECT` — well-structured with provider, agent, MCP, REST, and channel access paths. Multiple entry points are intentional. |
| **Future Canonical** | `core/providers/adapters/email_provider.py` `EmailProvider` — canonical ExecutionProvider. All other paths should route through or alongside it. |

---

## 11. Search

| Field | Value |
|-------|-------|
| **Purpose** | Unified web search with automatic fallback chain (SearXNG → DuckDuckGo → page extraction). Deep research pipeline with planning, async fetching, LLM extraction/synthesis. |
| **Entry Point** | `tools/search_tool.py:38` `SearchDecisionGate` — gating logic |
| **Entry Point** | `tools/search_tool.py:50` `DuckDuckGoFallback` — fallback searcher |
| **Entry Point** | `tools/search_tool.py` `SearchEngine` (singleton `search_engine`) — unified search |
| **Entry Point** | `tools/search_fallback.py` `search_fallback` — SearXNG → DDGS chain |
| **Entry Point** | `core/tools/execution/direct_tools.py:288` `web_search` — direct tool dispatch |
| **Entry Point** | `tools/deep_research.py:25` `do_deep_research()` — 5-step research pipeline |
| **Provider** | ❌ No dedicated ExecutionProvider. Search is handled through `ResearchProvider` (has "research" capabilities) or direct tool execution. |
| **Dependencies** | `httpx`, `requests`, `trafilatura`, `bs4`, `aiohttp`, `ddgs` (optional), `duckduckgo_search` (optional). External: SearXNG (localhost:8888), DuckDuckGo. |
| **Permissions** | `web_search` NOT in `NON_ADMIN_BLOCKED_TOOLS` (low-risk). `search_chats` IS blocked (requires HIGH). |
| **Health** | Implicit — no dedicated health function |
| **Reachable** | Tool: `web_search` mapped in `direct_tools.py:288`. MCP: mapped via `MCP_TOOL_MAP` (`mcp.py:24`). Agent: `ResearchAgent` (uses `web_fetch` + `browser_navigate`). REST: `POST /research/run` (deep research). |
| **Used** | `direct_tools.py`, `deep_research.py`, `parsing.py`, `api/research_routes.py`, `settings_tools.py` |
| **Registered** | ✅ `web_search` as native tool type in `execution/__init__.py`. ✅ `web_fetch` similarly. ✅ schemas in `schemas_shell_web.py`. ✅ MCP mapping. |
| **Production Usage** | High — called frequently during agent execution. Deep research used by NexusAdapter. |
| **Agent Usage** | `ResearchAgent` (uses `web_fetch` + `browser_navigate`). `NexusAdapter` (uses deep research). |
| **CLI** | None |
| **Web** | `POST /research/run` (deep research, uses search internally) |
| **TUI** | None |
| **Callers** | 20+ files |
| **Reality Score** | 8/10 |
| **Status** | `CORRECT` — unified search with fallback chain, well-integrated with research pipeline |
| **Future Canonical** | `tools/search_tool.py` `SearchEngine` — unified search entry point. Wrap as `SearchProvider` ExecutionProvider for consistency. |

---

## 12. Filesystem

| Field | Value |
|-------|-------|
| **Purpose** | File/directory CRUD: read, write, append, delete, list, edit (find/replace, unified diff), batch edit, refactor, undo. Path resolution with security allowlisting. |
| **Entry Point** | `brain/tools/project_tool.py:16` `ProjectTool` — `create_directory()`, `write_file()`, `read_file()`, `edit_file()`, `delete_file()`, `list_directory()` |
| **Entry Point** | `core/tools/execution/edit_tools.py:25` `do_edit_file()` — F/R edits with backup |
| **Entry Point** | `core/tools/execution/edit_tools.py:307` `do_batch_edit_file()` — glob-pattern batch |
| **Entry Point** | `plugins/file_tools_plugin.py:11` `FilePlugin` — `read_file`, `write_file`, `append_file`, `delete_file`, `list_folder` |
| **Entry Point** | `core/tools/document_tools.py` `do_create_document`, `do_edit_document` — document-level ops |
| **Entry Point** | `tools/file_search.py:45` `find_files` — file search |
| **Provider** | ❌ No dedicated ExecutionProvider. Accessed through `DesktopProvider` (desktop operations) or `WorkspaceProvider` (workspace ops). |
| **Dependencies** | `difflib`, `hashlib`, `ast`, `pathlib`, `py_compile` (optional), `ruff`/`prettier` (auto-format). DB: Document models (SQLAlchemy). |
| **Permissions** | `read_file`, `write_file`, `edit_file`, `delete_file`, `list_folder`, `append_file` in `NON_ADMIN_BLOCKED_TOOLS` (`security.py:28`) — requires `TOOLS_EXECUTE_HIGH`. Path allowlisting in `security.py:_tool_path_roots()` — restricts to `DATA_DIR`, `/tmp`, configured roots. Sensitive path blocking (`_is_sensitive_path()`): blocks `.ssh`, `.env`, `id_rsa`, etc. |
| **Health** | No dedicated health check |
| **Reachable** | Tool: All file ops registered in `execution/__init__.py` → `execute_tool_block`. Plugin: `file_tools_plugin.py` registers 5 tools. MCP: `MCP_TOOL_MAP` (`mcp.py:19-23`). Brain: `ProjectTool` registered in `brain/executor/executor.py`. Agent: `BuildAgent` uses file ops. |
| **Used** | `handlers.py` (main dispatch), `tool_registry (brain)`, `file_tools_plugin.py`, `project_tool.py`, tests |
| **Registered** | ✅ `do_create_document`, `do_edit_document`, `do_manage_documents`, `do_suggest_document`, `do_update_document` in `implementations.py:49-58`. ✅ Plugin tools in `file_tools_plugin.py`. ✅ MCP mapping. ❌ Edit tools (`do_edit_file` etc.) NOT in `implementations.py`. |
| **Production Usage** | High — filesystem tools are among the most frequently called |
| **Agent Usage** | `BuildAgent` (file ops for builds), `BrowserAgent` (may read/write artifacts) |
| **CLI** | None |
| **Web** | None directly (goes through tool execution dispatch) |
| **TUI** | None |
| **Callers** | 25+ files |
| **Reality Score** | 6/10 |
| **Status** | `DRIFT` — three registration paths (tool dispatch, plugin, brain executor) for overlapping operations. Edit tools (`do_edit_file` etc.) missing from `implementations.py`. `ProjectTool` duplicates low-level file ops already in `core/tools/`. |
| **Future Canonical** | `core/tools/execution/edit_tools.py` + `core/tools/document_tools.py` — single registration in `implementations.py`. Deprecate `ProjectTool` file ops in favor of `core/tools/`. |

---

## 13. Terminal

| Field | Value |
|-------|-------|
| **Purpose** | Shell command execution (bash/PowerShell), Python script execution, persistent shell via WebSocket. Docker sandbox isolation. |
| **Entry Point** | `core/tools/execution/direct_tools.py:40` `_direct_fallback()` — bash/python execution |
| **Entry Point** | `core/tools/execution/subprocess.py:15` `_run_subprocess_streaming()` — streaming subprocess |
| **Entry Point** | `core/routes/terminal.py:13` `terminal_websocket()` — persistent WS terminal |
| **Entry Point** | `core/sandbox/docker_sandbox.py` `DockerSandbox` — sandboxed execution |
| **Entry Point** | `core/sandbox/sandbox_manager.py` `SandboxManager` — sandbox management |
| **Provider** | ❌ No dedicated ExecutionProvider. Accessed through `DesktopProvider` (desktop/terminal ops) or direct tool execution. |
| **Dependencies** | `asyncio.subprocess`, `core/sandbox/*` (Docker, SandboxManager). External: Shell (cmd/pwsh on Windows, bash on Unix), Docker (optional). |
| **Permissions** | `bash`, `python`, `shell`, `shell_command` in `NON_ADMIN_BLOCKED_TOOLS` (`security.py:28`) — requires `TOOLS_EXECUTE_HIGH`. RBAC via `check_rbac`. Approval via `check_approval` (may require user confirmation). |
| **Health** | No dedicated health check. `DockerSandbox.available` flag for sandbox routing. |
| **Reachable** | WebSocket: `core/routes/terminal.py:13` (`/ws/terminal`). Tool: `bash`/`python` types in `direct_tools.py:54`. MCP: `MCP_TOOL_MAP` (`mcp.py:17-18`). |
| **Used** | `handlers.py` (dispatch bash/python to `_direct_fallback`), `direct_tools.py`, `core/routes/terminal.py`, `core/tools/persistent_shell.py`, tests |
| **Registered** | ✅ `bash` and `python` as native tool types in `execution/__init__.py`. ✅ schemas in `schemas_shell_web.py`. ✅ MCP mapping. |
| **Production Usage** | High — terminal execution is a core capability |
| **Agent Usage** | `BuildAgent` (uses bash/python for builds), `BrowserAgent` (may use shell commands) |
| **CLI** | None |
| **Web** | `WS /ws/terminal` — real-time terminal WebSocket |
| **TUI** | None |
| **Callers** | 15+ files |
| **Reality Score** | 8/10 |
| **Status** | `CORRECT` — well-structured with MCP mapping, sandbox isolation, RBAC, approval flow, and streaming subprocess |
| **Future Canonical** | `core/tools/execution/direct_tools.py` `_direct_fallback` — canonical shell execution. Wrap as `TerminalProvider` ExecutionProvider for consistency. |

---

## 14. Vision

| Field | Value |
|-------|-------|
| **Purpose** | Desktop vision automation: screen capture, object detection via Ollama vision models (Moondream/Gemma), pyautogui-based UI automation, screenshot description, multi-step task planning with verification loop |
| **Entry Point** | `core/vision_agent.py:80` `VisionAgent` — vision-based desktop automation (using mss + Ollama + pyautogui) |
| **Entry Point** | `core/tools/vision_tools.py:19` `do_vision_browser()` — tool wrapper for vision |
| **Entry Point** | `core/routes/vision.py:25` — REST endpoints for vision agent |
| **Provider** | ❌ No dedicated ExecutionProvider. Accessed through `DesktopProvider` (desktop automation includes vision). |
| **Dependencies** | `mss`, `pyautogui`, `Pillow`, `httpx`, `cv2`, `deepface`, `numpy`. External: Ollama vision models (Moondream, Gemma). |
| **Permissions** | `do_vision_browser` requires RBAC. `edit_image` in `NON_ADMIN_BLOCKED_TOOLS`. Not all vision tools are blocked by default. |
| **Health** | Implicit — checks vision model availability at startup |
| **Reachable** | REST: `core/routes/vision.py` (`POST /api/vision/screen`, `/analyze`, `/run`, `GET /task/{task_id}`). Tool: `do_vision_browser` in `implementations.py`. Direct: `VisionAgent` instantiated directly. |
| **Used** | `vision_tools.py`, `core/routes/vision.py`, `implementations.py`, tests |
| **Registered** | ✅ `do_vision_browser` in `implementations.py:74` (from `vision_tools`). ❌ NOT in MCP. ❌ NOT as ExecutionProvider. |
| **Production Usage** | Medium — used for desktop automation tasks. VisionAgent is active but bypasses DesktopProvider safety layer. |
| **Agent Usage** | Not a standalone agent — invoked as tool (`do_vision_browser`) |
| **CLI** | None |
| **Web** | `POST /api/vision/screen` (capture+describe), `POST /api/vision/analyze` (answer about screen), `POST /api/vision/run` (run task), `GET /api/vision/task/{task_id}` (check status) |
| **TUI** | None |
| **Callers** | 10+ files |
| **Reality Score** | 5/10 |
| **Status** | `DRIFT` — `VisionAgent` duplicates desktop control already in `core/desktop/`, bypasses `SafetyManager`, uses raw pyautogui. No ExecutionProvider wrapper. |
| **Future Canonical** | Merge into `core/desktop/` as `VisionDesktopController`. Wire through `DesktopProvider`. Deprecate standalone `VisionAgent`. |

---

## 15. Scheduling

| Field | Value |
|-------|-------|
| **Purpose** | Persistent time-driven autonomous activity scheduler with worker pool, queue prioritization, cron/interval scheduling, activity intelligence (scoring, resource mgmt), dependency resolution, lifecycle events |
| **Entry Point** | `core/scheduler/scheduler.py:42` `Scheduler` — main scheduler class with state machine (stopped/running/paused) |
| **Entry Point** | `core/scheduler/queue.py` `SchedulerQueue` — chain-aware prioritization |
| **Entry Point** | `core/scheduler/store.py` `SchedulerStore` — SQLite persistence |
| **Entry Point** | `core/scheduler/models.py:11` `ScheduledActivity`, `ScheduleModel` — data models |
| **Entry Point** | `core/scheduler/registry.py` `SchedulerRegistry` — executor function registry |
| **Entry Point** | `core/scheduler/policies.py` `PriorityPolicy` — scheduling policies |
| **Entry Point** | `core/scheduler/decision.py` `DecisionEngine` — EV/confidence/risk gating |
| **Entry Point** | `core/scheduler/intelligence.py` `ActivityIntelligence` — prediction + calibration |
| **Entry Point** | `core/scheduler/resources.py` `ResourceUsage` — resource tracking |
| **Entry Point** | `core/scheduler/metrics.py` `SchedulerMetrics` — metrics collection |
| **Entry Point** | `core/scheduler/autonomous.py` `AutonomousScheduler` — opportunity→decision→queue bridge |
| **Entry Point** | `core/scheduler/pipeline_executor.py` — pipeline execution |
| **Entry Point** | `core/scheduler/executors.py` — executor implementations |
| **Entry Point** | `core/scheduler/chain.py` `ChainExecutor` — chain execution |
| **Entry Point** | `core/scheduler/worker.py` `WorkerPool` — worker management |
| **Entry Point** | `core/tools/scheduler_tools.py` — 10 scheduler tool functions |
| **Entry Point** | `core/routes/scheduler.py:24` — REST API for schedules |
| **Provider** | ❌ No dedicated ExecutionProvider. Scheduling is a core system service, not a capability. |
| **Dependencies** | `core.activity.manager`, `core.activity.resume`, `core.scheduler.*` (15 files), `core.execution`. DB: SchedulerStore (SQLite). |
| **Permissions** | Scheduler tools in `NON_ADMIN_BLOCKED_TOOLS` — requires `TOOLS_EXECUTE_HIGH`. RBAC checked. |
| **Health** | Implicit via state machine (stopped/running/paused). No route-level health check. |
| **Reachable** | REST: `core/routes/scheduler.py:24` (`/api/schedules` CRUD). Tool: `core/tools/scheduler_tools.py` (10 functions). Autonomous: `core/scheduler/autonomous.py`. Internal: initialized in lifespan as background task. |
| **Used** | `scheduler_tools.py`, `core/routes/scheduler.py`, `core/scheduler/autonomous.py`, `core/lifespan.py` (initializes scheduler), tests |
| **Registered** | ✅ 10 scheduler tools in `implementations.py:122-133`. ✅ REST routes in `core/routes/scheduler.py`. |
| **Production Usage** | High — runs as background service managing autonomous activities |
| **Agent Usage** | Not directly (system-level scheduling) |
| **CLI** | `jarvis scheduler start` (from `do_scheduler_start`) |
| **Web** | `GET /api/schedules`, `POST /api/schedules`, `GET/PATCH/DELETE /api/schedules/{id}`, `POST /api/schedules/{id}/pause`, `POST /api/schedules/{id}/resume`, `GET /api/schedules/status` |
| **TUI** | Scheduler events feed into TUI activity monitoring |
| **Callers** | 15+ files |
| **Reality Score** | 8/10 |
| **Status** | `CORRECT` — self-contained package with clear tick-based lifecycle, REST API, tool interface, and autonomous bridge. Experimental parts (`autonomous.py`, `decision.py`) are isolated. |
| **Future Canonical** | `core/scheduler/scheduler.py` `Scheduler` — owns scheduling lifecycle |

---

## 16. Projects

| Field | Value |
|-------|-------|
| **Purpose** | High-level project lifecycle management: queue, priority, checkpoint/resume, state persistence, code analysis, build orchestration |
| **Entry Point** | `core/project_manager.py` `ProjectManager` (singleton `project_manager`) — queue/priority/lifecycle |
| **Entry Point** | `core/project_state.py` `ProjectState` — 25+ field dataclass, persisted to `~/.jarvis/projects/{name}/state.json` |
| **Entry Point** | `brain/tools/project_tool.py:16` `ProjectTool` — low-level file/build ops |
| **Entry Point** | `core/routing/project_context.py` `ContextManager` — project context management |
| **Entry Point** | `core/cloud/project_manager.py` — cloud-specific project manager |
| **Entry Point** | `core/workspace_manager.py` `WorkspaceManager` — workspace/project detection |
| **Entry Point** | `core/repository_analyzer.py` `RepositoryAnalyzer` — code analysis |
| **Provider** | ❌ No dedicated ExecutionProvider |
| **Dependencies** | `core/control_loop.py`, `core/project_state.py`, `brain/tools/project_tool.py`. DB: `~/.jarvis/manager_state.json`, `~/.jarvis/projects/{name}/state.json`. |
| **Permissions** | Project operations require RBAC (general tool permissions) |
| **Health** | No dedicated health check |
| **Reachable** | Internal only — used by `AgentOrchestrator`, `AutomationLoop`, `cli_commands`. Not exposed as REST endpoints. |
| **Used** | `AgentOrchestrator.code()/build()`, `AutomationLoop`, `cli_commands` (cmd_code, cmd_build, cmd_run, cmd_understand) |
| **Registered** | ❌ Not registered as tools |
| **Production Usage** | High — `ProjectManager` manages concurrent project queue with priorities (default 2 workers), checkpoint/resume. |
| **Agent Usage** | `BuildAgent` (project builds), `TestAgent` (project tests) |
| **CLI** | `jarvis code/build/run/understand/workspace` — all route through `AgentOrchestrator` |
| **Web** | None |
| **TUI** | None |
| **Callers** | `agent_orchestrator.py`, `cli_commands.py`, `automation/loop.py`, `project_state.py` |
| **Reality Score** | 7/10 |
| **Status** | `CORRECT` — well-layered: `ProjectManager` (queue) + `ProjectState` (persistence) + `ProjectTool` (low-level). Cloud variant adds complexity. |
| **Future Canonical** | `core/project_manager.py` `ProjectManager` — project lifecycle. `core/project_state.py` `ProjectState` — project persistence. |

---

## 17. Automation

| Field | Value |
|-------|-------|
| **Purpose** | Autonomous build automation loop: polls highest-priority active goal, runs full build pipeline (plan→generate→verify→build→test→verify→validate→finish), failure memory, plan evolution |
| **Entry Point** | `brain/automation/loop.py:977` `AutomationLoop` — core automation engine |
| **Entry Point** | `brain/automation/loop.py:1008` `AutomationLoop.start()` — starts tick loop |
| **Entry Point** | `brain/automation/loop.py:1046` `AutomationLoop._tick()` — polls highest-priority active goal |
| **Entry Point** | `brain/automation/loop.py:1111` `AutomationLoop._build_project()` — full build pipeline |
| **Entry Point** | `brain/automation/loop.py:69` `FailureMemory` — SQLite-backed pattern matching |
| **Entry Point** | `brain/automation/loop.py:228` `RequirementTracker` — requirement tracking |
| **Entry Point** | `brain/automation/loop.py:293` `ArchitecturalMemory` — architectural pattern store |
| **Entry Point** | `brain/automation/loop.py:430` `classify_error()` — error classification |
| **Provider** | `AutomationProvider` (`core/providers/adapters/automation_provider.py:20`). `provider_id: "automation"`. Registered in `bootstrap.py:16,26`. |
| **Dependencies** | `brain/automation/loop.py`, `brain/automation/failure_memory.py`, `brain/automation/architectural_memory.py`, `brain/automation/requirement_tracker.py`, `core/planner/` (UnifiedStore), `core/llm_router`, `core/execution.py` (ExecutionManager) |
| **Permissions** | Path allowlists, `PolicyEngine`, tool validation (same as Build) |
| **Health** | `AutomationProvider.health()` — tries to instantiate `WorkflowEngine` |
| **Reachable** | REST: `POST /build/overnight` (`cowork.py:110`). Agent: `BuildAgent`, `TestAgent`. Internal: `AutomationLoop.start()` called from `UnifiedBrain`. CLI: through `AgentOrchestrator`. |
| **Used** | `UnifiedBrain.start_automation()`, `AgentOrchestrator.code()/build()`, `build_tools.py`, `automated_build.py`, `BuildAgent`, 6 benchmark files |
| **Registered** | ✅ `do_build_project`, `do_repair_project`, `do_run_tests`, `do_runtime_validate`, `cancel_build` in `implementations.py`. ✅ `AutomationProvider` as ExecutionProvider. |
| **Production Usage** | High — core automated build engine with FailureMemory (SQLite), ArchitecturalMemory (JSON), 27 error patterns, 10 MAX_REPAIR_ATTEMPTS, plan evolution |
| **Agent Usage** | `BuildAgent` (build), `TestAgent` (test) |
| **CLI** | `jarvis code/build` (through `AgentOrchestrator`) |
| **Web** | `POST /build/overnight` (`cowork.py:110`), `GET /status/{build_id}`, `POST /cancel/{build_id}` |
| **TUI** | None |
| **Callers** | `loop.py` dependencies, `build_tools.py`, `automated_build.py`, `UnifiedBrain.py`, `agent_orchestrator.py`, `build_agent.py`, `test_agent.py`, `cowork.py`, benchmarks |
| **Reality Score** | 7/10 |
| **Status** | `CORRECT` — single automation engine. Dual wrapper layer (`build_tools.py` vs `automated_build.py`) around same `AutomationLoop`. |
| **Future Canonical** | `brain/automation/loop.py` `AutomationLoop` — owns build automation. Deprecate `build_tools.py` in favor of `automated_build.py`. |

---

## Cross-Cutting Summary

### By Reality Score

| Score | Capabilities |
|-------|-------------|
| **9/10** | Browser, Voice, Speech |
| **8/10** | Research, Search, Terminal, Scheduling |
| **7/10** | Coding, Build, Email, Projects, Automation |
| **6/10** | Memory, Filesystem |
| **5/10** | Vision |
| **4/10** | Desktop |
| **3/10** | Notifications |

### By Status

| Status | Count | Capabilities |
|--------|-------|-------------|
| `CORRECT` | 8 | Browser, Research, Voice, Speech, Search, Terminal, Email, Scheduling |
| `DRIFT` | 5 | Desktop, Memory, Filesystem, Vision, Notifications |
| `DUPLICATE` | 3 | Build, Coding, Notifications |
| `DORMANT` | 1 | (none fully dormant) |

### By Provider Coverage

| Has ExecutionProvider | Missing ExecutionProvider |
|----------------------|--------------------------|
| Desktop (`DesktopProvider`), Browser (`BrowserProvider`), Coding (`ForgeProvider`, `ClaudeCodeProvider`, `CodexProvider`), Build (`AutomationProvider`), Research (`ResearchProvider`), Email (`EmailProvider`), Automation (`AutomationProvider`), Projects (partial) | Memory, Voice, Speech, Notifications, Search, Filesystem, Terminal, Vision, Scheduling |

### Priority Consolidation Targets

1. **Desktop**: Merge `core/desktop/` + `pc_agent/` + `VisionAgent` → single safety-gated `DesktopProvider`
2. **Memory**: Consolidate `decision_memory.py` → `decision_store.py`, unify `fact_store.py` DB path
3. **Notifications**: Merge `SupervisorNotifier` + `AlertRouter` → `core/notifications/` with TTS bridge
4. **Filesystem**: Register `edit_tools` in `implementations.py`, deprecate `ProjectTool` file ops
5. **Build**: Deprecate `build_tools.py` → standardize on `automated_build.py`
6. **Vision**: Merge into `core/desktop/`, wire through `DesktopProvider`
