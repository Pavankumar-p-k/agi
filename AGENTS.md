# JARVIS — Architecture Guide for AI Coding Assistants

This document helps AI coding tools understand the JARVIS codebase structure, conventions, and patterns.

## Location of Key Files

| Component | Path |
|-----------|------|
| Entry point | `jarvis.py` (simplified CLI: chat, code, build, run, understand, workspace, doctor, models, settings, advanced) |
| CLI commands | `cli_commands.py` |
| CLI request helpers | `cli_requests.py` |
| CLI server management | `cli_server.py` |
| Workspace Intelligence | `core/workspace_manager.py` (WorkspaceManager, ProjectMap) |
| Repository Analysis | `core/repository_analyzer.py` (RepositoryAnalyzer — import graphs, auth, DB, API routes) |
| Agent Orchestrator | `core/agent_orchestrator.py` (unified code/build/run/understand API) |
| Config schema | `core/config_schema.py` |
| Agent loop | `core/agent_loop.py` |
| Tool execution | `core/tools/execution.py` |
| Tool implementations | `core/tools/skill_tools.py`, `settings_tools.py`, `admin_tools.py`, `cookbook_tools.py` |
| Persistent shell | `core/tools/persistent_shell.py` (now captures exit_code, cwd, duration) |
| Skill loader | `core/skill_loader.py` |
| Prompt security | `core/prompt_security.py` |
| SSRF protection | `core/ssrf.py` |
| API key vault | `core/api_key_vault.py` |
| Docker sandbox | `ai_os/docker_sandbox.py` |
| Diagnostics | `core/diagnostics.py` |
| FastAPI app | `core/main.py` |
| Skill index (SKILL.md format) | `core/tools/skill_tools.py` (`do_manage_skills`) |
| Media player | `media/player.py` |
| Voice Engine | `assistant/voice_pipeline.py` (VoiceEngine — replaces VoicePipeline + VoiceLoop) |
| STT providers | `assistant/stt.py`, `assistant/stt_protocol.py`, `assistant/providers/faster_whisper.py`, `deepgram.py`, `azure_speech.py` |
| TTS providers | `assistant/tts.py`, `assistant/tts_protocol.py`, `assistant/providers/kokoro_tts.py`, `edge_tts_provider.py` |
| Wake word | `assistant/wake_word.py` (WakeWordDetector + WakeWordRegistry + WatchdogService) |
| Voice API routes | `core/routes/voice.py` |
| Audio emotion | `core/audio_emotion.py` |
| Voice config | `core/config_registry.py` (voice.* entries lines 91-118) |
| Tests | `tests/unit/` |
| **Browser Planner** | `benchmarks/browser_planner.py` (`BrowserPlanner` — 4 rules: auto-snapshot, search-fill, result-detection, loop-breaker) |
| **Compiler Repair Engine** | `brain/compiler_repair_engine.py` (`CompilerRepairEngine` — 60 error parsers, 22 fix actions, PatternFailureMemory integration) |
| **Repair Modules** | `brain/repair_modules/` (7 modules: fix_imports, fix_class_names, fix_manifest, fix_layouts, fix_resources, fix_gradle, fix_dependencies) |
| **Build Output Audit** | `benchmarks/project_build_audit.py` — validates parse coverage across fixture files |
| **AutoBuild Loop** | `brain/automation/loop.py` (`AutomationLoop` — plan→generate→verify→build→test phase pipeline) |
| **Repair Chaining** | `brain/repair_chaining.py` (`RepairChain` — iterative fix→rebuild→detect→fix with rollback, loop detection, and priority ordering) |
| **Repair Chaining Benchmark** | `benchmarks/repair_chaining_benchmark.py` — validates chain on 4 synthetic projects (2–6 errors) |
| **Pattern Failure Memory** | `core/pattern_failure_memory.py` (`PatternFailureMemory` — JSON-backed, auto-generalization, record_success/record_failure, regex match) |
| **Legacy Failure Memory** | `brain/automation/loop.py` (`FailureMemory` — SQLite-backed, exact/prefix/pattern lookup) |

