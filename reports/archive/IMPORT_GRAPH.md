# PHASE 2 — Import Graph

Complete dependency graph for all Python files. Every claim verified by reading actual code.

---

## Entry Points

| Entry Point | File | Imported By |
|-------------|------|-------------|
| CLI entry | `jarvis.py` | Direct execution |
| FastAPI server | `core/main.py` | `cli_server.py`, `start_server.py` |
| CLI commands | `cli_commands.py` | `jarvis.py` |
| CLI requests | `cli_requests.py` | `cli_commands.py` |
| CLI server mgmt | `cli_server.py` | `cli_commands.py`, `cli_requests.py` |
| Agent loop | `core/agent_loop.py` | `core/routes/websocket.py`, `core/routes/chat.py` |
| Agent orchestrator | `core/agent_orchestrator.py` | `cli_commands.py`, `core/plan_routes.py` |

---

## Core Module Dependency Graph

```
jarvis.py
 └─► cli_commands.py
       ├─► cli_requests.py
       │     ├─► cli_utils.py, cli_state.py
       │     ├─► cli_server.py → cli_utils.py, cli_state.py
       │     ├─► jarvis_os.bootstrap (lazy)
       │     └─► core.routing (lazy)
       ├─► cli_server.py
       ├─► cli_helpers.py, cli_slash_commands.py
       ├─► cli_state.py, cli_utils.py
       ├─► cli_visuals.py / cli_visuals_new.py
       ├─► cli_completer.py, cli_config.py
       ├─► core.agent_orchestrator
       ├─► core.session.ConversationManager
       ├─► core.model_providers.*
       ├─► core.feature_registry
       ├─► core.diagnostics
       ├─► core.settings.store, core.config_registry
       ├─► core.plugins.*, core.skill_loader
       ├─► core.sub_agents.registry
       ├─► core.memory.*, core.memory_vector
       ├─► core.pattern_failure_memory
       ├─► core.integration_manager
       ├─► core.api_key_vault
       ├─► core.cloud.*
       ├─► brain.automation.loop
       ├─► jarvis_os.interface.cli (lazy)
       ├─► cognitive_agent.main (lazy)
       └─► jarvis_tui.main (lazy)

core/main.py (FastAPI app)
 ├─► core.config, core.lifespan, core.middleware
 ├─► core.observability.metrics, core.rate_limiter
 ├─► api/* — ALL api/ route modules mounted
 ├─► core/routes/* — ALL core/routes/ modules mounted
 ├─► routers/* — ALL routers/ modules mounted
 ├─► core/plan_routes, core/supervisor_routes, core/build_routes
 ├─► automation/routes, automation/call_sync_server
 ├─► learning/student_agi/api/student_routes
 └─► assistant/* (lazy, for voice routes)

core/agent_loop.py
 └─► core/graph (build_default_graph)
      ├─► core/graph/state.py (AgentState)
      ├─► core/graph/graph.py (StateGraph)
      ├─► core/graph/nodes.py (10 node functions)
      │     ├─► core/agent_helpers.py
      │     ├─► core/agent_prompts.py
      │     ├─► core/tools/execution.py
      │     ├─► core/tools/hot_files.py
      │     ├─► core/llm_core.py
      │     ├─► core/context_builder.py
      │     │     ├─► memory/memory_facade.py
      │     │     └─► core/session.py
      │     ├─► core/sub_agents/tool.py
      │     ├─► core/prompt_security.py
      │     ├─► services/memory/skills.py
      │     └─► brain/tools/tool_registry.py (lazy)
      └─► core/graph/edges.py (route_decision)

core/tools/execution.py
 ├─► core/tools/implementations.py
 │     ├─► core/tools/skill_tools.py
 │     ├─► core/tools/settings_tools.py
 │     ├─► core/tools/admin_tools.py
 │     ├─► core/tools/cookbook_tools.py
 │     ├─► core/tools/document_tools.py
 │     ├─► core/tools/vision_tools.py
 │     └─► core/tools/persistent_shell.py
 ├─► core/tools/security.py
 ├─► core/tools/hot_files.py
 ├─► core/tools/bg_jobs.py (CRITICAL: shell=True)
 ├─► core/tools/index.py
 ├─► core/prompt_security.py
 ├─► core/ssrf.py
 ├─► core/session.py
 ├─► core/config_registry.py
 └─► memory/memory_facade.py

memory/memory_facade.py
 ├─► memory/tiered_memory.py
 │     ├─► memory/mem0_adapter.py (ChromaDB)
 │     └─► memory/embedding_memory.py (SQLite + Ollama)
 └─► memory/mem0_adapter.py

brain/ (autonomous OS)
 ├─► brain/UnifiedBrain.py
 │     ├─► brain/reasoning_engine.py → core.llm_router
 │     ├─► brain/cognitive_patterns.py → reasoning_engine
 │     ├─► brain/memory/memory_manager.py
 │     │     ├─► brain/memory/episodic.py (SQLite)
 │     │     ├─► brain/memory/semantic.py (SQLite)
 │     │     ├─► brain/memory/task.py (SQLite)
 │     │     └─► brain/memory/decision.py (SQLite)
 │     ├─► brain/goals/goal_manager.py (SQLite)
 │     ├─► brain/planner/planner.py → task_graph.py
 │     ├─► brain/executor/executor.py
 │     ├─► brain/executor/verifier.py
 │     ├─► brain/tools/tool_registry.py
 │     │     └─► core/tools/implementations.py
 │     ├─► brain/tools/project_tool.py
 │     ├─► brain/automation/loop.py
 │     │     ├─► brain/compiler_repair_engine.py
 │     │     ├─► brain/task_resolver.py
 │     │     └─► brain/memory/ (all 4 stores)
 │     ├─► brain/observers/observer_manager.py
 │     │     ├─► brain/observers/filesystem.py
 │     │     ├─► brain/observers/system_monitor.py
 │     │     └─► brain/observers/time_observer.py
 │     ├─► brain/events/event_bus.py (typed pub/sub)
 │     ├─► brain/world_model.py
 │     ├─► brain/learning_engine.py → decision_memory
 │     ├─► brain/goal_generator.py → world_model
 │     ├─► brain/skill_acquisition.py → task_memory
 │     ├─► brain/self_improvement.py → task_memory
 │     ├─► brain/persistence.py (SQLite)
 │     └─► brain/epistemic_tagger.py
```

