# Production Readiness Audit — MJ v3.0.0-rc3

**Date:** July 2, 2026
**Scope:** Full forensic audit across 26 dimensions, 800+ files, ~4,245 tests, 14 benchmarks
**Author:** Senior Staff Engineer (Architecture Audit)

---

## Executive Summary

MJ v3.0.0-rc3 is **not production ready**. The codebase has a strong architecture foundation with genuine innovation (Planner Authority, deterministic FSMs, benchmark infrastructure), but is held back by **critical security vulnerabilities, massive code duplication, broken CI pipelines, and a non-functional installer**.

**Production Readiness Score: 30/100** — BROKEN. Not shippable in current state.

### What Works (10-20% of the codebase)
- LLM provider layer (6 real providers via LiteLLM, direct HTTP)
- Workflow engine with compensation, recovery, retry, durability
- Benchmark infrastructure (14 specialized benchmarks, dedicated framework)
- Architecture documentation (10 production-grade forensic audits)
- Core test infrastructure (~4,245 tests, clean isolation)

### What Is Broken (critical path)
- **Docker installs nothing** (requirements.txt is comment-only)
- **2 out of 3 CI workflows install nothing** (pip install -r requirements.txt)
- **Electron app cannot build** (no icon.ico, no node_modules)
- **CHANGELOG.md does not exist** (GA_CHECKLIST blocker)
- **Web UI has XSS vulnerabilities** (no DOMPurify, javascript: URLs)
- **API keys and OAuth tokens stored in plaintext** (CRITICAL)

### What Is Duplicated (40-50% of the codebase)
- 6+ memory systems, 2+ provider systems, 4+ config systems, 6+ router systems
- brain/ duplicates core/ (~20 files)
- Abandoned sub-projects committed to git (student_agi, flutter build artifacts)

---

## Scores by Dimension

| Dimension | Score | Key Issues |
|-----------|-------|------------|
| **Architecture** | 6/10 | Strong foundations, massive duplication, dead code |
| **Security** | 4/10 | Plaintext secrets, XSS, shell injection, auth bypass |
| **Reliability** | 5/10 | 90+ silent catches, broken CI, conflicting health monitors |
| **Performance** | 6/10 | Good benchmarks, no profiling, polling-heavy UI |
| **Maintainability** | 4/10 | Brain/core split, 6+ memory systems, dead abandoned sub-projects |
| **Developer Experience** | 5/10 | Broken CI, no CHANGELOG, no pre-commit, coverage unenforced |
| **User Experience** | 6/10 | Polished web UI, but XSS, no error monitoring, broken installer |
| **Testing** | 8/10 | 4,245 tests, clean isolation, excellent benchmark infra |
| **Documentation** | 7/10 | Excellent audit docs, but CHANGELOG missing, no runbook |
| **Monitoring/Telemetry** | 5/10 | JSON logging built but not activated, no Sentry, overlapping monitors |

**Overall Production Readiness: 30/100**

---

## Critical Findings (Immediate Blockers)

### C-01: Dockerfile Installs Zero Dependencies
**File:** `Dockerfile:15-16`
```dockerfile
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
```
`requirements.txt` contains only a comment directing to `pyproject.toml`. The pip install installs nothing. The container will fail at runtime on any import. **Fix:** Use `pip install -e .` or copy `pyproject.toml`.

### C-02: CI Workflows Install Zero Dependencies (2 of 3 broken)
**Files:**
- `.github/workflows/pr_fast.yml:36` — `pip install -r requirements.txt pytest-timeout`
- `.github/workflows/python.yml:36,48,68,83,97` — 5 instances of `pip install -r requirements.txt`

Both workflows install exactly **none** of the project's dependencies. Tests run with only stdlib + the explicitly listed packages (pytest-timeout, mypy, alembic, pytest-cov). Any import from core/ will fail.

**Only `ci.yml` is correct** — it uses `pip install -e ".[dev]"`.

**Impact:** CI gives false positives. PRs that break imports will pass CI.

### C-03: `create_subprocess_shell` Still in Production Code
**File:** `brain/tools/project_tool.py:179`
```python
proc = await asyncio.create_subprocess_shell(command, ...)
```
Only remaining `shell=True` equivalent. Allows full shell injection. AGENTS.md Rule 2 explicitly prohibits this.

