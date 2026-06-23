# PHASE 5 — Feature Reality Audit

For every advertised feature, determine actual implementation status.
No assumptions. Every claim verified by reading actual code.

---

## Grading Rubric

| Grade | Meaning | Definition |
|-------|---------|------------|
| ✅ IMPLEMENTED | Complete execution path from input to runtime | All layers connected |
| ⚠️ PARTIAL | Core logic exists but incomplete path | Missing routes, handlers, or integration |
| ❌ FAKE | Declared/advertised but no implementation | Stub, placeholder, or no-op |
| 💀 BROKEN | Code exists but returns error/disabled | BROKEN_TOOLS, disabled features |
| 🟡 DEAD | Code exists but unreachable | Commented-out routes, never-called functions |

---

## 1. Memory

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| TieredMemory: hot (RAM) → warm (ChromaDB/mem0) → cold (SQLite) | `memory/tiered_memory.py:74-125` |
| MemoryFacade: unified store/recall/format_context | `memory/memory_facade.py:62-176` |
| ConversationManager: JSON-persisted sessions | `core/session.py:54-92` |
| Context injection into prompts | `core/context_builder.py:34-44` |
| DecisionMemory: JSON-backed action→outcome learning | `memory/decision_memory.py:24-99` |
| Preferences: SQLite-backed key-value store | `memory/preferences.py:18-65` |
| Brain memory: 4 SQLite stores (episodic/semantic/task/decision) | `brain/memory/*.py` |
| Vector memory: ChromaDB collection `odysseus_memories` | `core/memory_vector.py:29-125` |
| Embedding memory: SQLite + Ollama nomic-embed-text | `memory/embedding_memory.py:36-118` |
| Agent checkpoints: SQLite with 7-day GC | `core/persistence/store.py:40-231` |

**Limitations:**
- Triple-write amplification (same data in ChromaDB + JSON + SQL)
- Full-scan cosine similarity in `embedding_memory.py` (O(n), degrades with scale)
- No cross-backend deduplication
- Hot tier (RAM) lost on restart (but warm/cold persist)

---

## 2. Browser Automation

**Grade:** ⚠️ PARTIAL

| Evidence | File:Line |
|----------|-----------|
| `do_vision_browser` tool registered | `core/tools/execution.py:1617` |
| Vision browser implementation | `core/tools/vision_tools.py` |
| Web search tool via `comprehensive_web_search` | `core/tools/execution.py:763-816` |
| Web fetch tool via `fetch_webpage_content` | `core/tools/execution.py:818-878` |
| Chrome launch via WebSocket | `core/routes/websocket.py:691` (shell=True — HIGH risk) |
| `/api/browser` REST endpoint | `operations.py:583` |

**Missing:**
- No headless browser agent with navigation/click/scroll
- No `playwright` or `selenium` integration found
- Vision browser is a screenshot→analyze cycle, not interactive browsing
- Chrome launch is a simple `start chrome` — no programmatic control

---

## 3. Voice

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| VoiceEngine: end-to-end pipeline | `assistant/voice_pipeline.py` |
| STT: 3 providers (faster_whisper, deepgram, azure_speech) | `assistant/providers/*stt*.py` |
| TTS: 2 providers (kokoro, edge_tts) | `assistant/providers/*tts*.py` |
| Wake word detection + registry + watchdog | `assistant/wake_word.py` |
| Audio emotion detection (MFCC → rule-based classifier) | `core/audio_emotion.py:128-289` |
| Voice REST endpoints: `/stt`, `/stt/local`, `/stt/base64`, `/tts` | `core/routes/voice.py:28-86` |
| Voice WebSocket: `/voice` (binary audio in/out) | `core/routes/voice.py:145` |
| TTS stream WebSocket: `/tts/stream` | `core/routes/voice.py:123` |
| Voice settings in config_registry (30+ entries) | `core/config_registry.py:91-123` |

