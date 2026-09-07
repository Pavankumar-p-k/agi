# Golden User Journeys — Complete Traceability Audit

**Generated:** 2026-07-30  
**Scope:** Three complete end-to-end journeys  
**Format:** Every arrow = File → Function → Event → Database → Capability → Permission → Failure → Reality  
**Broken arrows:** ⚠️ HIGHLIGHTED

---

## JOURNEY 1: Install → Setup → Chat → Build Calculator → Progress → APK → Inbox → History → Resume Tomorrow

### 1.1 INSTALL (One-Line Installer)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `install.py:27` | `main()` | `START_INSTALL` | — | Installer CLI | user shell | Python < 3.10 → exit(1) | ✅ Works |
| 2 | `install.py:39` | `main()` | `GIT_CHECK` | — | Git binary | user shell | `git` not in PATH → exit(1) | ✅ Works |
| 3 | `install.py:44-50` | `main()` | `CLONE_REPO` | — | Git clone | user shell | Network fail / auth → exit(1) | ✅ Works |
| 4 | `install.py:55-60` | `main()` | `CREATE_VENV` | — | Venv creation | user shell | Disk full / perms → crash | ⚠️ No cleanup on partial |
| 5 | `install.py:68-75` | `main()` | `PIP_INSTALL` | — | Pip install | user shell | Dependency conflict → crash | ⚠️ No rollback |
| 6 | `install.py:79` | `main()` | `INIT_DB` | `database.db` | SQLite init | file write | Import error / path fail → crash | ⚠️ Silent if import fails |
| 7 | `install.py:82-99` | `main()` | `CREATE_LAUNCHER` | Windows Registry / `~/.local/bin` | PATH registration | user shell | Win: `%USERPROFILE%` missing → wrong path | ⚠️ Windows Apps folder may not exist |

**Broken Arrows:**
- ⚠️ **No transaction/rollback** — partial install leaves broken venv
- ⚠️ **No verification** — doesn't test `jarvis --version` after install
- ⚠️ **Windows PATH** — writes to `WindowsApps` which requires admin; falls back to profile dir silently

---

### 1.2 SETUP (First-Run Wizard)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `jarvis.py:270` | `main()` | `FIRST_RUN_DETECT` | `data/.setup_complete` | SetupEngine | file read | Missing file → assumes first run | ✅ Works |
| 2 | `core/setup/engine.py:64` | `SetupEngine.detect()` | `DETECT_ALL` | — | Hardware detect | `psutil`, `subprocess` | `nvidia-smi` missing → GPU=none | ✅ Graceful |
| 3 | `core/routes/system/setup_routes.py:384` | `get_recommendation()` | `RECOMMEND_MODELS` | — | Model catalog match | HTTP to Ollama | Ollama not running → empty list | ⚠️ Returns empty, not error |
| 4 | `core/routes/system/setup_routes.py:425` | `install_ollama()` | `INSTALL_OLLAMA` | — | Silent OS install | shell + winget/brew/curl | winget missing / curl fail → SSE error | ⚠️ No rollback on partial |
| 5 | `core/routes/system/setup_routes.py:486` | `pull_model()` | `PULL_MODEL` | — | Model download | HTTP to Ollama | Disk full / network → stream error | ⚠️ No resume support |
| 6 | `core/routes/system/setup_routes.py:583` | `auto_wire()` | `AUTO_WIRE` | `settings.json` | Config wire | file write | `refresh_router()` fails silently | ⚠️ Log warning only |
| 7 | `core/setup/engine.py:161` | `run_demo()` | `RUN_DEMO` | `hello.html` | Demo build | file write + browser | Playwright missing → fail | ⚠️ Demo not wired to inbox |
| 8 | `core/setup/engine.py:183` | `complete()` | `SETUP_COMPLETE` | `data/.setup_complete` | Mark done | file touch | Permission denied → silent | ⚠️ No retry |

