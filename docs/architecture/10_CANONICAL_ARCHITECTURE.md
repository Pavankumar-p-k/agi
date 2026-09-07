# CANONICAL ARCHITECTURE — MJ (Final Audit)

**Generated:** 2026-07-30  
**Scope:** Complete architecture synthesis from 8 READ ONLY audits  
**Status:** ENGINEERING DOCUMENT — Target state definition

---

## 1. WHAT IS MJ?

MJ (formerly JARVIS) is a **multi-modal autonomous agent platform** with:

- **Single canonical request pipeline** (19 stages) handling 11 transport paths
- **Provider-agnostic LLM routing** with evidence-based selection
- **Unified memory facade** over 5 backends (episodic, semantic, task, decision, vector)
- **Desktop + Browser + Coding automation** via capability providers
- **Workflow engine** with compensation/rollback/idempotency
- **Governance layer** (RBAC, permissions, safety, audit)

**Core Philosophy:** One canonical owner per responsibility. All transports → One Pipeline → Downstream systems.

---

## 2. CORE SUBSYSTEMS (13 Canonical)

| # | Subsystem | Canonical Location | Reality Score | Status |
|---|-----------|-------------------|---------------|--------|
| 1 | **Startup** | `core/lifespan.py:lifespan()` | 100% | ACTIVE |
| 2 | **Request Pipeline** | `core/pipeline/pipeline.py:process_message()` | 95% | ACTIVE |
| 3 | **Goal Understanding** | `core/pipeline/stages/intent.py:IntentStage` | 90% | ACTIVE |
| 4 | **Planner** | `core/planner/executor.py:PlannerExecutor` | 85% | ACTIVE |
| 5 | **Execution Engine** | `core/tools/executor.py:ToolExecutor` | 90% | ACTIVE |
| 6 | **Workflow Engine** | `core/workflow/engine.py:WorkflowEngine` | 95% | ACTIVE |
| 7 | **Memory System** | `memory/memory_facade.py:MemoryFacade` | 95% | ACTIVE |
| 8 | **Provider System** | `core/providers/router.py:ProviderRouter` | 95% | ACTIVE |
| 9 | **Capability Registry** | `core/capability/registry.py:CapabilityRegistry` | 90% | ACTIVE |
| 10 | **Safety Engine** | `core/desktop/safety.py:SafetyManager` + `core/control/kill_switch.py` | 95% | ACTIVE |
| 11 | **EventBus** | `core/event_bus.py:global_event_bus` | 100% | ACTIVE |
| 12 | **Configuration** | `core/configuration/service.py:ConfigurationService` | 95% | ACTIVE |
| 13 | **Notifications** | `notifications/notifier.py:SupervisorNotifier` | 90% | ACTIVE |

---

## 3. THREE PIPELINES (Canonical Transport Paths)

| Pipeline | Entry Point | Stages | Use Case |
|----------|-------------|--------|----------|
| **Desktop Pipeline** | `core/desktop/controller.py:DesktopController` | Pipeline → DesktopProvider → pyautogui | Mouse, keyboard, window, screen, app launch |
| **Browser Pipeline** | `core/providers/adapters/browser_provider.py:BrowserProvider` | Pipeline → BrowserProvider → Playwright | Navigate, click, type, scroll, extract, evaluate |
| **Coding Pipeline** | `core/providers/adapters/forge.py:ForgeProvider` | Pipeline → ForgeProvider → SubAgent | Code gen, edit, refactor, build, test, scaffold |

All three pipelines share:
- Same 19-stage canonical pipeline (`core/pipeline/pipeline.py`)
- Same `ProviderRouter.select(capability)` for provider selection
- Same `ToolExecutor` for tool execution
- Same `MemoryFacade` for memory
- Same `global_event_bus` for events

---

## 4. WHAT SURVIVES (Canonical Keepers)