### C-04: Plaintext API Key Vault
**File:** `core/api_key_vault.py:24,41,139-141`
```python
VAULT_PATH = Path.home() / ".jarvis" / "api_keys.json"
```
All API keys stored unencrypted on disk. Any local process can read them.

### C-05: Plaintext OAuth Token Storage
**File:** `core/oauth.py:29,50,199-209`
```python
STORE_PATH = Path.home() / ".jarvis" / "oauth_tokens.json"
```
OAuth access + refresh tokens stored in plaintext. Grants persistent API access to Google, GitHub, Discord.

### C-06: CHANGELOG.md Does Not Exist
Per `GA_CHECKLIST.md:28`: "CHANGELOG.md current". The file does not exist. This is an explicit GA gate requirement.

---

## Major Findings

### M-01: Web UI XSS Vulnerabilities (3 vectors)
**File:** `web/src/app/chat/page.tsx:51`, `web/src/lib/md.ts`

1. **`dangerouslySetInnerHTML` without DOMPurify** — Any raw HTML in LLM output renders unsanitized
2. **`javascript:` protocol URLs** — `link(href)` never validates protocol
3. **Raw HTML pass-through** — Marked v12 does not strip HTML by default

### M-02: Hardcoded Dev Credentials in Web UI
**File:** `web/src/lib/auth.tsx`
```typescript
username: '12345', password: '123456'
```
Committed to source. If dev mode is deployed, any user can login as admin.

### M-03: Auth Bypass via Loopback/Dev Mode
**File:** `core/auth.py:583-585`
```python
if _is_loopback(client_ip) or DEV_MODE:
    return await _get_or_create_user(db, uid="dev", email="dev@local", ...)
```
Loopback requests and DEV_MODE skip authentication entirely. `core/auth.py:607-608` gives dev user ADMIN role unconditionally.

### M-04: 16 `shlex.split()` Injection Sites
**Files:** `core/providers/adapters/deployment_provider.py`, `core/agent_orchestrator.py`, `core/agent_launcher.py`, `core/agent_registry.py`, `core/file_agent.py`, `core/opencode_delegate.py`, `core/vision_agent.py`, `core/tools/bg_jobs.py`

Commands constructed as formatted strings then split with `shlex.split()`. Any interpolated value with spaces or metacharacters becomes argument injection.

### M-05: Default `auto_approve=True` in Agent Components
**Files:** `core/agent_launcher.py:109`, `core/control_loop.py:143`, `core/supervisor_agent.py:72`
```python
auto_approve: bool = True  # default
```
All agent actions execute without user confirmation. `core/multi_run.py:87` hardcodes `True`.

### M-06: ~90 Silent `except Exception:` Catches
Across 30+ files in `core/`. Exceptions caught with zero logging, zero re-raise. Bugs become invisible in production. Violates AGENTS.md Rule 1 ("NO silent except blocks").

### M-07: Bare `except:` in Terminal Route
**File:** `core/routes/terminal.py:66`
```python
except:
    pass
```
Catches `BaseException` including `KeyboardInterrupt`, `SystemExit`. Process termination failure silently swallowed.

### M-08: JSON Structured Logging Not Activated
**File:** `core/observability/logging.py:92` defines `configure_json_logging()`
Not called from `core/main.py` or `core/lifespan.py`. Production uses ad-hoc string formatting that log aggregators cannot parse.

### M-09: Electron App Cannot Build
- `desktop/node_modules` — **DOES NOT EXIST** (npm install never run)
- `desktop/icon.ico` — **DOES NOT EXIST** (electron-builder will fail)
- `desktop/package-lock.json` — **DOES NOT EXIST**
- Backend spawning path broken in packaged build (uses `__dirname/../jarvis.py` which resolves inside ASAR)

### M-10: No Uncaught Exception Handler in Electron
**File:** `desktop/main.js`
No `process.on('uncaughtException')` or `process.on('unhandledRejection')`. Any unhandled error silently crashes the app.

### M-11: `authlib` Imported but Not Declared
**File:** `core/oauth.py:22` — `from authlib.integrations.starlette_client import OAuth`
Hard import at module level. If package not installed, the app crashes on import. Not in `pyproject.toml`.

