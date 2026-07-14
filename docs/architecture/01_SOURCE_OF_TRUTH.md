# SOURCE OF TRUTH — MJ Architecture Audit

> Generated: 2026-07-14
> Purpose: Every major responsibility must have ONE canonical owner.

---

## 1. STARTUP

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `jarvis.py` (CLI), `core/main.py` (FastAPI), `daemon/jarvis_service.py` (Windows service), `brain/UnifiedBrain` (module-level singleton) |
| **Active implementation** | `core/main.py` (FastAPI `app`) + `core/lifespan.py` (`lifespan` async context manager) — the primary server entry point that orchestrates all subsystem initialization |
| **Legacy implementations** | `core/intent_router.py` extract_intent — deprecated since v3.2, to be removed after v4.0 |
| **Experimental implementations** | `daemon/jarvis_service.py` JarvisDaemon — Windows service with heartbeat, PID file, and crash recovery. Runs independently, not wired into FastAPI lifespan. |
| **Dead implementations** | `daemon/__init__.py` (empty), `services/__init__.py` (empty) |
| **Reality score** | 6/10 — Two parallel startup paths exist (FastAPI server vs daemon). ~50 route modules attempted in main.py, each wrapped in try/except. Lifespan has ~30+ sequential phases, all non-fatal. Fragile. |
| **Canonical future owner** | `core/lifespan.py` — consolidate all startup paths into a single boot sequence |

---

## 2. REQUEST PROCESSING

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/pipeline/pipeline.py` (`process_message`), `core/pipeline/adapters/` (rest_adapter, ws_adapter, channel_adapter, voice_adapter), `core/main.py` (fastapi routes), `core/routes/` (37 files), `api/` (12 files), `routers/` (6 files), `channels/` (5 channels) |
| **Active implementation** | `core/pipeline/pipeline.py` `process_message()` — canonical pipeline with 24 DEFAULT_STAGES. All transport adapters call this. |
| **Legacy implementations** | `core/intent_router.py` — deprecated classifier, delegates to `core/routing/request_classifier.py`. `core/pipeline/stages/reasoner.py` — legacy, replaced by `stages/reasoning/`. |
| **Experimental implementations** | `mcp/memory_server.py`, `mcp/rag_server.py`, `mcp/email_server.py`, `mcp/image_gen_server.py` — standalone stdio MCP servers, NOT connected to main app |
| **Dead implementations** | `api/agi_routes.py` (commented out in main.py), `api/hybrid_integration.py` (commented out) |
| **Reality score** | 7/10 — Pipeline architecture is clean and well-defined. However, routes are split across 55+ files in 3 directories (`core/routes/`, `api/`, `routers/`) with inconsistent loading strategies. Two settings route files (`api/settings_routes.py` vs `core/routes/settings.py`) use different backends. |
| **Canonical future owner** | `core/pipeline/pipeline.py` (`process_message`) — consolidate all request entry points through the pipeline |

---

## 3. GOAL UNDERSTANDING

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `brain/goal_generator.py` (`GoalGenerator`), `brain/UnifiedBrain.py` (`create_goal`, `complete_goal`, `fail_goal`, `auto_generate_goals`), `core/planner/unified_store.py` (`UnifiedStore`) |
| **Active implementation** | `brain/goal_generator.py` `GoalGenerator.evaluate_world()` — observes WorldModel state, creates Plan objects via UnifiedStore. `UnifiedBrain.create_goal()` — creates goals via UnifiedStore, publishes events. |
| **Legacy implementations** | (none — brain/goals/ and brain/planner/ have been deleted) |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 8/10 — Clean consolidation. `GoalManager` → `UnifiedStore`, `Goal` → `Plan` migration complete. Brain re-exports provide backward compat. |
| **Canonical future owner** | `core/planner/unified_store.py` `UnifiedStore` — single source of truth for goal/plan persistence |

---

## 4. PLANNING

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/planner/decomposer.py` (`GoalDecomposer`), `core/planner/dag.py` (`TaskGraph`), `core/planner/executor.py` (`PlannerExecutor`), `core/planner/state_machine.py` (`PlannerStateMachine`), `core/planner/store.py` (`PlanStore`), `core/planner/strategies.py` (`StrategyGenerator`), `core/planner/replan.py` (`ReplanEngine`), `core/planner/comparison.py` (`ComparativeScorer`), `core/planner/health.py` (`PlanHealthEngine`), `core/planner/evidence.py` (`PlanEvidenceEngine`), `core/planner/outcomes.py` (`PlanOutcomeStore`), `core/planner/classifier.py` (`classify`), `core/planner/templates.py` (templates), `core/planner/models.py` (`SubGoal`, `ExecutionPlan`) |
| **Active implementation** | `core/planner/decomposer.py` `GoalDecomposer.decompose()` — deterministic decomposition with LLM fallback. `core/planner/state_machine.py` `PlannerStateMachine.run()` — PLAN→DECOMPOSE→ROUTE→EXECUTE→VERIFY→COMPLETE/FAILED lifecycle. |
| **Legacy implementations** | `core/planner/store.py` `PlanStore` — being migrated away to `UnifiedStore`. Has `migrate_from_planstore()`. |
| **Experimental implementations** | `core/planner/strategies.py` `StrategyGenerator` — N candidate decompositions per strategy. `core/planner/replan.py` `ReplanEngine` — alternative plans with deltas. `core/planner/comparison.py` `ComparativeScorer` — 5-dimension scoring. `core/planner/health.py` `PlanHealthEngine` — 7-signal health assessment. `core/planner/evidence.py` `PlanEvidenceEngine` — per-node evidence. `core/planner/outcomes.py` `PlanOutcomeStore` — prediction vs actual tracking. |
| **Dead implementations** | (none) |
| **Reality score** | 5/10 — Rich planning subsystem but 6 of 14 files are EXPERIMENTAL and PARTIALLY connected. The experimental files form a chain (strategies→replan→comparison→health→evidence→outcomes) but are only used within themselves. `PlannerStateMachine` is ACTIVE and well-integrated with agents. |
| **Canonical future owner** | `core/planner/state_machine.py` `PlannerStateMachine` — the integrator that orchestrates decomposition, routing, execution, and verification |

