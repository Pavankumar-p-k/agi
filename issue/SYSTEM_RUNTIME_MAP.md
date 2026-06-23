# SYSTEM RUNTIME MAP — JARVIS Reality Audit

> Generated: 2026-06-10
> Method: Python import test + static import analysis (no docs/comments trusted)

---

## Classification Legend

| Status | Meaning |
|--------|---------|
| **ACTIVE** | Importable, referenced by production code, removal breaks runtime |
| **PARTIAL** | Importable but self-contained (not imported by other Python code); may connect via HTTP |
| **LEGACY** | Importable but being replaced; still referenced but slated for removal |
| **DEAD** | Not importable, not referenced, no runtime impact if removed |

---

## 1. `core/` — ACTIVE

| Check | Result |
|-------|--------|
| Python import | `import core` — OK (core\__init__.py) |
| Imported by | 100+ files across the entire codebase: jarvis.py, cli_*.py, ai_os/, assistant/, channels/, daemon/, demo/, governance/, models/, mcp/, tests/ |
| Active code paths | Entry point (jarvis.py), CLI, FastAPI server, agent loop, tool execution, config, database, auth, etc. |
| Can be deleted? | **NO** — removing this would collapse the entire system |

**Verdict**: Core runtime. Central nervous system of JARVIS.

---

## 2. `brain/` — ACTIVE

| Check | Result |
|-------|--------|
| Python import | `import brain` — OK (brain\__init__.py) |
| Imported by | 32+ files: api/server.py, channels/processor.py, core/adversarial.py, core/config_init.py, core/document_processor.py, core/lifespan.py, core/prompts.py, core/real_validator.py, core/routes/websocket.py, core/routes/admin.py, governance/GovernanceValidator.py, learning/student_agi/, routers/chat.py, tools/scene_generator.py, _archive/dreaming.py |
| Active code paths | UnifiedBrain, epistemic tagging, reasoning engine, prompt optimization, cognitive patterns, execution context |
| Can be deleted? | **NO** — deep integration with core modules and API server |

**Verdict**: Active reasoning layer. Provides UnifiedBrain, epistemic_tagger, reasoning_engine, cognitive_patterns, prompt_optimizer, execution_context.

---

## 3. `memory/` — ACTIVE

| Check | Result |
|-------|--------|
| Python import | `import memory` — OK (memory\__init__.py) |
| Imported by | 29+ files: api/server.py, api/memory_routes.py, core/context_builder.py, core/control_loop.py, core/routes/chat.py, core/routes/intelligence.py, core/sub_agents/agents/nexus.py, mcp/server.py, learning/student_agi/, _archive/dreaming.py, tests/ |
| Active code paths | MemoryFacade (primary entry point), tiered memory, embedding memory, decision memory, mem0 adapter |
| Can be deleted? | **NO** — removing would break core memory-dependent features and API endpoints |

**Verdict**: Active memory subsystem. Uses facade pattern via memory.memory_facade.MemoryFacade.

---

## 4. `skills/` — ACTIVE

| Check | Result |
|-------|--------|
| Python import | `import skills` — OK (skills\__init__.py) |
| Imported by | 55+ files: ai_os/orchestrator.py, core/lifespan.py, core/governance/work_queue.py, routers/jarvishub.py, core/skill_loader.py (docstring), all 40+ skill implementations under skills/library/ |
| Active code paths | Skill loading via core/skill_loader, skill manager, skill registry, individual skill execution |
| Can be deleted? | **NO** — removing would disable all skill-based functionality |

**Verdict**: Active skill system with 40+ individual skills in library/. skills.utils provides helpers used by all skills.

---

## 5. `tools/` — ACTIVE