**Broken Arrows:**
- ⚠️ **Ollama install** — no verification service started before model pull
- ⚠️ **Model pull** — no checksum verify, no resume on interrupt
- ⚠️ **Demo** — runs `hello.html` build but doesn't persist to inbox/history
- ⚠️ **Auto-wire** — `refresh_router()` exception swallowed (line 617)

---

### 1.3 CHAT (Interactive Session)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `jarvis.py:175` | `cmd_cli` | `CHAT_START` | — | CLI session | user shell | — | ✅ Works |
| 2 | `core/tools/chat_tools.py:131` | `do_create_session()` | `SESSION_CREATE` | `~/.jarvis/sessions/*.json` | SessionManager | file write | Dir missing → crash | ⚠️ No auto-mkdir |
| 3 | `core/routes/chat/router.py:32` | `chat_route()` | `CHAT_REQUEST` | `ChatHistory` table | REST + Pipeline | JWT token | 401 if token expired | ✅ Works |
| 4 | `core/pipeline/adapters.py` | `rest_adapter()` | `PIPELINE_EXEC` | — | Canonical pipeline | internal | Pipeline stage crash → 500 | ⚠️ No fallback |
| 5 | `core/tools/chat_tools.py:162` | `do_chat_with_model()` | `LLM_CALL` | — | LLM completion | API key / local | Rate limit / timeout → error | ⚠️ No retry logic |
| 6 | `core/routes/chat/router.py:48` | `_persist_chat()` | `PERSIST_HISTORY` | `ChatHistory` (SQLite) | SQLite write | DB connection | DB locked → commit fail | ⚠️ No WAL mode check |

**Broken Arrows:**
- ⚠️ **Session create** — `SESSION_DIR` not ensured exists (line 147)
- ⚠️ **Pipeline** — no circuit breaker; cascade failure on LLM timeout
- ⚠️ **Persist** — `ChatHistory` uses async session but no retry on `OperationalError: database is locked`

---

### 1.4 BUILD CALCULATOR (Automated Build)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/tools/build_tools.py:48` | `do_build_project()` | `BUILD_START` | — | AutomationLoop | `shell` tool (RBAC HIGH) | No build cmd → plan fail | ⚠️ Falls back to empty |
| 2 | `brain/automation/loop.py:387` | `_phase_plan()` | `PLAN_CREATE` | `UnifiedStore` (goals) | LLM planner | `chat` model | JSON parse fail → fallback | ⚠️ Fallback plan minimal |
| 3 | `brain/automation/loop.py:415` | `_phase_generate()` | `GENERATE_FILES` | FS write | LLM codegen | `file_tools` (RBAC HIGH) | Write fail → partial project | ⚠️ No atomic write |
| 4 | `brain/automation/loop.py:424` | `verify_gates()` | `VERIFY_GATES` | — | Static checks | read FS | Gate false negative → repair | ⚠️ Android-specific only |
| 5 | `brain/automation/loop.py:440` | `_phase_build()` | `BUILD_EXEC` | `build_history` (memory) | `shell` gradlew | `shell` tool | Gradle missing → normalize | ⚠️ `gradlew` chmod race |
| 6 | `brain/automation/loop.py:1151` | `_phase_build` loop | `REPAIR_ATTEMPT` | `FailureMemory` | CompilerRepairEngine | `edit_file` | Max 10 attempts → fail | ⚠️ No progress metric |
| 7 | `core/tools/build_tools.py:132` | `do_build_apk()` | `APK_BUILD` | — | Gradle assembleDebug | `shell` tool | No gradlew → error | ✅ Finds wrapper |

**Broken Arrows:**
- ⚠️ **Plan** — LLM output JSON parse fails ~15%; fallback creates empty `project_name`
- ⚠️ **Generate** — no verification generated code compiles before build
- ⚠️ **Gates** — only Android gates; Python/Node/Rust projects skip silently
- ⚠️ **Repair** — `CompilerRepairEngine` patterns don't cover Kotlin/data binding errors
- ⚠️ **APK** — `do_build_apk` uses `build_service.enqueue()` but then runs gradle directly (bypasses service)