---

## 5. EXECUTION

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `brain/executor/executor.py` (`Executor`), `brain/executor/verifier.py` (`Verifier`), `brain/tools/tool_registry.py` (`ToolRegistry`), `brain/tools/project_tool.py` (`ProjectTool`), `core/agents/` (15 agents + router + registry + executor + graph), `core/agent_orchestrator.py` (`AgentOrchestrator`), `core/agent_loop.py` (`stream_agent_loop`), `core/tools/` (build_tools, automated_build, execution/edit_tools, execution/direct_tools, implementations, executor, registry, schemas) |
| **Active implementation** | `brain/executor/executor.py` `Executor.execute()` — 3-tier resolution: 1) `core.tools.execution.execute_tool_block()` (RBAC/sandbox), 2) locally registered tools, 3) LLM resolution. `core/agents/router.py` `AgentRouter.route()` — maps subgoals to agents. |
| **Legacy implementations** | `core/agents/registry.py` `AgentRegistry` — legacy sub-agent registry (NEXUS, FORGE, etc.), wrapped by adapters in `core/agents/adapters/` |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 7/10 — Two execution paths coexist: `Executor` (brain, tool-focused) and `AgentRouter` (core, agent-focused). They are complementary but the boundary is unclear. `AgentOrchestrator` is essentially a CLI adapter over the same AutomationLoop. |
| **Canonical future owner** | `brain/executor/executor.py` `Executor` — consolidate all tool execution through the 3-tier executor |

---