---

## Orphan Files (Not Imported By Any Other Module)

These files exist but are never imported by any production code path. `tests/` and `scripts/` are excluded from this analysis (they're callers, not runtime).

| File | Reason Orphaned | Risk |
|------|----------------|------|
| `run_autonomous.py` | Standalone script, executed directly | LOW — direct execution entry point |
| `run_memory_audit.py` | Standalone script | LOW |
| `run_production_audit.py` | Standalone script | LOW |
| `run_stress_test.py` | Standalone script | LOW |
| `run_validation.py` | Standalone script | LOW |
| `locustfile.py` | Load testing, loaded by locust CLI | LOW |
| `login_body.json` | Data file | LOW |
| `project_root/` (Main.java + MainTest.java) | Test fixture, not Python | LOW |
| `android-calculator/` (all files) | Dead project | HIGH — dead code |
| `android_calculator/` (all files) | Dead project | HIGH — dead code |
| `build_an_android_calculator_ap/` (all files) | Dead project | HIGH — dead code |
| `e2e/` test files | Test-only | N/A |
| `contract/` test files | Test-only | N/A |
| Various `_*.py` test scripts | Root-level test scripts | N/A |

---

## Circular Imports

No circular import chains were found after analyzing the import structure. The dependency graph is acyclic at the module level.

**Potential risk areas (lazy imports prevent runtime cycles):**
- `cli_commands.py` has lazy imports of `core.*` and `brain.*` modules — intentional design
- `core/routes/websocket.py` has lazy imports of `core/config`, `core/plugins`, `core/rate_limiter`
- `brain/__init__.py` uses lazy imports (`_optional_import()`) for all sub-modules

---

## Duplicate Implementations

| Area | File 1 | File 2 | Overlap |
|------|--------|--------|---------|
| Settings system | `core/config_registry.py` | `core/settings/store.py` | Both manage config, different backends |
| Memory system | `memory/memory_facade.py` | `core/memory.py` | Both store/recall memories, different backends |
| Vector memory | `memory/embedding_memory.py` | `core/memory_vector.py` | Both use ChromaDB/embeddings |
| Process execution | `core/tools/execution.py` (bash/python tools) | `crauto/repair/executor.py` | Both run subprocesses |
| WebSocket streaming | `core/routes/websocket.py` | `network/websocket_server.py` | Both handle WebSocket connections |
| Shell execution | `core/tools/persistent_shell.py` | `brain/executor/executor.py` | Both manage shell execution |

---

## Legacy Replacements

| Legacy | Replacement | Migration Status |
|--------|-------------|-----------------|
| `core/memory.py` (JSON-based) | `memory/memory_facade.py` (tiered vector) | Partial — both still used |
| `core/memory_vector.py` (ChromaDB) | `memory/mem0_adapter.py` (mem0) | Partial — coexisting |
| `core/settings_legacy.py` | `core/settings/store.py` | Partial — references remain |
| `app/` (old web app) | `web/` (Next.js) | Complete — `app/` is dead |
| `brain/memory/memory_manager.py` (SQLite) | `memory/memory_facade.py` (tiered) | No migration — different use cases |
| `brain/executor/executor.py` | `core/tools/execution.py` | No migration — two parallel systems |

---

## Module-Level Singletons (30+ found)

These are module-level instances created at import time. Eager initialization can cause startup latency and hidden dependencies.

| Singleton | File:Line | Created |
|-----------|-----------|---------|
| `config` | `core/config_registry.py:441` | At import |
| `jarvis_config` | `core/config_schema.py:381` | At import |
| `vault` | `core/api_key_vault.py:144` | At import |
| `emotion_detector` | `core/audio_emotion.py:361` | At import |
| `multimodal_pipeline` | `core/multimodal/pipeline.py:179` | At import |
| `checkpoint_store` | `core/persistence/store.py:336` | At import |
| `tag_invalidator` | `core/cache/invalidation.py:75` | At import |
| `unified_brain` | `brain/UnifiedBrain.py` | At import |
| `reasoning_engine` | `brain/reasoning_engine.py:214` | At import |
| `cognitive_patterns` | `brain/cognitive_patterns.py:213` | At import |
| `epistemic_tagger` | `brain/epistemic_tagger.py:117` | At import |
| `global_event_bus` | `brain/events/event_bus.py:138` | At import |
| `memory_manager` | `brain/memory/memory_manager.py:126` | At import |
| `executor` | `brain/executor/executor.py:187` | At import |
| `verifier` | `brain/executor/verifier.py:145` | At import |
| `observer_manager` | `brain/observers/observer_manager.py:98` | At import |
| `planner` | `brain/planner/planner.py:66` | At import |
| `tool_registry` | `brain/tools/tool_registry.py:103` | At import |
| `project_tool` | `brain/tools/project_tool.py:308` | At import |
| `production_gate` | `brain/production_gate.py:240` | At import |
| `task_resolver` | `brain/task_resolver.py:321` | At import |

**Lazy singletons** (None, initialized on first use):
- `learning_engine` — `brain/learning_engine.py`
- `automation_loop` — `brain/automation/loop.py`
- `get_settings_store()` — `core/settings/store.py`
- `get_platform()` — `core/model_providers/hybrid.py`
- `get_router()` — `core/model_providers/router.py`