### 4.1 Infrastructure (100% Keep)
```
core/lifespan.py                     # Single startup orchestrator (30+ subsystems)
core/pipeline/pipeline.py            # 19-stage canonical pipeline
core/pipeline/adapters/*.py          # 4 transport adapters (REST, WS, Channel, Voice)
core/event_bus.py                    # global_event_bus (tenant-aware, namespace-isolated)
core/configuration/service.py        # ConfigurationService (5-source resolution chain)
memory/memory_facade.py              # MemoryFacade over 5 backends
core/tools/executor.py               # ToolExecutor with lifecycle events
core/providers/router.py             # ProviderRouter (evidence-based, 7-dim scoring)
core/providers/registry.py           # ProviderRegistry (13 providers, persistence)
core/capability/registry.py          # CapabilityRegistry (23 built-in capabilities)
core/desktop/safety.py               # SafetyManager (7 gates + emergency stop)
core/control/kill_switch.py          # Global kill switch
core/workflow/engine.py              # WorkflowEngine (compensation, idempotency)
core/planner/executor.py             # PlannerExecutor (template-based, deterministic)
core/scheduler/scheduler.py          # ActivityScheduler (5 executors → Pipeline)
```

### 4.2 Capability Providers (Keep, Consolidate Internals)
```
core/providers/adapters/desktop_provider.py    # → core/desktop/controller.py
core/providers/adapters/browser_provider.py    # ← merge browser_fsm + browser_planner + browser_tools
core/providers/adapters/forge.py               # Primary coding provider
core/providers/adapters/ollama_provider.py     # Local LLM provider (10 capabilities)
core/providers/adapters/research_provider.py   # Research workflows
core/providers/adapters/automation_provider.py # Workflow automation
notifications/notifier.py                      # SupervisorNotifier
core/project_manager.py                        # ProjectManager + BuildService
```

### 4.3 Governance & Observability (Keep)
```
core/permission/manager.py             # PermissionManager (RBAC + policies)
core/authz/engine.py                   # PolicyEngine (scopes + glob matching)
core/governance/task_router.py         # Governance validation
core/audit_log.py                      # AuditLog (PII redaction, JSONL)
core/observability/logging.py          # Structured logging
core/observability/metrics.py          # Metrics collection
```

---

## 5. WHAT GETS DEPRECATED (Shims → Remove After Migration)

| Module | Replaced By | Migration Target | Evidence |
|--------|-------------|------------------|----------|
| `core/config.py` | `ConfigurationService` | DELETE | Shim with `__getattr__` delegation (Phase 7) |
| `core/config_registry.py` | `ConfigurationService` | DELETE | Delegates to ConfigurationService (Phase 7) |
| `core/config_schema.py` | `ConfigurationService` | DELETE | Pydantic models, delegates (Phase 7) |
| `core/event_bus.py:PluginEventBus` | `global_event_bus` + `namespace="plugin"` | DELETE | Deprecated adapter, routes to global (Phase 5) |
| `core/event_bus.py:get_bus()` | `global_event_bus` | DELETE | Legacy singleton (Phase 5) |
| `core/event_bus.py:emit_event()` | `global_event_bus.publish()` | DELETE | Legacy shim (Phase 5) |
| `core/plugins/automation.py` | `PCAutomationPlugin` + `DesktopProvider` | DELETE | Old plugin interface (Phase 1) |
| `core/llm_calls.py` | `llm_router` + `ProviderRouter` | DELETE | Unused, dead code (Phase 6) |
| `core/llm_core.py` | `llm_router` | DELETE | Legacy, only in deprecated paths (Phase 6) |
| `core/llm_failover.py` | `ProviderRouter` health checks | DELETE | Legacy, only deprecated paths (Phase 6) |

---

## 6. WHAT GETS REMOVED (Dead/Dormant/Duplicate)

| Module | Reason | Evidence |
|--------|--------|----------|
| `core/graph/` (entire directory) | LangGraph fallback only, DORMANT | Used only by `agent_loop.py` fallback + `/api/v1/agent` (Phase 4) |
| `core/agent_loop.py` fallback path | `_disable_pipeline` flag, DRIFT | Pipeline is canonical, fallback counter tracked (Phase 2) |
| `api/agent_routes.py` | Legacy graph endpoint, DORMANT | Uses `build_default_graph()` (Phase 2) |
| `automation/pc_automation.py` | 100% duplicate, DEPRECATED | Header says "Use core/desktop/controller.py" (Phase 1, 4, 6) |
| `automation/routes.py` | Legacy HTTP routes, DUPLICATE | Open Interpreter integration (Phase 4) |
| `brain/UnifiedBrain.py` | Duplicates Intent/Planner/Execution/Memory, DUPLICATE | Methods → Pipeline stages (Phase 1, 4, 6) |
| `core/routing/request_classifier.py` | Legacy pre-pipeline classification, PARTIAL | Pipeline has `IntentStage` (Phase 1) |
| `WorkflowEvent` / `MJEvent` (in `core/workflow/events.py`) | Parallel event hierarchy, LEGACY | Unified `Event` class exists (Phase 5) |
| `core/workflow/calibration.py` | Experimental, LEGACY | Workflow calibration (Phase 1) |
| `core/scheduler/pipeline_executor.py` | Pipeline-specific executor, LEGACY | Scheduler executors delegate to Pipeline (Phase 1) |

