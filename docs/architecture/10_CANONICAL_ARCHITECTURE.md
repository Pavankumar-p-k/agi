# CANONICAL ARCHITECTURE — JARVIS/MJ v3.x

> **Generated:** 2026-07-15  
> **Audit scope:** Phases 6–10 consolidation sweep complete.  
> **Purpose:** Define the ONE canonical path for every subsystem. All findings backed by file/function evidence.

---

## Table of Contents

1. [What is MJ?](#1-what-is-mj)
2. [Core Subsystems](#2-core-subsystems)
   - [One Startup](#21-one-startup)
   - [One Goal Understanding Engine](#22-one-goal-understanding-engine)
   - [One Capability Registry](#23-one-capability-registry)
   - [One Provider System](#24-one-provider-system)
   - [One Planner](#25-one-planner)
   - [One Execution Engine](#26-one-execution-engine)
   - [One EventBus](#27-one-eventbus)
   - [One Configuration System](#28-one-configuration-system)
   - [One Memory System](#29-one-memory-system)
   - [One Safety Engine](#210-one-safety-engine)
   - [One Notification System](#211-one-notification-system)
   - [One Desktop Pipeline](#212-one-desktop-pipeline)
   - [One Browser Pipeline](#213-one-browser-pipeline)
   - [One Coding Pipeline](#214-one-coding-pipeline)
3. [Reality Scores](#3-reality-scores)
4. [Migration Order](#4-migration-order)
5. [Technical Debt](#5-technical-debt)
6. [Risks](#6-risks)
7. [Future Roadmap](#7-future-roadmap)

---

## 1. What is MJ?

**MJ** is the internal shorthand for the JARVIS autonomous coding agent system. It is not an acronym expansion — it is simply the project's initials used as a concise identifier throughout the codebase.

### Evidence

| Artifact | File | Line |
|----------|------|------|
| `MJEvent` — canonical typed event class | `core/event_bus.py` | 396 |
| "unified MJ event bus" — docstring description | `core/event_bus.py` | 397 |
| "MJ v3 routes" — FastAPI route section marker | `core/main.py` | 590 |
| "everything MJ wants to tell the user" — InboxStore purpose | `core/inbox/store.py` | 1 |
| "what MJ is currently focused on" — WorkflowTracker | `core/workflow/tracker.py` | 34 |
| "what MJ is doing right now" — ProgressCanvas | `core/routes/progress.py` | 3 |
| "MJ Architecture Audit" — source-of-truth document | `docs/architecture/01_SOURCE_OF_TRUTH.md` | 1 |
| `MJEvent` exported from workflow package | `core/workflow/__init__.py` | 4 |

### Naming Convention

| Term | Meaning | Canonical? |
|------|---------|------------|
| `MJEvent` | Canonical typed event for the unified event bus | **YES** |
| `MJ v3 routes` | Modern API route registration | **YES** |
| `mj_` prefix | Internal method/variable convention | Convention |

---

## 2. Core Subsystems

### 2.1 ONE Startup

#### Canonical

| Component | File | Key Entry Point |
|-----------|------|-----------------|
| FastAPI application | `core/main.py` | `app` (FastAPI instance) |
| Lifecycle manager | `core/lifespan.py` | `lifespan()` async context manager |
| Config bootstrap | `core/config_init.py` | `init_config()` — idempotent, thread-safe |
| CLI entry | `jarvis.py` | Command-line runner |

#### Deprecated

| Path | Deprecation Evidence | Replacement |
|------|---------------------|-------------|
| `core/intent_router.py` | Line 28: `DeprecationWarning` | `core.routing.request_classifier.classify_request()` |
| `core/environment_monitor.py` | Line 23: `DeprecationWarning` | `monitors` package |
| `core/governance/resource_monitor.py` | Line 30: `DeprecationWarning` | `monitors.resource` |

#### Removed (Phases 6–8)

| Path | Reason | Phase |
|------|--------|-------|
| `core/memory.py` | Zero-consumer stub; replaced by `memory.memory_facade` | 7 |
| `core/memory_vector.py` | Zero-consumer stub; replaced by `memory.mem0_adapter` | 7 |
| `core/plan_manager.py` | Logic inlined to `core/plan_routes.py:_PlanStore` | 7 |
| `core/control_loop.py` (D06) | Moved to `core/legacy/control_loop.py` | 8.6 |
| `brain/memory/` (6 files) | Consumers migrated to `memory.memory_facade` | 7 |
| `brain/executor/` package | Consolidated into single `brain/executor.py` | 7 |
| `core/agents/_legacy/` (9 files) | SubAgent classes inlined into adapter files | 7 |

#### Reality Score: **6/10**

Two parallel startup paths exist (FastAPI server vs daemon). `core/lifespan.py` has 945+ lines with ~30 sequential phases, all non-fatal. `core/main.py` attempts ~50 route modules each wrapped in try/except — fragile.

---

### 2.2 ONE Goal Understanding Engine

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Goal interpreter | `core/goal_interpreter.py` | `interpret_goal(goal: str) -> dict` |
| Intent classifier | `core/routing/request_classifier.py` | `classify_request()` — canonical intent classification |
| Goal generator | `brain/goal_generator.py` | `GoalGenerator.evaluate_world()` |
| Ambiguity resolver | `core/ambiguity_resolver.py` | `AmbiguityResolver` |
| Success criteria | `core/success_criteria.py` | `is_done()`, `get_summary()` |

#### Deprecated

| Path | Deprecation Evidence | Replacement |
|------|---------------------|-------------|
| `core/intent_router.py` | Line 28: `DeprecationWarning` | `core.routing.request_classifier.classify_request()` |

#### Removed

None — all goal-related modules survived consolidation.

#### Reality Score: **7/10**

Clean separation of concerns. `interpret_goal()` is the primary entry point, used by both `ControlLoop` and `AutomationLoop`. Intent classification has one canonical path. Ambiguity resolution is independently wired.

---

### 2.3 ONE Capability Registry

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Capability registry | `core/capability/registry.py` | `CapabilityRegistry` — singleton: `capability_registry` |
| Capability model | `core/capability/models.py` | `Capability` (frozen dataclass) — 18 built-in capabilities |
| Capability graph | `core/capability/graph.py` | `CapabilityGraph` — singleton: `capability_graph` |
| Capability composition | `core/capability/composition.py` | `CompositionEngine` |
| Capability negotiation | `core/capability/negotiation.py` | `CapabilityNegotiator` — singleton: `capability_negotiator` |
| Pipeline stage | `core/pipeline/stages/capability_selection.py` | `CapabilitySelectionStage` — uses registry via DI |
| Intent resolution | `core/capability/registry.py` | `resolve_intent(intent) -> list[Capability]` |
| Goal matching | `core/capability/registry.py` | `match_goal(goal) -> list[Capability]` |

#### Deprecated

| Path | Deprecation Evidence | Replacement |
|------|---------------------|-------------|
| `core/agents/capabilities.py` (\(CAPABILITIES\) dict) | Line 11: `DeprecationWarning` | `core.capability.capability_registry` |

#### Removed

None — entirely new subsystem built during consolidation.

#### Reality Score: **8/10**

Well-factored subsystem with clean DI in pipeline stage. 49 imports from `core.capability` across the codebase confirm adoption. Built-in intent map handles 17 intents mapping to 18 capabilities. `risk` field added in Phase 10 enables policy-based filtering.

---

### 2.4 ONE Provider System

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Provider abstract base | `core/providers/base.py` | `ExecutionProvider` (ABC), `ExecutionResult` |
| Provider registry | `core/providers/registry.py` | `ProviderRegistry` — singleton: `provider_registry` |
| Provider router | `core/providers/router.py` | `ProviderRouter` — singleton: `provider_router` |
| Provider bootstrap | `core/providers/bootstrap.py` | `bootstrap_providers()` |
| Provider budget | `core/providers/budget.py` | `ProviderBudgetManager` |
| Provider feedback | `core/providers/feedback/` | Feedback/calibration subsystem |
| Provider orchestration | `core/providers/orchestration/` | Provider orchestration |
| Provider adapters | `core/providers/adapters/` | 12 adapters: Forge, Browser, Research, Automation, Messaging, Deployment, Workspace, GitHub, Email, Desktop, ClaudeCode, Codex |

#### Deprecated

None — provider system was built as canonical from inception.

#### Removed

None.

#### Reality Score: **8/10**

Comprehensive provider abstraction with 12 production adapters, 7-dimension scoring router, persistence, and feedback loop. The `bootstrap.py` orchestrates registration from multiple sources (internal, external, SDK, plugins). Some adapters (ClaudeCode, Codex) may be experimental.

---

### 2.5 ONE Planner

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Planner state machine | `core/planner/state_machine.py` | `PlannerStateMachine.run()` — PLAN→DECOMPOSE→ROUTE→EXECUTE→VERIFY→COMPLETE/FAILED |
| Goal decomposer | `core/planner/decomposer.py` | `GoalDecomposer.decompose()` |
| Task graph (DAG) | `core/planner/dag.py` | `TaskGraph`, `TaskNode` |
| Plan executor | `core/planner/executor.py` | `PlannerExecutor` |
| Unified store | `core/planner/unified_store.py` | `UnifiedStore` — single source of truth for goal/plan persistence |
| Plan templates | `core/planner/templates.py` | `TEMPLATES`, `get_template()` |
| Plan classifier | `core/planner/classifier.py` | `classify()`, `extract_parameters()` |
| Plan protocol | `core/planner/protocol.py` | `Plan`, `PlanStatus`, `Planner` (ABC) |
| Plan routes | `core/plan_routes.py` | FastAPI router — goal submission, plan management, approval |
| Plan evolution | `core/plan_evolution.py` | `PlanEvolutionEngine` — dynamic DAG mutation mid-run |
| Site planner | `core/site_planner.py` | Template selection, page mapping, nav structure |

#### Deprecated

| Path | Deprecation Evidence | Replacement |
|------|---------------------|-------------|
| `core/planner/store.py` (`PlanStore`) | Has `migrate_from_planstore()` method | `core/planner/unified_store.py` (`UnifiedStore`) |

#### Removed

| Path | Reason | Phase |
|------|--------|-------|
| `brain/planner/` | Fixed 3-node DAG, in-memory only | 6 |
| `brain/goals/` | Duplicate goal CRUD | 6 |
| `core/plan_manager.py` | No persistence, no thread safety | 7 |

#### Reality Score: **5/10**

Rich planning subsystem (18 files) but 6 of 14 planner files are experimental: `strategies.py`, `replan.py`, `comparison.py`, `health.py`, `evidence.py`, `outcomes.py`. These form a chain but are only used within themselves. `PlannerStateMachine` is active and well-integrated with agents. Dual store path (`PlanStore` → `UnifiedStore`) still in migration.

---

### 2.6 ONE Execution Engine

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Execution manager | `core/execution/manager.py` | `ExecutionManager` — `start_workflow()`, `cancel()`, `resume()`, `get_status()` |
| Execution context | `core/execution/context.py` | `ExecutionContext` — immutable lifecycle context |
| Workflow engine | `core/workflow/engine.py` | `WorkflowEngine` — core workflow orchestration |
| Workflow models | `core/workflow/models.py` | `StepDefinition`, `WorkflowStatus` |
| Workflow events | `core/workflow/events.py` | `WorkflowEvent`, workflow lifecycle event types |
| Workflow recovery | `core/workflow/recovery.py` | `recover_active_workflows()` |
| Workflow storage | `core/workflow/storage.py` | `WorkflowStore` — SQLite persistence |
| Activity manager | `core/activity/manager.py` | `ActivityManager` — status transitions via `ExecutionManager` |
| Activity resume | `core/activity/resume.py` | `ResumeEngine` — resume lifecycle events |
| Runtime manager | `core/runtime/manager.py` | `RuntimeManager` — wraps Pipeline + StateGraph + ExecutionManager |
| Tool executor | `core/tools/executor.py` | `ToolExecutor` — wraps tool execution with `ExecutionManager` |
| Tool registry | `core/tools/registry.py` | `ToolRegistry` — canonical tool registry |
| Tool resolver | `core/tools/resolver.py` | `ToolResolver` — tool name → handler |
| Scheduler | `core/scheduler/scheduler.py` | `Scheduler` — persistent activity scheduler with `ExecutionManager` lifecycle |
| Autonomous scheduler | `core/scheduler/autonomous.py` | `AutonomousScheduler` — opportunity → activity bridge |
| State graph | `core/graph/graph.py` | `StateGraph` — `ExecutionManager`-driven node execution |
| Cron | `core/cron.py` | Legacy cron `Scheduler` with `ExecutionManager` events |

#### Deprecated

| Path | Deprecation Evidence | Replacement |
|------|---------------------|-------------|
| `core/agent_runtime.py` | Line 21: DeprecationWarning | `core.agents.BaseAgent` + `ExecutionManager` |
| `core/agent_registry.py` | Line 24: DeprecationWarning | `core/agents/` + `core/providers/` |
| `brain/automation/loop.py:_ensure_workflow_engine()` | Line 50: logger.warning | `ExecutionManager.engine` |
| `core/legacy/control_loop.py` (moved D06) | All consumers migrated | `ExecutionManager` + `WorkflowEngine` |

#### Removed

| Path | Reason | Phase |
|------|--------|-------|
| `brain/executor/` (package) | Consolidated into single `brain/executor.py` | 7 |

#### Reality Score: **7/10**

Strong unified architecture with `ExecutionManager` as the central orchestrator wrapping `WorkflowEngine` + `EventBus` + `MemoryFacade`. 25 dedicated unit tests in `test_execution_manager.py` and 18 integration tests in `test_execution_integration.py`. The legacy `ControlLoop` (1152 lines) is isolated in `core/legacy/` with 8 migrated consumers.

---

### 2.7 ONE EventBus

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Event bus | `core/event_bus.py` | `EventBus` — `subscribe()`, `publish()`, `publish_sync()`, `subscribe_stream()`, `register_ws()` |
| Event (typed) | `core/event_bus.py` | `Event` (dataclass) — `type`, `source`, `payload`, `namespace` |
| Subscription | `core/event_bus.py` | `Subscription` (dataclass) |
| Global singleton | `core/event_bus.py` | `global_event_bus` |
| Event types | `core/event_types.py` | Canonical typed events: `GoalCreated`, `GoalCompleted`, `TaskCompleted`, `MemoryStored`, `VerificationPassed`, `UserMessage`, `FileCreated`, `EmailReceived`, `SystemDiskLow`, `ObserverTick` + 30+ more |
| Default subscribers | `core/event_bus.py` | `register_default_subscribers()` — logs telemetry events |
| Namespace isolation | `core/event_bus.py` | `namespace` parameter for event scoping |

#### Deprecated

| Path | Deprecation Evidence | Replacement |
|------|---------------------|-------------|
| `core/event_bus.py:PluginEventBus` | Line 509: `DeprecationWarning` | `global_event_bus` with `namespace='plugin'` |
| `core/event_bus.py:get_bus()` | Legacy compat | `global_event_bus` |
| `core/event_bus.py:emit_event()` | Legacy compat | `global_event_bus.publish()` |
| `core/event_bus.py:fire_event()` | Legacy compat | `global_event_bus.publish()` |
| `core/event_bus.py:MJEvent` | Legacy compat | `Event` (dataclass) |

#### Removed

None — EventBus was designed as canonical from inception.

#### Reality Score: **9/10**

Mature, well-factored event bus with typed events, namespace isolation, WebSocket broadcasting, and sync/async publish. Single `global_event_bus` singleton with backward-compat wrappers. The `PluginEventBus` adapter is deprecated but retained for plugin compatibility.

---

### 2.8 ONE Configuration System

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Configuration service | `core/configuration/service.py` | `ConfigurationService` — `load()`, `get()`, `set()`, `reset()`, `resolve()`, `on_change()` |
| Configuration singleton | `core/configuration/__init__.py` | `configuration` |
| Config resolver chain | `core/configuration/service.py` | Overrides → env → flat config → SettingsStore → auto-resolve → defaults |
| Config bootstrap | `core/config_init.py` | `init_config()` — idempotent, called from `main.py` |
| Settings store | `core/settings/store.py` | `SettingsStore` — `_migrate_legacy_configs()` |
| Config registry | `core/config_registry.py` | `ConfigEntry` (metadata for 80+ config keys), `_REGISTRY` |

#### Deprecated

| Path | Deprecation Evidence | Replacement |
|------|---------------------|-------------|
| `core/config_registry.py:Config/config` | Line 263: `DeprecationWarning` | `core.configuration.configuration` |
| `core/config.py` | Line 23: `DeprecationWarning` | `core.configuration.configuration.get(key)` |
| `core/config_schema.py` | Line 28: `DeprecationWarning` | `core.configuration.configuration` |

#### Removed

None — deprecated modules retained as re-export shims for backward compat.

#### Reality Score: **7/10**

Clean resolution chain with proper deprecation warnings. Three deprecated config modules remain as re-export shims. SettingsStore has a `_migrate_legacy_configs()` function for data migration. Config registry holds metadata for 80+ keys.

---

### 2.9 ONE Memory System

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Memory facade | `memory/memory_facade.py` | `MemoryFacade` — `store()`, `recall()`, `search_all()`, `store_trace()`, `store_decision()`, `summarize()` |
| Facade singleton | `memory/memory_facade.py` | `memory` |
| Tiered memory | `memory/tiered_memory.py` | `TieredMemory` — hot (RAM) / warm (SQLite/mem0) / cold (semantic) |
| Fact store | `memory/fact_store.py` | `FactStore` — SQLite-backed subject-predicate-object with embeddings |
| Episodic store | `memory/episodic_store.py` | `EpisodicStore` — SQLite-backed episodic memories |
| Semantic store | `memory/semantic_store.py` | `SemanticStore` — SQLite-backed semantic facts |
| Decision store | `memory/decision_store.py` | `DecisionStore` — SQLite-backed decision memories |
| Decision memory | `memory/decision_memory.py` | `DecisionMemory` — JSON-file-backed action→outcome learning |
| Task store | `memory/task_store.py` | `TaskStore` — action trace storage |
| CRUD store | `memory/crud_store.py` | `CrudStore` — flat JSON-file CRUD (replaces deprecated `MemoryManager`) |
| Vector store | `memory/vector_store.py` | Unified ChromaDB interface |
| Embedding memory | `memory/embedding_memory.py` | Semantic memory using nomic-embed-text + SQLite |
| Mem0 adapter | `memory/mem0_adapter.py` | `mem0_memory` — mem0 integration |
| Fact extraction | `memory/extraction.py` | `ExtractedFact`, `extract_facts()` — regex-based extraction |
| Similarity | `memory/similarity.py` | `get_text_similarity()` |

#### Deprecated

None — all memory modules are canonical.

#### Removed

| Path | Reason | Phase |
|------|--------|-------|
| `core/memory.py` (`MemoryManager`) | Zero-consumer stub; replaced by `memory.memory_facade` | 7 |
| `core/memory_vector.py` (`MemoryVectorStore`) | Zero-consumer stub; replaced by `memory.mem0_adapter` | 7 |
| `brain/memory/` (6 files) | Duplicate stores consolidated into `memory/` package | 7 |

#### Reality Score: **8/10**

Comprehensive memory subsystem with 17 modules, unified facade, tiered architecture (hot/warm/cold), multiple store backends, and clean migration path. All consumers migrated from `brain/memory/` to `memory.memory_facade`. `CrudStore` provides API parity with deprecated `MemoryManager`.

---

### 2.10 ONE Safety Engine

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| System governor | `core/system_governor.py` | `SystemGovernor` — `decide()`, `submit()`, `route()`, `get_status()` |
| Governor decisions | `core/system_governor.py` | `GovernorDecision` — retry/replan/abort/switch_tool/escalate/pause |
| Real validator | `core/real_validator.py` | `RealValidator` — `validate_all()`, 9 check methods |
| Tool safety | `core/routing/safety.py` | `SafetyLevel` (SAFE/CONFIRM/DANGEROUS), `classify_tool()` |
| Desktop safety | `core/desktop/safety.py` | `SafetyManager` — region blocking, cooldowns, rate limits |
| Self-modification safety | `core/self_modification/safety.py` | Self-modification safety checks |
| Prompt security | `core/prompt_security.py` | Prompt injection detection |
| SSRF protection | `core/ssrf.py` | Server-side request forgery protection |
| Security audit | `core/security_audit.py` | Security event auditing |
| Privacy classification | `core/privacy_classifier.py` | PII/confidential data classification |
| Audit logging | `core/audit_log.py` | Immutable audit event log |
| Interrupt/override | `core/interrupt_override.py` | `interrupt_manager` — cancel/pause/override signals |
| Rate limiter | `core/rate_limiter.py` | API rate limiting |
| Permission system | `core/permission/` | Capability-based access control |
| Governance | `core/governance/` | Task routing, resource monitoring, work queue |

#### Deprecated

| Path | Deprecation Evidence | Replacement |
|------|---------------------|-------------|
| `core/governance/resource_monitor.py` | Line 30: `DeprecationWarning` | `monitors.resource` |

#### Removed

None.

#### Reality Score: **8/10**

15+ safety-related modules covering governance, validation, security, permissions, privacy, and audit. RealValidator provides 9 concrete build-validation checks. SystemGovernor integrates all signals into a unified decision. Desktop safety includes region blocking and cooldowns.

---

### 2.11 ONE Notification System

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Notifier | `notifications/notifier.py` | `SupervisorNotifier` — `notify()`, `_write_event_log()`, `_send_email()`, `_send_push()` |
| Notifier singleton | `notifications/notifier.py` | `notifier` |
| Push channels | `notifications/notifier.py` | ntfy.sh + Pushover |
| WebSocket registration | `notifications/notifier.py` | `register_ws()`, `unregister_ws()` |

#### Deprecated

None.

#### Removed

None.

#### Reality Score: **9/10**

Single module, single singleton, clean API. Push notifications via two channels (ntfy.sh + Pushover), WebSocket broadcast, email delivery, and event log. Used by both `ControlLoop` and `AutomationLoop`.

---

### 2.12 ONE Desktop Pipeline

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Desktop controller | `core/desktop/controller.py` | `DesktopController` — 14 action methods (move_mouse, click, type_text, etc.) |
| Controller singleton | `core/desktop/controller.py` | `desktop_controller` |
| Screen capture | `core/desktop/screen.py` | `ScreenCapture` — singleton: `screen_capture` |
| Window controller | `core/desktop/window.py` | `WindowController` — singleton: `window_controller` |
| Desktop replay | `core/desktop/replay.py` | `ReplayNode`, `ReplayGraph` — singleton: `desktop_replay` |
| Desktop safety | `core/desktop/safety.py` | `SafetyManager` — 13 action types, region blocking, cooldowns |
| Desktop state | `core/workspace/desktop_state.py` | Desktop state tracking |
| Window detection | `core/workspace/window_detector.py` | Window detection utilities |
| Process monitor | `core/workspace/process_monitor.py` | Process monitoring |
| Browser context | `core/workspace/browser_context.py` | Browser session context |
| Clipboard manager | `core/workspace/clipboard_manager.py` | Clipboard operations |

#### Deprecated

| Path | Deprecation Evidence | Replacement |
|------|---------------------|-------------|
| `pc_agent/` (whole package) | Line 16: `DeprecationWarning` | `core/desktop/` |

#### Removed

None.

#### Reality Score: **8/10**

Well-factored desktop automation pipeline with safety layer, replay capability, and peripheral workspace modules. 14 controller actions with region-cooldown protection. Experimental `pc_agent/` package deprecated in favor of `core/desktop/`.

---

### 2.13 ONE Browser Pipeline

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Browser agent | `core/agents/browser_agent.py` | `BrowserAgent` (extends `BaseAgent`) — browse, navigate, scrape, login, form, click |
| Browser manager | `core/browser_manager.py` | `BrowserManager` (Playwright-based) |
| Browser provider | `core/providers/adapters/browser_provider.py` | `BrowserProvider` — provider adapter |
| Browser context | `core/workspace/browser_context.py` | Browser session context management |
| Search tool | `tools/search_tool.py` | Web search tool |
| Crawl4ai tool | `tools/crawl4ai_tool.py` | AI-powered crawling |
| Search fallback | `tools/search_fallback.py` | Search fallback mechanism |

#### Deprecated

None.

#### Removed

None.

#### Reality Score: **7/10**

Browser capability is split across agents (`BrowserAgent`), providers (`BrowserProvider`), and peripheral tools (`crawl4ai_tool`, `search_tool`). No single "browser pipeline" stage exists in the 24-stage pipeline — browser acts as a capability resolved by `CapabilitySelectionStage`.

---

### 2.14 ONE Coding Pipeline

#### Canonical

| Component | File | Key Function/Class |
|-----------|------|--------------------|
| Repository indexer | `core/coding/repository_indexer.py` | `RepositoryIndexer`, `FileEntry` |
| Dependency graph | `core/coding/dependency_graph.py` | `DependencyGraph`, `DependencyNode` |
| Architecture map | `core/coding/architecture_map.py` | `ArchitectureMap`, `ArchitectureMapper` |
| Impact analyzer | `core/coding/impact_analyzer.py` | `ImpactAnalyzer`, `ImpactResult` |
| Change planner | `core/coding/change_planner.py` | `ChangePlanner`, `ChangePlan`, `ChangeStep` |
| Change simulation | `core/coding/change_simulation.py` | `ChangeSimulation`, `SimulationResult`, `PredictedBreakage` |
| Refactor safety | `core/coding/refactor_safety.py` | `RefactorSafetyEngine`, `SafetyAssessment` |
| Refactoring engine | `core/coding/refactoring_engine.py` | `RefactoringEngine`, `CodePatch`, `RollbackSnapshot` |
| Architecture reasoning | `core/coding/architecture_reasoning.py` | `ArchitectureScorer`, `DesignAnalyzer`, `TradeoffEngine`, `MigrationPlanner` |
| Build benchmark | `core/coding/build_benchmark.py` | Build benchmarking |
| Codebase indexer | `core/codebase_indexer.py` | Codebase indexing |
| Format classifier | `core/format_classifier.py` | Code format detection |

#### Deprecated

None.

#### Removed

None.

#### Reality Score: **6/10**

Rich coding intelligence subsystem (12 modules) covering repository analysis, dependency graphs, impact analysis, change planning, refactoring, and architecture reasoning. However, this subsystem is not yet wired into the 24-stage pipeline — it operates as a standalone intelligence layer used by agents and tools. Integration with `CapabilitySelectionStage` and `ExecutionStage` is pending.

---

## 3. Reality Scores

| # | Subsystem | Score | Rationale |
|---|-----------|-------|-----------|
| 1 | Startup | **6/10** | Two parallel paths (FastAPI + daemon), fragile ~50 route registrations, 945-line lifespan |
| 2 | Goal Understanding | **7/10** | Clean primary path, ambiguity resolver, but `interpret_goal()` used by both legacy and modern loops |
| 3 | Capability Registry | **8/10** | Well-factored, 49 imports confirm adoption, DI-injected pipeline stage, built-in intent map |
| 4 | Provider System | **8/10** | 12 production adapters, 7-dim scoring router, persistence, feedback loop; some experimental adapters |
| 5 | Planner | **5/10** | 18 files but 6 experimental; dual store path; `PlannerStateMachine` is active but experimental chain is disconnected |
| 6 | Execution Engine | **7/10** | Strong `ExecutionManager`+`WorkflowEngine` core, 43 tests, legacy `ControlLoop` isolated |
| 7 | EventBus | **9/10** | Single global bus, typed events, namespace isolation, WS broadcast, sync/async, mature |
| 8 | Configuration | **7/10** | Clean resolution chain, 80+ config entries, 3 deprecated shims remain |
| 9 | Memory System | **8/10** | 17 modules, unified facade, tiered architecture, all consumers migrated |
| 10 | Safety Engine | **8/10** | 15+ modules, governor + validator + security + privacy + audit + permissions |
| 11 | Notification | **9/10** | Single module, single singleton, push + WS + email + event log |
| 12 | Desktop Pipeline | **8/10** | 14 controller actions, safety layer, replay, all in `core/desktop/` |
| 13 | Browser Pipeline | **7/10** | Split across agent + provider + tools; no dedicated pipeline stage |
| 14 | Coding Pipeline | **6/10** | Rich intelligence layer but not wired into pipeline; standalone tooling |
| | **OVERALL** | **7.3/10** | Strong canonical core with isolated legacy; experimental subsystems pending integration |

---

## 4. Migration Order

Based on the deletion/migration tracker and current consolidation status:

### Phase 7 ✅ COMPLETE — Memory & Planner Deletion
- **D01** `core/memory.py` — REMOVED
- **D02** `core/memory_vector.py` — REMOVED
- **D03** `core/plan_manager.py` — REMOVED
- **D08** `brain/planner/` — REMOVED
- **D09** `brain/memory/` — REMOVED
- **D10** `brain/goals/` — REMOVED
- **D11** `brain/executor/` — REMOVED
- **I03** `brain.planner.Planner` — REMOVED
- **I05** `brain.goals.GoalManager` — REMOVED
- **M01–M07** — REMOVED
- Deleted 9 `core/agents/_legacy/` files

### Phase 8 ✅ COMPLETE — Workflow & Loop Consolidation
- **D06** `core/control_loop.py` — REMOVED (moved to `core/legacy/control_loop.py`)
- `brain/automation/loop.py` — refactored from 2770→2034 lines, 5 sub-modules extracted
- All 8 D06 consumers migrated

### Phase 9 ✅ COMPLETE — Test Gap Closure
- `tests/unit/test_execution_manager.py` — 25 new tests
- `tests/unit/test_automated_build.py` — 606 lines of tests (existing)

### Phase 10 ✅ COMPLETE — Capability Wiring
- `Capability` model: added `risk` field
- `CapabilitySelectionStage`: constructor DI for `CapabilityRegistry`

### Remaining (Highest Priority)

| Priority | Item | Files | Effort |
|----------|------|-------|--------|
| **P0** | D05: Delete `core/pipeline.py` (RuntimePipeline) | `core/pipeline.py` (legacy 10-phase) | Migrate callers to `core/pipeline/pipeline.py` |
| **P0** | D13–D16: Legacy RuntimePipeline references | Various callers of `.run()` | Standardize on `.execute()` |
| **P1** | D04: Delete `core/database_models.py` | `core/database_models.py` | Migrate to `core/database.py` |
| **P1** | D12: Delete `brain/persistence.py` | `brain/persistence.py` | Migrate to `core/checkpoint_manager.py` |
| **P2** | D18: Delete `PluginEventBus` | `core/event_bus.py:PluginEventBus` | Already deprecated, no active consumers |
| **P2** | D20: Wire workflow events through EventBus | `core/workflow/storage.py` | Publish `workflow.*` events in addition to SQLite log |
| **P2** | D21: Replace scheduler callbacks with EventBus | `core/scheduler/scheduler.py` | Publish `scheduler.tick` events |
| **P3** | D07: Delete `core/runtime/registry.py` | `core/runtime/registry.py` | Zero-consumer module |
| **P3** | D38–D39: Config cleanup | `core/config_registry.py`, `core/settings/store.py` | Live env var reads, route through ConfigService |
| **P4** | D40–D43: Identity consolidation | `core/identity/models.py`, `provider_sdk/permissions.py` | Delete old AuthContext, IdentityContext |
| **P4** | D22–D36: Database consolidation | 15 database files | Consolidate to bounded-context SQLite databases |

### Database Consolidation Targets

| Current Database | Target |
|-----------------|--------|
| `data/auth.json` | `data/system.db` (users table) |
| `data/sessions.json` | `data/system.db` (sessions table) |
| `data/brain.db` | `data/memory.db` + `data/planner.db` |
| `data/workflow.db` (shared) | `data/workflow.db` (workflow only) |
| `data/jarvis_memory.db` | `data/memory.db` |
| `data/jarvis.db` (shared ORM) | `data/app.db` (single async ORM) |
| `~/.jarvis/decision_memory.json` | `data/memory.db` (DecisionStore) |
| `~/.jarvis/checkpoints/*.json` | `~/.jarvis/user.db` (CheckpointStore) |
| `ai_os_memory.db` | Remove (owned by deleted `core/memory.py`) |

---

## 5. Technical Debt

### 5.1 Critical

| Debt | Location | Impact |
|------|----------|--------|
| **55+ route files in 3 directories** | `core/routes/` (37 files), `api/` (12 files), `routers/` (6 files) | Inconsistent loading, duplicate settings routes |
| **945-line lifespan with 30+ sequential phases** | `core/lifespan.py` | All phases are non-fatal; failures are logged not raised |
| **Sync ORM + async ORM sharing `data/jarvis.db`** | `core/database_models.py` + `core/database.py` | Schema conflicts, thread-safety issues |
| **Two config loading APIs** | `core/configuration/service.py` (canonical) vs `core/config.py`/`core/config_registry.py` (deprecated) | Consumers may use wrong API |
| **15 separate database files** | Various paths under `data/`, `~/.jarvis/` | Fragmented state, no bounded contexts |

### 5.2 High

| Debt | Location | Impact |
|------|----------|--------|
| **6 experimental planner modules** | `strategies.py`, `replan.py`, `comparison.py`, `health.py`, `evidence.py`, `outcomes.py` | Dead code — chain is disconnected |
| **Legacy ReasonerStage in pipeline** | `core/pipeline/stages/reasoner.py` | Dual stage path (reasoner vs reasoning) |
| **`brain/automation/loop.py` still 2034 lines** | `brain/automation/loop.py` | Refactored from 2770 but still large |
| **JSON-file-backed stores** | `memory/decision_memory.py`, `memory/crud_store.py`, `core/checkpoint_manager.py` | Crash-unsafe, no transactions |
| **`core/legacy/control_loop.py` still live** | Used by 5 production files + 3 test files | Legacy code in production path |

### 5.3 Medium

| Debt | Location | Impact |
|------|----------|--------|
| **ChromeDriver path hardcoded** | `core/real_validator.py:check_browser_load()` | ChormeDriver path hardcoded to `C:/chromedriver-win64/chromedriver.exe` |
| **`core/event_bus.py:MJEvent` legacy compat** | `core/event_bus.py:396` | Dual event type system |
| **Test isolation failures** | `tests/unit/test_activity_manager.py`, `tests/unit/test_activity_recorder.py` | Windows event-loop asyncio isolation |
| **Docker sandbox unavailable** | Various tests | Test environment limitation |
| **`pc_agent/` experimental package** | `pc_agent/computer_agent.py` | Deprecated but not removed |

### 5.4 Low

| Debt | Location | Impact |
|------|----------|--------|
| **QdrantClient shutdown errors** | All test runs | Harmless `ImportError` during Python shutdown |
| **Pydantic v2.11 deprecation warnings** | `core/settings/store.py:155` | `.model_fields` instance access |
| **`torch.jit.script` deprecation** | Various | PyTorch version mismatch |
| **`pynvml` package deprecation** | `core/benchmark/perf_baseline.py`, `core/health_monitor.py`, `core/hardware_advisor.py` | Replace with `nvidia-ml-py` |

---

## 6. Risks

### 6.1 Architectural Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `core/legacy/control_loop.py` is live code used by 5 production files | Medium | High — changes to `ExecutionManager` may break legacy loop | Complete migration to `ExecutionManager` + `WorkflowEngine` |
| Dual pipeline paths (canonical 24-stage + legacy RuntimePipeline) | Medium | High — inconsistent request processing | Delete D05/D13-D16 as P0 |
| 15 fragmented databases with no migration orchestration | High | High — data loss on crash | Enforce bounded-context DBs (Phase 9 tracker) |
| 6 experimental planner modules produce dead code | Medium | Low — unused but maintained | Either wire into `PlannerStateMachine` or delete |

### 6.2 Security Risks

| Risk | Location | Impact |
|------|----------|--------|
| `ChromeDriver` hardcoded path | `core/real_validator.py` | Path traversal if attacker controls workspace |
| `failures.jsonl` in working directory | `core/legacy/control_loop.py:969` | Sensitive failure data in world-readable file |
| In-memory audit log | `core/permission/manager.py` | Compliance violation on crash |
| Secrets in `failures.jsonl` | `core/legacy/control_loop.py:962-974` | API keys, tokens may be logged |

### 6.3 Operational Risks

| Risk | Impact |
|------|--------|
| All lifespan phases are non-fatal — silent failures | Services start with misconfigured subsystems |
| ~50 route registrations wrapped in try/except | Routes silently fail to register |
| Memory facade silently catches all exceptions (`logger.debug`) | Memory failures invisible in production |
| No health check endpoint for critical subsystems | Unable to detect Memory/EventBus/Config failures at runtime |

---

## 7. Future Roadmap

### Short Term (Next Sprint)

| Item | Description | Owner |
|------|-------------|-------|
| **P0: Delete D05** | Remove legacy `core/pipeline.py` RuntimePipeline; migrate all `.run()` callers to `.execute()` | Execution |
| **P0: Delete D13–D16** | Remove 10-phase state enum, LangGraph references, standardize on `.execute()` | Execution |
| **P1: Delete D04** | Migrate `core/database_models.py` consumers to `core/database.py` | Storage |
| **Wire experimental planner** | Integrate `strategies.py` → `replan.py` → `comparison.py` → `health.py` chain into `PlannerStateMachine` | Planner |

### Medium Term

| Item | Description |
|------|-------------|
| **Delete D07** | Remove zero-consumer `core/runtime/registry.py` |
| **Delete D18** | Remove deprecated `PluginEventBus` from `core/event_bus.py` |
| **Wire workflow events through EventBus** | Publish `workflow.*` events in addition to SQLite log (D20) |
| **Replace scheduler callbacks** | Publish `scheduler.tick` through EventBus (D21) |
| **Wire Coding Pipeline** | Integrate `core/coding/` intelligence into `CapabilitySelectionStage` and `ExecutionStage` |
| **Merge config APIs** | Remove deprecated `Config`/`config` from `core/config_registry.py`; route all through `core.configuration.configuration` |
| **Consolidate databases** | Merge 15 database files into bounded-context databases (D22–D36) |

### Long Term

| Item | Description |
|------|-------------|
| **Kill `core/legacy/control_loop.py`** | Rewrite remaining 5 consumers to use `ExecutionManager` + `WorkflowEngine` directly |
| **Delete JSON-file stores** | Migrate `decision_memory.json`, `crud_store` JSON, `checkpoint_manager` JSON to SQLite |
| **Identity consolidation** | Delete old `AuthContext`, `IdentityContext`, `provider_sdk/permissions.py` (D40–D43) |
| **Bounded-context databases** | Enforce single-owner databases with Alembic migrations |
| **Pipeline health checks** | Add `/health` endpoint for all canonical subsystems |
| **Remove `pc_agent/` package** | Complete desktop migration to `core/desktop/` |
| **Rationalize route directories** | Consolidate `core/routes/`, `api/`, `routers/` into single `core/routes/` |

### Target State

```
core/
├── lifespan.py          ← ONE startup
├── goal_interpreter.py  ← ONE goal understanding
├── capability/          ← ONE capability registry
├── providers/           ← ONE provider system
├── planner/             ← ONE planner
├── execution/           ← ONE execution engine
├── event_bus.py         ← ONE event bus
├── configuration/       ← ONE configuration system
├── pipeline/            ← ONE pipeline (24 stages)
│   └── stages/
│       ├── desktop/     ← Desktop pipeline stage
│       ├── browser/     ← Browser pipeline stage
│       └── coding/      ← Coding pipeline stage
memory/                  ← ONE memory system
notifications/           ← ONE notification system
core/
├── system_governor.py   ← ONE safety engine
├── real_validator.py    ← ONE validator
├── routing/safety.py    ← ONE tool safety
├── desktop/safety.py    ← ONE desktop safety
└── permission/          ← ONE permission system
```

---

*End of CANONICAL ARCHITECTURE document. All findings backed by file/function evidence from the live codebase as of 2026-07-15.*