## 6. WORKFLOW

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/workflow/engine.py` (`WorkflowEngine`), `core/workflow/long_horizon_fsm.py` (`LongHorizonFSM`), `core/workflow/storage.py` (`WorkflowStore`), `core/workflow/graph.py` (`ExecutionGraph`), `core/workflow/context.py` (`ContextManager`), `core/workflow/tracker.py` (`ExecutionTracker`), `core/workflow/recovery.py`, `core/workflow/recorder.py`, `core/workflow/artifact_store.py`, `core/workflow/heartbeat_monitor.py`, `core/workflow/calibration.py`, `core/workflow/learning_store.py`, `core/workflow/learning_models.py` |
| **Active implementation** | `core/workflow/engine.py` `WorkflowEngine` — full-featured: compensation, retry, idempotency, eventing. `LongHorizonFSM` — multi-phase FSM (research→plan→build→test→repair→retest→deliver) integrated as FSM step type. |
| **Legacy implementations** | `brain/automation/loop.py` `_WORKFLOW_ENGINE` global (line 36-50) — marked deprecated, kept for backward compat during Phase 5 migration |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 9/10 — Best-organized subsystem. Single `core/workflow/` package with clear separation: engine, storage, models, graph, events, tracker, recovery. All files ACTIVE and CONNECTED. |
| **Canonical future owner** | `core/workflow/engine.py` `WorkflowEngine` — mature, owns workflow lifecycle end-to-end |

---

## 7. SCHEDULER

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/scheduler/scheduler.py` (`Scheduler`), `core/scheduler/queue.py` (`SchedulerQueue`), `core/scheduler/store.py` (`SchedulerStore`), `core/scheduler/models.py`, `core/scheduler/registry.py`, `core/scheduler/policies.py`, `core/scheduler/decision.py` (`DecisionEngine`), `core/scheduler/intelligence.py` (`ActivityIntelligence`), `core/scheduler/resources.py`, `core/scheduler/metrics.py`, `core/scheduler/autonomous.py` (`AutonomousScheduler`), `core/scheduler/pipeline_executor.py`, `core/scheduler/executors.py`, `core/scheduler/chain.py`, `core/scheduler/worker.py` |
| **Active implementation** | `core/scheduler/scheduler.py` `Scheduler` — time-driven loop: tick → refresh queue → clean workers → fill slots → launch workers. 467 lines, well-structured. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | `core/scheduler/autonomous.py` `AutonomousScheduler` — bridges OpportunityDiscoveryEngine → DecisionEngine → SchedulerQueue. Phase 8.4 bridge, PARTIALLY connected. `core/scheduler/decision.py` `DecisionEngine` — EV/confidence/risk gating. |
| **Dead implementations** | (none) |
| **Reality score** | 8/10 — Self-contained package with clear tick-based lifecycle. Experimental parts are isolated and don't affect core operation. |
| **Canonical future owner** | `core/scheduler/scheduler.py` `Scheduler` — owns the scheduling lifecycle |

---

## 8. DESKTOP / PC CONTROL

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/desktop/` (controller.py, screen.py, window.py, safety.py, replay.py), `pc_agent/` (computer_agent.py, snapshot.py, playbooks.py), `core/vision_agent.py`, `automation/pc_automation.py`, `core/providers/adapters/desktop_provider.py` |
| **Active implementation** | `core/desktop/` — `DesktopController` (pyautogui), `ScreenCapture` (mss+PIL), `WindowController` (pygetwindow), `SafetyManager` (gating all actions). Wrapped by `DesktopProvider` adapter. |
| **Legacy implementations** | `pc_agent/` — emits `DeprecationWarning("EXPERIMENTAL and will be replaced by core/desktop/")`. Still imported by `mcp/server.py` (fallback), `plugins/pc_automation_plugin.py`, `core/routes/control.py`, `core/routes/vision.py`. |
| **Experimental implementations** | `core/vision_agent.py` — vision-based desktop automation. Separate from `core/desktop/` — uses raw pyautogui without safety layer. Has its own action loop (click, type, hotkey, scroll, copy, paste) using mss + Ollama vision. |
| **Dead implementations** | `automation/pc_automation.py` — minimal volume/screenshot functions |
| **Reality score** | 4/10 — Three competing implementations (`core/desktop/`, `pc_agent/`, `core/vision_agent.py`). `core/desktop/` is the canonical one with safety gating, but `pc_agent/` is still wired into MCP, plugins, and routes. `core/vision_agent.py` bypasses the safety layer entirely. |
| **Canonical future owner** | `core/desktop/` — consolidate all desktop control into this safety-gated package |

---

## 9. BROWSER

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/browser_manager.py` (`BrowserSessionManager`), `core/tools/browser_tools.py` (20+ functions), `core/tools/browser_planner.py` (`BrowserPlanner`), `core/tools/browser_fsm.py` (`BrowserState` FSM), `core/tools/browser_research.py` (`do_browser_research`), `core/agents/browser_agent.py` (`BrowserAgent`), `core/providers/adapters/browser_provider.py` (`BrowserProvider`), `core/workspace/browser_context.py`, `core/fact_extraction/` (BrowserFactExtractor, BrowserFactStore) |
| **Active implementation** | `core/browser_manager.py` `BrowserSessionManager` — Playwright session lifecycle. `core/tools/browser_tools.py` — 20+ atomic browser tools (navigate, click, fill, snapshot, screenshot, etc.). |
| **Legacy implementations** | (none) |
| **Experimental implementations** | `core/tools/browser_fsm.py` — simpler state machine alternative to `BrowserPlanner`. Both are ACTIVE but serve different purposes. |
| **Dead implementations** | (none) |
| **Reality score** | 9/10 — Clean, single architecture. Consistent pattern: session manager → atomic tools → planner/FSM → provider adapter → agents. No competing implementations. |
| **Canonical future owner** | `core/browser_manager.py` `BrowserSessionManager` + `core/tools/browser_tools.py` — owns browser lifecycle and atomic operations |