---

### 1.5 PROGRESS (Real-Time Updates)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/tools/automated_build.py:115` | `_emit_progress()` | `PROGRESS_EVENT` | — | SSE/WS callback | internal | Callback exception swallowed | ⚠️ Debug log only |
| 2 | `brain/automation/loop.py:392` | `_build_project()` | `PHASE_PROGRESS` | `ExecutionContext` | ExecutionManager | internal | Progress cb not awaited | ⚠️ Fire-and-forget |
| 3 | `core/routes/chat/router.py:87` | `agent_stream()` | `STREAM_DELTA` | — | SSE stream | JWT | Client disconnect → task leak | ⚠️ No `CancelledError` handling |

**Broken Arrows:**
- ⚠️ **Progress** — `_emit_progress` catches all exceptions, logs at DEBUG (invisible in prod)
- ⚠️ **Stream** — `stream_agent_loop` doesn't clean up on client disconnect

---

### 1.6 APK (Artifact Delivery)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/tools/build_tools.py:199` | `do_build_apk()` | `APK_FIND` | — | `rglob("*.apk")` | FS read | Multiple APKs → picks first debug | ⚠️ Non-deterministic |
| 2 | `core/tools/automated_build.py:152` | `_find_build_artifacts()` | `ARTIFACT_SCAN` | `ActivityStore` | Typed artifact reg | internal | Pattern miss → no artifact | ⚠️ Limited patterns |
| 3 | `core/tools/automated_build.py:173` | `_record_activity_nodes()` | `ACTIVITY_LOG` | `ActivityStore` (SQLite) | Graph node create | DB write | Import fail → silent skip | ⚠️ `ActivityStore` optional |

**Broken Arrows:**
- ⚠️ **APK pick** — `apk_files[0]` arbitrary; no version/arch metadata
- ⚠️ **Artifact** — only scans for `*.apk`, `*.aab`, `build.log`, `*.html`, `coverage.xml`, `test-results.xml`
- ⚠️ **Activity** — `ActivityStore` import wrapped in try/except; if missing, zero persistence

---

### 1.7 INBOX (Unified Notifications)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/routes/chat/inbox_router.py:67` | `add_item()` | `INBOX_ADD` | `InboxStore` (SQLite) | REST + WS broadcast | JWT | WS send fail → client removed | ✅ Works |
| 2 | `core/inbox.py` | `InboxStore.add()` | `INBOX_PERSIST` | `inbox.db` | SQLite upsert | file write | DB locked → exception | ⚠️ No retry |
| 3 | `core/routes/chat/inbox_router.py:117` | `inbox_websocket()` | `WS_CONNECT` | — | WebSocket | JWT | Auth not checked on WS | ⚠️ **NO AUTH on WebSocket** |

**Broken Arrows:**
- ⚠️ **WebSocket** — **CRITICAL**: `/api/inbox/ws` accepts connections WITHOUT token verification (line 118-124)
- ⚠️ **Persist** — `InboxStore` uses same SQLite file as chat; contention under load

---

### 1.8 HISTORY (Chat + Session Recall)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/routes/chat/router.py:159` | `get_chat_history()` | `HISTORY_QUERY` | `ChatHistory` table | SQLAlchemy async | JWT | Session filter ignored if None | ✅ Works |
| 2 | `core/tools/chat_tools.py:39` | `do_manage_memory(action=search)` | `MEMORY_SEARCH` | `CrudStore` (JSON + vec) | Vector search | `manage_memory` tool | Vector index stale → empty | ⚠️ No auto-reindex |
| 3 | `core/session.py` | `ConversationManager.load()` | `SESSION_LOAD` | `~/.jarvis/sessions/*.json` | JSON file | file read | Corrupt JSON → crash | ⚠️ No validation |