---

## 7. WHAT BECOMES CANONICAL (Consolidation Targets)

| Responsibility | Current Fragmented State | Canonical Target | Action |
|----------------|-------------------------|------------------|--------|
| **Browser** | `browser_tools.py` (37K) + `browser_fsm.py` + `browser_planner.py` (67K) | `core/providers/adapters/browser_provider.py` | Merge 3 files into provider adapter |
| **Coding** | `core/coding/` (9 modules) + `core/tools/implementations.py` (58K) + `cookbook_tools.py` (67K) + `build_tools.py` | `core/coding/` | Move all tools into `core/coding/` |
| **Desktop** | `DesktopController` + `SafetyManager` (separate files) | `core/desktop/controller.py` | Merge safety as internal concern |
| **Schedulers** | `core/cron.py:scheduler` + `core/scheduler/scheduler.py:Scheduler` | Single `Scheduler` with cron mode | Remove `core/cron.py` |
| **Event Systems** | `Event` + `WorkflowEvent` + `MJEvent` | Single `Event` class | Delete `WorkflowEvent`, `MJEvent` |
| **Voice Providers** | STT/TTS in `assistant/providers/` not registered | Register with `ProviderRegistry` | Add provider adapters |
| **Model Routing** | Hardcoded in 9+ locations | Data-driven via `ProviderRouter` + capability metadata | Remove all hardcoded model names |

---

## 8. REALITY SCORES (Evidence-Based)

| Subsystem | Score | Key Evidence |
|-----------|-------|--------------|
| **Startup** | 100% | Single lifespan, 30+ subsystems initialized in order (Phase 1) |
| **Pipeline** | 95% | 19 stages, 11 transports delegate, legacy fallback exists (Phase 2) |
| **Goal Understanding** | 90% | `IntentStage` canonical, `UnifiedBrain` duplicates (Phase 1) |
| **Planner** | 85% | `PlannerExecutor` canonical, `UnifiedBrain.plan_goal()` duplicates (Phase 1) |
| **Execution** | 90% | `ToolExecutor` canonical, legacy executors exist (Phase 4) |
| **Workflow** | 95% | `WorkflowEngine` canonical, compensation + idempotency (Phase 4) |
| **Memory** | 95% | Facade over 5 backends, tiered + mem0 + embeddings (Phase 6) |
| **Providers** | 95% | Router + Registry clear, evidence-based selection (Phase 7) |
| **Capabilities** | 90% | Registry + Graph + Composition + Pipeline stage (Phase 3) |
| **Safety** | 95% | SafetyManager (7 gates) + KillSwitch + permissions (Phase 8) |
| **EventBus** | 100% | Single canonical bus, tenant-aware, namespace isolation (Phase 5) |
| **Configuration** | 95% | Service canonical, 5-source chain, 9 hardcoded violations (Phase 7) |
| **Notifications** | 90% | SupervisorNotifier, 4 channels, wired in lifespan (Phase 1) |
| **Desktop** | 95% | Controller + SafetyManager, pyautogui + rate limits (Phase 1) |
| **Browser** | 90% | Provider canonical, internal tools fragmented (Phase 3) |
| **Coding** | 85% | Forge primary, Ollama fallback, capability naming inconsistent (Phase 3) |
| **Research** | 95% | Provider canonical, planner + retriever + synthesizer (Phase 3) |
| **Permissions** | 85% | Manager + RBAC + Pipeline stage (Phase 1) |
| **Recovery** | 85% | Workflow + Self-healing + Orphan (Phase 1) |
| **Plugins** | 95% | Loader + Registry + Manifests + hooks (Phase 1) |
| **Voice** | 90% | VoiceLoop canonical, providers not in registry (Phase 1) |
| **Automation** | 85% | PCAutomation + Plugin + Desktop split (Phase 1) |
| **History** | 70% | HistoryService + ActivityManager split (Phase 1) |
| **Projects** | 90% | ProjectManager + BuildService (Phase 1) |
| **Rules/Governance** | 75% | Split across task_router, work_queue, resource_monitor (Phase 1) |