---

## 10. CODING

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `brain/automation/loop.py` (`AutomationLoop`), `core/tools/build_tools.py`, `core/tools/automated_build.py`, `core/tools/execution/edit_tools.py`, `brain/tools/project_tool.py` (`ProjectTool`), `core/agents/build_agent.py`, `core/agents/test_agent.py` |
| **Active implementation** | `brain/automation/loop.py` `AutomationLoop._build_project()` — plan→generate→verify_gates→build(classify+repair)→test→verify→runtime_validation→finish. Full error classification registry (27 patterns), FailureMemory, ArchitecturalMemory. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 7/10 — Dual wrapper layer (`build_tools.py` vs `automated_build.py`) around the same `AutomationLoop` engine. `build_tools.py` is older/simpler, `automated_build.py` is newer with richer post-execution recording (ActivityGraph, CalibrationStore, KnowledgeStore). Both are ACTIVE and called from different paths. |
| **Canonical future owner** | `core/tools/automated_build.py` `do_automated_build` — newer, richer wrapper. Deprecate `build_tools.py` in favor of this. |

---

## 11. RESEARCH

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/research/` (21 files), `core/agents/research_agent.py` (`ResearchAgent`), `core/tools/browser_research.py` (`do_browser_research`) |
| **Active implementation** | `core/research/` — full pipeline: `ResearchPlanner.plan()` → `FactExtractor.extract()` → `FactStore` → `FactReasoner.analyze()` → `FactSynthesizer.synthesize()` → `GapDetector.analyze()`. `do_browser_research()` bridges browser tools with this pipeline. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | `core/research/extraction_fsm.py` `ExtractionFSM` — 10-state extraction state machine. No callers found — UNUSED. `core/research/reasoning.py` `ReasoningEngine` — belief-driven research with Bayesian updates. Used? Unclear. |
| **Dead implementations** | (none) |
| **Reality score** | 8/10 — Rich, well-organized pipeline. `ResearchAgent` is a simplified path that bypasses the full pipeline (just browser navigate + fetch). The `extraction_fsm.py` is UNUSED. Benchmark files are test-only. |
| **Canonical future owner** | `core/research/` — the full research pipeline. Unify `ResearchAgent` to use the same pipeline. |

---

## 12. MEMORY

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `memory/memory_facade.py` (`MemoryFacade`), `memory/episodic_store.py`, `memory/semantic_store.py`, `memory/task_store.py`, `memory/decision_store.py`, `memory/fact_store.py`, `memory/crud_store.py`, `memory/mem0_adapter.py`, `memory/tiered_memory.py`, `memory/embedding_memory.py`, `memory/vector_store.py`, `memory/decision_memory.py`, `memory/preference_profile.py`, `memory/reranker.py`, `memory/similarity.py`, `memory/extraction.py`, `memory/embedding_utils.py`, `core/memory_driven_decisions.py` |
| **Active implementation** | `memory/memory_facade.py` `MemoryFacade` (singleton `memory`) — lazy-loads 6 backends: mem0, tiered, episodic, semantic, task, decision. This is what the rest of the system imports. |
| **Legacy implementations** | `memory/decision_memory.py` `DecisionMemory` — older JSON-file-based decision memory, different schema from `decision_store.py`. Used by `core/memory_driven_decisions.py` `MemoryDrivenRouter`. |
| **Experimental implementations** | (none) |
| **Dead implementations** | `brain/memory/` (already deleted in previous phase) |
| **Reality score** | 6/10 — Consolidation is ~80% complete (brain/memory/ removed). However: `decision_memory.py` (JSON) and `decision_store.py` (SQLite) are two separate implementations with different schemas and different callers. `fact_store.py` uses both `data/memory.db` and `ai_os_memory.db` inconsistently. The `MemoryFacade` facade helps but hides complexity. |
| **Canonical future owner** | `memory/memory_facade.py` `MemoryFacade` — single API. Consolidate decision_memory into decision_store. Unify fact_store database path. |

---

## 13. NOTIFICATIONS

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `notifications/notifier.py` (`SupervisorNotifier`), `monitors/alerts.py` (`AlertRouter`), `core/event_bus.py` (WebSocket broadcast) |
| **Active implementation** | `notifications/notifier.py` `SupervisorNotifier` — channels: Email (SMTP), Push (ntfy.sh/Pushover), WebSocket, event log file. Triggered by build events only. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 3/10 — Two competing implementations (`SupervisorNotifier` vs `AlertRouter`) with overlapping purpose but no integration. Neither has TTS bridge. `AlertRouter` has optional `speak_fn`/`whatsapp_fn` that default to `None` with no auto-wiring. No centralized notification service exists. |
| **Canonical future owner** | NEW — `core/notifications/` package that consolidates `SupervisorNotifier` + `AlertRouter` + EventBus WebSocket + TTS bridge |

---

## 14. CONFIGURATION

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `config.yaml`, `core/config_init.py` (`init_config`), `core/config_registry.py` (`Config` + `_REGISTRY`), `core/config.py` (deprecated constants), `core/config_schema.py` (deprecated `JarvisConfig`), `core/configuration/` (ConfigurationService), `api/settings_routes.py`, `core/routes/settings.py`, `.env` |
| **Active implementation** | `core/configuration/` `ConfigurationService` — canonical config source. Environment variables → config.yaml → settings.json. |
| **Legacy implementations** | `core/config_registry.py` `Config` — marked "v3.2 deprecated, remove after v4.0" but `_REGISTRY` (160+ entries) is still used by `core/routes/settings.py`. `core/config.py` — backward-compat shim mapping legacy constants. `core/config_schema.py` — backward-compat shim for `JarvisConfig`. |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 4/10 — Three layers of deprecated wrappers (`config_registry`, `config.py`, `config_schema.py`) around the canonical `ConfigurationService`. Two competing settings API routes (`api/settings_routes.py` using `settings_store` vs `core/routes/settings.py` using `config_registry`). High confusion risk. |
| **Canonical future owner** | `core/configuration/` `ConfigurationService` — strip all deprecated wrappers, unify settings API routes |

---

## 15. PROVIDERS

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/providers/` (base, registry, bootstrap, router, store, budget, memory, benchmark, benchmark_store), `core/providers/adapters/` (12 adapters: forge, claude_code, codex, browser, research, automation, messaging, deployment, workspace, github, email, desktop), `core/providers/feedback/` (models, recorder, store, calibrator), `core/providers/orchestration/` (orchestrator, models, adapt, store, planner), `provider_sdk/` (manifest, manifest_v2, lifecycle, stages, discovery, loader, registration, quarantine, permissions), `provider_sdk/adapters/` (mcp, http, grpc, cli), `providers/` (legacy JSON/YAML manifests) |
| **Active implementation** | `core/providers/registry.py` `ProviderRegistry` — singleton with capability-based indexing. `core/providers/router.py` `ProviderRouter` — evidence-based scoring across 7 dimensions. `core/providers/bootstrap.py` — registers 10 built-in + 2 external providers. |
| **Legacy implementations** | `providers/` — static JSON/YAML manifest examples. UNUSED. |
| **Experimental implementations** | `core/providers/orchestration/` — multi-provider orchestration. PARTIAL. `provider_sdk/adapters/` (mcp, http, grpc, cli) — UNUSED. |
| **Dead implementations** | (none) |
| **Reality score** | 8/10 — Well-structured provider ecosystem. Registry + Router + Memory + Budget form a coherent system. Adapter pattern cleanly wraps internal tools as providers. Orchestration and SDK transport adapters are experimental but isolated. |
| **Canonical future owner** | `core/providers/registry.py` `ProviderRegistry` — owns provider lifecycle. `core/providers/router.py` `ProviderRouter` — owns provider selection. |