## Key Architecture Rules

1. **NO silent except blocks** — every `except` must log with `logger.warning()` and include `as e`. Zero remaining in live code.
2. **NO shell=True** in `subprocess` calls — always use `shell=False` with a list argument.
3. **ALL API keys** must come from environment variables or `core/config.py`, never hardcoded.
4. **Config** is type-validated by `core/config_schema.py` (`JarvisConfig` pydantic model).
5. **Tools** are registered in `core/tools/execution.py` `_TOOL_HANDLERS` dict — add new tools there plus in `core/tools/index.py` (description), `core/agent_prompts.py` (usage docs), and `core/agent_helpers.py` (ALWAYS_AVAILABLE list).
6. **New primary CLI commands** go in `jarvis.py` via `build_parser()` and `cli_commands.py` as handler functions. Use `core/agent_orchestrator.py` for multi-step code/build/run/understand workflows.
7. **Workspace scanning** should use `core/workspace_manager.py` (os.walk with skip dirs, not rglob) for performance on large projects.

## Adding a New Tool

1. Add implementation function in `core/tools/` (e.g., `skill_tools.py`, `settings_tools.py`)
2. Export it via `core/tools/implementations.py`
3. Add handler + register in `core/tools/execution.py` `_TOOL_HANDLERS`
4. Add doc line in `core/agent_prompts.py`
5. Add index entry in `core/tools/index.py`
6. Add to `ALWAYS_AVAILABLE` in `core/agent_helpers.py` if it should be available in every turn

## Import Convention

- `jarvis_os/` provides `bootstrap.py`, `core/planner.py`, `memory/memory_manager.py` — these are stubs imported by `cli_requests.py`, `api/os_routes.py`, `ai_os/`
- `skills/` contains `{name}.md` (frontmatter + triggers) + `{name}.py` (handler)
- `core/` contains all core logic — no deep nesting beyond 1 level

## Agent-Browser Wiring Fix (June 17, 2026)

The agent pipeline for local Ollama models was broken by **9 bugs** across 6 files. Summary:

| Bug | File | Fix |
|-----|------|-----|
| `TOOL_TAGS` missing all browser tools | `core/tools/_constants.py` | Added 22 browser tool names |
| `_TOOL_NAME_MAP` no browser aliases | `core/tools/parsing.py` | Added 40+ browser tool aliases |
| `_TOOL_SHORTLIST` hardcoded 6 code tools | `core/agent_prompts.py` | Dynamic `_build_tool_shortlist()` |
| `_TOOL_SECTIONS` never injected | `core/agent_prompts.py` | Now appended for relevant tools |
| `_build_base_prompt` passes `set()` for tools | `core/agent_prompts.py` | Changed to `relevant_tools or set()` |
| Graph never calls `route_node` after `think` | `core/graph/__init__.py` | Added `think`→`route` edge |
| `ToolBlock` not imported | `core/agent_helpers.py` | Added import |
| `_cached_skill_index_block` no `global` | `core/agent_prompts.py` | Added `global` declaration |
| `OLLAMA_KEEP_ALIVE=-1` invalid duration | `core/llm_providers.py` | Added keep_alive validation |

**Result:** Pipeline infrastructure works (`setup→think→route→tool_call→dispatch`).  

### Tool Selection Benchmark (June 18-19, 2026)

100 agent-choice tasks across 10 categories (search, read, login, docs, GitHub, shopping, forms, research, learning, multi-page). Every task required a browser tool.

| Approach | Tool Choice | Count | Accuracy |
|----------|------------|-------|----------|
| **Fenced code blocks** (without tool schemas) | `no_tool` | 57/100 | **0%** |
| | `python` | 31/100 | |
| | `bash` | 10/100 | |
| | `browser_*` | 0/100 | |
| **Native function calling** (with tool schemas) | `browser_navigate` | **100/100** | **100%** |