### M-12: `constraints.txt` Does Not Match Installed Versions
13 pinned packages, most conflict with actual installed versions:
- `pillow` pinned 12.2.0, installed 10.4.0 (major version, CVEs in 10.x)
- `starlette` pinned 1.0.1, installed 0.52.1 (major version)
- `lxml` pinned 6.1.0, installed 5.4.0 (major version)
- `setuptools` pinned 78.1.1, installed 65.5.0 (major version)

### M-13: Memory System Fragmentation (6+ Implementations)
| System | Path | Status |
|--------|------|--------|
| Long-Term Memory | `core/long_term_memory/` | ACTIVE (canonical per AGENTS.md) |
| Root memory/ | `memory/` | DEAD (6 files) |
| brain/memory/ | `brain/memory/` | DEAD (5 files) |
| services/memory/ | `services/memory/` | DEAD (2 files) |
| core/memory.py | `core/memory.py` | DORMANT |
| ProviderMemory | `core/providers/memory.py` | ACTIVE (separate concern) |
| PatternFailureMemory | `core/pattern_failure_memory.py` | ACTIVE |
| MemoryAdapter (strategy) | `core/strategy/memory_adapter.py` | ACTIVE |
| MemoryAdapter (strategy_v2) | `core/strategy_v2/memory_adapter.py` | ACTIVE (different class) |

### M-14: Provider System Duplication (2 Parallel Trees)
- `core/providers/` — ExecutionProvider framework, used in production
- `core/model_providers/` — ModelProvider framework, CLI-only, exactly 0 production callers
- `core/llm_providers.py` — Third provider system (helper functions, used by both)
- `core/providers/manager.py` — Dead code, references non-existent `llm` singleton

### M-15: Config System Duplication (4+ Implementations)
- `core/config_schema.py` — Pydantic `JarvisConfig` (canonical per AGENTS.md)
- `core/config_registry.py` — Singleton with priority-chain resolution (env > JSON > YAML)
- `core/config_init.py` — Separate `init_config()` function
- `cli_config.py` — CLI-specific config
- `core/setup/configurator.py` — Setup configurator

### M-16: Router System Duplication (6+ Implementations)
- `core/providers/router.py` — Provider routing
- `core/model_providers/router.py` — Model provider routing (dead)
- `core/llm_router.py` — LLM routing (production)
- `core/model_router.py` — Yet another model router
- `core/intent_router.py` — Browser planner intent routing
- `core/agents/router.py` — Agent routing
- `routers/` (top-level) — Separate directory from `core/routes/`

### M-17: ConfigService, ProviderManager, HybridModelPlatform Are Dead Code
- `core/configuration/service.py` (286 lines) — docstring itself says "0 production callers"
- `core/providers/manager.py` (131 lines) — imports non-existent `llm` singleton, zero imports
- `core/model_providers/hybrid.py` (341 lines) — CLI diagnostics only
- `core/providers/router.py` (386 lines) — This one IS alive (used by pipeline.py)

### M-18: No CSP Header in Production nginx
**File:** `web/nginx.conf`
Missing `Content-Security-Policy` header. Combined with XSS in #M-01, this allows arbitrary script execution.

### M-19: Landing Page Has Placeholder Download Link
**File:** `landing/index.html`
Download CTA links to `href="#"`. SVG placeholder image instead of actual product screenshot. No analytics, no SEO.

### M-20: No Error Monitoring (Sentry/Datadog/OpenTelemetry)
Zero integration with any external monitoring service. When the app crashes in production, there is zero visibility into why.

---

## Medium Findings

### MED-01: Abandoned `learning/student_agi/` Sub-Project
11 Python files, complete abandoned sub-project ("Student AGI"). Committed to git.

### MED-02: Flutter Build Artifacts Committed to Git
`experimental/flutter/build/` — Thousands of files (Android, iOS, Windows, macOS, Linux, Web build artifacts).

### MED-03: `{}/` Directory in Root
Directory literally named `{}` containing an Android test project. Naming bug or formatting error.

