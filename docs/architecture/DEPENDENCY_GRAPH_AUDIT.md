# Dependency Graph Audit — Phase 0 (Document 1)

> **Purpose:** Every import relationship, circular import, singleton ownership, bootstrap order, runtime initialization, and global state across the entire codebase.
>
> **Scope:** All `.py` files in the JARVIS project (~450+ files across 30+ packages).
>
> **Prerequisite for:** All remaining audit phases. Without this map, every later audit has blind spots.

---

## Table of Contents

1. [Package Inventory](#1-package-inventory)
2. [Layer Architecture](#2-layer-architecture)
3. [Import Direction Map](#3-import-direction-map)
4. [Circular Dependencies](#4-circular-dependencies)
5. [Singleton Registry](#5-singleton-registry)
6. [Global Mutable State](#6-global-mutable-state)
7. [sys.path Mutations & Side Effects](#7-syspath-mutations--side-effects)
8. [Lazy Import Catalog](#8-lazy-import-catalog)
9. [Bootstrap Order](#9-bootstrap-order)
10. [Key Findings & Risks](#10-key-findings--risks)
11. [Recommendations](#11-recommendations)

---

## 1. Package Inventory

### Layer 0 — Entry Points

| Package | Files | Role |
|---------|-------|------|
| `jarvis.py` (root) | 1 | CLI entry point, argparse, dispatches to `cli_commands` |
| `cli_commands` (implicit) | 1+ | All command handlers (chat, code, build, etc.) |

### Layer 1 — Core Framework (`core/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `core/` (root) | ~45 | Config, LLM routing, pipeline, identity, auth, errors, types, events, scheduling, plugins, memory, sandbox, tools, workflow, scheduler, planner, research, capability, providers, governance, sessions, settings, routes |
| `core/pipeline/` | 19 + 5 adapters + 19 stages = 43 | 19-stage canonical request pipeline |
| `core/pipeline/adapters/` | 5 | Channel, REST, WebSocket, Voice adapters |
| `core/pipeline/stages/` | 19 | Individual pipeline stage implementations |
| `core/providers/` | 11 + 4 orchestration + 7 adapters + 4 feedback = 26 | Provider registry, routing, memory, budget, orchestration, adapters |
| `core/providers/adapters/` | 10+ | Concrete provider implementations (Forge, Claude, Codex, Browser, Research, etc.) |
| `core/providers/feedback/` | 4 | Calibration, recording, storage for provider feedback |
| `core/providers/orchestration/` | 5 | Multi-provider orchestration |
| `core/capability/` | 6 | Capability models, registry, graph, negotiation, composition |
| `core/identity/` | ~8+ | Identity, sessions, tenants, RBAC, scopes |
| `core/tools/` | ~10+ | Tool execution, parsing, constants, individual tool implementations |
| `core/agents/` | ~10+ | Agent registry, sub-agents (legacy), runtime, prompts |
| `core/routes/` | ~25 | FastAPI route definitions for admin, activity, auth, brain, etc. |
| `core/scheduler/` | ~5 | Activity scheduler, queue, models, store |
| `core/workflow/` | ~8 | Workflow engine, models, storage, tracker, events |
| `core/planner/` | ~8 | Plan comparison, decomposition, evidence, health, outcomes, replan, store, strategies |
| `core/research/` | ~5 | Research planner, storage, synthesizer, models |
| `core/event_bus.py` | 1 | Central event bus singleton |
| `core/llm_router.py` | 1 | LLM request routing |
| `core/main.py` | 1 | Core startup/initialization |

### Layer 2 — Brain (`brain/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `brain/` (root) | 12 | UnifiedBrain, reasoning engine, cognitive patterns, memory manager, goals, planner, executor, persistence, learning, skill acquisition, self-improvement, goal generator |
| `brain/events/` | 3 | Event bus (re-export from core), event types |
| `brain/memory/` | 6 | Memory providers (episodic, semantic, task, decision), manager |
| `brain/goals/` | 3 | Goal models, goal manager |
| `brain/planner/` | 3 | Task graph, planner |
| `brain/executor/` | 3 | Executor, verifier |
| `brain/observers/` | 4 | Observer manager, filesystem, system monitor, time observer |
| `brain/automation/` | 2 | Automation loop (2679 lines — largest single file) |
| `brain/repair_modules/` | 9 | Android-focused code repair (imports, class names, manifest, layouts, gradle, etc.) |
| `brain/compiler_repair_engine.py` | 1 | 944-line compiler error repair engine |
| `brain/learning_engine.py` | 1 | Learning engine |
| `brain/production_gate.py` | 1 | Production readiness gate |
| `brain/prompt_optimizer.py` | 1 | Prompt optimization |

### Layer 3 — Assistants & Channels (`assistant/`, `channels/`, `automation/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `assistant/` | 14 | Wake word, voice pipeline, TTS, STT, providers (faster-whisper, deepgram, azure, kokoro, edge-tts) |
| `channels/` | 10 | Telegram, Slack, Matrix, IRC, Discord, Email channel plugins |
| `automation/` | 5 | PC automation (deprecated), messaging, call sync server, routes |

### Layer 4 — Integrations (`integrations/`, `mcp/`, `notifications/`, `network/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `integrations/gmail/` | 4 | Gmail auth, client, types |
| `integrations/whatsapp/` | 10 | WhatsApp Cloud API, Twilio, webhook, media, history, models |
| `mcp/` | 7 | MCP server, email server, memory server, image gen server, rag server |
| `notifications/` | 1 | Supervisor notifier |
| `network/` | 2 | WebSocket server, connection manager |

### Layer 5 — Persistence & Memory (`memory/`, `services/`, `learning/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `memory/` | 10 | Tiered memory, memory facade, mem0 adapter, fact store, embedding memory, decision memory, reranker, preference profile, extraction |
| `services/memory/` | 2 | Skill format, skills manager |
| `learning/` | 15 | Training collector, pattern engine, habit tracker, student AGI subsystem |

### Layer 6 — Provider SDK (`provider_sdk/`, `jarvis_plugin_sdk/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `provider_sdk/` | 17 | Manifest (v1/v2), discovery, loader, registration, lifecycle, permissions, quarantine, stages, adapters (HTTP, CLI, gRPC, MCP) |
| `jarvis_plugin_sdk/` | 2 | Plugin base, setup |

### Layer 7 — API & UI (`api/`, `routers/`, `monitors/`, `static/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `api/` | 15 | FastAPI routes for agents, AGI, cloud, cookbook, email, governance, hybrid, memory, plugins, RAGflow, research, settings, vision, website |
| `routers/` | 7 | Secondary API routes (chat, dot, jarvishub, screen, setup, whatsapp) |
| `monitors/` | 4 | Resource monitor, service health checker, alert router |

### Layer 8 — Utilities & Support (`utils/`, `tools/`, `config/`, `models/`, `providers/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `utils/` | 4 | Env loader, logger, telemetry |
| `tools/` | 17 | Search, crawl4ai, deep research, image gen, website generator, scene generator, registry, plugin base, file search, template library |
| `providers/` | 1 | Example provider |
| `models/` | 1 | Hybrid model manager |
| `config/` | 0 (.py) | JSON/YAML config files only |

### Layer 9 — Agents & Desktop (`pc_agent/`, `daemon/`, `media/`, `demo/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `pc_agent/` | 4 | Computer agent, snapshots, playbooks |
| `daemon/` | 2 | Jarvis service daemon |
| `media/` | 2 | Media player, music suggester |
| `demo/` | 6 | Voice demo, quick demo, parallel agents, benchmark, agent stream |

### Layer 10 — Governance (`governance/`, `plugins/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `governance/` | 5 | Runtime governance layer, meta-governor, governance validator, exceptions |
| `plugins/` | 4 | File tools, PC automation, PII routing, wake word plugins |

### Skills (`skills/`)

| Subpackage | Files | Role |
|------------|-------|------|
| `skills/` (root) | 3 | Manager, utils, init |
| `skills/library/entertainment/` | 11 | Joke, movie, news, quiz, quote, recipe, sports, spotify, weather, games |
| `skills/library/finance/` | 11 | Bill reminder, budget, crypto, expenses, gold, inflation, loan, stocks, tax, UPI |
| `skills/library/knowledge/` | 10 | Code snippet, dictionary, fact check, LaTeX, paper, regex, SQL, thesaurus, translator, Wikipedia |
| `skills/library/productivity/` | 11 | Calendar, email summary, GitHub, habit, LinkedIn, meeting, PDF, pomodoro, todoist, URL shortener |
| `skills/library/system/` | 10 | Clipboard, file organizer, IP lookup, password, QR, screenshot, speedtest, system monitor, timer, unit converter |

### Tests & Other

| Subpackage | Files | Role |
|------------|-------|------|
| `tests/` | ~20+ | Integration tests, unit tests, voice pipeline tests |
| `alembic/` | ~5 | Database migrations |

---

## 2. Layer Architecture

### Ideal Layering (what SHOULD exist)

```
Entry Points (jarvis.py, cli_commands)
    ↓
API Layer (api/, routers/, channels/)
    ↓
Pipeline (core/pipeline/)
    ↓
Capability Registry (core/capability/)
    ↓
Providers (core/providers/)
    ↓
Execution (core/tools/, brain/executor/)
    ↓
Services (memory/, services/, core/scheduler/, core/workflow/)
    ↓
Infrastructure (core/, utils/, models/)
```

### Actual Import Direction Violations

The following imports point **upward** (lower layer importing from higher layer — a layering violation):

| Source | Imports From | Violation |
|--------|-------------|-----------|
| `core/pipeline/stages/capability_selection.py` | `core.capability.registry` | Pipeline → Capability (valid, but lazy) |
| `core/pipeline/stages/context_retrieval.py` | `memory.memory_facade` | Pipeline → Memory (cross-package, valid) |
| `core/pipeline/stages/execution.py` | `core.llm_router`, `core.activity.*` | Pipeline → LLM + Activity |
| `core/providers/router.py` | `core.providers.feedback.models` | Intra-provider (valid) |
| `core/providers/adapters/*.py` | `core.tools.*`, `mcp.*`, `channels.*` | Providers importing from higher-level service packages |
| `core/routes/*.py` | Everything | Routes import across all layers (expected for API layer) |
| `core/capability/negotiation.py` | `core.providers.feedback.models` | Capability → Provider feedback (acceptable) |

### Cross-Package Import Clusters

The most heavily imported-from packages:

| Imported Package | Imported By (# of unique callers) |
|-----------------|-----------------------------------|
| `core.llm_router` | 15+ files across brain/, tools/, core/pipeline, api/, routers/ |
| `core.config_registry` | 12+ files across assistant/, core/, brain/ |
| `core.event_bus` | 8+ files (including brain/events which re-exports it) |
| `core.providers.registry` | 8+ files across core/providers, core/capability, provider_sdk/ |
| `brain.UnifiedBrain` | 5+ files across brain/, core/ |
| `memory.memory_facade` | 6+ files across core/pipeline, api/, core/providers |

---

## 3. Import Direction Map

### Key Import Chains (Critical Paths)

#### Startup Chain
```
jarvis.py
  → cli_commands (implicit)
  → core.version
  → core.setup.detector
  → core.setup.engine
  → core.dev_mode
```

#### Chat Request Chain
```
api/* or channels/* or routers/chat.py
  → core.pipeline.process_message
  → core.pipeline.pipeline.Pipeline.execute()
      → core.pipeline.stages.* (19 stages)
          → core.identity.* (auth, authorization, tenant)
          → core.capability.registry (capability selection)
          → memory.memory_facade (context retrieval)
          → core.pipeline.stages.execution.ExecutionStage
              → core.llm_router
              → core.activity.*
```

#### Provider Registration Chain
```
core.providers.bootstrap
  → core.providers.registry (provider_registry)
  → core.capability.registry (capability_registry)
  → provider_sdk.lifecycle
      → provider_sdk.stages.*
      → provider_sdk.registration
          → core.providers.registry
          → core.capability.registry
```

#### Event Bus Chain
```
core.event_bus
  ← brain/events/event_bus.py (re-exports from core.event_bus)
      ← brain/events/__init__.py (re-exports event_bus symbols)
          ← brain/observers/* (consumes events)
          ← brain/skill_acquisition.py
          ← brain/self_improvement.py
          ← brain/learning_engine.py
          ← brain/goal_generator.py
```

### Bidirectional Import Pairs (Potential Cycles)

| Forward Import | Backward Import | Risk |
|---------------|-----------------|------|
| `brain/*` → `core.llm_router` | `core/*` → `brain.UnifiedBrain` | **CYCLE** — `core/adversarial.py` imports `brain.UnifiedBrain` |
| `brain/*` → `core.event_bus` | `core.event_bus` does not import brain (safe) | Safe |
| `core/pipeline/stages/*` → `memory.*` | `memory/*` does not import core/pipeline | Safe (memory is leaf) |
| `core/providers/adapters/*` → `core.tools.*` | `core/tools/*` does not import providers (safe) | Safe |
| `core/capability/*` → `core.providers.*` | `core/providers/bootstrap.py` → `core.capability.registry` | **CYCLE RISK** — bootstrap imports capability, capability imports provider |
| `core/main.py` → everything | Everything → `core.config_registry` | Hub-and-spoke (acceptable) |

---

## 4. Circular Dependencies

### Confirmed Circular Import Pairs

All are handled via lazy imports (import inside function body), but represent architectural coupling that should be untangled:

#### Cycle 1: `brain.UnifiedBrain` ↔ `core` (via adversarial)
```
core/adversarial.py → brain.UnifiedBrain (lazy)
brain/UnifiedBrain.py → core.llm_router, core.plugins, core.schemas
```
**Mechanism:** Lazy import in `adversarial.py`. At module load time, `adversarial.py` does NOT trigger `brain.UnifiedBrain` import. Only at runtime.

#### Cycle 2: `core/providers` ↔ `core/capability`
```
core/providers/bootstrap.py → core.capability.registry (top-level)
core/capability/registry.py → core.providers.registry (top-level)
```
**Mechanism:** Both import each other at top level. Bootstrap is the main entry that loads capabilities, but capability registry references provider registry. **This is a true circular import at module-load time** — it only works because `bootstrap.py` is called after both modules are partially loaded.

#### Cycle 3: `core.pipeline` ↔ `core.pipeline.stages.*`
```
core/pipeline/__init__.py → core.pipeline.stages.DEFAULT_STAGES
core/pipeline/stages/__init__.py → core.pipeline.base, core.pipeline.context, etc.
```
**Mechanism:** Pipeline imports stages, stages import pipeline base/context. Managed via careful `__init__.py` ordering and lazy imports in some stage methods.

#### Cycle 4: `mcp.server` ↔ Various core/channels modules
```
mcp/server.py → core.tools.policy, core.gateway.auth, core.browser_manager, pc_agent, memory, channels (all lazy)
channels/processor.py → mcp.server (lazy)
```
**Mechanism:** All managed via lazy imports inside method bodies.

#### Cycle 5: `routers/whatsapp.py` ↔ `integrations/whatsapp/*`
```
routers/whatsapp.py → integrations.whatsapp.webhook, .media, .cloud_api (lazy)
integrations/whatsapp/* → None back to routers (safe)
```

#### Cycle 6 (Potential): `core.scheduler` ↔ `core.activity` ↔ `core.pipeline`
```
core/pipeline/stages/execution.py → core.activity.manager (lazy)
core/activity/recorder.py → core.planner.models
core/scheduler/* → core.activity.* (likely)
```
**Mechanism:** Activity recording bridges pipeline and scheduler.

### Danger Zones — No Lazy Import Protection

These are top-level imports that cross major package boundaries:

| Source | Target | Risk |
|--------|--------|------|
| `brain/UnifiedBrain.py` | `core.plugins` | Top-level import — if `core.plugins` ever imports `brain`, cycle breaks |
| `brain/world_model.py` | `brain.goals.goal_manager` | Intra-brain — tightly coupled |
| `brain/world_model.py` | `brain.executor.executor` | Intra-brain — tightly coupled |
| `brain/automation/loop.py` | `core.pattern_failure_memory` | Brain → Core (top-level) |
| `brain/skill_acquisition.py` | `brain.events.event_bus` | Intra-brain (safe) |
| `core/providers/bootstrap.py` | `core.capability.registry` | **Top-level bidirectional** with `capability/registry.py → core.providers.registry` |

---

## 5. Singleton Registry

### All Module-Level Singletons

Every singleton instance created at module load time or via factory function:

| # | Singleton Variable | Module | Type | Creation | Accessor |
|---|-------------------|--------|------|----------|----------|
| 1 | `unified_brain` | `brain/UnifiedBrain.py:543` | `UnifiedBrain` | Eager at import | Direct import |
| 2 | `reasoning_engine` | `brain/reasoning_engine.py:214` | `ReasoningEngine` | Eager at import | Direct import |
| 3 | `cognitive_patterns` | `brain/cognitive_patterns.py:213` | `CognitivePatterns` | Eager at import | Direct import |
| 4 | `epistemic_tagger` | `brain/epistemic_tagger.py:117` | `EpistemicTagger` | Eager at import | Direct import |
| 5 | `task_resolver` | `brain/task_resolver.py:321` | `TaskResolver` | Eager at import | Direct import |
| 6 | `planner` | `brain/planner/planner.py:66` | `Planner` | Eager at import | Direct import |
| 7 | `executor` | `brain/executor/executor.py:187` | `Executor` | Eager at import | Direct import |
| 8 | `verifier` | `brain/executor/verifier.py:145` | `Verifier` | Eager at import | Direct import |
| 9 | `memory_manager` | `brain/memory/memory_manager.py:144` | `MemoryManager` | Eager at import | Direct import |
| 10 | `tool_registry` | `brain/tools/tool_registry.py:103` | `ToolRegistry` | Eager at import | Direct import |
| 11 | `project_tool` | `brain/tools/project_tool.py:308` | `ProjectTool` | Eager at import | Direct import |
| 12 | `observer_manager` | `brain/observers/observer_manager.py:98` | `ObserverManager` | Eager at import | Direct import |
| 13 | `production_gate` | `brain/production_gate.py:240` | `ProductionGate` | Eager at import | Direct import |
| 14 | `learning_engine` | `brain/learning_engine.py:150` | `LearningEngine\|None` | Lazy (starts None) | Direct import |
| 15 | `automation_loop` | `brain/automation/loop.py:2679` | `AutomationLoop\|None` | Lazy (starts None) | Direct import |
| 16 | `capability_registry` | `core/capability/registry.py:92` | `CapabilityRegistry` | Eager at import | Direct import or `capability/__init__` |
| 17 | `capability_negotiator` | `core/capability/negotiation.py:293` | `CapabilityNegotiator` | Eager at import | Direct import |
| 18 | `capability_graph` | `core/capability/graph.py:170` | `CapabilityGraph` | Eager at import | Direct import |
| 19 | `composition_engine` | `core/capability/composition.py:179` | `CompositionEngine` | Eager at import | Direct import |
| 20 | `provider_registry` | `core/providers/registry.py` | `ProviderRegistry` | Eager at import | `providers/__init__` or direct |
| 21 | `provider_router` | `core/providers/router.py` | `ProviderRouter` | Eager at import | Direct import |
| 22 | `provider_memory` | `core/providers/memory.py` | `ProviderMemory` | Eager at import | Direct import |
| 23 | `provider_budget` | `core/providers/budget.py` | `ProviderBudgetManager` | Eager at import | Direct import |
| 24 | `benchmark_store` | `core/providers/benchmark_store.py` | `BenchmarkStore` | Eager at import | Direct import |
| 25 | `orchestration_store` | `core/providers/orchestration/store.py` | `OrchestrationStore` | Eager at import | Direct import |
| 26 | `desktop_provider` | `core/providers/adapters/desktop_provider.py` | `DesktopProvider` | Eager at import | Direct import |
| 27 | `feedback_store` | `core/providers/feedback/__init__.py` | `FeedbackStore\|None` | Lazy via `get_feedback_store()` | Factory function |
| 28 | `global_event_bus` | `core/event_bus.py` | `EventBus` | Eager at import | Direct import |
| 29 | `config` | `core/config_registry.py` | `ConfigRegistry` | Eager at import | Direct import |
| 30 | `connection_manager` | `network/websocket_server.py:51` | `ConnectionManager` | Eager at import | Direct import |
| 31 | `notifier` | `notifications/notifier.py:109` | `SupervisorNotifier` | Eager at import | Direct import |
| 32 | `channel_controller` | `channels/__init__.py:19` | `ChannelController` | Eager at import | Direct import |
| 33 | `resource_monitor` | `monitors/resource.py:179` | `ResourceMonitor` | Eager at import | Direct import |
| 34 | `service_health` | `monitors/services.py:193` | `ServiceHealthChecker` | Eager at import | Direct import |
| 35 | `alert_router` | `monitors/alerts.py:90` | `AlertRouter` | Eager at import | Direct import |
| 36 | `tiered_memory` | `memory/tiered_memory.py` | `TieredMemory` | Eager at import | Direct import |
| 37 | `memory` (facade) | `memory/memory_facade.py` | `MemoryFacade` | Eager at import | Direct import |
| 38 | `mem0_memory` | `memory/mem0_adapter.py` | `Mem0Adapter` | Eager at import | Direct import |
| 39 | `fact_store` | `memory/fact_store.py` | `FactStore` | Lazy via `get_fact_store()` | Factory function |
| 40 | `embedding_memory` | `memory/embedding_memory.py` | `EmbeddingMemory` | Lazy via `get_embedding_memory()` | Factory function |
| 41 | `decision_memory` | `memory/decision_memory.py` | `DecisionMemory` | Eager at import | Direct import |
| 42 | `search_engine` | `tools/search_tool.py` | `SearXNGSearch` | Eager at import | Direct import |
| 43 | `decision_gate` | `tools/search_tool.py` | `SearchDecisionGate` | Eager at import | Direct import |
| 44 | `image_generator` | `tools/image_gen.py` | `ImageGenerator` | Eager at import | Direct import |
| 45 | `scene_generator` | `tools/scene_generator.py` | `SceneGenerator` | Eager at import | Direct import |
| 46 | `whatsapp_sender` | `tools/whatsapp_sender.py` | `WhatsAppSender` | Eager at import | Direct import |
| 47 | `hybrid_manager` | `models/hybrid_models.py:410` | `HybridModelManager` | Eager at import | Direct import |
| 48 | `skill_manager` | `skills/manager.py:228` | `SkillManager` | Eager at import | Direct import |
| 49 | `reminder_manager` | `reminders/manager.py:90` | `ReminderManager` | Eager at import | Direct import |
| 50 | `mcp_server` | `mcp/server.py:568` | `MCPServer` | Eager at import | Direct import |
| 51 | `snapshot_manager` | `pc_agent/snapshot.py:155` | `SystemSnapshot` | Eager at import | Direct import |
| 52 | `computer_agent` | `pc_agent/computer_agent.py:220` | `ComputerAgent` | Eager at import | Direct import |
| 53 | `runtime_governance` | `governance/RuntimeGovernanceLayer.py:116` | `RuntimeGovernanceLayer` | Eager at import | Direct import |
| 54 | `stt_registry` | `assistant/stt_protocol.py:73` | `STTProviderRegistry` | Eager at import | Direct import |
| 55 | `media_player` | `media/player.py:204` | `MediaPlayer` | Eager at import | Direct import |
| 56 | `music_suggester` | `media/player.py:205` | `MusicSuggester` | Eager at import | Direct import |
| 57 | `lifecycle_manager` | `provider_sdk/lifecycle.py:228` | `ProviderLifecycleManager` | Eager at import | Direct import |
| 58 | `quarantine_store` | `provider_sdk/quarantine.py:113` | `QuarantineStore` | Eager at import | Direct import |
| 59 | `discovery_service` | `provider_sdk/discovery.py:62` | `ProviderDiscovery` | Eager at import | Direct import |
| 60 | `registration_pipeline` | `provider_sdk/registration.py:98` | `ProviderRegistrationPipeline` | Eager at import | Direct import |
| 61 | `permission_manager` | `provider_sdk/permissions.py:104` | `PermissionManager` | Eager at import | Direct import |
| 62 | `action_engine` | `core/action_engine.py` | `ActionEngine` | Eager at import | Direct import |
| 63 | `format_classifier` | `routers/chat.py` | `FormatClassifier` | Eager at import | Direct import |
| 64 | `default_pipeline` | `core/pipeline/pipeline.py` | `Pipeline\|None` | Lazy via `get_pipeline()` | Factory function |
| 65 | `manifest_verifier` | `core/pipeline/stages/verification/manifest.py:151` | `ManifestVerifier` | Eager at import | Direct import |

### Singleton Ownership Breakdown

| Owner | Count | Examples |
|-------|-------|----------|
| `brain/` | 15 | UnifiedBrain, reasoning_engine, executor, planner, memory_manager, etc. |
| `core/` | 15+ | provider_registry, capability_registry, event_bus, config, pipeline, etc. |
| `memory/` | 6 | memory (facade), tiered_memory, mem0_memory, decision_memory, fact_store, embedding_memory |
| `provider_sdk/` | 5 | lifecycle_manager, quarantine_store, discovery_service, registration_pipeline, permission_manager |
| `tools/` | 4 | search_engine, image_generator, scene_generator, whatsapp_sender |
| `monitors/` | 3 | resource_monitor, service_health, alert_router |
| Other | 15 | channel_controller, mcp_server, computer_agent, runtime_governance, stt_registry, etc. |

### Double-Checked Locking Singletons (Thread-Safe)

These use `_instance` + `_lock` patterns:

| Function | Module | Mechanism |
|----------|--------|-----------|
| `get_detector()` | `assistant/wake_word.py` | `_watchdog_instance` + `_watchdog_lock` |
| `get_pipeline()` | `assistant/voice_pipeline.py` | `_engine_instance` + `_engine_lock` |
| `get_tts()` | `assistant/tts.py` | `_tts_instance` + `_tts_lock` |
| `get_auth()` | `integrations/gmail/auth.py` | `_auth_instance` + `_auth_lock` |

---

## 6. Global Mutable State

### Mutable Module-Level Variables (Non-Singleton)

These are not singletons — they are mutable state variables at module scope:

| Variable | Module | Type | Mutated By |
|----------|--------|------|------------|
| `_DEFAULT_STAGES` | `core/pipeline/stages/__init__.py` | `list[tuple]` | Pipeline initialization |
| `DEFAULT_VERIFIERS` | `core/pipeline/stages/verification/__init__.py` | `list[Verifier]` | Implicit (defined once) |
| `STAGE_OWNERSHIP` | `core/pipeline/base.py` | `dict[str, set[str]]` | Pipeline configuration |
| `_CONTEXT_FALLBACK_CHAIN` | `core/providers/feedback/models.py` | `list[tuple]` | Read-only at module load |
| `_KNOWLEDGE_PROVIDERS` | `core/providers/store.py` | `dict[str, dict]` | Read-only (hardcoded) |
| `_TASKS` | `core/providers/benchmark.py` | `list[BenchmarkTask]` | Read-only (hardcoded) |
| `_PB` | `pc_agent/playbooks.py` | `dict` | Playbook definitions (hardcoded) |
| `APP_MAP` | `pc_agent/computer_agent.py` | `dict` | App name mappings (hardcoded) |
| `APP_MAP` | `automation/pc_automation.py` | `dict` | App name mappings (hardcoded) |
| `SITE_MAP` | `automation/pc_automation.py` | `dict` | Site name mappings (hardcoded) |
| `_GOAL_TEMPLATES` | `core/capability/graph.py` | `dict` | Goal templates (hardcoded) |
| `_BUILTIN_CAPABILITIES` | `core/capability/models.py` | `dict[str, Capability]` | Capability definitions (hardcoded) |
| `_jobs` | `api/research_routes.py` | `dict` | Runtime job tracking |
| `_jobs` | `api/website_routes.py` | `dict` | Runtime job tracking |
| `_tasks` | `api/vision_routes.py` | `dict` | Runtime task tracking |
| `_ACCOUNT_CACHE` | `mcp/email_server.py` | `dict` | Cached email account configs |
| `_DEFAULT_WEIGHTS` | `core/providers/router.py` | `dict` | Scoring weights (hardcoded) |
| `BILLS` | `skills/.../bill_reminder/main.py` | `list` | In-memory state (skill) |
| `BUDGETS` | `skills/.../budget/main.py` | `dict` | In-memory state (skill) |
| `SPENDING` | `skills/.../budget/main.py` | `dict` | In-memory state (skill) |
| `EXPENSES` | `skills/.../expenses/main.py` | `list` | In-memory state (skill) |
| `_timers` | `skills/.../timer/main.py` | `dict` | In-memory state (skill) |
| `_events` | `skills/.../calendar/main.py` | `list` | In-memory state (skill) |
| `_habits` | `skills/.../habit_tracker/main.py` | `dict` | In-memory state (skill) |
| `_state` | `skills/.../pomodoro/main.py` | `dict` | In-memory state (skill) |

### Red flags in global mutable state:

1. **API-level job dicts** (`_jobs` in `research_routes.py`, `website_routes.py`, `_tasks` in `vision_routes.py`) — in-memory, not persistent, not thread-safe. Lost on restart.

2. **Skill in-memory state** (`BILLS`, `BUDGETS`, `EXPENSES`, `_timers`, `_events`, `_habits`, `_state`) — all skills use module-level mutable state that persists only as long as the process lives. No persistence layer.

3. **`_DEFAULT_STAGES`** and **`DEFAULT_VERIFIERS`** — mutable lists at module scope that could be modified by any code importing the module.

4. **`STAGE_OWNERSHIP`** — a critical architectural map defined as a mutable module-level dict.

5. **`_ACCOUNT_CACHE`** in `mcp/email_server.py` — module-level dict acting as a global cache for email account configs (including potentially sensitive credentials).

---

## 7. sys.path Mutations & Side Effects

### Files that mutate `sys.path` at import time

| File | Mutation | Type |
|------|----------|------|
| `jarvis.py:23-30` | `sys.path.insert(0, ROOT)` + jarvis-export paths | Side effect at module level |
| `assistant/voice_pipeline.py:20` | `sys.path.insert(0, ...)` | Side effect at module level |
| `daemon/jarvis_service.py:28` | `sys.path.insert(0, str(ROOT))` | Side effect at module level |
| `mcp/*_server.py` (all 4) | `sys.path.insert(0, ...)` | Side effect at module level in each server file |
| `skills/manager.py:131-147` | Dynamic `sys.modules` manipulation | Conditional during skill loading |

### Files with module-level side effects

| File | Side Effect | Impact |
|------|-------------|--------|
| `utils/env_loader.py:34` | Calls `load_env_files()` at import | Mutates `os.environ` for entire process |
| `automation/pc_automation.py:16-18` | `warnings.warn(DEPRECATED)` | Prints deprecation warning on import |
| `pc_agent/computer_agent.py:14` | `warnings.warn(EXPERIMENTAL)` | Prints deprecation warning on import |
| `learning/student_agi/cognition/world_model.py` | `DB_PATH.parent.mkdir(...)` | Creates directories on import |
| `learning/student_agi/brain/student_brain.py` | `DB_PATH.parent.mkdir(...)` | Creates directories on import |
| `assistant/providers/__init__.py:17` | Calls `_register_tts_providers()` | Registers TTS providers during import |
| `core/pipeline/stream.py:303` | Monkey-patches `Pipeline.stream` | Modifies Pipeline class at import time |
| `skills/manager.py` | Dynamic `sys.modules` manipulation | Injects parent packages for skills |

---

## 8. Lazy Import Catalog

### Why Lazy Imports Exist

The codebase uses ~150+ lazy/conditional imports. They fall into categories:

#### Category A: Circular Import Avoidance (most common)

These are imports that would create a circular dependency if placed at the top of the file:

| File | Lazy Import | Breaks Cycle Between |
|------|-------------|---------------------|
| `core/adversarial.py` | `brain.UnifiedBrain` | `core` ↔ `brain` |
| `core/capability/registry.py` | `core.capability.models._BUILTIN_CAPABILITIES` | `registry` ↔ `models` |
| `core/capability/negotiation.py` | `__import__("core.capability.graph")` | `negotiation` ↔ `graph` |
| `core/providers/bootstrap.py` | ALL imports (10 adapters + SDK) | `providers` ↔ all adapter modules |
| `mcp/server.py` | 11 lazy imports (policy, auth, browser, etc.) | `mcp` ↔ `core.*`, `pc_agent`, `memory`, `channels` |
| `channels/processor.py` | `mcp.server` | `channels` ↔ `mcp` |
| `routers/whatsapp.py` | `integrations.whatsapp.*` | `routers` ↔ `integrations` |
| `api/vision_routes.py` | `core.vision_agent` | `api` ↔ `core` |

#### Category B: Heavy Dependency Deferral (optional/rarely used)

| File | Lazy Import | Reason |
|------|-------------|--------|
| `assistant/wake_word.py` | `numpy`, `soundfile`, `sounddevice`, `webrtcvad` | Heavy audio libraries, only needed when wake word active |
| `assistant/tts.py` | `torch`, `kokoro`, `numpy`, `soundfile` | Heavy ML inference deps |
| `assistant/providers/faster_whisper.py` | `torch`, `faster_whisper`, `numpy`, `soundfile` | Heavy ML inference deps |
| `tools/search_fallback.py` | `ddgs`, `duckduckgo_search` | Optional search backends |
| `tools/image_gen.py` | `openai`, `httpx` (×3 methods) | Per-provider API clients |
| `automation/pc_automation.py` | `selenium.*`, `pyautogui` | Browser automation (heavy) |

#### Category C: Optional Feature Gating

| File | Lazy Import | Guard |
|------|-------------|-------|
| `memory/tiered_memory.py` | `mem0`, `embedding_memory` | `try/except ImportError` |
| `memory/mem0_adapter.py` | `mem0` | `try/except ImportError` |
| `monitors/resource.py` | `psutil`, `pynvml.*` | `try/except ImportError` |
| `governance/GovernanceValidator.py` | `concurrent.futures`, `logging`, `core.llm_router` | Conditional feature branches |
| `brain/observers/system_monitor.py` | `psutil` | `try/except ImportError` |

#### Category D: Bootstrap Circularity

| File | Lazy Import | Reason |
|------|-------------|--------|
| `core/pipeline/stages/capability_selection.py` | `core.capability.registry`, `core.capability.models` | Pipeline stage defers capability registry import |
| `core/routes/planner.py` | 15+ lazy imports from `core.planner.*` | Route file defers all planner imports |
| `core/routes/settings.py` | 10+ lazy imports from `core.config_registry` | Route file has import ordering issues |

---

## 9. Bootstrap Order

### Current Startup Sequence

```
1. jarvis.py
   ├── sys.path.insert (root)
   ├── sys.path.insert (jarvis-export)
   ├── Import: cli_commands (triggers cascade)
   │   ├── Import: core.version
   │   ├── Import: core.setup.detector
   │   └── Import: core.setup.engine
   └── build_parser()
       └── Import: core.dev_mode

2. Command Execution (e.g., chat, server)
   └── core.main (if server or chat)
       ├── core.config_registry ← config singleton EARLY
       │   └── os.environ populated via utils.env_loader (side effect)
       ├── core.event_bus ← global_event_bus singleton
       ├── core.llm_router ← LLM routing infrastructure
       ├── core.providers.bootstrap ← registers all providers
       │   ├── core.providers.registry ← provider_registry singleton
       │   ├── core.capability.registry ← capability_registry singleton
       │   ├── provider_sdk.lifecycle ← lifecycle_manager singleton
       │   ├── core.providers/adapters/* (all 10+ adapters)
       │   └── core/providers/* (router, memory, budget, store, benchmark, etc.)
       ├── brain.UnifiedBrain ← unified_brain singleton (if loaded)
       │   ├── brain.reasoning_engine
       │   ├── brain.memory.memory_manager
       │   ├── brain.goals.goal_manager
       │   ├── brain.planner
       │   ├── brain.executor.executor
       │   └── brain.events (re-exports core.event_bus)
       ├── channels ← channel_controller singleton
       ├── memory.memory_facade ← main memory singleton
       ├── mcp.server ← mcp_server singleton
       ├── monitors ← resource_monitor, service_health, alert_router
       ├── api/* or routers/* ← FastAPI route registration
       └── core.pipeline ← DEFAULT_STAGES list built
```

### Bootstrap Problems

1. **No single boot function** — initialization is scattered across module-level side effects in 15+ files.

2. **Import order matters** — `core/providers/bootstrap.py` must be called after `config_registry` is loaded but before any adapter or capability is accessed.

3. **`brain.UnifiedBrain` initialization is implicit** — `unified_brain` singleton is created at import time. If nobody imports `brain/UnifiedBrain.py`, the brain never initializes.

4. **`core/pipeline/stream.py` monkey-patches at import time** — `Pipeline.stream` is replaced at module load. Must be imported before any Pipeline instance is used.

5. **Provider adapter registration order** — `bootstrap.py` imports all 10+ adapters eagerly. If any adapter has heavyweight imports (selenium, torch), they block startup.

---

## 10. Key Findings & Risks

### Critical

1. **65 module-level singletons** with no central registry, no lifecycle management, no teardown, no dependency ordering.

2. **`core/providers/bootstrap.py` ↔ `core/capability/registry.py`** is a true circular import at top level — works only because of Python's import system tolerance and careful ordering.

3. **150+ lazy imports** — the codebase uses lazy imports as a substitute for architectural separation. Every lazy import represents a design coupling that should be resolved.

4. **sys.path mutations in 7 files** — each server under `mcp/` mutates `sys.path`. If more than one is loaded, duplicate path entries accumulate.

5. **`brain/automation/loop.py` at 2,679 lines** — the largest file in the project. Imports from `core.llm_router`, `core.pattern_failure_memory`, `brain.executor`, `brain.goals`, `brain.memory`, `brain.task_resolver`. A massive coupling hub.

### High

6. **No import boundary enforcement** — any module can import any other module. No layer access control.

7. **`core/pipeline/stages/context_retrieval.py` and `stages/memory.py`** import from `memory.*` with lazy imports wrapped in `try/except` — degrading gracefully on import failure masks real errors.

8. **Bootstrap is implicit** — no `initialize()` function. Module-level side effects (15+ files) mean the order of `import` statements determines runtime behavior.

9. **`core/tools/execution.py` at 3,024 lines** — the central tool execution dispatcher. Imports from across the entire codebase. A bottleneck in every sense.

10. **`api/routers` split** — routes are split between `api/` (15 files) and `core/routes/` (~25 files) and `routers/` (7 files). No clear reason for the split.

### Medium

11. **Skill system uses module-level mutable state** — `BILLS`, `BUDGETS`, `EXPENSES`, `_timers`, `_events` are all in-memory Python lists/dicts at module scope. Lost on restart.

12. **Global `_jobs` dicts in API routes** — `research_routes.py`, `website_routes.py`, `vision_routes.py` use module-level dicts for async job tracking. Not thread-safe, not persisted.

13. **`Pipline.stream` monkey-patch** in `core/pipeline/stream.py` modifies the `Pipeline` class at import time. If `stream.py` is not imported, streaming is silently unavailable.

14. **Config directory has no `__init__.py`** but `core/config_registry.py` acts as the config module.

### Low

15. **Duplicate constant definitions** — `APP_MAP` defined in both `pc_agent/computer_agent.py` and `automation/pc_automation.py`, with different values.

16. **Dead analysis file** — `analysis_output.txt` (12,160 lines) at the project root. Remnant from this audit.

---

## 11. Recommendations

### Pre-Build (Fix Before Any Other Audit)

1. **Centralize singleton management** — create a `ServiceLocator` or `AppContext` that owns all singleton lifetimes. Each singleton should be registered once and accessed through the context.

2. **Remove `sys.path` mutations** — use a single `setup_paths()` call in `jarvis.py` before any other import.

3. **Remove module-level side effects** — move all `load_env_files()`, `warnings.warn()`, `mkdir()` calls out of import time into explicit initialization.

4. **Fix `core/providers/bootstrap.py` ↔ `core/capability/registry.py` cycle** — extract a shared dependency that both can import, or make one depend on the other without the reverse.

### Design-Level (For Target Architecture)

5. **Enforce import layers** — use `import-linter` or a custom lint rule. Pipeline stages should not import `brain.*` directly. Providers should not import `mcp.*`.

6. **Replace lazy imports with explicit dependency injection** — each lazy import is a hidden coupling. Make dependencies explicit via constructor injection.

7. **Merge `api/`, `core/routes/`, and `routers/`** — all route files should live in one place with consistent import patterns.

8. **Add persistence to skill in-memory state** — skills using `BILLS`, `BUDGETS`, etc. should use the fact store or a dedicated skill storage interface.

### Architectural (For Target Architecture Document)

9. **Replace `monkey-patch` pattern in `stream.py`** — streaming should be a protocol/interface on Pipeline, not a runtime attribute assignment.

10. **Normalize singleton creation patterns** — the codebase has 5 different singleton patterns. Pick one (eager module-level, lazy factory, double-checked locking, dependency-injected, or class-level `__new__`) and use it everywhere.

---

*End of DEPENDENCY_GRAPH_AUDIT.md — 65 singletons cataloged, 150+ lazy imports mapped, 5 cycle risks identified, 10 recommendations.*