**Root cause confirmed:** `qwen2.5-coder:3b` (and all tested local models) cannot generate ````browser_navigate```` fenced code blocks (0% accuracy). **The fix is to send browser tool schemas via Ollama's native `tools` parameter** — with schemas, `qwen2.5:7b` achieves 100% browser tool selection. The pipeline infrastructure (setup→think→route→tool_call→dispatch) works correctly; the bottleneck was the free-form code block generation format.

**Architectural changes made:**

1. Created `core/tools/schemas_browser.py` — JSON Schema definitions for all 23 browser tools (OpenAI function calling format)
2. Registered in `core/tools/schemas.py` — browser schemas now part of `FUNCTION_TOOL_SCHEMAS`
3. Added browser arg parsing in `function_call_to_tool_block()` — converts structured `{"selector": "...", "text": "..."}` to the content string format expected by handlers
4. Removed `is_api_model` gate in `think_node()` — local Ollama models now receive tool schemas (previously set to `[]`)
5. Fixed Ollama SSE response parser in `llm_core.py` — now detects and normalizes `message.tool_calls` from Ollama responses, converting from Ollama's `{"function": {"name": ..., "arguments": {...}}}` to the normalized `{"name": ..., "arguments": "..."}` format consumed by `_resolve_tool_blocks`

## Current Architecture

```
User
 │
 ▼
 Planner
 │  (auto-snapshot, search-fill, result-detection, loop-breaker)
 ▼
 LLM (tool selection + action planning)
 │
 ▼
 Tool Execution (browser, code, shell, etc.)
 │
 ▼
 Verification
 │
 ▼
 Memory (PatternFailureMemory + FailureMemory, bidirectionally synced)
 │
 ▼
 Learning (success/failure tracking, pattern generalization)
```

## Compiler Repair Pipeline

The `brain/compiler_repair_engine.py` implements a deterministic repair pipeline:

```
Build Output
    ↓
 60 Regex Parsers (javac, AAPT2, Gradle, Room, D8, NDK, Navigation, etc.)
    ↓
 Structured JavacError {file, line, category, symbol, message}
    ↓
 Priority 1: PatternFailureMemory match (exact → regex)
 Priority 2: Deterministic repair rule (~22 action types)
 Priority 3: LLM fallback (last resort)
    ↓
 success → PatternFailureMemory.record_success() → FailureMemory.store()
 failure → PatternFailureMemory.record_failure() (prevents repeat loops)
```

### Build Output Audit (June 20, 2026)

`benchmarks/project_build_audit.py` validates parse coverage against real-world build output:

| Metric | Before | After (4 parsers added) |
|--------|--------|------------------------|
| Parse rate | 73.3% (11/15 files) | **100% (15/15 files)** |
| Total errors parsed | 80 | 90 |
| Unique categories | 26 | 30 |
| False positives | 0 | 0 |
| Taxonomy conformity | 100% | 100% |

**4 gap parsers added**: `d8_duplicate_class`, `kotlin_jvm_target`, `d8_desugar_error`, `ndk_build_error`.

### Repair Chaining (June 20, 2026)

`brain/repair_chaining.py` (`RepairChain`) implements iterative multi-turn repair:

```
Build
  ↓
Parse
  ↓
0 errors? ──Yes──→ Success
  │ No
  ↓
Safety Checks:
  • max_iterations (25) → Stop
  • loop detected (same error signature 3×) → Stop
  • no progress (error count not decreasing) → Stop
  │ Pass
  ↓
Snapshot affected files → Apply Fix #1 → Rebuild → Errors ↓?
  │ No → Rollback → Try next error
  │ Yes → Record Success → Repeat
```

Chaining benchmark (`benchmarks/repair_chaining_benchmark.py`):