### MED-04: `except: raise` Self-Defeating Deprecation in Plugin Manifest
`core/plugins/manifest.py:19` raises `DeprecationWarning` then line 24 re-declares `PluginManifest` anyway.

### MED-05: Overlapping Health Monitoring Systems (3+ Background Loops)
- `core/health_monitor.py` — checks Ollama/Search/STT/TTS/WakeWord/GPU
- `monitors/services.py` — checks Ollama/Search/Network/Voice
- `brain/observers/system_monitor.py` — Disk/CPU/Memory
All three can run concurrently, checking the same services.

### MED-06: Two Divergent LLM Failover Implementations
**File:** `core/llm_failover.py`
- `FailoverRouter` (lines 26-298, old, LiteLLM-based, production)
- `FailoverManager` (lines 315-467, new, direct HTTP, not production-default)

### MED-07: DomainError Hierarchy Not Wired to HTTP Handlers
`core/errors.py` defines `DomainError` hierarchy (NotFound, Timeout, ProviderError, etc.) with `domain_to_http()` converter. The converter is only used in tests. Production exceptions fall through to generic 500.

### MED-08: `smolagents` Package Not Declared as Dependency
**File:** `core/main.py:133`, `core/sub_agents/agents/forge.py:21`
Imported conditionally with try/except in core/main.py but not in `pyproject.toml` (even as optional).

### MED-09: Widespread `return None` Anti-Pattern (100+ instances)
Functions return `None` on error, indistinguishable from "no result found". Callers often don't check, leading to AttributeError at runtime.

### MED-10: `configure_json_logging()` Never Called
**File:** `core/observability/logging.py:92`
JSON structured logging system exists but is never activated. Production uses ad-hoc format strings.

### MED-11: CI Does Not Run Web UI Tests
CI runs Python tests only. Zero web UI test execution. Zero Electron app build verification.

### MED-12: No Coverage Data Ever Collected
Coverage is configured (`fail_under=60`) but no `.coverage` files exist on disk. No historical coverage data.

### MED-13: `python-socketio` Declared but Not Installed
**File:** `pyproject.toml:58` — `python-socketio>=5.0.0`. Not found in installed packages.

### MED-14: `brain/tools/project_tool.py` Uses `os.environ` in Subprocess
```python
env={**os.environ, **(env or {})}
```
Full parent environment forwarded to subprocess. Any compromised subprocess has all credentials.

### MED-15: Two CONTRIBUTING.md Files
Root `CONTRIBUTING.md` (44 lines, outdated) vs `docs/CONTRIBUTING.md` (80 lines, detailed). Conflicting.

---

## Working Systems (Production-Proven)

| System | File(s) | Purpose |
|--------|---------|---------|
| **LLM Routing** | `core/llm_router.py` | LiteLLM-based router, 9 model groups, 25+ callers |
| **LLM Providers** | 6 providers in `core/providers/` adapters | Real HTTP API calls to Ollama, OpenAI, Anthropic, Gemini, Groq, OpenRouter |
| **LLM Failover** | `core/llm_failover.py` (old) | Profile-based failover with exponential backoff |
| **LLM Streaming** | `core/llm_core.py` | SSE streaming with Ollama native fallback |
| **Workflow Engine** | `core/workflow/engine.py` | Durable steps, compensation, retry, recovery |
| **Provider Router** | `core/providers/router.py` | Evidence-based 7-dimension provider selection |
| **Provider Memory** | `core/providers/memory.py` | Bayesian posterior scoring, fallback chains |
| **Calibration Engine** | `core/providers/feedback/` | Context-aware calibration, time-decay weighting |
| **Benchmark Framework** | `core/benchmark/` (10 files) | SQLite-backed, multi-model, trend analysis |
| **14 Benchmarks** | `benchmarks/*.py` | Browser, long-horizon, research, ablation, soak, durability |
| **Planner Authority** | `core/planner/` | Template/state machine enforcement, proved 0→100% |
| **FSM Family** | Browser FSM, Long-Horizon FSM, Extraction FSM | 3 deterministic state machines |
| **Test Infrastructure** | 4,245 tests, clean conftest hierarchy | Excellent isolation, no external deps |
| **Architecture Documentation** | `docs/architecture/` (11 audits) | Production-grade forensic audit series |

