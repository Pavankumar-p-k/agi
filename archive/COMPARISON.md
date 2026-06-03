# JARVIS × OpenClaw — Architecture & Code Quality Comparison

## 1. Scale & Composition

| Dimension | JARVIS | OpenClaw |
|-----------|--------|----------|
| **Language** | Python 3.11+ | TypeScript (primary), Swift, Kotlin, Go |
| **Files** | ~250 `.py` | 15,871 `.ts` + 671 `.swift` + 177 `.kt` + 28 `.go` |
| **Lines (est.)** | ~45,000 | ~1,200,000 |
| **Type strictness** | Gradual (PEP 604, some `Any`, some untyped) | Full strict TypeScript |
| **Entry points** | `jarvis.py` (CLI), `core/main.py` (FastAPI) | Multiple SDK entry points (asynchronous) |
| **Core pattern** | Monolithic FastAPI + plugin extensions | Modular SDK with first-class plugin system |

## 2. Plugin Architecture

| Aspect | JARVIS | OpenClaw |
|--------|--------|----------|
| **Plugin base** | `Plugin` class in `core/plugins/base.py` | `Plugin` interface in `src/plugin/plugin.ts` |
| **Discovery** | JSON manifest files (`*.json`) scanned from directory | Code-based registration via `definePlugin()` |
| **Lifecycle** | `on_load()`, `on_unload()`, `health_check()`, middleware hooks (`on_request`, `on_response`), domain hooks (`on_execute`, `on_redact`, etc.) | Hooks for tool/provider/channel registration, MCP server lifecycle |
| **Isolation** | AST-level import sandbox (`_is_allowed_module`) + runtime attribute check; `strict_sandbox=True` default | Type-level interfaces, no runtime sandbox (trusts SDK consumers) |
| **API surface** | `PluginAPI` dataclass (register_tool, register_provider, register_http_route, register_channel, register_service) | Schema-driven (`ToolInputSchema`, `ToolOutputSchema`); providers registered via `registerProvider()` |
| **Hierarchical types** | `VoicePlugin`, `AutomationPlugin`, `PrivacyPlugin`, `MemoryPlugin` subclasses | Single `Plugin` type with generic hooks; providers are separate concept |
| **Security model** | Import allowlist + strict_sandbox rejection | Trust model — plugins assumed to be first-party or vetted |

### Key difference
JARVIS invested in **runtime security** (AST sandbox) because plugins are dynamically loaded from untrusted JSON manifests. OpenClaw trusts its SDK consumers and relies on **type safety at compile time** rather than runtime isolation.

## 3. Error Handling

| Aspect | JARVIS | OpenClaw |
|--------|--------|----------|
| **Result type** | `Ok[T]` / `Err[E]` in `core/result.py` with `__match_args__`, `.map()`, `.map_err()`, `.unwrap()`, `.unwrap_or()` | `Result<T, E>` in `src/result.ts` with `.ok()`, `.err()`, value/no-value variants |
| **Domain errors** | `DomainError` hierarchy: `NotFound`, `Timeout`, `ProviderError`, `NotConfigured`, `ValidationFailed`, `StorageError`, `AuthFailed`, `RateLimited`, `LLMError` | Custom error classes per domain; SDKError wrapping layer |
| **HTTP bridge** | `domain_to_http()` maps domain → HTTP error | Direct HTTP status assignment in server handlers |
| **Error wrapping** | `ErrorWrapper(message, code, cause)` via `err_from()` helper | Nested cause chains via `SDKError.cause` |
| **Swallowed errors** | **64/67** formerly-silent `except: return ""` paths now logged; 3 intentional (Ctrl+C, PermissionError, port-closed) | Proper propagation — no silent swallow patterns found |
| **Fallback chains** | `unwrap_or("")` in multi-model fallback — can hide all failures | Explicit fallback with status tracking |

### Key difference
Both use monadic `Result` types. JARVIS has a 2-layer architecture (domain + HTTP) with a bridge function, which is cleaner for internal/API separation. OpenClaw uses a single error layer with broader cause-chain support. **JARVIS is still converting functions to return `Result`** — about 30% of the codebase uses it, the rest still uses bare exceptions.

## 4. Test Infrastructure

| Aspect | JARVIS | OpenClaw |
|--------|--------|----------|
| **Framework** | pytest + asyncio (`asyncio_mode = auto`) | Vitest |
| **Test levels** | Unit (20), Integration (6), Contract (2), E2E (6) + legacy scripts | Unit + Integration (Vitest), E2E (Playwright) |
| **Property-based** | ✅ Hypothesis (22 fuzz tests for Result type) | Not observed |
| **Conftest** | `tests/conftest.py` — server fixture (multiprocessing + httpx) | Vitest setup files |
| **Markers** | `unit`, `integration`, `contract`, `e2e`, `slow`, `intent` | `describe`/`it` blocks |
| **Coverage gaps** | No unit tests for `control_loop.py` (980 lines), `scheduler.py`, `agent_registry.py` | Not audited |
| **Legacy tests** | `_test_100.py`, `_test_world.py` — standalone scripts mixing prints + requests | Not observed |