| Check | Result |
|-------|--------|
| Python import | `import tools` — OK (tools\__init__.py) |
| Imported by | 83+ files: jarvis.py, cli_slash_commands.py, api/hybrid_integration.py, api/research_routes.py, api/ragflow_routes.py, api/website_routes.py, mcp/server.py, routers/whatsapp.py, routers/chat.py, orchestrator/hybrid_orchestrator.py, core/control_loop.py, core/context_builder.py, core/main.py, core/lifespan.py, core/integrations/*.py, core/routes/*.py, core/sub_agents/*.py, tests/ |
| Active code paths | Search, executor (OpenClaw), browser, website generator, deep research, RAGflow, template library, WhatsApp sender, image generation, scene generation |
| Can be deleted? | **NO** — widely imported, many lazy imports at runtime |

**Verdict**: Active standalone tools package. Contains executor.py, search_tool.py, browser_tool.py, website_generator.py, deep_research.py, image_gen.py, etc. Note: this is NOT the same as core/tools/.

---

## 6. `agents/` — DEAD

| Check | Result |
|-------|--------|
| Python import | `import agents` — ModuleNotFoundError |
| Imported by | Zero production imports found |
| Active code paths | None |
| Can be deleted? | **YES** — directory does not exist at project root (was deleted in commit 9bab93e "v1.0 release"). Only vestigial references remain in pyproject.toml include list and data/jarvis_os/agents/ directory. |

**Verdict**: Deleted in v1.0 release. The agents/ project directory is gone. It was replaced by core/sub_agents/. Remove "agents*" from pyproject.toml includes.

---

## 7. `api/` — ACTIVE

| Check | Result |
|-------|--------|
| Python import | `import api` — OK (api\__init__.py) |
| Imported by | 43+ files: core/main.py (primary consumer, registers all route handlers), tests/unit/test_*.py, api/*.py (self-refs) |
| Active code paths | FastAPI route handlers for: vision, cookbook, research, email, settings, website, plugin, cloud, governance, memory, RAGflow |
| Can be deleted? | **NO** — core/main.py imports and registers 12+ API route modules |

**Verdict**: Active API route handlers. Contains 18 .py files providing FastAPI routers registered in core/main.py.

---

## 8. `routers/` — ACTIVE

| Check | Result |
|-------|--------|
| Python import | `import routers` — OK (routers\__init__.py) |
| Imported by | 11 files: core/main.py (primary consumer), core/routes/chat.py, routers/*.py (self-refs), tests/ |
| Active code paths | WhatsApp bot, screen capture, setup wizard, dot routes, JARVIS Hub, three-pass chat handler |
| Can be deleted? | **NO** — registered in core/main.py, provides communication channel endpoints |

**Verdict**: Active routing layer. Focused on communication channels (WhatsApp, screen, setup) plus the three-pass chat handler.

---

## 9. `ai_os/` — ACTIVE

| Check | Result |
|-------|--------|
| Python import | `import ai_os` — OK (warning for urllib3/chardet, but imports successfully) |
| Imported by | 15 files: core/settings/store.py, core/tools/execution.py, core/routes/infrastructure.py, core/governance/work_queue.py, api/ai_os_routes.py, pc_agent/computer_agent.py, tests/ |
| Active code paths | Docker sandbox, event bus, orchestrator, config, sandbox manager, tool registry |
| Can be deleted? | **NO** — core tool execution depends on docker_sandbox; settings depends on event_bus |

**Verdict**: Active "AI OS" subsystem. Provides Docker sandboxing, event bus, and orchestration.

---

## 10. `web/` — PARTIAL (frontend)

| Check | Result |
|-------|--------|
| Python import | `import web` — OK as namespace package (no __init__.py) |
| Imported by | Zero Python files import it |
| Active code paths | Not a Python module; it is a Next.js (TypeScript/Node.js) frontend. Connects to Python API via HTTP (web/src/lib/api.ts -> /api/chat, /api/health, /api/system/status). |
| Can be deleted? | **YES from Python package** — it does not affect Python runtime. But it IS used as a frontend. |

**Verdict**: Standalone Next.js frontend. Communicates with Python backend via HTTP API. Not part of Python import graph.

---

## 11. `jarvis_tui/` — PARTIAL (standalone TUI)

| Check | Result |
|-------|--------|
| Python import | `import jarvis_tui` — OK (jarvis_tui\__init__.py) |
| Imported by | Zero external Python imports. Only self-references within jarvis_tui/. |
| Active code paths | Standalone Textual TUI app. Entry: jarvis_tui/main.py (if __name__ == "__main__"). Not registered as a console_scripts entry point. |
| Can be deleted? | **YES from Python package** — no external imports. But it is a functional TUI client. |

**Verdict**: Standalone Textual-based TUI. Self-contained. Not integrated into the main import graph.

---

## 12. `electron/` — PARTIAL (desktop app)

| Check | Result |
|-------|--------|
| Python import | `import electron` — OK as namespace package (no __init__.py) |
| Imported by | Zero Python files import it |
| Active code paths | Standalone Electron/Node.js desktop app. electron/main.js connects to Python backend via JARVIS_URL=http://localhost:8000. |
| Can be deleted? | **YES from Python package** — no Python imports. But it is a built desktop client (78MB installer exists in dist/). |

**Verdict**: Standalone Electron desktop app. Communicates with Python API via HTTP. Not part of Python import graph.

---

## 13. `apps/jarvis_app/` — DEAD (mobile app)

| Check | Result |
|-------|--------|
| Python import | `from apps.jarvis_app import` — OK but no consumers |
| Imported by | Zero imports from any Python file |
| Active code paths | Flutter/Dart mobile app. Never imported by any Python module. |
| Can be deleted? | **YES from Python package** — zero imports. But it is a Flutter mobile app project. |

**Verdict**: Standalone Flutter mobile app project. Completely disconnected from Python runtime.

---

## Summary Table

| Directory | Status | Importable | Imported By | Can Remove from Python? |
|-----------|--------|------------|-------------|------------------------|
| core/ | **ACTIVE** | Yes | 100+ files | NO |
| brain/ | **ACTIVE** | Yes | 32 files | NO |
| memory/ | **ACTIVE** | Yes | 29 files | NO |
| skills/ | **ACTIVE** | Yes | 55+ files | NO |
| tools/ | **ACTIVE** | Yes | 83+ files | NO |
| agents/ | **DEAD** | No (missing) | 0 | YES |
| api/ | **ACTIVE** | Yes | 43 files | NO |
| routers/ | **ACTIVE** | Yes | 11 files | NO |
| ai_os/ | **ACTIVE** | Yes | 15 files | NO |
| web/ | PARTIAL | Yes (ns) | 0 (HTTP only) | YES |
| jarvis_tui/ | PARTIAL | Yes | 0 | YES |
| electron/ | PARTIAL | Yes (ns) | 0 (HTTP only) | YES |
| apps/jarvis_app/ | DEAD | Yes | 0 | YES |

**Key finding: 9 ACTIVE directories, 3 PARTIAL, 1 DEAD (agents/), 1 DEAD for Python (apps/jarvis_app/).**