**Limitations:**
- No streaming STT (all POST-based, full utterance at a time)
- Emotion detection rule-based (not ML model)
- Wake word detection not verified (depends on platform support)

---

## 4. Agent Loop

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| StateGraph: 10-node execution engine | `core/graph/graph.py:25-88` |
| AgentState: 40-field state dataclass | `core/graph/state.py:55-198` |
| 10 node implementations (setup → think → tool_call → verify → ...) | `core/graph/nodes.py:71-1193` |
| Streaming SSE output | `core/agent_loop.py:31-87` |
| Stuck detection (recent_call_sigs deque, maxlen=6) | `core/graph/state.py:147-155` |
| Loop breaker (>15 rounds) | `core/graph/edges.py` |
| Tool block parsing and execution | `core/tools/execution.py` |
| Fallback chains for model providers | `core/model_providers/hybrid.py:177-215` |

**Limitations:**
- Max 15 rounds / 25 tool calls before forced finish
- No dynamic tool RAG in loop (tools are pre-selected in setup node)
- Single LLM call per think node (no tree-of-thought)

---

## 5. Project Analysis

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| WorkspaceManager: full project scan (git, build system, languages, frameworks) | `core/workspace_manager.py:61-666` |
| RepositoryAnalyzer: import graphs, auth, DB, API routes, dead code | `core/repository_analyzer.py:20-395` |
| Multi-language support: Python, JavaScript, Java, etc. | `core/workspace_manager.py:402-420` |
| Build system detection: gradle, maven, make, cmake, cargo, npm, etc. | `core/workspace_manager.py:131-156` |
| Entry point detection | `core/workspace_manager.py:456-488` |
| CLI command: `jarvis.py understand` | `cli_commands.py:2173-2226` |

**Limitations:**
- Import graph is line-by-line parsing (not AST-based)
- Dead code detection is file-level (not function-level)
- No runtime coverage analysis

---

## 6. Build Generation

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| CompilerRepairEngine: 170+ regex patterns → 30+ fix categories → 18 fix functions | `brain/compiler_repair_engine.py:225-733` |
| 7 deterministic repair modules | `brain/repair_modules/*.py` |
| FailureMemory: pattern-based error repair (exact → prefix → regex) | `brain/automation/loop.py:50-170` |
| ArchitecturalMemory: project context learning | `brain/automation/loop.py:270-340` |
| TaskResolver: LLM plan → tool calls | `brain/task_resolver.py:91-283` |
| CLI command: `jarvis.py build` | `cli_commands.py:2302-2331` |

**Limitations:**
- The AGENTS.md acknowledges javac compilation is the current bottleneck (46 errors for NoteTaker benchmark)
- Java-only fix modules (no Python/JS/Go support)

---

## 7. Repair System

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| Automated build → detect error → classify → repair → rebuild loop | `brain/automation/loop.py:2548-2600` |
| Priority chain: exact match → prefix match → regex → deterministic rules → LLM → vision search | `brain/automation/loop.py` |
| 10+ deterministic fix categories (imports, class names, manifest, layouts, resources, dependencies, etc.) | `brain/repair_modules/__init__.py:29-38` |
| Pattern learning: successful repairs stored as regex patterns | `brain/automation/loop.py:125-170` |

**Limitations:**
- Only targets Android/Java compilation errors
- No TypeScript, Python, or general language repair

---

## 8. Multi-Step Planning

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| DAG task graph with cycle detection + topological sort | `brain/planner/task_graph.py:56-269` |
| Goal system: create → prioritize → execute → complete/fail | `brain/goals/goal_manager.py:16-306` |
| Planner: generates 3-node DAG (create_dir → write_file → run_command) | `brain/planner/planner.py:13-66` |
| GoalGenerator: auto-creates goals from world state | `brain/goal_generator.py:30-178` |
| Persistence: checkpoint/resume (SQLite, 7-day GC) | `brain/persistence.py:46-313` |
| Event-driven goal flow via EventBus | `brain/events/event_bus.py` |