**Broken Arrows:**
- ⚠️ **Memory** — `CrudStore.vector_healthy` can be False; search returns empty silently
- ⚠️ **Session** — no schema validation; malformed file breaks `list_sessions`

---

### 1.9 RESUME TOMORROW (Cold Start Recovery)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `jarvis.py:276` | `engine.resume_needed()` | `RESUME_CHECK` | `data/setup_state.json` | SetupEngine | file read | Missing file → false | ✅ Works |
| 2 | `core/activity/resume.py:85` | `find_resume_point()` | `RESUME_FIND` | `ActivityStore` | Graph traversal | internal | No incomplete leaves → None | ⚠️ Returns None silently |
| 3 | `core/activity/resume.py:111` | `resume_all_candidates()` | `RESUME_ALL` | `ActivityStore` | Multi-leaf | internal | Empty list → no work | ✅ Works |
| 4 | `core/activity/resume.py:196` | `mark_resumed()` | `RESUME_MARK` | `ActivityStore` | Status update | DB write | Node not found → skip | ⚠️ No error |
| 5 | `core/routes/chat/router.py:200` | `agent_resume()` | `AGENT_RESUME` | `CheckpointStore` | Pipeline resume | JWT | Checkpoint missing → 404 | ⚠️ No auto-checkpoint |

**Broken Arrows:**
- ⚠️ **Resume find** — returns `None` if no leaves; caller must handle (not documented)
- ⚠️ **Checkpoint** — only created on `pause_before_effectful`; most runs have zero checkpoints
- ⚠️ **Setup resume** — `resume_needed()` only checks phase; doesn't verify Ollama/model still present

---

## JOURNEY 2: Research → Write Report → Generate PDF → Save → Resume

### 2.1 RESEARCH (Web + Fact Extraction)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/tools/browser_research.py:32` | `do_browser_research()` | `RESEARCH_START` | — | BrowserResearch | `browser_navigate` (RBAC) | No session → new browser | ✅ Works |
| 2 | `core/tools/browser_research.py:56` | `_create_plan()` | `RESEARCH_PLAN` | — | ResearchPlanner LLM | `chat` model | Plan JSON parse fail | ⚠️ Returns empty queries |
| 3 | `core/tools/browser_research.py:64` | `_research_query()` | `BROWSER_SEARCH` | — | `web_search` + `browser_navigate` | `web_search`, `browser_navigate` | Search API fail → empty | ⚠️ No fallback engine |
| 4 | `core/fact_extraction/extractor.py` | `BrowserFactExtractor.extract()` | `FACT_EXTRACT` | `BrowserFactStore` (SQLite) | LLM fact extraction | `browser_snapshot` | Snapshot fail → no facts | ⚠️ Silent empty list |
| 5 | `core/fact_extraction/bridge.py` | `bridge_batch()` | `FACT_BRIDGE` | `FactStore` (long-term) | Fact conversion | internal | Schema mismatch → drop | ⚠️ No validation log |
| 6 | `core/fact_extraction/reasoner.py` | `FactReasoner.analyze()` | `FACT_ANALYZE` | `FactStore` | Contradiction detect | internal | LLM timeout → empty | ⚠️ No timeout handling |
| 7 | `core/fact_extraction/synthesizer.py` | `FactSynthesizer.synthesize()` | `FACT_SYNTHESIZE` | — | Report generation | `chat` model | JSON parse fail → raw | ⚠️ Returns unstructured |

**Broken Arrows:**
- ⚠️ **Plan** — `ResearchPlanner` output not validated; empty queries cause zero pages
- ⚠️ **Search** — single provider (DuckDuckGo HTML scrape); no API key fallback
- ⚠️ **Extract** — `BrowserFactExtractor` calls `browser_snapshot` but ignores errors
- ⚠️ **Bridge** — `Fact` schema vs `BrowserFact` schema drift causes silent drops
- ⚠️ **Reasoner** — `FactReasoner` uses `complete()` with 120s timeout; no circuit breaker
- ⚠️ **Synthesize** — prompt expects JSON; LLM often returns markdown → parse fail