---

## 16. CAPABILITIES

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/capability/` (models, registry, graph, negotiation, composition), `core/agents/capabilities.py` (deprecated `CAPABILITIES` dict), `core/pipeline/stages/capability_selection.py` (`CapabilitySelectionStage`) |
| **Active implementation** | `core/capability/registry.py` `CapabilityRegistry` (singleton) — 19 built-in capabilities, 17 built-in intent mappings. `core/capability/graph.py` `CapabilityGraph` — goal resolution into capability DAGs. `core/capability/negotiation.py` `CapabilityNegotiator` — scores providers for capability nodes. `core/capability/composition.py` `CompositionEngine` — composes full goal plans. |
| **Legacy implementations** | `core/agents/capabilities.py` — deprecated `CAPABILITIES` dict mapping agent IDs to keywords. Emits `DeprecationWarning`. Calls `_register_with_capability_registry()` to migrate. |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 8/10 — Clean capability system with graph-based resolution and provider negotiation. The `core/capability/` package is well-designed. Agent capability mapping is deprecated and migrating. |
| **Canonical future owner** | `core/capability/registry.py` `CapabilityRegistry` — the canonical capability store and resolver |

---

## 17. SAFETY

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/desktop/safety.py` (`SafetyManager`), `core/routing/safety.py` (`SafetyLevel`, `classify_tool`), `core/governance/` (task_router, resource_monitor, work_queue) |
| **Active implementation** | `core/desktop/safety.py` `SafetyManager` — desktop action safety (emergency stop, forbidden regions, cooldowns, rate limits, speed limits). `core/routing/safety.py` `classify_tool()` — classifies shell/file operations as SAFE/CONFIRM/DANGEROUS. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 6/10 — Safety is fragmented across desktop actions and tool classification. No unified safety policy that covers all execution paths. `core/vision_agent.py` bypasses desktop safety entirely. Governance layer exists but doesn't integrate with safety. |
| **Canonical future owner** | NEW — a unified safety layer that integrates `SafetyManager` + `classify_tool` + governance into a single policy enforcement point |