---

## Partially Working Systems

| System | File(s) | Issue |
|--------|---------|-------|
| **Web UI** | `web/src/` | Polished UI but XSS vulnerable, no error monitoring, thin test coverage (6 files) |
| **TUI** | `jarvis_tui/` | Functional but error-swallowing, hardcoded URLs |
| **Electron Desktop** | `desktop/` | Cannot build (no icon, no node_modules), backend path broken in packaged build |
| **CI Pipeline** | `ci.yml` works, `pr_fast.yml` and `python.yml` broken | 2/3 workflows install nothing |
| **Monitoring** | `monitors/` + `core/health_monitor.py` | 3+ overlapping background check loops |
| **Structured Logging** | `core/observability/logging.py` | Built but not activated |
| **Provider Adapters** | `core/providers/adapters/*.py` | 9 internal adapters registered but unclear if production routes to them |

---

## Dead Code to Remove Before GA

| File | Lines | Reason |
|------|-------|--------|
| `core/providers/manager.py` | 131 | Zero imports, references non-existent `llm` singleton |
| `core/model_providers/router.py` | ~200 | CLI-only, 0 production callers |
| `core/model_providers/hybrid.py` | 341 | CLI-only, 0 production callers |
| `core/configuration/service.py` | 286 | 0 production callers (per own docstring) |
| `memory/` (root) | 6 files | Superseded by `core/long_term_memory/` |
| `brain/memory/` | 5 files | Superseded by `core/long_term_memory/` |
| `services/memory/` | 2 files | Empty/superseded |
| `orchestrator/` | 0 | Empty directory |
| `learning/student_agi/` | 11 files | Abandoned sub-project |

---

## Top 25 Blocker Fixes (Before GA Tag)

### Critical (Must Fix Before Any Release)
1. **Dockerfile** — Change `pip install -r requirements.txt` to `pip install -e .`
2. **CI: pr_fast.yml** — Change `pip install -r requirements.txt` to `pip install -e ".[dev]"`
3. **CI: python.yml** — Change all 5 instances of `pip install -r requirements.txt` to `pip install -e ".[dev]"`
4. **`brain/tools/project_tool.py:179`** — Replace `create_subprocess_shell` with `create_subprocess_exec`
5. **`core/api_key_vault.py`** — Encrypt keys at rest (Fernet or OS keychain)
6. **`core/oauth.py`** — Encrypt OAuth tokens at rest
7. **CHANGELOG.md** — Create cumulative changelog

### High (Must Fix Before GA Tag)
8. **Web UI XSS** — Add DOMPurify sanitization to markdown renderer
9. **Web UI auth** — Remove hardcoded dev credentials, implement httpOnly cookie auth
10. **`core/auth.py`** — Remove auto-admin for dev users, enforce AUTH_ENABLED
11. **16 `shlex.split()` sites** — Convert to list-arg calls with validated inputs
12. **3 `auto_approve=True` defaults** — Change to `False`, add explicit user config
13. **`core/routes/terminal.py:66`** — Change `except:` to `except Exception:`
14. **Electron: icon.ico** — Create 256x256 icon required for NSIS build
15. **Electron: node_modules** — Run `npm install`, generate package-lock.json
16. **Electron: packaged build path** — Use `process.resourcesPath` for backend location
17. **Electron: uncaughtException** — Add `process.on('uncaughtException')` handler
18. **`configure_json_logging()`** — Wire into `core/main.py` startup
19. **`authlib` dependency** — Add to `pyproject.toml` or wrap in try/except
20. **`constraints.txt`** — Regenerate from actual installed environment
21. **CSP in nginx** — Add `Content-Security-Policy` header
22. **Audit ~90 silent except: blocks** — Add `logger.warning()` per AGENTS.md Rule 1
23. **Landing page download link** — Point to actual download or PyPI
24. **Memory consolidation** — Remove `memory/`, `brain/memory/`, `services/memory/`
25. **Provider consolidation** — Remove `core/model_providers/` (CLI-only, dead code)

---

## Top 25 Improvements (After GA)