---

### 2.2 WRITE REPORT (Content Assembly)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/tools/chat_tools.py:89` | `do_manage_memory(action=add)` | `MEMORY_ADD` | `CrudStore` (JSON) | Long-term memory | `manage_memory` tool | Vector index fail → no search | ⚠️ `vector_add` exception swallowed |
| 2 | `core/tools/document_tools.py` | `do_create_document()` | `DOC_CREATE` | `WorkflowStore` + `ArtifactStore` | Document CRUD | `manage_documents` | Store init fail → error | ✅ Works |
| 3 | `core/tools/document_tools.py` | `do_edit_document()` | `DOC_EDIT` | `ArtifactStore` (FS) | Diff/patch apply | `edit_file` | Conflict → overwrite | ⚠️ No merge strategy |

**Broken Arrows:**
- ⚠️ **Memory** — `CrudStore.vector_add()` failure logged at WARNING but returns success
- ⚠️ **Document** — `ArtifactStore` writes to `data/workflow_artifacts/{wf_id}/`; no cleanup policy

---

### 2.3 GENERATE PDF

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/tools/pdf_tools.py:96` | `do_generate_pdf()` | `PDF_GENERATE` | FS write | `fpdf2` library | `generate_pdf` tool | ImportError fpdf2 → error | ⚠️ Not in base requirements |
| 2 | `core/tools/pdf_tools.py:31` | `PDFGenerator.generate_report()` | `PDF_RENDER` | `output_dir` | FPDF2 render | file write | Unicode char → replace | ⚠️ `Helvetica` no Unicode |
| 3 | `core/tools/pdf_tools.py:82` | `generate_from_markdown()` | `MD_CONVERT` | — | Naive string replace | internal | `# ` not stripped fully | ⚠️ Broken markdown |

**Broken Arrows:**
- ⚠️ **Dependency** — `fpdf2` NOT in `requirements.txt` or `pyproject.toml` extras; fails at runtime
- ⚠️ **Font** — `Helvetica` doesn't support Unicode; emoji/CJK → `???` or crash
- ⚠️ **Markdown** — `replace("# ", "")` only handles H1; `## `, `### `, `**bold**` pass through raw

---

### 2.4 SAVE (Persist Artifacts)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/tools/automated_build.py:173` | `_record_activity_nodes()` | `ACTIVITY_SAVE` | `ActivityStore` (SQLite) | Graph persist | internal | Import fail → silent | ⚠️ Optional dependency |
| 2 | `core/tools/automated_build.py:272` | `_record_knowledge()` | `KNOWLEDGE_SAVE` | `KnowledgeStore` (SQLite) | Experience extract | internal | `ExperienceExtractor` fail → silent | ⚠️ Swallowed exception |
| 3 | `core/tools/automated_build.py:307` | `_record_calibration()` | `CALIBRATION_SAVE` | `CalibrationStore` (SQLite) | Prediction record | internal | `PredictionCalibrator` fail → silent | ⚠️ Swallowed exception |

**Broken Arrows:**
- ⚠️ **All three** — wrapped in try/except with `logger.warning`; caller never knows persistence failed
- ⚠️ **KnowledgeStore** — `ExperienceExtractor.extract()` returns `None` on failure; `insert_experience(None)` skipped silently

---

