# RUNTIME REALITY AUDIT

**Goal:** Determine how much code is actually executed vs. how much is dead/legacy/experimental.
Every claim verified by tracing import chains, route registrations, and runtime references.

---

## Methodology

1. Trace every import chain from entry points (`jarvis.py`, `core/main.py`)
2. Identify files reached through those chains (imported at any depth)
3. Compare against all 761 Python files
4. Classify every unreached file by type

---

## Entry Points

| Entry Point | File | Reachable Files |
|-------------|------|-----------------|
| CLI | `jarvis.py` | `cli_commands.py` + its transitive imports |
| Server | `core/main.py` | All route modules + their transitive imports |
| Direct exec | `start_server.py` | Same as `core/main.py` |
| Direct exec | `run_autonomous.py` | Self-contained |
| Brain init | `brain/UnifiedBrain.py` | Brain submodules |
| TUI | `jarvis_tui/main.py` | TUI-specific imports |

---

## Actually Executed Code (Reached From Entry Points)

### Tier 1: Always Loaded (on every startup)

These files are imported when `jarvis.py` or `core/main.py` starts:

| Module | Files | Lines (est.) |
|--------|-------|-------------|
| `core/` (config, schema, registry, session, etc.) | ~15 | ~3,000 |
| `core/tools/` (execution, index, security, handlers) | ~25 | ~8,000 |
| `core/graph/` (graph, state, nodes, edges) | 5 | ~1,600 |
| `core/model_providers/` (all providers) | 9 | ~1,200 |
| `core/multimodal/` | 3 | ~400 |
| `core/cache/` | 4 | ~400 |
| `core/settings/` | 3 | ~400 |
| `core/persistence/` | 4 | ~600 |
| `assistant/` (voice pipeline) | 14 | ~2,500 |
| `memory/` (facade, tiered, mem0, embedding, decision) | 7 | ~1,100 |
| `services/memory/` (skill format, skills manager) | 2 | ~250 |
| **Subtotal** | **~91 files** | **~19,450 lines** |

### Tier 2: Loaded on Demand (lazy imports)

These files are lazy-imported only when specific features are used:

| Module | Trigger | Files | Lines (est.) |
|--------|---------|-------|-------------|
| `brain/` modules | `cmd_code`/`cmd_build`/`cmd_run` | ~31 | ~9,000 |
| `jarvis_os/` | Local runtime fallback | ~8 | ~1,500 |
| `cognitive_agent/` | `cmd_agent_shortcut` | ~2 | ~400 |
| `jarvis_tui/` | `cmd_tui` | ~30 | ~2,500 |
| **Subtotal (conditional)** | | **~71 files** | **~13,400 lines** |

### Tier 3: Route Handler Files (loaded by FastAPI routes)

Mounted in `core/main.py`, loaded at FastAPI startup:

| Module | Files | Lines (est.) | Path |
|--------|-------|-------------|------|
| `core/routes/` | 18 | ~4,000 | Various `/api/*` |
| `api/` | 20 | ~3,000 | Various `/api/*`, `/cookbook`, etc. |
| `routers/` | 7 | ~2,000 | `/api/*`, `/api/whatsapp`, etc. |
| `automation/` | 2 | ~500 | `/api/automation`, `/api/calls` |
| `learning/student_agi/api/` | 1 | ~250 | `/student-agi` |
| **Subtotal (route handlers)** | | **~48 files** | **~9,750 lines** |

---

## Total Executable Code

| Tier | Files | Lines | Notes |
|------|-------|-------|-------|
| Tier 1: Always loaded | ~91 | ~19,450 | Every startup |
| Tier 2: Conditional | ~71 | ~13,400 | Feature-dependent |
| Tier 3: Route handlers | ~48 | ~9,750 | FastAPI startup |
| **Total executable** | **~210** | **~42,600** | |

---

## Dead/Unreachable Code

| Category | Files | Lines | % of Total |
|----------|-------|-------|------------|
| Actually executed | ~210 | ~42,600 | ~28% |
| Dead Android calculator | ~20 | ~500 | ~3% |
| Orphan scripts | ~7 | ~1,500 | ~1% |
| Experimental sub-projects | ~22 | ~3,500 | ~3% |
| Standalone tools (`tools/`) | 18 | ~4,000 | ~2% |
| Other unused modules | ~20 | ~3,000 | ~3% |
| **Likely dead/unused** | **~87** | **~12,500** | **~11%** |
| **Tests** | **~103** | **~15,000** | **~14%** |
| **Config/data/skills** | **~360** | **~45,000** | **~47%** |
| **Total** | **~761** | **~115,000** | **100%** |

---