---

## 9. Vision

**Grade:** ⚠️ PARTIAL

| Evidence | File:Line |
|----------|-----------|
| Vision REST endpoints: `/api/vision/screen`, `/api/vision/analyze` | `core/routes/vision.py:25-65` |
| Vision browser tool: screenshot + analyze | `core/tools/vision_tools.py` |
| Face recognition module | `vision/face_recognition.py` |
| MultiModalPipeline: vision provider support | `core/multimodal/pipeline.py:40-179` |
| Provider support: Ollama (moondream), OpenAI, Anthropic (native) | `core/model_providers/*.py` |
| Face detection REST endpoints | `core/routes/operations.py:717-758` |

**Missing:**
- No real-time video processing
- No object detection/tracking
- No OCR pipeline
- Face recognition quality depends on model choice

---

## 10. PC Control

**Grade:** ⚠️ PARTIAL

| Evidence | File:Line |
|----------|-----------|
| PC automation endpoints: screenshot, volume, lock, sleep, shutdown | `automation/routes.py:164-195` |
| PC agent module | `pc_agent/computer_agent.py` |
| `/computer` REST endpoint for NL-based PC automation | `core/routes/control.py:24` |
| `computer_control` tool | `core/tools/execution.py` |

**Missing:**
- No mouse/keyboard input simulation
- No window management
- No clipboard integration via tool (separate skill exists at `skills/library/system/clipboard/main.py`)
- `subprocess.Popen([cmd])` in `pc_automation.py:377` — potential argument injection on non-Windows

---

## 11. Session Management

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| ConversationManager: JSON-persisted session files | `core/session.py:40-196` |
| SessionManager: in-memory active session registry | `core/session.py:198-334` |
| HierarchicalSession: parent/child session trees | `core/session.py:198-334` |
| Agent checkpoints: SQLite pause/resume | `core/persistence/store.py` |
| `sessions_spawn` tool for sub-session creation | `core/tools/sub_agents/tool.py` |
| Sub-agent session support | `core/sub_agents/tool.py` |

**Limitations:**
- Session `.compact()` requires explicit call (no automatic pruning)
- No session search/query capability
- `manage_session` tool is in BROKEN_TOOLS

---

## 12. Tool Execution

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| 49 implemented tools in `_TOOL_HANDLERS` | `core/tools/execution.py:1600-1652` |
| MCP bridge with direct fallback | `core/tools/execution.py:1570-1598` |
| Path confinement system: allowlist + sensitive path deny list | `core/tools/execution.py:68-186` |
| Session-level persistent shell | `core/tools/persistent_shell.py` |
| Background jobs (`#!bg` marker) | `core/tools/bg_jobs.py` |
| Hot file tracking | `core/tools/hot_files.py` |
| Tool security: NON_ADMIN_BLOCKED list | `core/tools/security.py:27-36` |
| Tool execution with progress SSE streaming | `core/graph/nodes.py:729-878` |

**Limitations:**
- 10 BROKEN tools return "disabled" (manager_session, manage_memory, ui_control, etc.)
- 2 ghost tools described in prompts but not implemented (build_repomap, code_graph)
- bg_jobs uses `create_subprocess_shell()` — CRITICAL security issue

---

## 13. Autonomous Loop (Brain/AGI)

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| UnifiedBrain: central orchestrator with 20+ subsystems | `brain/UnifiedBrain.py:73-543` |
| Full event system: 18 typed events, pub/sub | `brain/events/event_types.py`, `event_bus.py` |
| 4 observers: filesystem, system monitor, time, observer lifecycle | `brain/observers/*.py` |
| Cognitive patterns: 10 reasoning strategies | `brain/cognitive_patterns.py:33-165` |
| Self-improvement: A/B testing with auto-revert | `brain/self_improvement.py:32-231` |
| Skill acquisition: n-gram pattern detection from traces | `brain/skill_acquisition.py:34-231` |
| Learning engine: behavior modification from lessons | `brain/learning_engine.py:14-150` |
| Compiler repair engine: 170+ regex patterns | `brain/compiler_repair_engine.py:89-225` |