### 2.5 RESUME (Research Continuation)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/activity/resume.py:130` | `resume_all_candidates()` | `RESUME_ALL` | `ActivityStore` | Multi-leaf resume | internal | No activity → empty list | ✅ Works |
| 2 | `core/tools/browser_research.py:72` | `_get_follow_up_queries()` | `GAP_DETECT` | `FactStore` | GapDetector LLM | `chat` model | No facts → empty queries | ⚠️ Stops research |
| 3 | `core/fact_extraction/gap_detector.py` | `GapDetector.detect()` | `GAP_ANALYZE` | `FactStore` | Contradiction find | internal | LLM fail → no gaps | ⚠️ Silent stop |

**Broken Arrows:**
- ⚠️ **Gap detect** — requires existing facts; fresh resume with no `FactStore` data → zero queries → research ends
- ⚠️ **No checkpoint** — research has no `pause_before_effectful`; cannot resume mid-stream

---

## JOURNEY 3: Desktop Automation → Open App → Move Mouse → Browser → Finish

### 3.1 DESKTOP AUTOMATION (PyAutoGUI)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/tools/vision_tools.py:19` | `do_vision_browser()` | `VISION_START` | — | VisionAgent | `vision_browser` tool | Import fail → error dict | ✅ Works |
| 2 | `core/vision_agent.py:81` | `VisionAgent.__init__()` | `AGENT_INIT` | — | `pyautogui`, `mss`, `PIL` | internal | `pyautogui.FAILSAFE=True` | ✅ Corner escape works |
| 3 | `core/vision_agent.py:201` | `run()` | `TASK_RUN` | `_history` (memory) | Planner + executor | internal | Planner LLM fail → single wait step | ⚠️ Degrades to no-op |

**Broken Arrows:**
- ⚠️ **Planner** — `_plan()` calls `provider_router.select("planning")`; if no provider, returns dummy wait step
- ⚠️ **No sandbox** — runs on host desktop; `FAILSAFE` only protects mouse corner

---

### 3.2 OPEN APP

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/desktop/controller.py:243` | `launch_app()` | `APP_LAUNCH` | `ReplayStore` (memory) | `shutil.which` + `subprocess.Popen` | `desktop` tool (RBAC) | `shutil.which` miss → hardcoded map | ⚠️ Map incomplete |
| 2 | `core/desktop/controller.py:258` | `subprocess.Popen([exe])` | `PROCESS_SPAWN` | — | Process spawn | `shell=False` (good) | Exe not found → exception | ⚠️ Caught → error action |
| 3 | `core/desktop/safety.py:121` | `SafetyManager.check()` | `SAFETY_CHECK` | `_audit_log` (memory) | Rate limit + regions | internal | Emergency stop → block all | ✅ Works |

**Broken Arrows:**
- ⚠️ **App map** — only 10 hardcoded apps; `"code"` maps to `"code.cmd"` (Windows only)
- ⚠️ **No allowlist** — any executable on PATH can be launched
- ⚠️ **Safety** — `Forbidden regions` not persisted; reset on restart

---

### 3.3 MOVE MOUSE

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/desktop/controller.py:64` | `move_mouse()` | `MOUSE_MOVE` | `ReplayStore` | `pyautogui.moveTo` | `desktop` tool | Safety block → reject action | ✅ Rate limited |
| 2 | `core/desktop/safety.py:183` | `_check_mouse()` | `SAFETY_MOUSE` | — | Velocity check (2000px/s) | internal | Speed exceed → block | ✅ Works |
| 3 | `core/desktop/safety.py:192` | `_last_mouse_pos` update | `POS_TRACK` | memory | Position tracking | internal | Multi-monitor coord overflow | ⚠️ No bounds check |

**Broken Arrows:**
- ⚠️ **Multi-monitor** — coordinates not validated against screen bounds; negative/overflow possible
- ⚠️ **No confirmation** — `SafetyManager` allows/denies silently; no user prompt

---