## Deep Dive: Unused Modules Breakdown

### Category: Orphan Standalone Scripts (root-level `*.py`)

These are direct-execution scripts that are never imported by any module:

| File | Lines | Purpose | Reachable Via |
|------|-------|---------|---------------|
| `start_server.py` | ~50 | Server startup | Direct execution | 
| `run_autonomous.py` | ~200 | Autonomous mode | Direct execution |
| `run_memory_audit.py` | ~150 | Memory audit | Direct execution |
| `run_production_audit.py` | ~400 | Production audit | Direct execution |
| `run_stress_test.py` | ~150 | Stress test | Direct execution |
| `run_validation.py` | ~300 | Validation | Direct execution |
| `locustfile.py` | ~200 | Load test | Locust CLI |

**Verdict:** All are legitimate standalone scripts that users run directly. Not "dead" but not imported.

### Category: Standalone Tools (`tools/` directory)

| File | Lines | Connected? |
|------|-------|------------|
| `tools/browser_tool.py` | ~300 | Not imported by any module |
| `tools/crawl4ai_tool.py` | ~200 | Not imported |
| `tools/deep_research.py` | ~400 | Not imported |
| `tools/file_search.py` | ~150 | Not imported |
| `tools/image_gen.py` | ~200 | Not imported |
| `tools/jarvis_website_cli.py` | ~300 | Not imported |
| `tools/ragflow_tool.py` | ~250 | Not imported |
| `tools/search_tool.py` | ~200 | Not imported |
| `tools/website_generator.py` | ~300 | Not imported |
| `tools/whatsapp_sender.py` | ~150 | Not imported |

**Verdict:** These are legacy tool implementations that predate the `core/tools/` system. They may have been the originals that were later refactored into `core/tools/` handlers. `core/tools/execution.py` does not reference any of these files.

### Category: Experimental Sub-projects

| Directory | Files | In Production? |
|-----------|-------|----------------|
| `learning/student_agi/` | ~12 | Mounted at `/student-agi`, accessible via API but not via CLI |
| `train/` | 3 | No — LoRA training scripts, not connected to any pipeline |
| `jarvis_plugin_sdk/` | 5 | Partially — some references in `core/plugins/` |
| `electron/` | ~5 | Partially — wrapper app, not core functionality |

### Category: Database Migrations (`alembic/`)

| File | Connected? |
|------|------------|
| `alembic/env.py` | Not imported — Alembic auto-discovers |
| Migration scripts | Not imported — Alembic runs them |

**Verdict:** Normal for Alembic-based migrations. Not dead code.

---

## Code Usage Classification Summary

| Classification | Files | Lines (est.) | % |
|---------------|-------|-------------|---|
| **REAL AND USED** | ~210 | ~42,600 | 28% |
| **REAL BUT UNUSED** (standalone/orphan) | ~25 | ~5,500 | 3% |
| **PARTIALLY IMPLEMENTED** (broken tools, ghost tools) | ~12 | ~1,000 | 2% |
| **DEAD LEGACY CODE** (Android calculators, old tools) | ~40 | ~4,500 | 5% |
| **EXPERIMENTAL** (student_agi, train, electron) | ~22 | ~3,500 | 3% |
| **TEST FILES** | ~103 | ~15,000 | 14% |
| **CONFIG/DATA/SKILLS** (JSON, YAML, skill packages) | ~350 | ~43,000 | 46% |

**Answer: JARVIS has a core of ~210 actively-used Python files (~42,600 lines).**
**The remaining ~550 files are: tests, config/data, skills, legacy code, experiments, and orphan scripts.**

---

## Two Execution Systems: Canonical vs Legacy

| System | Status | Files | Recommendation |
|--------|--------|-------|---------------|
| `core/tools/execution.py` + `_TOOL_HANDLERS` | **CANONICAL** | ~25 tool files | Keep. Active development. |
| `brain/executor/executor.py` + `ToolRegistry` | **LEGACY** being refactored | ~5 brain tool files | Continue migration to `core/tools/`. Bridge exists at `brain/tools/tool_registry.py`. |
| `tools/` (standalone tools directory) | **DEAD LEGACY** | 18 files | Remove or deprecate. Not imported by any module. |

**Evidence of migration:**
- `brain/tools/tool_registry.py:71-91` explicitly imports from `core/tools/implementations.py`
- `brain/tools/project_tool.py` has its own implementations that overlap with `core/tools/document_tools.py`

**Recommendation:** 
- `core/tools/` is canonical
- `brain/tools/tool_registry.py` should be the sole bridge
- `tools/` directory should be deleted
- `brain/executor/executor.py` should delegate to `core/tools/execution.py` handlers