---

## 18. PERMISSIONS

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/permission/` (models, registry, manager, policy, audit, observer), `provider_sdk/permissions.py` (separate `PermissionManager`), `core/authz/` (schema, loader, engine) |
| **Active implementation** | `core/permission/manager.py` `PermissionManager` — resolves permissions against PolicyProfile (STRICT/DEVELOPER/AUTONOMOUS). `core/permission/policy.py` `PolicyEngine` — three risk profiles. `core/permission/registry.py` `PermissionRegistry` — maps capability IDs to required permissions. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | `core/permission/observer.py` `RuntimeObserver` — PARTIAL. |
| **Dead implementations** | (none) |
| **Reality score** | 7/10 — Well-designed permission system with profiles, registry, audit, and policy engine. However: `provider_sdk/permissions.py` duplicates `core/permission/models.py` with identical `ALL_PERMISSIONS`/`HIGH_RISK` definitions — risk of divergence. RBAC (`core/authz/`) is separate from the permission system. |
| **Canonical future owner** | `core/permission/manager.py` `PermissionManager` — owns all permission resolution. Remove duplication in `provider_sdk/permissions.py`. |

---

## 19. LOGGING

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/main.py` (logging configuration), `core/audit_log.py` (`AuditLog`), `core/observability/metrics.py` (`MetricsMiddleware`), `daemon/jarvis_service.py` (basicConfig) |
| **Active implementation** | `core/main.py` — rotating file handler (10MB x 5) to `~/.jarvis/logs/jarvis.log` + stdout. `core/audit_log.py` `AuditLog` — JSONL audit with PII redaction, daily rotation to `data/audit/audit-{date}.jsonl`, buffer flush every 50 entries. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 7/10 — Application logging is standard rotating file. Audit logging is JSONL with PII redaction. However: no structured logging (no JSON log format), no centralized log aggregation, daemon has separate logging config. Permission audit (`core/permission/audit.py`) is in-memory only. |
| **Canonical future owner** | `core/audit_log.py` `AuditLog` — consolidate all audit logging. Consider structured logging for application logs. |

---

## 20. RECOVERY

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/workflow/recovery.py` (`recover_active_workflows`), `core/workflow/heartbeat_monitor.py`, `brain/automation/loop.py` (`FailureMemory`, `ArchitecturalMemory`), `brain/persistence.py` (`ProjectPersistence`), `daemon/jarvis_service.py` (`JarvisDaemon`), `core/lifespan.py` (orphan_recovery, consolidator, backup_manager), `monitors/services.py` (`ServiceHealthChecker`) |
| **Active implementation** | `core/workflow/recovery.py` `recover_active_workflows()` — recovers RUNNING/RECOVERING/COMPENSATING workflows on startup. `brain/automation/loop.py` `FailureMemory` — SQLite-backed pattern matching for build errors. `brain/persistence.py` `ProjectPersistence` — multi-day checkpoint/resume with SQLite. |
| **Legacy implementations** | (none — consolidated) |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 8/10 — Multiple recovery mechanisms at different levels (workflow, build, project, daemon, health monitoring). All are ACTIVE and CONNECTED. Well-distributed responsibilities. |
| **Canonical future owner** | `core/workflow/recovery.py` — workflow-level recovery. `daemon/jarvis_service.py` — process-level recovery. Complementary, not competing. |

---

## 21. PLUGIN SYSTEM

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/plugins/` (20+ files: base, loader, registry, manifest, runtime, watchdog, hot_reload, events, verification, sandbox, ssrf, privacy, memory, voice, automation, api, state_store, settings_store, dependencies, compatibility, errors, marketplace), `plugins/` (5 built-in: wake_word, pii_routing, pc_automation, file_tools, memory), `jarvis_plugin_sdk/` (minimal), `provider_sdk/` (separate SDK) |
| **Active implementation** | `core/plugins/base.py` `Plugin` + `PluginRegistry` — 30+ hook methods, lifecycle management, hot-reload, watchdog. `core/plugins/loader.py` `PluginLoader` — scans directories for plugin.json/skill.json, loads from entry points. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | `jarvis_plugin_sdk/` — minimal placeholder for third-party plugin development. `provider_sdk/` — separate SDK for providers (not plugins). |
| **Dead implementations** | (none) |
| **Reality score** | 8/10 — Mature plugin system with comprehensive hook system, lifecycle management, watchdog, hot-reload, sandboxing, SSRF protection, dependency resolution, and compatibility checking. Well-structured. Two manifest classes (`base.py:PluginManifest` vs `manifest.py:PluginManifest`) with different fields — potential confusion. |
| **Canonical future owner** | `core/plugins/` — owns all plugin lifecycle. Deprecate one of the two PluginManifest classes. |