| Project | Errors | Fixes | Iterations | Status |
|---------|--------|-------|------------|--------|
| A (2 fixable) | syntax + import | 2/2 | 3 | PASS |
| B (4 fixable) | syntax + LiveData + color + string | 3/4 | 5 | PASS |
| C (1 fixable, 1 unfixable) | syntax + ndk | 1/2 | 3 | PASS |
| D (6 fixable) | syntax + 5 imports/resources | 5/6 | 7 | PASS |

**Key metrics**: 11/14 errors fixed deterministically (79%), 0 rollbacks, 0 loop detections.

### Safety Guards
- `max_iterations` (default 25) prevents infinite loops
- `error_signature()` hashes (file, line, category) sets — if same set seen 3+ times, chain stops
- `max_no_progress_count` (default 2) — if error count doesn't decrease, chain stops
- `FileSnapshot` — backs up .java/.xml/.gradle files before each fix, restores on rollback

### Priority Order
Syntax → imports → build config → resources → structure → class/symbol → Room → Manifest → fallback

Missing: `fix_room.py`, `fix_navigation.py`, `fix_override.py` repair modules (inline implementations exist but lack dedicated modules). Automated tests for engine + repair modules.

## Browser Planner (deterministic layer)

The `benchmarks/browser_planner.py` implements 4 deterministic rules that run BEFORE and AFTER each LLM tool call:

| Rule | Phase | Trigger | Action |
|------|-------|---------|--------|
| auto-snapshot | pre_plan | After `browser_navigate` | Inject `browser_snapshot` |
| search-fill | post_plan | Search form detected on page | Inject `browser_fill` + `browser_press` |
| result-detection | post_plan | One turn after search-fill | Check URL/DOM for results → inject `browser_snapshot` |
| loop-breaker | post_plan | Same tool sequence ≥3× | Inject `browser_snapshot` |

The planner lives in `benchmarks/` — move to `core/tools/` for agent pipeline integration when stable.

## Failure Memory (Two Systems, One Interface)

| System | Storage | Scope | Used By |
|--------|---------|-------|---------|
| `PatternFailureMemory` (core/) | JSON file (`~/.jarvis/pattern_failures.json`) | Generalized regex patterns | CompilerRepairEngine, CLI commands |
| `FailureMemory` (brain/automation/) | SQLite (`data/failure_memory.db`) | Exact + prefix + pattern | AutomationLoop legacy fallback |

**Now bidirectionally synced:** Successes/failures from either system feed into the other after each repair cycle. Failed repairs are recorded with `FAILED:` prefix to prevent repeat attempts.

## Browser E2E Benchmark (June 2026)

### Key Findings

| Finding | Evidence |
|---------|----------|
| Tool selection solved | qwen2.5:7b achieves 100% browser tool selection with native function calling |
| Page inspection partially solved | Model reads pages (snapshot) when prompted but not reliably |
| Form interaction unsolved | `browser_fill`/`browser_press` usage near zero across 100 tasks |
| Action planning is the bottleneck | Model navigates once and stops — cannot plan multi-step workflows |

### Planner v2 (4 rules)

| Rule | Phase | Trigger | Action |
|------|-------|---------|--------|
| auto-snapshot | pre_plan | After `browser_navigate` | Inject `browser_snapshot` |
| search-fill | post_plan | Search form detected on page | Inject `browser_fill` + `browser_press` |
| result-detection | post_plan | One turn after search-fill | Check URL/DOM for results → inject `browser_snapshot` |
| loop-breaker | post_plan | Same tool sequence ≥3× | Inject `browser_snapshot` |

### Running the Benchmark

```powershell
$env:MAX_TASKS="10"; $env:USE_PLANNER="1"; python benchmarks/browser_e2e_benchmark.py
```

## Testing

- `pytest tests/unit/` for unit tests
- `pytest tests/integration/` for integration tests
- Tests must NOT depend on external services — use `mock_external_calls` autouse fixture in `tests/conftest.py`
- Do NOT use the `db_init` fixture unless the test actually needs a database