---

## 9. MIGRATION ORDER (Priority Sequence)

### Phase 0: Immediate Cleanup (Week 1)
```
1. DELETE core/graph/                    # 60KB dead LangGraph code
2. DELETE core/agent_loop.py fallback    # _disable_pipeline flag
3. DELETE api/agent_routes.py            # Legacy graph endpoint
4. DELETE core/llm_calls.py              # Dead, no imports
5. DELETE core/llm_core.py               # Legacy
6. DELETE core/llm_failover.py           # Legacy
7. DELETE automation/pc_automation.py    # Deprecated, header says so
8. DELETE automation/routes.py           # Duplicate HTTP routes
9. DELETE core/plugins/automation.py     # Legacy plugin interface
```

### Phase 1: Event System Unification (Week 2)
```
10. DELETE WorkflowEvent / MJEvent classes      # core/workflow/events.py
11. DELETE PluginEventBus, get_bus(), emit_event()  # core/event_bus.py
12. MIGRATE InboxStore → global_event_bus       # Uses legacy get_bus()
13. MIGRATE ActivityRecorder → Event class      # Uses WorkflowEvent
```

### Phase 2: Configuration Consolidation (Week 2)
```
14. DELETE core/config.py              # Shim
15. DELETE core/config_registry.py     # Shim
16. DELETE core/config_schema.py       # Pydantic shim
17. MOVE hardcoded model mappings → config data (9 locations, Phase 7)
```

### Phase 3: Browser Consolidation (Week 3)
```
18. MERGE browser_tools.py + browser_fsm.py + browser_planner.py 
    → core/providers/adapters/browser_provider.py
19. UPDATE BrowserProvider to use consolidated internals
```

### Phase 4: Coding Consolidation (Week 3)
```
20. MOVE core/tools/implementations.py → core/coding/
21. MOVE core/tools/cookbook_tools.py → core/coding/
22. MOVE core/tools/build_tools.py → core/coding/
23. CONSOLIDATE capability names: code/coding/codegen → coding
```

### Phase 5: Desktop + Safety Merge (Week 3)
```
24. MERGE core/desktop/safety.py into core/desktop/controller.py
    SafetyManager becomes internal class
```

### Phase 6: Scheduler Unification (Week 4)
```
25. MERGE core/cron.py:scheduler into core/scheduler/scheduler.py
    Add cron mode to Scheduler class
26. DELETE core/cron.py
```

### Phase 7: Provider Registry Completion (Week 4)
```
27. REGISTER STT/TTS providers with ProviderRegistry
28. CREATE VisionProvider adapter (currently only Ollama)
29. REGISTER VoiceLoop as capability provider
```

### Phase 8: Brain Migration (Week 5)
```
30. MIGRATE UnifiedBrain.reason() → ReasoningStage (pipeline)
31. MIGRATE UnifiedBrain.plan_goal() → PlannerStage (pipeline)
32. MIGRATE UnifiedBrain.executor → ExecutionStage (pipeline)
33. MIGRATE UnifiedBrain.memory → MemoryStage (pipeline)
34. DELETE brain/UnifiedBrain.py
```

---

## 10. TECHNICAL DEBT (Evidence-Based)