### Key difference
JARVIS's test infrastructure is **more layered** (4 explicit levels) and includes **property-based testing** — OpenClaw's tests appear more conventional. However, JARVIS has critical coverage gaps in its most complex modules.

## 5. Top 7 Critical JARVIS Bugs (from deep audit)

| # | File:Line | Severity | Description |
|---|-----------|----------|-------------|
| 1 | `core/main.py:1415` | **CRASH** | Missing `await` on `computer_agent.execute_natural_language()` — endpoint always returns coroutine |
| 2 | `jarvis.py:1782` | **CRASH** | `get_local_os_runtime()` calls `None()` when `build_jarvis_os` import fails |
| 3 | `assistant/stt.py:28` | **CRASH** | `asyncio.run()` called from inside running event loop — `RuntimeError` on startup |
| 4 | `memory/tiered_memory.py:114` | **SILENT DATA LOSS** | `unwrap_or([])` hides all semantic search failures — user sees empty results |
| 5 | `pc_agent/computer_agent.py:87` | **STATE CORRUPTION** | Shared Open-Interpreter singleton across concurrent requests — history + LLM state corrupted |
| 6 | `assistant/engine.py:40-521` | **MAINTENANCE** | 480 lines dead code: `JarvisAssistant`, Vosk STT, pyttsx3 TTS, LLMEngine — replaced but never removed |
| 7 | `brain/UnifiedBrain.py:60` | **LOGIC BUG** | Coroutine detection inspects *return value* not *function* — sync listeners never execute |

## 6. Four Gaps (Original Goal)

| Gap | Before Work | Current State | Remaining |
|-----|-------------|---------------|-----------|
| **Error typing** | No `Result` type, bare `try/except` everywhere | `Ok[T]/Err[E]` + `DomainError` hierarchy + `domain_to_http` bridge. `embed()`, `search()`, `complete()`, `complete_vision()` return `Result`. | ~70% of functions still return bare values or raise. Silent `unwrap_or()` patterns remain in 4 integrations (news, stocks, weather, sports). |
| **Plugin isolation** | No isolation; plugins could import `os`, `subprocess` | AST import sandbox + `strict_sandbox=True`. 16 safe stdlib + 10 project prefixes allowed. 4 built-in + 3 external plugins audited. | Only static import checking. No exec sandbox (jailing file/network access at runtime). No resource limits (CPU, memory). No permission system per-plugin. |
| **Test infrastructure** | Minimal tests (a few legacy scripts) | 4-level suite: 20 unit + 6 integration + 2 contract + 6 e2e + 22 hypothesis fuzz. Missing: control_loop, scheduler, agent_registry. | No CI pipeline. No coverage enforcement. No mutation testing. |
| **Silent error swallowing** | 67 bare `except: return ""/[]/False/None` | 64 now logged (warning/error/exception). 3 intentional remain. `unwrap_or("")` in llm_router fallback chain still hides vision+triage failures. | 4 integrations with `unwrap_or([])` still silent. Need audit of `unwrap_or` usage across all 30% converted functions. |

## 7. Architecture Pattern Comparison

```
Error Propagation:
  OpenClaw:  fn() → Result<T, E> → map/and_then → Result<T, E>
  JARVIS:    fn() → Ok/Err → unwrap_or/if is_ok → continue/fallback

Plugin Registration:
  OpenClaw:  definePlugin({name, hooks}) → registerProvider({type, handler})
  JARVIS:    JSON manifest → importlib → PluginAPI → OrderedDict

Tool Resolution:
  OpenClaw:  ProviderRegistry → getTool(name) → execute(params)
  JARVIS:    ToolRegistry → execute(name, params) → ToolResult

Service Lifecycle:
  OpenClaw:  Provider lifecycle (init → ready → dispose)
  JARVIS:    Plugin lifecycle (load → unload) with separate scheduler
```

## 8. Recommendations (Priority Order)

1. **Fix 7 critical bugs** (#1 and #2 are crashes, #3 blocks voice startup, #5 causes data corruption)
2. **Extend `Result` to remaining functions** — systematically convert all public APIs to return `Ok/Err`
3. **Add coverage to control_loop.py** — 980 lines, zero unit tests, most complex module in the system
4. **Replace `unwrap_or()` fake responses** with structured error propagation in integrations
5. **Remove dead code** — 480 lines in `assistant/engine.py` alone
6. **Add per-plugin permissions** — extend sandbox beyond import checking (e.g., network/filesystem allowlists)