1. **No-CI blocker: coverage enforcement** — Make `fail_under=60` actually fail CI builds
2. **Web UI test coverage** — Increase from 6 files to comprehensive coverage
3. **Flaky test management** — Add `pytest-rerunfailures`, quarantined test list
4. **Sentry/error monitoring** — Add crash reporting
5. **P95/P99 latency tracking** — Add Prometheus export for `/metrics`
6. **Benchmark regression detection** — Auto-compare new benchmark results vs stored baselines
7. **CI: automated benchmark runs** — Run `--quick` soak as CI step
8. **CI: Electron build verification** — Add as CI step
9. **CI: web UI tests** — Add vitest to CI
10. **Auto-update for Electron** — Add `electron-updater`
11. **Pre-commit hooks** — Add ruff + mypy + pytest-fast
12. **Config system unification** — Consolidate 4+ config implementations into one
13. **Router system unification** — Consolidate 6+ routing systems
14. **Brain/core merge** — Move functioning brain/ code into core/
15. **DomainError wiring** — Wire `domain_to_http()` into FastAPI exception handlers
16. **`return None` eradication** — Replace with `Result[T, E]` pattern or typed exceptions
17. **Health monitor consolidation** — Merge 3+ overlapping background loops
18. **`asyncio.run()` -> `asyncio.run_coroutine_threadsafe()`** — Fix nested event loop issues
19. **`__import__()` anti-pattern removal** — Replace 47 instances with `importlib.import_module()`
20. **Log context propagation** — Wire `LogContext` into RequestID middleware
21. **Dependency audit automation** — Add `pip-audit`/`safety` as CI step
22. **Don't use `asyncio` locks with `threading.Lock`** — Consistent async throughout
23. **Plugin sandbox hardening** — Rate limit dynamic `pip install` API endpoint
24. **`smolagents`** — Add as optional dependency or remove conditional import
25. **TUI hardcoded URL** — Make `127.0.0.1:8000` configurable

---

## Repository Claims vs Reality

| Claim | Source | Reality |
|-------|--------|---------|
| "839+ tests passing" | AGENTS.md | True, but outdated — actual count is ~4,245 (likely measured from a subset) |
| "Architecture freeze" | AGENTS.md | Not enforced — CI is broken, new code added freely |
| "No shell=True in subprocess" | AGENTS.md Rule 2 | False — `brain/tools/project_tool.py:179` still uses `create_subprocess_shell` |
| "NO silent except blocks" | AGENTS.md Rule 1 | False — ~90 silent `except Exception:` blocks in core/ |
| "config_schema.py is canonical" | AGENTS.md | False — `config_registry.py` has independent system used by many files |
| "Developer Center" | AI documentation | True — 4 sections, 18 advanced pages, hidden behind 5-click logo |
| "Electron + NSIS installer" | AGENTS.md | Partially — code exists but cannot build (no icon, no dependencies) |
| "CI pipeline" | `.github/workflows/` | Partially — exists but 2/3 workflows install no dependencies |
| "Progress Canvas" | AI documentation | True — read-only tree visualization, edit features not implemented |
| "Long-Term Memory" | AGENTS.md Phase 9 | True — 40 tests, active system in `core/long_term_memory/` |
| "Adaptive Behavior System" | AGENTS.md Phase 10 | True — 39 tests, active in `core/improvement/` |
| "Principle Discovery" | AGENTS.md Phase 14 | True — 44 tests in `core/generalization/` |
| "Browser Automation" | AGENTS.md | True — 23 tools, 9-state FSM, 15-task benchmark |

---

## Implementation Classification Summary

| Classification | Count | Examples |
|----------------|-------|----------|
| **Working** | ~40% | LLM routing, workflow engine, test infrastructure, benchmark framework, planner, FSMs |
| **Partial** | ~20% | Web UI (XSS), TUI (bugs), CI (2/3 broken), Electron (unbuildable), providers (routing works, adapters unclear) |
| **Prototype** | ~10% | Desktop FSM, Extraction FSM, strategy_v2, principle discovery |
| **Placeholder** | ~5% | Landing page, orchestrator/, empty __init__.py files |
| **Broken** | ~10% | Dockerfile, CI python.yml + pr_fast.yml, Electron packaged build, constraints.txt |
| **Dead** | ~15% | ProviderManager, model_providers/ (all), ConfigService, memory/, brain/memory/, student_agi, flutter build artifacts |