| Category | Debt Item | Location | Severity |
|----------|-----------|----------|----------|
| **Hardcoded Models** | 9 locations with hardcoded model names | `config/service.py:431`, `ollama_provider.py:40`, `forge.py:48`, `llm_router.py`, `hybrid_models.py` | CRITICAL |
| **Silent Failures** | `is_public_blocked_tool()` returns False on exception | `core/tools/security.py:86-87` | HIGH |
| **Silent Failures** | `_tool_path_roots()` exceptions caught at DEBUG only | `core/tools/execution/security.py:58-59` | HIGH |
| **Silent Failures** | `MemoryStage` sync call in async context | `core/pipeline/stages/memory.py:67` | MEDIUM |
| **TOCTOU** | Path check → file operation race | `core/tools/execution/security.py:64-67` | HIGH |
| **TOCTOU** | DNS checked at validation, not fetch time | `core/ssrf.py:202` | MEDIUM |
| **Blocking Call** | `_check_redirect_chain()` uses sync httpx in async | `core/ssrf.py:204` | MEDIUM |
| **No Timeout** | `wait_for_approval()` blocks indefinitely | `core/tools/execution/authorization.py:49` | HIGH |
| **No Fallback** | MCP approval no fallback if server down | `core/tools/execution/authorization.py:57` | HIGH |
| **Duplicate Event Systems** | `WorkflowEvent` + `Event` parallel hierarchies | `core/workflow/events.py` + `core/event_bus.py` | HIGH |
| **Legacy Config Shims** | 3 shim files delegating to ConfigurationService | `core/config.py`, `config_registry.py`, `config_schema.py` | MEDIUM |
| **Fragmented Browser** | 3 files (170K lines) for one capability | `browser_tools.py`, `browser_fsm.py`, `browser_planner.py` | MEDIUM |
| **Fragmented Coding** | Tools split across coding/ + tools/ | `core/coding/` + `implementations.py` + `cookbook_tools.py` | MEDIUM |
| **Missing Capabilities** | 15+ missing (forensics, backup, monitoring, etc.) | Phase 3 audit | MEDIUM |
| **Windows Gaps** | No UNC/junction handling, no PowerShell patterns | `core/tools/execution/security.py`, `routing/safety.py` | MEDIUM |
| **Plaintext Secrets** | API keys stored unencrypted | `core/api_key_vault.py:261` | HIGH |
| **Arbitrary JS** | `browser_evaluate` allows any JS execution | `core/tools/browser_tools.py:525` | CRITICAL |
| **No App Allowlist** | `launch_app()` uses `shutil.which()` only | `core/desktop/controller.py:248` | MEDIUM |
| **Fake Async** | `await asyncio.sleep(0.1)` polling hacks | `core/history/service.py:71,127` | LOW |

---

## 11. RISKS

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Pipeline fallback re-enabled** | Medium | High | Remove `_disable_pipeline` flag, delete `core/graph/` |
| **Hardcoded models break provider routing** | High | High | Phase 2 migration — data-driven routing |
| **Silent auth failures allow dangerous tools** | Medium | Critical | Fix `is_public_blocked_tool()` exception handling |
| **Browser evaluate RCE** | Low | Critical | Sandbox, CSP, or remove `browser_evaluate` |
| **SSRF bypass via DNS rebinding** | Low | High | Validate at fetch time, not check time |
| **Secrets leakage** | Medium | High | Encrypt `api_keys.json`, use key derivation |
| **Windows path bypass** | Medium | Medium | Add UNC/junction handling, case-insensitive roots |
| **Event system split causes missed events** | High | Medium | Phase 1 unification — single Event class |
| **Scheduler overlap causes double execution** | Medium | Medium | Phase 6 unification — single Scheduler |
| **Legacy config shims cause inconsistency** | High | Low | Phase 2 deletion — single ConfigurationService |
| **Memory sync calls block pipeline** | Medium | Low | Make `MemoryFacade` fully async |
| **Brain methods called directly bypassing pipeline** | Medium | Medium | Phase 8 migration — delete UnifiedBrain |

---

## 12. FUTURE ROADMAP (Post-Canonical)

### Q3 2026: Canonical Completion
- [ ] All Phase 0-8 migrations complete
- [ ] Single pipeline, single event bus, single config, single memory
- [ ] All hardcoded models removed
- [ ] Browser/coding/desktop consolidated

