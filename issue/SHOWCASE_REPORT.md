# SHOWCASE REPORT — JARVIS Component Reality Audit

> Generated: 2026-06-10  
> Methodology: Source code analysis + dependency check for each suspected component

---

## VERDICT KEY

| Classification | Meaning |
|---|---|
| **REAL** | Performs actual work — has real implementation, real dependencies |
| **SHOWCASE** | Looks real in UI/CLI, has handler registered, but does nothing substantive |
| **STUB** | Explicitly "not implemented" or raises NotImplementedError |
| **GHOST** | Depends on missing jarvis_os package, can never run |
| **DISCONNECTED** | Has real implementation but is not wired into the execution path |

---

## COMPONENT AUDIT

### 1. gent/ directory

**Does not exist.** The only adjacent directory is pc_agent/ (real computer automation agent).

**Status: N/A (absent)**

---

### 2. skills/library/ — 50 skills

| Aspect | Finding |
|---|---|
| **Structure** | 50 skill directories across 5 categories (entertainment, finance, knowledge, productivity, system) |
| **Real implementations** | Many skills have real code: weather (OpenWeatherMap API), 	odoist (Todoist REST API), paper_summarizer (NLP text analysis), system_monitor (psutil), stocks, crypto, screenshot, clipboard, etc. |
| **SkillManager** | skills/manager.py has a sophisticated loader that reads skill.json manifests, resolves imports, and loads main.py entry points |
| **The disconnect** | SkillManager.SKILLS_DIR points to skills/installed/ — which is **empty**. The load_all() method searches skills/installed/ for skill.json files. All 50 skills live in skills/library/, NOT skills/installed/. |
| **Never auto-loaded** | There is no code that copies or links skills/library/ → skills/installed/. The SkillManager.load_all() finds zero skills. |

**Status: SHOWCASE** — 50 skill implementations exist but are never loaded by the skill manager. They are only accessible if manually copied to skills/installed/.

---

### 3. core/personal_docs.py — Personal Documents Manager

| Aspect | Finding |
|---|---|
| extract_pdf_text() | **REAL** — 4 fallback extractors (pypdf, pdfminer, PyPDF2, pdftotext) with proper error handling and logging |
| PersonalDocsManager.__init__ | Takes data_dir but does nothing with it |
| index_personal_documents() | **STUB** — Explicitly logs "not implemented" and returns {"indexed": 0, "errors": 0} |
| search() | **STUB** — Always returns [] |
| **Integration** | mcp/rag_server.py tries to import PersonalDocsManager and call methods like dd_directory(), emove_directory(), get_indexed_directories() that DON'T EXIST on the stub class. These calls will hit AttributeError. |

**Status: PARTIAL STUB** — PDF extraction is real, but the document management API is a total stub with missing methods that break integration.

---

### 4. core/security_audit.py — Security Auditor