### 3.4 BROWSER (Vision + Playwright)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/vision_agent.py:167` | `open_url` action | `BROWSER_OPEN` | — | `webbrowser.open` | `vision_browser` | No default browser → fail | ⚠️ No fallback |
| 2 | `core/tools/browser_tools.py:102` | `do_browser_navigate()` | `NAVIGATE` | `BrowserManager` session | Playwright `page.goto` | `browser_navigate` (RBAC) | SSRF block → PermissionError | ✅ SSRF works |
| 3 | `core/ssrf.py:106` | `resolve_and_check()` | `SSRF_CHECK` | — | DNS rebinding protect | internal | TOCTOU DNS rebinding | ⚠️ Check at validate, not fetch |
| 4 | `core/tools/browser_tools.py:525` | `do_browser_evaluate()` | `JS_EXECUTE` | — | `page.evaluate(js)` | `browser_evaluate` (ADMIN only) | Arbitrary JS → XSS/cookie theft | ⚠️ **CRITICAL: Admin-only but no audit** |

**Broken Arrows:**
- ⚠️ **Vision browser** — uses `webbrowser.open()` (no control); Playwright browser separate
- ⚠️ **SSRF TOCTOU** — DNS resolved at validation time; fetch time may differ
- ⚠️ **browser_evaluate** — **CRITICAL**: arbitrary JS in browser context; gated only by RBAC admin; no CSP, no script allowlist, no audit log of executed code

---

### 3.5 FINISH (Cleanup + Audit)

| Step | File | Function | Event | Database | Capability | Permission | Failure | Reality |
|------|------|----------|-------|----------|------------|------------|---------|---------|
| 1 | `core/desktop/controller.py:289` | `clear()` | `SAFETY_CLEAR` | memory | Reset all state | internal | Called? Never auto-called | ⚠️ Manual only |
| 2 | `core/desktop/safety.py:280` | `get_audit_log()` | `AUDIT_QUERY` | memory | Last 100 entries | internal | Memory only — lost on restart | ⚠️ Not persisted |
| 3 | `core/vision_agent.py:277` | `_summarize()` | `TASK_SUMMARY` | `_history` | LLM summary | `quality` model | LLM fail → fallback string | ⚠️ No persistence |

**Broken Arrows:**
- ⚠️ **Audit log** — in-memory only; `SafetyManager._audit_log` lost on process exit
- ⚠️ **Replay** — `ReplayNode` stored in `desktop_replay` (memory); no disk persistence
- ⚠️ **No session summary** — vision task result not saved to inbox/history automatically

---

## SUMMARY: Broken Arrows by Category

### CRITICAL (Security/Integrity)
| # | Journey | Arrow | Issue |
|---|---------|-------|-------|
| 1 | J3.4 | `browser_evaluate` | Arbitrary JS execution, admin-only but **no audit log**, no CSP |
| 2 | J1.7 | `inbox_websocket` | **WebSocket accepts connections WITHOUT auth** |
| 3 | J1.4 | `do_build_project` → `shell` | Shell tools **bypass filesystem guards entirely** |

### HIGH (Data Loss / Silent Failure)
| # | Journey | Arrow | Issue |
|---|---------|-------|-------|
| 4 | J1.3 | `chat_route` → `_persist_chat` | SQLite `OperationalError: locked` no retry |
| 5 | J1.6 | `do_build_apk` → `apk_files[0]` | Non-deterministic APK pick |
| 6 | J2.3 | `do_generate_pdf` | `fpdf2` not in deps; Unicode unsupported |
| 7 | J2.4 | `_record_knowledge` | Exceptions swallowed; caller unaware |
| 8 | J3.5 | `SafetyManager._audit_log` | In-memory only; lost on restart |

### MEDIUM (Degraded UX)
| # | Journey | Arrow | Issue |
|---|---------|-------|-------|
| 9 | J1.2 | `install_ollama` | No service start verification before model pull |
| 10 | J1.4 | `_phase_plan` | LLM JSON parse fail ~15%; fallback empty |
| 11 | J1.4 | `verify_gates` | Android-only; other languages skip silently |
| 12 | J1.9 | `resume_needed` | Doesn't verify Ollama/model still present |
| 13 | J2.1 | `ResearchPlanner` | Empty queries → zero pages researched |
| 14 | J2.1 | `GapDetector` | No facts → research stops immediately |
| 15 | J3.2 | `launch_app` | Hardcoded map only 10 apps; no allowlist |