### Q4 2026: Capability Expansion
- [ ] **Forensics Provider** (disk, memory, network analysis)
- [ ] **Backup/Restore Capability** (encrypted, incremental)
- [ ] **Monitoring/Alerting Provider** (Prometheus/Grafana integration)
- [ ] **Tracing/Profiling Capability** (OpenTelemetry)
- [ ] **Packaging/Distribution Provider** (Docker, PyPI, npm)
- [ ] **Containerization Provider** (K8s, Docker Compose)
- [ ] **Secrets/Key Management Provider** (Vault, AWS KMS, HSM)
- [ ] **Compliance/Audit Capability** (SOC2, GDPR reports)

### Q1 2027: Platform Hardening
- [ ] **Sandboxed Browser** (Firecracker/gVisor for `browser_evaluate`)
- [ ] **Windows Parity** (full desktop automation support)
- [ ] **Multi-tenant Isolation** (hardened tenant boundaries)
- [ ] **Plugin Marketplace** (signed, verified, sandboxed plugins)
- [ ] **Federated Providers** (multi-cluster provider registry)

### Q2 2027: Intelligence Layer
- [ ] **Constitutional AI** (self-correction via quality grader)
- [ ] **Prompt Optimization** (automatic few-shot selection)
- [ ] **Reasoning Engine** (neuro-symbolic, formal verification)
- [ ] **Autonomous Scheduling** (predictive, goal-driven)

---

## 13. CANONICAL ARCHITECTURE DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              TRANSPORT LAYER                                    │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌────┐ │
│  │REST │ │ WS  │ │CLI  │ │Voice│ │TUI  │ │Disc │ │Slack│ │Tele │ │Matr │ │IRC │ │
│  └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬─┘ │
└─────┼───────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼────┼─────────────┘
      ▼       ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        TRANSPORT ADAPTERS (normalize → Request)                 │
│  rest_adapter  │  ws_adapter  │  channel_adapter  │  voice_adapter  │ cli_adapter│
└────────────────┬───────────────┬───────────────────┬─────────────────┬───────────┘
                 ▼               ▼                   ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    CANONICAL PIPELINE (19 Stages — ADR-006)                     │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ RECEIVE → LOAD_CTX → AUTH → TENANT → AUTHZ → RESOURCE → RATE_LIMIT      │   │