| Aspect | Finding |
|---|---|
| udit_config() | **REAL** — Scans ~/.jarvis/*.json for dangerous flags (dev_mode, CORS, API keys in config) |
| udit_filesystem() | **REAL** — Checks sensitive files (*.db, *credentials*, *.pem, *token*) and session file count |
| udit_network() | **REAL** — Tests SSRF against test URLs, checks cloud provider env vars |
| udit_auth() | **REAL** — Checks DEV_MODE, Firebase credentials file |
| un_full_audit() | **REAL** — Aggregates all audits, logs findings, writes report to ~/.jarvis/security_audits/ |
| **Integration** | Exportable via core/main.py routes, called from diagnostics |

**Status: REAL** — Performs actual security scanning with structured findings.

---

### 5. i_os/ — AI OS Package

| Component | Status | Evidence |
|---|---|---|
| orchestrator.py | **REAL** | execute() and un() methods with real dispatch to task router, sub-agents, skills, tools. Real event publishing. |
| planner.py | **GHOST** | Delegates to jarvis_os.core.planner.PlanningEngine. If not available (which it isn't — jarvis_os not installed), raises RuntimeError: "Canonical planner is required". |
| policy.py | **REAL** | ssess_step() and enforce() do real policy checking on tool calls against allowlists/blocklists. |
| 	ool_registry.py | **REAL** | Registers open_app, safe_shell, ile_ops, rowser_control, code_agent. First 4 are real. |
| *code_agent_handler* | **SHOWCASE** | eturn {"success": True, "message": f"Code agent would run: {task}"} — never runs anything |
| model_router.py | **REAL** | Selects models by task type, calls Ollama |
| memory.py | **GHOST** | Delegates to jarvis_os.memory.memory_manager.MemoryManager. Raises RuntimeError if not available. |
| event_bus.py | **REAL** | Working publish/subscribe with streaming queues |
| config.py | **REAL** | Reads from settings store |
| sandbox.py | **REAL** | Subprocess execution with shell=False, timeout, output truncation, blocked executables list |
| sandbox_manager.py | Needs check | — |
| docker_sandbox.py | **REAL** | Docker container creation, code execution, cleanup. Network-disabled by default. |
| ollama_client.py | **REAL** | HTTP client for Ollama |

**Status: Mixed** — 60% REAL, 20% GHOST (depends on missing jarvis_os), 10% SHOWCASE (code_agent_handler), 10% other.

---

### 6. 	ools/ (root) — Root Tools Package

| Component | Status | Evidence |
|---|---|---|
| ase_tool.py | **REAL** | Data classes: ToolResult, ToolDefinition |
| egistry.py | **REAL** | ToolRegistry with register, list, execute, catalog |
| search_tool.py | **REAL** | SearchDecisionGate + DuckDuckGoFallback + multiple search engines |
| search_fallback.py | **REAL** | Multi-engine search fallback chain |
| rowser_agent.py | **REAL** | Playwright-based vision-driven browser automation |
| rowser_tool.py | **REAL** | Browser navigation and scraping tool |
| crawl4ai_tool.py | **REAL** | Async web crawler using crawl4ai |
| deep_research.py | **REAL** | Multi-step deep research with LLM-driven query refinement |
| executor.py | **REAL** | Tool execution and dispatch |
| ile_search.py | **REAL** | File system search tool |
| image_gen.py | **REAL** | Image generation via API |
| plugin_base.py | **REAL** | Plugin infrastructure |
| agflow_tool.py | **REAL** | RAG flow integration |
| website_generator.py | **REAL** | LLM-powered website generation |
| 	emplate_library.py | **REAL** | Template management and filling |
| scene_generator.py | **REAL** | 3D scene generation (Three.js/Blender) |
| whatsapp_sender.py | **REAL** | Meta Cloud API WhatsApp sender |
| parse_pip_audit.py | **REAL** | pip audit output parser |
| jarvis_website_cli.py | **REAL** | CLI for website generation |

**BUT:** These tools go through 	ools/registry.py (ToolRegistry), which is **NOT** the same as core/tools/execution.py (_TOOL_HANDLERS). The i_os/tool_registry.py also has its own separate registry. Root tools are imported ad-hoc by specific consumers rather than being centrally discoverable.

**Status: REAL but DISCONNECTED** — Every tool has real implementation, but none are registered in the main core/tools/execution.py dispatcher. They are imported ad-hoc or accessed through the separate 	ools/registry.py.

---

### 7. ssistant/voice_pipeline.py — Voice Pipeline

| Aspect | Finding |
|---|---|
| **STT** | **REAL** — Uses aster_whisper with VAD filter, deepgram, zure_speech providers |
| **TTS** | **REAL** — Uses edge_tts module |
| **Wake word** | **REAL** — Two-stage: WebRTC VAD + Faster-Whisper confirmation. Actually imports webrtcvad. |
| **Emotion detection** | **REAL** — Uses core/audio_emotion for emotional context |
| **VoiceLoop** | **REAL** — Background thread with wake event, audio capture, pipeline processing |
| **Plugin hooks** | **REAL** — Emits on_voice_command events |
| **Dependencies** | webrtcvad — **installed and used** (confirmed at wake_word.py:25) |

**Status: REAL** — Full working voice pipeline. The question "voice without webrtcvad = ?" is answered: webrtcvad IS present and actively used.

---

### 8. mcp/ — Model Context Protocol Servers

| Component | Status | Evidence |
|---|---|---|
| server.py (MCPServer) | **REAL** | Tool registration, WebSocket bridge, JSON-RPC 2.0 handling, approval workflow, event queue, FastAPI router. 564 lines of real code. |
| email_server.py | **REAL** | IMAP/SMTP email operations, 1636 lines. Real email fetching, parsing, draft reply generation. |
| image_gen_server.py | **REAL** | MCP-compliant image generation via OpenAI-compatible APIs. Real HTTP calls. |
| memory_server.py | **REAL** | Memory CRUD operations (list, add, edit, delete, search) connected to core/memory.py. Real implementations. |
| ag_server.py | **REAL but FRAGILE** | RAG document management, but depends on PersonalDocsManager which is a STUB (missing methods). Calls to dd_directory, emove_directory, get_indexed_directories will hit AttributeError. |
| _common.py | **REAL** | Shared constants (	runcate(), timeouts) |

**Status: REAL** — All MCP servers have real implementations. ag_server.py is fragile due to stub dependency.

---

### 9. rain/ — Cognitive Systems

| Component | Status | Evidence |
|---|---|---|
| epistemic_tagger.py | **REAL** | Source-based response classification with [VERIFIED], [ASSUMED], [UNCERTAIN] tags. Strip/re-tag workflow. |
| UnifiedBrain.py | **REAL** | Unified cognitive processing |
| prompt_optimizer.py | **REAL** | LLM-based prompt optimization with iterative improvement |
| easoning_engine.py | **REAL** | Structured reasoning |
| cognitive_patterns.py | **REAL** | Pattern detection and matching |
| execution_context.py | **REAL** | Context management |

**Status: REAL**

---

### 10. core/agi_core.py — AGI Core

| Aspect | Finding |
|---|---|
| start() | **STUB** — Logs "Started" but background loop is commented as "would go here" |
| solve() | **REAL** — Delegates to gent_registry.run("ORACLE", ...) |
| set_goal() | **REAL** — Creates background task via _run_goal() |
| _run_goal() | **REAL** — Delegates to ORACLE agent |
| get_status() | **REAL** — Returns real settings + agent list |
| **Background loop** | **STUB** — Commented out at line 76: # Background loop would go here |

**Status: PARTIAL STUB** — The AGI API endpoints work but the autonomous background loop that the system was designed for does not exist.

---

### 11. core/sub_agents/ — Sub-Agent System

| Component | Status | Evidence |
|---|---|---|
| gents/forge.py | **REAL** — Uses smolagents CodeAgent if available, falls back to standard generation |
| gents/nexus.py | **REAL** — Orchestrator agent with execution loop |
| ase_agent.py | **REAL** — Base agent class with status, execute, hooks |
| egistry.py | **REAL** — Agent registry with run, list, get |

**Status: REAL** — But forge.py depends on smolagents which is conditionally imported. Falls back gracefully.

---

## SUMMARY TABLE

| Component | Status | Notes |
|---|---|---|
| gent/ directory | N/A | Does not exist |
| skills/library/ (50 skills) | **SHOWCASE** | All 50 skills are in library/ but SkillManager reads from installed/ (empty). Never loaded. |
| core/personal_docs.py | **STUB** | extract_pdf_text is real, but index_personal_documents and search are stubs |
| core/security_audit.py | **REAL** | Actual config/filesystem/network/auth scanning |
| i_os/ package | **MIXED** | 60% REAL, 20% GHOST (planner, memory depend on missing jarvis_os), 10% SHOWCASE (code_agent_handler), 10% unused |
| 	ools/ root package | **REAL (DISCONNECTED)** | All 19 tools are real but not registered in core/tools/execution.py dispatcher |
| ssistant/voice_pipeline.py | **REAL** | Full pipeline with STT, TTS, wake word, emotion detection |
| mcp/ servers | **REAL** | All servers have real implementations (5 servers) |
| rain/ cognitive systems | **REAL** | All 6 components are real |
| core/agi_core.py | **PARTIAL STUB** | API endpoints work, background loop does not exist |
| core/sub_agents/ | **REAL** | Forge, Nexus, registry all real |

---

## KEY SHOWCASE FINDINGS

### Critical SHOWCASE — skills/library/ (50 skills)
These 50 skills look complete in the file tree and have real code, but the SkillManager is configured to read from skills/installed/ (empty directory). There is no mechanism that copies or links library/ → installed/. The load_all() method finds nothing. Every skill is a fully-realized implementation that never runs.

**Fix:** Either change SKILLS_DIR to point to library/, or add an install step that copies skills from library/ to installed/.

### SHOWCASE — i_os/tool_registry.py:107 code_agent_handler
`python
def code_agent_handler(args: dict[str, Any]) -> dict[str, Any]:
    task = args.get("task")
    return {"success": True, "message": f"Code agent would run: {task}"}
`
This handler always returns success but never actually executes any code. It's registered as a real tool in the AI OS but performs zero work.

### GHOST — i_os/planner.py and i_os/memory.py
Both delegate to jarvis_os.* which is NOT installed:
`python
try:
    from jarvis_os.core.planner import PlanningEngine
except ImportError:
    PlanningEngine = None  # Crashes later with RuntimeError
`
These are legacy adapter stubs that will always crash at runtime.

### STUB — core/personal_docs.py:49-58
`python
class PersonalDocsManager:
    def index_personal_documents(self, directory: str) -> dict:
        logger.info(f"PersonalDocsManager.index not implemented")
        return {"indexed": 0, "errors": 0}
    def search(self, query: str, k: int = 5) -> list[dict]:
        return []
`
Explicit stub. Worse, mcp/rag_server.py calls dd_directory(), emove_directory(), and get_indexed_directories() on this class — methods that don't exist, causing AttributeError at runtime.