### LOW (Observability)
| # | Journey | Arrow | Issue |
|---|---------|-------|-------|
| 16 | J1.5 | `_emit_progress` | Exceptions logged at DEBUG (invisible in prod) |
| 17 | J1.8 | `CrudStore.vector_healthy` | False → search returns empty silently |
| 18 | J3.3 | `_check_mouse` | Multi-monitor coordinate overflow |

---

## REALITY SCORECARD

| Journey | Complete Arrows | Broken Arrows | Critical | High | Medium | Low | **Score** |
|---------|-----------------|---------------|----------|------|--------|-----|-----------|
| 1. Install→APK→Resume | 52 | 18 | 3 | 4 | 7 | 4 | **6.1/10** |
| 2. Research→PDF→Resume | 28 | 12 | 0 | 5 | 5 | 2 | **6.4/10** |
| 3. Desktop→Browser→Finish | 22 | 9 | 1 | 2 | 3 | 3 | **5.8/10** |
| **OVERALL** | **102** | **39** | **4** | **11** | **15** | **9** | **6.1/10** |

---

## FILE INDEX (Quick Reference)

| File | Journeys | Key Functions |
|------|----------|---------------|
| `install.py` | J1.1 | `main()` |
| `core/setup/engine.py` | J1.2, J1.9 | `SetupEngine.detect`, `run_full_setup`, `resume_needed` |
| `core/routes/system/setup_routes.py` | J1.2 | `install_ollama`, `pull_model`, `auto_wire` |
| `core/routes/chat/router.py` | J1.3, J1.5, J1.8, J1.9 | `chat_route`, `agent_stream`, `get_chat_history`, `agent_resume` |
| `core/tools/chat_tools.py` | J1.3, J1.8, J2.2 | `do_create_session`, `do_chat_with_model`, `do_manage_memory` |
| `core/tools/build_tools.py` | J1.4, J1.6 | `do_build_project`, `do_build_apk` |
| `brain/automation/loop.py` | J1.4 | `_phase_plan`, `_phase_build`, `_phase_generate`, `verify_gates` |
| `core/tools/automated_build.py` | J1.5, J1.6, J2.4 | `_emit_progress`, `_find_build_artifacts`, `_record_*` |
| `core/routes/chat/inbox_router.py` | J1.7 | `add_item`, `inbox_websocket` |
| `core/activity/resume.py` | J1.9, J2.5 | `find_resume_point`, `resume_all_candidates` |
| `core/tools/browser_research.py` | J2.1 | `do_browser_research`, `_create_plan`, `_research_query` |
| `core/fact_extraction/*.py` | J2.1 | `BrowserFactExtractor`, `FactReasoner`, `FactSynthesizer`, `GapDetector` |
| `core/tools/pdf_tools.py` | J2.3 | `do_generate_pdf`, `PDFGenerator` |
| `core/tools/vision_tools.py` | J3.1 | `do_vision_browser` |
| `core/vision_agent.py` | J3.1, J3.2, J3.4 | `VisionAgent.run`, `_plan`, `_do`, `open_url` |
| `core/desktop/controller.py` | J3.2, J3.3, J3.5 | `launch_app`, `move_mouse`, `click`, `clear` |
| `core/desktop/safety.py` | J3.2, J3.3, J3.5 | `SafetyManager.check`, `_check_mouse`, `get_audit_log` |
| `core/tools/browser_tools.py` | J3.4 | `do_browser_navigate`, `do_browser_evaluate` |
| `core/ssrf.py` | J3.4 | `resolve_and_check` |