│  │ → INTENT → CTX_RETRIEVAL → KNOWLEDGE → REASONING → PLANNER             │   │
│  │ → PLAN_VALIDATOR → CAPABILITY_SELECT → EXECUTION → VERIFICATION        │   │
│  │ → EPISTEMIC → REFLECTION → LEARNING → POLICY_OPT → MEMORY              │   │
│  │ → NOTIFICATION → METRICS → EXPLAINABILITY → FORMATTER                   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│   EVENTBUS       │       │   WEBSOCKET      │       │   MEMORY         │
│   (global)       │       │   (streaming)    │       │   FACADE         │
│                  │       │                  │       │                  │
│  - Pattern sub   │       │  - stage_start   │       │  - Episodic      │
│  - Priority      │       │  - stage_end     │       │  - Semantic      │
│  - Namespace     │       │  - stream_token  │       │  - Task          │
│  - Tenant filter │       │  - pipeline_end  │       │  - Decision      │
│  - History (100) │       │  - pipeline_err  │       │  - Vector        │
└────────┬─────────┘       └────────┬─────────┘       └────────┬─────────┘
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DOWNSTREAM SYSTEMS                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ PROVIDER     │  │ CAPABILITY   │  │ WORKFLOW     │  │ SCHEDULER    │        │
│  │ ROUTER       │  │ REGISTRY     │  │ ENGINE       │  │ (5 executors)│        │
│  │              │  │              │  │              │  │              │        │
│  │ 13 providers │  │ 23 caps      │  │ Compensation │  │ → Pipeline   │        │
│  │ Evidence     │  │ Graph/Comp   │  │ Idempotency  │  │              │        │
│  │ scoring      │  │ Pipeline     │  │ Recovery     │  │              │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│         │                 │                 │                 │                │
│         ▼                 ▼                 ▼                 ▼                │
│  ┌────────────────────────────────────────────────────────────────────────┐    │
│  │                        CAPABILITY PROVIDERS                             │    │
│  │  DesktopProvider  │  BrowserProvider  │  ForgeProvider  │  Research... │    │
│  │  (pyautogui)      │  (Playwright)     │  (SubAgent)     │  (Planner)   │    │
│  └────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            UI / OUTPUT LAYER                                    │
│  Web  │  TUI  │  CLI  │  Voice  │  Discord  │  Slack  │  Telegram  │  Channels │
└───────┴───────┴───────┴─────────┴───────────┴─────────┴────────────┴───────────┘
```

---

## 14. CONSTITUTIONAL RULES (Enforced)

1. **ONE PIPELINE** — All request processing goes through 19-stage pipeline
2. **ONE EVENTBUS** — `global_event_bus` is the only event system
3. **ONE CONFIG** — `ConfigurationService` is the only config source
4. **ONE MEMORY** — `MemoryFacade` is the only memory interface
5. **ONE PLANNER** — `PlannerExecutor` is the only planner
6. **ONE EXECUTOR** — `ToolExecutor` wraps all tool calls
7. **ONE SAFETY** — `SafetyManager` + `KillSwitch` are the only guards
8. **ONE PROVIDER ROUTER** — `ProviderRouter` selects all providers
9. **ONE CAPABILITY REGISTRY** — All capabilities registered here
10. **NO SHELL WITHOUT ALLOWLIST** — `bash`/`python` tools require explicit allowlist
11. **NO SILENT FAILURES** — Every error must raise or return structured error
12. **AUDIT EVERYTHING** — Every decision, execution, config change logged
13. **TENANT ISOLATION** — Every request carries `resource_scope.tenant_id`
14. **PLUGIN HOOKS ONLY** — Extensions via `Pipeline.hooks` + `EventBus`
15. **VERSIONED ARCHITECTURE** — `Pipeline.version` incremented on breaking changes

---

## 15. FILE EVIDENCE INDEX

| Doc | Key Files Referenced |
|-----|---------------------|
| Phase 1 | `core/lifespan.py`, `core/pipeline/pipeline.py`, `core/pipeline/stages/intent.py`, `core/planner/executor.py`, `core/tools/executor.py`, `core/workflow/engine.py`, `core/scheduler/scheduler.py`, `core/desktop/controller.py`, `core/tools/browser_tools.py`, `core/coding/`, `core/research/`, `memory/memory_facade.py`, `notifications/notifier.py`, `core/configuration/service.py`, `core/providers/router.py`, `core/capability/registry.py`, `core/desktop/safety.py`, `core/permission/manager.py`, `core/event_bus.py`, `core/history/service.py`, `core/project_manager.py`, `core/governance/` |
| Phase 2 | `core/pipeline/adapters/*.py`, `core/routes/chat/`, `channels/processor.py`, `mcp/server.py`, `core/agent_loop.py`, `core/graph/`, `api/agent_routes.py` |
| Phase 3 | `core/providers/adapters/*.py`, `core/capability/registry.py`, `core/capability/graph.py`, `core/providers/bootstrap.py` |
| Phase 4 | `core/pipeline/pipeline.py`, `core/graph/`, `core/workflow/engine.py`, `core/scheduler/scheduler.py`, `automation/pc_automation.py`, `core/tools/executor.py`, `brain/executor.py` |
| Phase 5 | `core/event_bus.py`, `core/workflow/events.py`, `core/pipeline/context.py`, `notifications/notifier.py`, `core/history/service.py`, `core/inbox/store.py` |
| Phase 6 | `memory/memory_facade.py`, `memory/tiered_memory.py`, `memory/*_store.py`, `core/scheduler/scheduler.py`, `core/cron.py`, `core/workflow/engine.py`, `brain/automation/loop.py`, `core/activity/resume.py` |
| Phase 7 | `core/configuration/service.py`, `core/config.py`, `core/providers/registry.py`, `core/providers/router.py`, `core/capability/registry.py`, `core/providers/adapters/*.py` |
| Phase 8 | `core/tools/security.py`, `core/tools/execution/authorization.py`, `core/tools/execution/security.py`, `core/routing/safety.py`, `core/desktop/safety.py`, `core/desktop/controller.py`, `core/tools/browser_tools.py`, `core/ssrf.py`, `core/api_key_vault.py`, `core/prompt_security.py`, `governance/*.py` |

---

**End of Canonical Architecture Document**

*This document synthesizes 8 READ ONLY audits (~165KB total). All findings backed by file/function evidence. No implementation, no refactoring, no code modifications — only reality documentation and target definition.*