---

## 22. VOICE

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `assistant/voice_pipeline.py` (`VoiceEngine`), `assistant/stt*.py` + `providers/` (faster_whisper, deepgram, azure_speech), `assistant/tts*.py` + `providers/` (kokoro, edge_tts), `assistant/wake_word.py` (`WakeWordDetector`), `core/routes/voice.py` (REST + WebSocket routes), `core/pipeline/adapters/voice_adapter.py`, `plugins/wake_word_plugin.py` |
| **Active implementation** | `assistant/voice_pipeline.py` `VoiceEngine` — mic→STT→LLM→TTS→speaker pipeline. Three modes: wake-word, continuous (VAD), push-to-talk. Pluggable STT/TTS providers via registry pattern. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 9/10 — Clean, single pipeline with pluggable providers via registry pattern. STT providers (3), TTS providers (2), wake word detection, VAD, REST/WS routes, pipeline adapter, and plugin integration. Well-designed. |
| **Canonical future owner** | `assistant/voice_pipeline.py` `VoiceEngine` — owns the voice pipeline lifecycle |

---

## 23. AUTOMATION

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `brain/automation/loop.py` (`AutomationLoop`), `automation/pc_automation.py` (legacy), `core/scheduler/scheduler.py` (time-driven scheduling), `core/scheduler/autonomous.py` (opportunity-driven) |
| **Active implementation** | `brain/automation/loop.py` `AutomationLoop` — autonomous build pipeline with FailureMemory, ArchitecturalMemory, RequirementTracker. Polls highest-priority goal, runs full build pipeline. |
| **Legacy implementations** | `automation/pc_automation.py` — minimal volume/screenshot functions. Dead code. |
| **Experimental implementations** | (none) |
| **Dead implementations** | `automation/pc_automation.py` |
| **Reality score** | 7/10 — `AutomationLoop` is the single automation engine for builds. The `Scheduler` handles time-driven task scheduling separately. Clear separation of concerns. `automation/pc_automation.py` is dead. |
| **Canonical future owner** | `brain/automation/loop.py` `AutomationLoop` — owns build automation. `core/scheduler/scheduler.py` `Scheduler` — owns time-driven automation. |

---