**Limitations:**
- Cognitive patterns use LLM calls (not local computation) — high latency
- Self-improvement A/B tests require manual review
- Skill acquisition has not been validated on real usage data

---

## 14. API Routes (REST)

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| 90+ REST endpoints registered in FastAPI app | `core/main.py:192-511` |
| CORS, rate limiting, auth middleware | `core/main.py:114-188` |
| SSRF protection on all URL fetches | `core/ssrf.py:106-163` |
| Auth: token-based session auth | `core/main.py:146` |

**Limitations:**
- ~28 endpoints not wired to any frontend page
- `/api/hybrid/*` and `/api/mobile/*` routes commented out
- Many endpoints have no authentication (see WEBSOCKET_AUDIT.md)

---

## 15. WebSocket

**Grade:** ✅ IMPLEMENTED

| Evidence | File:Line |
|----------|-----------|
| 8 WebSocket endpoints: chat_stream, agent_stream, logs, mcp/bridge, terminal, voice, tts/stream, device-specific | Various |
| SSE streaming via `StreamingResponse` | `core/routes/chat.py:75-107` |
| Word-by-word token streaming | `core/routes/websocket.py` |
| Tool call progress events | `core/graph/nodes.py:729-878` |
| 60s ping interval, 30s ping timeout | `core/main.py:715-716` |

**Limitations:**
- All WebSocket endpoints unauthenticated
- No reconnection logic (except client-side in web UI with 3s delay)
- No backpressure handling

---

## 16. Authentication

**Grade:** ⚠️ PARTIAL

| Evidence | File:Line |
|----------|-----------|
| Session token auth middleware | `core/main.py:146` |
| OAuth providers support | `core/routes/auth.py` |
| TOTP secrets | `core/auth.py:380-412` |
| API key vault | `core/api_key_vault.py` |

**Limitations:**
- Auth middleware exempts `/ws/*`, `/health`, `/docs`, `/static`, `/`, `/{path:path}`
- Most `api/` route modules have no auth middleware at all
- Login page in web UI just redirects to `/`
- Token stored in localStorage (XSS-vulnerable)

---

## Summary Scorecard

| Feature | Grade | Classification | Key Gap |
|---------|-------|---------------|---------|
| Memory | ✅ IMPLEMENTED | SAFE | Triple-write, no dedup |
| Browser Automation | ⚠️ PARTIAL | WARNING | No interactive browsing |
| Voice | ✅ IMPLEMENTED | SAFE | No streaming STT |
| Agent Loop | ✅ IMPLEMENTED | SAFE | No dynamic tool RAG |
| Project Analysis | ✅ IMPLEMENTED | SAFE | File-level only |
| Build Generation | ✅ IMPLEMENTED | SAFE | Java-only |
| Repair System | ✅ IMPLEMENTED | SAFE | Java-only |
| Multi-Step Planning | ✅ IMPLEMENTED | SAFE | 3-node only |
| Vision | ⚠️ PARTIAL | WARNING | No real-time video |
| PC Control | ⚠️ PARTIAL | WARNING | No mouse/kbd input |
| Session Management | ✅ IMPLEMENTED | SAFE | No auto-prune |
| Tool Execution | ✅ IMPLEMENTED | SAFE | 10 broken, 2 ghost |
| Autonomous Loop | ✅ IMPLEMENTED | SAFE | High latency |
| API Routes | ✅ IMPLEMENTED | SAFE | 28 unused endpoints |
| WebSocket | ✅ IMPLEMENTED | SAFE | No auth on WS |
| Authentication | ⚠️ PARTIAL | WARNING | Major auth gaps |