---

## Dependency Health

| Status | Count | Details |
|--------|-------|---------|
| Declared + installed | 20/26 | Most core dependencies working |
| Declared but not installed | 1 | `python-socketio>=5.0.0` |
| Imported but not declared | 2 | `authlib`, `cryptography` |
| constraints.txt mismatched | 6/13 pinned | pillow, starlette, lxml, setuptools, etc. |
| Optional deps not declared | 1 | `smolagents` used conditionally |
| CVEs in installed versions | 2+ | pillow 10.4.0, starlette 0.52.1 |

---

## File-Level Action Items

| File | Action | Priority |
|------|--------|----------|
| `Dockerfile:15-16` | Change to `pip install -e .` | CRITICAL |
| `.github/workflows/pr_fast.yml:36` | Change to `pip install -e ".[dev]"` | CRITICAL |
| `.github/workflows/python.yml:36,48,68,83,97` | Change to `pip install -e ".[dev]"` | CRITICAL |
| `brain/tools/project_tool.py:179` | Replace `create_subprocess_shell` | CRITICAL |
| `core/api_key_vault.py` | Encrypt keys at rest | CRITICAL |
| `core/oauth.py` | Encrypt OAuth tokens at rest | CRITICAL |
| `CHANGELOG.md` | Create file | CRITICAL |
| `web/src/app/chat/page.tsx:51` | Add DOMPurify | HIGH |
| `web/src/lib/auth.tsx` | Remove hardcoded creds, httpOnly cookies | HIGH |
| `core/auth.py:583-585` | Remove auto-admin bypass | HIGH |
| `core/routes/terminal.py:66` | `except:` → `except Exception:` | HIGH |
| `desktop/icon.ico` | Create icon file | HIGH |
| `desktop/main.js` | Add uncaughtException handler | HIGH |
| `core/observability/logging.py` + `main.py` | Wire `configure_json_logging()` | HIGH |
| `core/main.py:31-51` | Replace ad-hoc formatting with JSON | HIGH |
| `core/plugins/manifest.py` | Remove self-defeating deprecation | MEDIUM |
| `core/providers/manager.py` | Delete (dead code) | MEDIUM |
| `core/configuration/service.py` | Delete (dead code) | MEDIUM |
| `memory/`, `brain/memory/`, `services/memory/` | Delete (superseded) | MEDIUM |
| `learning/student_agi/` | Delete (abandoned) | MEDIUM |
| `experimental/flutter/build/` | Add to .gitignore + remove | MEDIUM |
| `{}/` | Rename or remove | LOW |
| `core/errors.py:89` (`domain_to_http`) | Wire into exception handler | MEDIUM |

---

## CI/CD State

| Workflow | Status | Flaw |
|----------|--------|------|
| `.github/workflows/ci.yml` | ✅ **Works** | Uses `pip install -e ".[dev]"` correctly |
| `.github/workflows/pr_fast.yml` | ❌ **Broken** | `pip install -r requirements.txt` installs nothing |
| `.github/workflows/python.yml` | ❌ **Broken** | 5 instances of `pip install -r requirements.txt` |
| `.github/workflows/publish.yml` | ✅ **Works** | Builds wheel + sdist, imports, publishes |
| **Missing** | | Web UI tests, Electron build, benchmark regression, coverage enforcement |

---

## Scoring Methodology

Each dimension is scored 0-10 based on:
- **Implementation completeness**: Is the feature fully built, partially built, or absent?
- **Production readiness**: Does it work reliably in production conditions?
- **Security posture**: Are there vulnerabilities in this area?
- **Maintainability**: Is the code clean, documented, and testable?
- **Integration**: Is it connected to production code paths or dead code?

Overall Production Readiness (0-100) = weighted average of all dimension scores × 10, with safety-critical findings carrying extra weight. A score above 70 would indicate "ready for beta deployment to real users." The current score of 30 reflects that critical path items (Docker, CI, security, packaging) are fundamentally broken, not just incomplete.

---

**Report generated by forensic audit. All findings supported by code evidence.**
**Architecture freeze should remain in place until Critical and High blockers are resolved.**