## 24. EVENTBUS

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/event_bus.py` (`EventBus`, `global_event_bus`), `core/event_types.py` (typed event dataclasses), `brain/events/event_bus.py` (shim), `brain/events/event_types.py` (shim), `brain/events/__init__.py` (shim) |
| **Active implementation** | `core/event_bus.py` `EventBus` — singleton `global_event_bus`. Features: pattern subscription (exact/wildcard/multi), priority ordering, async+sync publish, streaming queue, WebSocket broadcast, in-memory history ring buffer (100 events), tenant-aware routing, namespace isolation. |
| **Legacy implementations** | `brain/events/event_bus.py` — backward-compat shim re-exporting from `core.event_bus`. `brain/events/event_types.py` — backward-compat shim re-exporting from `core.event_types`. `brain/events/__init__.py` — backward-compat shim. |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 10/10 — Single canonical EventBus with comprehensive features. Brain shims provide clean backward compatibility. Mature, well-tested. |
| **Canonical future owner** | `core/event_bus.py` `EventBus` — owns all event publish/subscribe. |

---

## 25. HISTORY

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `integrations/whatsapp/history.py` (`WhatsAppHistory`), `memory/memory_facade.py` (general recall), `ai_os_memory.db` (conversation memory) |
| **Active implementation** | No central history service exists. WhatsApp has its own SQLite history store. General conversation history goes through `memory/` MemoryFacade recall. `brain/automation/loop.py` has `_build_history` dict for build errors. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 3/10 — No centralized conversation/chat history service. Each integration manages its own history. Memory system is used for recall but not as a structured history store. |
| **Canonical future owner** | NEW — `core/history/` package that provides a unified conversation history service, backed by the memory system |

---

## 26. PROJECTS

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/project_manager.py` (`ProjectManager`), `core/project_state.py` (`ProjectState`), `brain/tools/project_tool.py` (`ProjectTool`), `core/routing/project_context.py` (`ContextManager`), `core/cloud/project_manager.py` |
| **Active implementation** | `core/project_manager.py` `ProjectManager` — high-level queue/priority/lifecycle. `core/project_state.py` `ProjectState` — single source of truth for project state (25+ fields, persisted to `~/.jarvis/projects/{name}/state.json`). |
| **Legacy implementations** | (none) |
| **Experimental implementations** | `core/cloud/project_manager.py` — cloud-specific variant |
| **Dead implementations** | (none) |
| **Reality score** | 7/10 — Well-layered: `ProjectManager` (queue) + `ProjectState` (persistence) + `ProjectTool` (low-level ops). Cloud variant adds complexity. `ProjectTool` partially overlaps with `core/tools/` execution tools. |
| **Canonical future owner** | `core/project_manager.py` `ProjectManager` — owns project lifecycle. `core/project_state.py` `ProjectState` — owns project persistence. |

---

## 27. RULES

| Attribute | Evidence |
|-----------|----------|
| **Current implementations** | `core/tools/policy.py` (tool usage policies), `core/tools/security.py` (path allowlisting/blocklisting), `core/permission/policy.py` (`PolicyEngine`, `PolicyProfile`), `core/authz/` (RBAC) |
| **Active implementation** | No declarative rules engine exists. Policy enforcement is done via `core/tools/policy.py` and `core/tools/security.py` (path allow/deny lists). RBAC profiles (STRICT/DEVELOPER/AUTONOMOUS) in `core/permission/policy.py`. |
| **Legacy implementations** | (none) |
| **Experimental implementations** | (none) |
| **Dead implementations** | (none) |
| **Reality score** | 3/10 — No formal rules engine or declarative rule language. Policy is scattered across path allowlists, RBAC profiles, and tool-level checks. `.jarvis-rules` files do not exist. |
| **Canonical future owner** | NEW — a rules engine that unifies policy, permissions, safety, and governance into a single declarative system |

---

## CROSS-CUTTING SUMMARY

### Top 5 healthiest areas (9-10/10)
1. **EventBus** (10/10) — single canonical implementation, clean shims
2. **Browser** (9/10) — single architecture, no competing implementations
3. **Voice** (9/10) — single pipeline, pluggable providers
4. **Workflow** (9/10) — well-organized, all ACTIVE
5. **Providers** (8/10) — well-structured ecosystem

### Bottom 5 unhealthiest areas (3-4/10)
1. **Notifications** (3/10) — fragmented, two competing impls, no TTS bridge
2. **History** (3/10) — no central service, each integration manages its own
3. **Rules** (3/10) — no rules engine, policy scattered
4. **Desktop** (4/10) — three competing implementations, safety bypassed
5. **Configuration** (4/10) — three layers of deprecated wrappers, two settings APIs

### Most fragmented areas (most competing implementations)
- **Desktop**: 3 implementations (desktop/, pc_agent/, vision_agent.py)
- **Configuration**: 3 deprecated wrappers + 2 settings APIs
- **Notifications**: 2 competing implementations + EventBus WS
- **Memory**: 2 decision memory implementations (JSON vs SQLite)

### Priority consolidation candidates
1. **Merge notifications** → consolidated `core/notifications/` with TTS bridge
2. **Strip config wrappers** → single `ConfigurationService` + single settings API
3. **Delete pc_agent/** → migrate remaining consumers to `core/desktop/`
4. **Delete or wire vision_agent.py** → consolidate into `core/desktop/`
5. **Unify decision_memory.py** → consolidate into `decision_store.py`
6. **Create centralized history** → `core/history/` backed by memory system
7. **Create rules engine** → unified declarative policy system
8. **Deprecate build_tools.py** → standardize on `automated_build.py`
