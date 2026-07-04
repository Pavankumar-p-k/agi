# SOURCE OF TRUTH — JARVIS System Constitution

> **File:** `docs/architecture/01_SOURCE_OF_TRUTH.md`
> **Date:** 2026-07-04 (updated after Phase 2 consolidation — 7 steps complete)
> **Purpose:** Canonical owner and reality score for every architectural responsibility in the JARVIS system.
> **Rule:** READ ONLY — this document describes what IS, not what SHOULD BE. All evidence is file paths and line numbers.

---

## Responsibility Area Inventory

| # | Area | Canonical Owner | Score | Status |
|---|------|-----------------|-------|--------|
| 1 | Startup & Lifespan | `core/main.py` + `core/lifespan.py` | 10/10 | CLEAN |
| 2 | Request Processing | `core/graph/` (StateGraph + nodes) | 8/10 | ACTIVE |
| 3 | Goal Understanding | `brain/planner/planner.py` | 6/10 | FRAGMENTED |
| 4 | Planning | `brain/planner/` | 7/10 | ACTIVE |
| 5 | Execution | `core/tools/execution.py` | 8/10 | ACTIVE |
| 6 | Workflow | `core/workflow/engine.py` | 9/10 | CLEAN |
| 7 | Scheduler | `core/scheduler/scheduler.py` | 8/10 | ACTIVE |
| 8 | Desktop Control | `core/desktop/` | 7/10 | PARTIAL |
| 9 | Browser Automation | `core/browser_manager.py` | 8/10 | ACTIVE |
| 10 | Coding | `core/codebase_indexer.py` + `core/providers/adapters/` | 7/10 | ACTIVE |
| 11 | Research | `core/research/` | 9/10 | CLEAN |
| 12 | Memory | `brain/memory/memory_manager.py` | 5/10 | PARTIAL |
| 13 | Notifications | `notifications/notifier.py` + `monitors/alerts.py` + `channels/` | 7/10 | SPRAWL |
| 14 | Configuration | `core/configuration/service.py` | 8/10 | UNIFIED |
| 15 | Providers (LLM/Model) | `core/llm_router.py` + `core/providers/manager.py` | 6/10 | PARTIAL |
| 16 | Capabilities | `core/capability/` + `core/tools/policy.py` | 6/10 | PARTIAL |
| 17 | Safety & Permissions | `governance/GovernanceValidator.py` + `core/auth.py` | 7/10 | ACTIVE |
| 18 | Logging & Observability | `core/observability/logging.py` + `core/observability/metrics.py` | 8/10 | ACTIVE |
| 19 | Recovery & Fault Tolerance | `core/self_healing.py` + `core/workflow/recovery.py` | 8/10 | ACTIVE |
| 20 | Plugin System | `core/plugins/` | 7/10 | ACTIVE |
| 21 | Voice | `assistant/voice_pipeline.py` | 9/10 | CLEAN |
| 22 | Automation (Autonomous Build) | `brain/automation/loop.py` | 8/10 | ACTIVE |
| 23 | EventBus | `brain/events/event_bus.py` | 9/10 | UNIFIED |
| 24 | History | `core/database.py` (ChatHistory) | 6/10 | PARTIAL |
| 25 | Projects | `core/project_manager.py` | 8/10 | ACTIVE |
| 26 | Rules & Governance | `governance/` | 6/10 | SPRAWL |
| 27 | Cron / Periodic Tasks | `core/cron.py` | 8/10 | ACTIVE |

---

## 1. Startup & Lifespan

**Canonical Owner:** `core/main.py` + `core/lifespan.py`
**Score:** 10/10 — Single, clear startup pathway. All phases documented.

### Entry Points

| Entry Point | File | Line | Type |
|-------------|------|------|------|
| CLI | `jarvis.py` | 1 | Root argparse entry (290 lines) |
| Server (FastAPI) | `core/main.py` | 1 | FastAPI app creation (400 lines) |
| Lifespan Manager | `core/lifespan.py` | 1 | Async startup/shutdown (907 lines) |
| Daemon (Windows svc) | `daemon/jarvis_service.py` | 1 | Windows service wrapper (250 lines) |

### Startup Phases (in `core/lifespan.py`)

| Phase | Line | Action |
|-------|------|--------|
| 1 | 39-47 | Warm up LLM router (pre-warm LiteLLM) |
| 2 | 62-80 | Migrate legacy settings (`_migrate_legacy_settings_once`) |
| 3 | 108-112 | Deferred import research routes |
| 4 | 140-141 | Wire `SupervisorNotifier` to supervisor |
| 5 | 171-175 | Load call-sync routes (deferred) |
| 6 | 220-228 | Start orphan subagent recovery |
| 7 | 244-280 | Start reminder manager (TTS injected) |
| 8 | 283-317 | Start consolidated monitoring (`ServiceHealthChecker`, `ResourceMonitor`, fallback `health_monitor`) |
| 9 | 319-331 | Start LLM failover `CooldownProbe` (if enabled) |
| 10 | 423-433 | Warm up `ReasoningEngine` (background) |
| 11 | 436-442 | Start `VoiceLoop` (wake word + voice) |
| 12 | 467-473 | Attach `self_healing` + `learning_loop` to `app.state` |
| 13 | 509-513 | Start `project_manager.process_queue()` |
| 14 | 536-539 | Register `PCAutomationPlugin` |
| 15 | 566-571 | Bootstrap providers (`bootstrap_providers()`) |
| 16 | 590 | Load skills library |
| 17 | 613-619 | Start `work_queue` |
| 18 | 622-628 | Init `AuditLog` |
| 19 | 632-635 | Log `PolicyEngine` import |
| 20 | 639-643 | Load RBAC roles from `config/roles.yaml` |
| 21 | 645-669 | Register and start multi-channel plugins (Discord, Slack, Telegram, Matrix, IRC, Email) |
| 22 | 676-690 | Start MCP server (background) |
| 23 | 700-708 | Start cron scheduler (`core.cron.scheduler`) |
| 24 | 710-737 | Start activity scheduler (`core.scheduler.Scheduler`) |
| 25 | 741-747 | Attach `BackupManager` |
| 26 | 760-766 | Load all skills (`skills.manager.load_all()`) |
| 27 | 780-793 | Legacy `proactive_monitor` fallback |
| 28 | 796-827 | Workflow engine + heartbeat + recovery |
| 29 | 880-906 | Shutdown: stop scheduler, cron, workflow engine, flush audit log |

---

## 2. Request Processing

**Canonical Owner:** `core/graph/` — `StateGraph` + agent node pipeline
**Score:** 8/10 — Clean graph-based pipeline but partially bypassed by legacy paths.

### Core Files

| File | Lines | Role |
|------|-------|------|
| `core/graph/graph.py` | 88 | `StateGraph` — lightweight state machine with SSE event streaming |
| `core/graph/state.py` | 203 | `AgentState`, `RoundState`, `AgentPhase` — runtime state for agent graph |
| `core/graph/edges.py` | 47 | `route_decision()` — conditional edge routing by AgentPhase |
| `core/graph/nodes.py` | 1193+ | Node implementations: setup, think, route, tool_call, pause, resume, verify, finish |
| `core/graph/__init__.py` | 93 | `build_default_graph()` — constructs the full agent execution graph |

### Processing Flow

```
setup_node → think_node → route_node → (plan → tool_call_node | pause_node | finish_node) → verify_node → cycle
```

### Bypass Paths

| Bypass | File | Line | How |
|--------|------|------|-----|
| Direct tool dispatch | `core/tools/execution.py` | 1 | Routes tool blocks to MCP or native handlers — bypasses state graph |
| CLI direct handler | `jarvis.py` | 1 | Argparse → handler without graph |
| Daemon loop | `daemon/jarvis_service.py` | ~100 | Direct heartbeat/build cycle without graph |

---

## 3. Goal Understanding

**Canonical Owner:** `brain/planner/planner.py`
**Score:** 6/10 — FRAGMENTED between brain planner, goal manager, and requirement tracker.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `brain/planner/planner.py` | 66 | `Planner` — breaks goals into DAG task graphs | ACTIVE |
| `brain/goals/goal_manager.py` | ~200 | `GoalManager` — persistent goal CRUD, status, priority queue | ACTIVE |
| `brain/goals/goal.py` | ~80 | `Goal` dataclass, `GoalStatus` enum | ACTIVE |
| `brain/automation/loop.py` | 2679 | `RequirementTracker` — parses goals into requirements (inner class) | ACTIVE |
| `brain/cognitive_patterns.py` | ~200 | 10 cognitive strategies for goal decomposition | ACTIVE |

### Duplications

- Goals are parsed/created in at least 3 places: `goal_manager.py`, `AutomationLoop._plan_evolution()`, `brain/UnifiedBrain.py`
- Requirement tracking exists in `AutomationLoop` but not exposed to `Planner` or `GoalManager`

---

## 4. Planning

**Canonical Owner:** `brain/planner/`
**Score:** 7/10 — Clear DAG-based planner but mixed with cognitive strategies.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `brain/planner/planner.py` | 66 | `Planner.plan()` + `replan()` — fixed generic plan structure | ACTIVE |
| `brain/planner/task_graph.py` | 269 | `TaskGraph` — DAG with Kahn sort, cycle detection, critical path | ACTIVE |
| `brain/planner/__init__.py` | 8 | Exports `TaskGraph`, `TaskNode`, `Planner` | ACTIVE |
| `brain/reasoning_engine.py` | 214 | `ReasoningEngine` — CoT LLM reasoning with `<think>/<answer>` | ACTIVE |
| `brain/task_resolver.py` | 321 | `TaskResolver` — plan nodes → executable tool calls | ACTIVE |
| `brain/UnifiedBrain.py` | 543 | Composes all brain subsystems | ACTIVE |
| `brain/automation/loop.py` | 2679 | Autonomous build loop with integrated planning | ACTIVE |

### Notes

- `Planner` uses a fixed generic plan because "LLM is unreliable for structured JSON output" (line comment)
- `TaskResolver` bridges plan nodes to tool calls via LLM
- `UnifiedBrain` is the cognitive composition root but only indirectly wired into lifespan

---

## 5. Execution

**Canonical Owner:** `core/tools/execution.py`
**Score:** 8/10 — Central dispatcher for ~70+ tools, dual routing (MCP + native).

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/tools/execution.py` | 2373+ | Central tool dispatcher: `execute_tool_block()` + subprocess/sandbox execution | ACTIVE |
| `core/action_engine.py` | 148 | `ActionEngine` — bridges LLM reasoning to tool execution | ACTIVE |
| `core/tools/implementations.py` | ~500 | Native implementations of all tool functions | ACTIVE |
| `brain/executor/executor.py` | 187 | `Executor` — brain's unified action executor | ACTIVE |
| `brain/executor/verifier.py` | 145 | `Verifier` — action result verification via LLM | ACTIVE |
| `core/tools/workflow_tools.py` | 175 | Bridges workflow engine ↔ tool dispatch | ACTIVE |

### Tool Count (~70+)

Tools defined in `core/tools/browser_tools.py`, `implementations.py`, `build_tools.py`, `scheduler_tools.py`, `settings_tools.py`, `document_tools.py`, `skill_tools.py`, `email_tools.py`, model_serving, etc.

### Routing

```
execute_tool_block() → ActionEngine (if core tool) or handler map (if registered)
                     → MCP server (if agent tool) or subprocess (if bash)
```

---

## 6. Workflow

**Canonical Owner:** `core/workflow/engine.py`
**Score:** 9/10 — Clean saga-pattern workflow engine with full persistence and recovery.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/workflow/engine.py` | 606 | `WorkflowEngine` — create, run, pause, resume, cancel, compensate | ACTIVE |
| `core/workflow/storage.py` | 487 | `WorkflowStore` — SQLite persistence (5 tables, migrations) | ACTIVE |
| `core/workflow/models.py` | ~120 | Dataclass models for workflow instances, steps | ACTIVE |
| `core/workflow/recovery.py` | 77 | `recover_active_workflows()` — crash recovery | ACTIVE |
| `core/workflow/heartbeat_monitor.py` | 63 | `HeartbeatMonitor` — stale workflow detection | ACTIVE |
| `core/workflow/context.py` | ~120 | `ExecutionContext` — per-workflow variables and artifacts | ACTIVE |
| `core/workflow/artifact_store.py` | ~100 | `ArtifactStore` — workflow output registration | ACTIVE |
| `core/workflow/events.py` | ~100 | Workflow event types and constants | ACTIVE |
| `core/workflow/graph.py` | 207 | `ExecutionGraph` — domain model for goal execution tracking | ACTIVE |
| `core/workflow/recorder.py` | ~100 | Outcome recording for analytics | ACTIVE |
| `core/workflow/tracker.py` | ~100 | `ExecutionTracker` with `FocusMode` | ACTIVE |
| `core/workflow/calibration.py` | ~50 | Calibration utilities | ACTIVE |
| `core/workflow/learning_store.py` | ~100 | Learning data store | ACTIVE |
| `core/workflow/learning_models.py` | ~50 | Learning models | ACTIVE |
| `core/workflow/long_horizon_fsm.py` | ~100 | Long-horizon FSM for lifecycle | ACTIVE |
| `core/workflow/__init__.py` | 44 | Package exports | ACTIVE |
| **Total:** | **16 files** | | |

### Production Wiring

- Wired into `core/lifespan.py` lines 796-827: engine creation, heartbeat start, recovery
- Bridge to tools: `core/tools/workflow_tools.py`

---

## 7. Scheduler

**Canonical Owner:** `core/scheduler/scheduler.py`
**Score:** 8/10 — 16-file package plus cron scheduler, one legacy shim.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/scheduler/scheduler.py` | — | `Scheduler` — persistent async activity loop (5s tick, worker pool) | ACTIVE |
| `core/scheduler/queue.py` | — | `SchedulerQueue` — dependency-aware persistent queue | ACTIVE |
| `core/scheduler/store.py` | — | `SchedulerStore` — SQLite persistence (`data/workflow.db`) | ACTIVE |
| `core/scheduler/registry.py` | — | `SchedulerRegistry` — maps node_type → executor | ACTIVE |
| `core/scheduler/executors.py` | — | 7 executor adapters (research, build, repair, email, benchmark, etc.) | ACTIVE |
| `core/scheduler/models.py` | — | `ScheduledActivity`, `ScheduleModel` dataclasses | ACTIVE |
| `core/scheduler/policies.py` | — | Priority scoring policies | ACTIVE |
| `core/scheduler/intelligence.py` | — | Activity intelligence, prediction, resource estimation | ACTIVE |
| `core/scheduler/decision.py` | — | `DecisionEngine` — opportunity/tradeoff analysis | ACTIVE |
| `core/scheduler/autonomous.py` | — | `AutonomousScheduler` — opportunity → activity bridge | EXPERIMENTAL |
| `core/scheduler/chain.py` | — | `ChainManager` — lightweight chain grouping | ACTIVE |
| `core/scheduler/resources.py` | — | Resource estimation/calibration | ACTIVE |
| `core/scheduler/worker.py` | — | `SchedulerWorker` — connects to ResumeEngine + PlannerStateMachine | ACTIVE |
| `core/scheduler/metrics.py` | — | Tick telemetry | ACTIVE |
| `core/cron.py` | — | Cron scheduler (interval + cron expr) | ACTIVE |
| `core/task_scheduler.py` | — | `compute_next_run()` — legacy utility | LEGACY |

### Production Wiring

- `core/lifespan.py` lines 700-708: cron `scheduler.start()`
- `core/lifespan.py` lines 710-737: activity scheduler start
- `core/lifespan.py` lines 880-885: both stopped on shutdown
- REST API: `core/main.py` line 477: `scheduler_router`
- Tools: `core/tools/scheduler_tools.py` (global `_scheduler` set by lifespan)

---

## 8. Desktop Control

**Canonical Owner:** `core/desktop/` (6 files)
**Score:** 7/10 — PARTIAL: `core/desktop/` has `open_url()` + `launch_app()`, `action_engine.py` redirected to `DesktopController`. Legacy `automation/pc_automation.py` and `pc_agent/` emit deprecation warnings.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/desktop/controller.py` | 220 | `DesktopController` — mouse/keyboard + app launch + URL open | ACTIVE |
| `core/desktop/window.py` | 109 | `WindowController` — window ops via pygetwindow | ACTIVE |
| `core/desktop/screen.py` | 152 | `ScreenCapture` — screenshot via mss + PIL | ACTIVE |
| `core/desktop/safety.py` | 299 | `SafetyManager` — emergency stop, rate limits, forbidden regions | ACTIVE |
| `core/desktop/replay.py` | 64 | `ReplayGraph` — DAG action recording | ACTIVE |
| `core/providers/adapters/desktop_provider.py` | 169 | `DesktopProvider` — wraps desktop as ExecutionProvider | ACTIVE |
| `automation/pc_automation.py` | 657 | Legacy NL-driven PC control — DEPRECATED | LEGACY |
| `automation/routes.py` | 203 | REST API for legacy automation — DEPRECATED | LEGACY |
| `pc_agent/computer_agent.py` | 199 | Sandboxed PC control with governance — DEPRECATED | EXPERIMENTAL |
| `pc_agent/snapshot.py` | 135 | Filesystem + registry snapshot/rollback — DEPRECATED | EXPERIMENTAL |
| `pc_agent/playbooks.py` | 339 | Pre-built step sequences — DEPRECATED | EXPERIMENTAL |
| `plugins/pc_automation_plugin.py` | 86 | Plugin wrapper around ComputerAgent | ACTIVE |

### Production Wiring

- `core/desktop/` providers registered via `bootstrap_providers()` in lifespan
- `PCAutomationPlugin` registered directly in lifespan (line 536-539)
- `action_engine.py` uses `DesktopController.open_url()` / `.launch_app()` instead of `automation.pc_automation`

---

## 9. Browser Automation

**Canonical Owner:** `core/browser_manager.py`
**Score:** 8/10 — Single Playwright-based driver, clean tool layer, FSM planner, research integration.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/browser_manager.py` | 387 | `BrowserManager` — Playwright Chromium singleton, sessions, tabs, stealth | ACTIVE |
| `core/tools/browser_tools.py` | 741 | 20+ browser tool functions | ACTIVE |
| `core/tools/browser_planner.py` | 1608 | `BrowserPlanner` — deterministic planning, intent routing, FSM | ACTIVE |
| `core/tools/browser_fsm.py` | 454 | `BrowserFSM` — execution state machine (8 states) | ACTIVE |
| `core/tools/browser_research.py` | 352 | Multi-page research orchestration → FactStore | ACTIVE |
| `core/tools/schemas_browser.py` | 304 | JSON function-calling schemas for all browser tools | ACTIVE |
| `core/agents/browser_agent.py` | 40 | Minimal browser sub-agent | ACTIVE |
| `core/workspace/browser_context.py` | 71 | `BrowserContextAwareness` — queries browser state | ACTIVE |
| `core/providers/adapters/browser_provider.py` | 256 | `BrowserProvider` — 19 capabilities | ACTIVE |
| `tools/browser_tool.py` | 18 | Deprecated shim re-exporting BrowserManager | DEAD |

### Legacy

- Selenium-based browser in `automation/pc_automation.py` lines 104-168 (LEGACY)

---

## 10. Coding

**Canonical Owner:** `core/codebase_indexer.py` + `core/providers/adapters/codex.py` + `core/providers/adapters/claude_code.py`
**Score:** 7/10 — Delegates to external tools (opencode, codex, claude CLI), no native code execution.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/codebase_indexer.py` | 219 | `CodebaseIndexer` — VectorRAG code search, symbol search | ACTIVE |
| `core/opencode_delegate.py` | 168 | Delegates coding to external `opencode` CLI subprocess | ACTIVE |
| `core/providers/adapters/codex.py` | 134 | `CodexProvider` — wraps `codex` CLI as ExecutionProvider | ACTIVE |
| `core/providers/adapters/claude_code.py` | 126 | `ClaudeCodeProvider` — wraps `claude` CLI as ExecutionProvider | ACTIVE |

### Production Wiring

- Both providers registered via `bootstrap_providers()` in lifespan

---

## 11. Research

**Canonical Owner:** `core/research/`
**Score:** 9/10 — Clean pipeline: planner → extractor → storage → retriever → reasoner → synthesizer → reflection.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/research/planner.py` | 423 | `ResearchPlanner` — question-driven research plans | ACTIVE |
| `core/research/extractor.py` | 319 | `FactExtractor` — structured fact extraction from text/DOM | ACTIVE |
| `core/research/extraction_fsm.py` | 560 | `ExtractionFSM` — extraction workflow state machine | ACTIVE |
| `core/research/storage.py` | 182 | `FactStore` — SQLite persistent fact storage | ACTIVE |
| `core/research/retriever.py` | 96 | `FactRetriever` — multi-source fact retrieval | ACTIVE |
| `core/research/reasoner.py` | 281 | `FactReasoner` — contradiction/agreement/gap analysis | ACTIVE |
| `core/research/synthesizer.py` | 216 | `FactSynthesizer` — structured `ResearchReport` generation | ACTIVE |
| `core/research/reasoning.py` | 433 | `ReasoningEngine` — Belief, Conclusion, CounterHypothesis | ACTIVE |
| `core/research/hypothesis.py` | 171 | `HypothesisManager` — claim-level evidence tracking | ACTIVE |
| `core/research/gap_detector.py` | 237 | `GapDetector` — missing information identification | ACTIVE |
| `core/research/evidence_tracker.py` | 189 | `EvidenceTracker` — links facts to research goals | ACTIVE |
| `core/research/reflection.py` | 292 | `ResearchReflection` — post-research meta-analysis | ACTIVE |
| `core/research/knowledge_graph.py` | 203 | Graph-based knowledge representation | ACTIVE |
| `core/research/graph_store.py` | 266 | Persistent graph storage | ACTIVE |
| `core/research/graph_models.py` | 43 | `GraphNode`, `GraphEdge` data structures | ACTIVE |
| `core/research/linker.py` | 170 | Entity linking across facts | ACTIVE |
| `core/research/models.py` | 27 | `Fact` dataclass | ACTIVE |
| `core/research/__init__.py` | 69 | Package exports | ACTIVE |
| `core/fact_extraction/` | 5 files | `BrowserFactExtractor` — browser facts → research Facts | ACTIVE |
| `tools/deep_research.py` | 241 | 5-step LLM-driven deep research | ACTIVE |
| `tools/search_tool.py` | 227 | Web search (DuckDuckGo + trafilatura) | ACTIVE |
| `tools/crawl4ai_tool.py` | 104 | JS-rendered scraping via crawl4ai | ACTIVE |
| **Total:** | **~21 files** | | |

---

## 12. Memory

**Canonical Owner:** `brain/memory/memory_manager.py`
**Score:** 5/10 — PARTIAL: Common `MemoryProvider` ABC established, `MemoryManager.register_provider()` extensible, 4 brain types unified. External adapters still experimental.

### Canonical Interface

`brain/memory/base.py` — `MemoryProvider` ABC with `count()`, `clear()`, `get_recent()`, `maintenance()`.

### Brain Memory (Canonical Quad)

| File | Lines | Role | Status |
|------|-------|------|--------|
| `brain/memory/memory_manager.py` | 126 | `MemoryManager` — orchestrates all types + extensible provider registry | ACTIVE |
| `brain/memory/episodic.py` | 205 | `EpisodicMemory(MemoryProvider)` — SQLite goal-driven episodes | ACTIVE |
| `brain/memory/semantic.py` | 221 | `SemanticMemory(MemoryProvider)` — SQLite fact/knowledge store | ACTIVE |
| `brain/memory/task.py` | 189 | `TaskMemory(MemoryProvider)` — SQLite execution traces | ACTIVE |
| `brain/memory/decision.py` | 182 | `DecisionMemory(MemoryProvider)` — SQLite decisions + outcomes | ACTIVE |
| `brain/memory/base.py` | 20 | `MemoryProvider` ABC — common interface | ACTIVE |

### External/Additional Memory Adapters

| File | Role | Status |
|------|------|--------|
| `memory/mem0_adapter.py` | mem0 cloud memory adapter | EXPERIMENTAL |
| `memory/memobase_adapter.py` | Memobase memory adapter | EXPERIMENTAL |
| `memory/chromadb_memory.py` | ChromaDB vector memory | EXPERIMENTAL |
| `memory/faiss_memory.py` | FAISS vector memory | EXPERIMENTAL |
| `memory/tiered_memory.py` | Tiered memory with plugin events | EXPERIMENTAL |
| `core/context_builder.py` | `build_unified_context()` — gathers from ChatHistory + memory + RAG | ACTIVE |

### Key Finding

- 4 brain memory types now implement `MemoryProvider` ABC (unified interface)
- `MemoryManager.register_provider()` allows external providers to be plugged in
- External adapters remain EXPERIMENTAL and do not implement `MemoryProvider` yet
- Up next: wrap experimental adapters in `MemoryProvider` shims

---

## 13. Notifications

**Canonical Owner:** `notifications/notifier.py` (supervisor) + `monitors/alerts.py` (alert routing) + `channels/` (multi-channel)
**Score:** 7/10 — SPRAWL: 5+ notification paths (push, email, WebSocket, MCP event, desktop, channel plugins, reminders).

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `notifications/notifier.py` | 109 | `SupervisorNotifier` — push (ntfy.sh, Pushover), email digest, JSONL log | ACTIVE |
| `monitors/alerts.py` | 90 | `AlertRouter` — WebSocket + TTS + WhatsApp dispatch | ACTIVE |
| `network/websocket_server.py` | 97 | `ConnectionManager` — WebSocket broadcast | ACTIVE |
| `channels/` | 10 files | Discord, Slack, Telegram, Matrix, IRC, Email channel plugins | ACTIVE |
| `core/webhook_manager.py` | 253 | `WebhookDispatcher` — HMAC-signed webhooks with retry | ACTIVE |
| `mcp/server.py` | 564 | MCP event relay (WebSocket push) | ACTIVE |
| `reminders/manager.py` | 138 | `ReminderManager` — polls + TTS notification | ACTIVE |
| `automation/call_sync_server.py` | 214 | Desktop notification via plyer | EXPERIMENTAL |

### Production Wiring

- All active systems wired in lifespan
- SupervisorNotifier: line 140-141
- AlertRouter + WebSocket: lines 294-298
- Channels: lines 645-669
- Reminders: lines 244-280
- MCP: lines 676-690

---

## 14. Configuration

**Canonical Owner:** `core/configuration/service.py`
**Score:** 5/10 — DUPLICATED: 4+ parallel config systems with different resolution chains.

### The Four Systems

| System | File | Lines | Mechanism | Status |
|--------|------|-------|-----------|--------|
| **ConfigRegistry** | `core/config_registry.py` | 449 | Priority chain: overrides → env → settings.json → config.yaml → defaults. 168 ConfigEntry objects. Global `config` singleton. | ACTIVE |
| **JarvisConfig** | `core/config_schema.py` | 393 | Pydantic-like dataclass with 14 sub-configs. Reads YAML + JSON + JARVIS_* env vars. Global `jarvis_config` singleton. | ACTIVE |
| **SettingsStore** | `core/settings/store.py` | 303 | Pydantic `JarvisSettings`. Persists to `~/.jarvis/settings.json`. User-facing API keys. Global via `get_settings_store()`. | ACTIVE |
| **ConfigurationService** | `core/configuration/service.py` | 286 | Unifying wrapper over ConfigRegistry + SettingsStore + providers.json. Capability-based model resolution. | ACTIVE |

### Resolution Chain (ConfigurationService)

```
1. Environment variable (highest)
2. ConfigRegistry (config.yaml → data/settings.json → defaults)
3. SettingsStore (~/.jarvis/settings.json)
4. providers.json routing preferences
5. Code default (lowest)
```

### Legacy Shims

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/config.py` | 56 | Re-exports constants from `jarvis_config` for backward compat | ACTIVE |
| `core/settings_legacy.py` | 98 | Read-only bridge from old API to SettingsStore. Writes hard-blocked. | LEGACY |
| `core/tools/settings_tools.py` | 913 | Settings management tool — writes blocked | LEGACY/DEAD |

### Startup Order

```
core/main.py: load .env → init_config() [ConfigRegistry] → imports config.py [JarvisConfig]
core/lifespan.py: _migrate_legacy_settings_once() [SettingsStore]
```

---

## 15. Providers (LLM/Model)

**Canonical Owner:** `core/llm_router.py` + `core/providers/manager.py`
**Score:** 5/10 — DUPLICATED: 2 parallel provider systems (`core/providers/` vs `core/model_providers/`) plus multiple LLM routing strategies.

### System A: `core/providers/` (Execution Provider Ecosystem)

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/providers/manager.py` | — | `ProviderManager` — registers/caches all ExecutionProviders | ACTIVE |
| `core/providers/adapters/desktop_provider.py` | 169 | Desktop capabilities | ACTIVE |
| `core/providers/adapters/browser_provider.py` | 256 | Browser capabilities | ACTIVE |
| `core/providers/adapters/codex.py` | 134 | Codex CLI wrapper | ACTIVE |
| `core/providers/adapters/claude_code.py` | 126 | Claude CLI wrapper | ACTIVE |
| `core/providers/adapters/automation_provider.py` | — | Automation provider | ACTIVE |

### System B: `core/model_providers/` (Parallel Model Provider Ecosystem)

| File | Role | Status |
|------|------|--------|
| `core/model_providers/router.py` | Alternative model router | ACTIVE |
| `core/model_providers/hybrid.py` | Hybrid provider | ACTIVE |
| `core/model_providers/ollama.py` | Ollama provider | ACTIVE |

### LLM Routing

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/llm_router.py` | ~358+ | Primary LLM dispatch via LiteLLM Router (52 call sites) | ACTIVE |
| `core/llm_failover.py` | 467 | `FailoverRouter` + `CooldownProbe` | ACTIVE |
| `core/model_router.py` | — | Another router with health checker integration | ACTIVE |
| `core/provider_registry.py` | — | Provider registry | ACTIVE |

### Key Finding

- 3 router files (`llm_router.py`, `model_router.py`, `model_providers/router.py`)
- 2 provider ecosystems (`core/providers/`, `core/model_providers/`)
- No documented reason for the split

---

## 16. Capabilities

**Canonical Owner:** `core/capability/` + `core/tools/policy.py`
**Score:** 6/10 — PARTIAL: Capability registry exists but coverage is incomplete.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/capability/models.py` | ~120 | `Capability` dataclass, capability definitions (notifications, etc.) | ACTIVE |
| `core/capability/registry.py` | — | Capability registration | ACTIVE |
| `core/tools/policy.py` | 85 | `PolicyEngine` — evaluates capabilities against ToolPolicy | ACTIVE |

### Notes

- Capabilities are defined but not consistently enforced across all subsystems
- `PolicyEngine` is logged in lifespan (line 632-635) but not deeply integrated

---

## 17. Safety & Permissions

**Canonical Owner:** `governance/GovernanceValidator.py` + `core/auth.py`
**Score:** 7/10 — Multi-layer safety but fragmented across files.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `governance/GovernanceValidator.py` | 126 | Keyword blocklist + LLM semantic classification | ACTIVE |
| `governance/RuntimeGovernanceLayer.py` | 118 | Request budget, concurrency limits, circuit breaker | ACTIVE |
| `governance/MetaGovernor.py` | 463 | Continuous governance loop (observe→analyze→decide→act→learn) | EXPERIMENTAL |
| `governance/exceptions.py` | 25 | `GovernanceViolation`, `SecurityViolation` exceptions | ACTIVE |
| `core/auth.py` | ~585 | Auth bypass via loopback/dev mode (lines 583-585) | ACTIVE |
| `core/authz/loader.py` | — | RBAC policy loader (`config/roles.yaml`) | ACTIVE |
| `core/rate_limiter.py` | 67 | `SlidingWindowRateLimiter` — loopback exempt | ACTIVE |
| `core/desktop/safety.py` | 299 | `SafetyManager` — emergency stop, rate limits, forbidden regions | ACTIVE |
| `core/sandbox/` | — | Docker sandbox for code execution | ACTIVE |
| `brain/production_gate.py` | 240 | `ProductionGate` — benchmark-based gating for Android builder | ACTIVE |

### Layers

1. **Input**: `GovernanceValidator` blocks injection/destructive patterns
2. **Runtime**: `RuntimeGovernanceLayer` enforces budgets + concurrency
3. **Rate**: `RateLimiter` per-IP/scope sliding window
4. **Auth**: `core/auth.py` loopback bypass (dev mode)
5. **Desktop**: `SafetyManager` emergency stop, mouse/keyboard rate limits
6. **Execution**: `SandboxManager` Docker isolation
7. **Governance Loop**: `MetaGovernor` adaptive throttling (experimental)

---

## 18. Logging & Observability

**Canonical Owner:** `core/observability/logging.py` + `core/observability/metrics.py`
**Score:** 8/10 — Clean structured logging + Prometheus-style metrics + audit trail.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/observability/logging.py` | 128 | `LogContext` (context vars), `JsonFormatter`, `configure_json_logging()` | ACTIVE |
| `core/observability/metrics.py` | 157 | `MetricsMiddleware`, in-process Prometheus-style counters | ACTIVE |
| `core/observability/__init__.py` | 16 | Package exports | ACTIVE |
| `core/request_id.py` | 54 | `RequestIDMiddleware` — traces requests via X-Request-ID | ACTIVE |
| `core/audit_log.py` | 106 | `AuditLog` — buffered JSONL with PII redaction, daily rotation | ACTIVE |
| `core/agent_metrics.py` | 81 | Per-agent token/timing metrics | ACTIVE |
| `utils/logger.py` | 23 | `SystemLogger` — thin wrapper | LEGACY |

### Production Wiring

- `core/main.py` lines 223-231: `RequestIDMiddleware` + metrics init
- `core/lifespan.py` lines 622-628: `AuditLog` init; lines 904-906: flush on shutdown

---

## 19. Recovery & Fault Tolerance

**Canonical Owner:** `core/self_healing.py` + `core/workflow/recovery.py`
**Score:** 8/10 — Comprehensive: self-healing, service health, resource monitor, workflow recovery, orphan recovery, LLM failover, backup, rate limiter, voice auto-recovery.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/self_healing.py` | 319 | 3-layer: Detection → Diagnosis → Recovery. + `LearningLoop` | ACTIVE |
| `monitors/services.py` | 193 | `ServiceHealthChecker` — Ollama, Search, Network, Voice | ACTIVE |
| `monitors/resource.py` | 152 | `ResourceMonitor` — CPU, RAM, Disk, GPU | ACTIVE |
| `core/workflow/recovery.py` | 77 | `recover_active_workflows()` — stale workflow resume | ACTIVE |
| `core/workflow/heartbeat_monitor.py` | 63 | `HeartbeatMonitor` — period stale check | ACTIVE |
| `core/spawning/orphan.py` | 76 | `OrphanRecovery` — orphaned subagent recovery | ACTIVE |
| `core/llm_failover.py` | 467 | `FailoverRouter` + `CooldownProbe` + `FailoverManager` | ACTIVE |
| `core/backup.py` | 169 | `BackupManager` — tar.gz state backup/restore | ACTIVE |
| `core/rate_limiter.py` | 67 | `SlidingWindowRateLimiter` | ACTIVE |
| `core/system_governor.py` | 211 | `SystemGovernor` — retry/replan/abort decisions | ACTIVE |
| `assistant/voice_pipeline.py` | 1007 | Built-in STT/TTS auto-recovery (3 attempts) | ACTIVE |
| `assistant/wake_word.py` | 611 | Watchdog retry for wake word | ACTIVE |
| `daemon/jarvis_service.py` | 250 | Windows service with watchdog and crash recovery | ACTIVE |
| `core/health_monitor.py` | 223 | Per-module health monitor | LEGACY |
| `core/environment_monitor.py` | 229 | Disk/memory/Ollama/network monitoring | LEGACY |
| `core/proactive_monitor.py` | 38 | Stub — replaced by AlertRouter | DEAD |

---

## 20. Plugin System

**Canonical Owner:** `core/plugins/`
**Score:** 7/10 — Clean plugin architecture with hooks, events, and per-plugin settings.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/plugins/base.py` | — | `BasePlugin` — abstract base class | ACTIVE |
| `core/plugins/base_plugin.py` | — | `JarvisPlugin` — concrete plugin interface | ACTIVE |
| `core/plugins/manager.py` | — | `PluginManager` — load/unload/register lifecycle | ACTIVE |
| `core/plugins/registry.py` | — | Plugin registry | ACTIVE |
| `core/plugins/events.py` | 73 | `PluginEventBus` — event → plugin hook bridge | ACTIVE |
| `core/plugins/voice.py` | 89 | `VoicePlugin` hooks | ACTIVE |
| `core/plugins/automation.py` | 89 | `AutomationPlugin` hooks | ACTIVE |
| `core/plugins/settings_store.py` | 92 | `PluginSettingsStore` — per-plugin JSON key/value | ACTIVE |

---

## 21. Voice

**Canonical Owner:** `assistant/voice_pipeline.py`
**Score:** 9/10 — Clean pipeline: mic → STT → LLM → TTS → speaker. Multiple providers, auto-recovery, health monitoring.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `assistant/voice_pipeline.py` | 1007 | `VoiceEngine` — full voice pipeline (VAD, wake word, continuous/PTT, health) | ACTIVE |
| `assistant/tts.py` | 90 | `JarvisTTS` — Kokoro-TTS integration, lazy-load, audio cache | ACTIVE |
| `assistant/stt.py` | 64 | STT bootstrap + `get_stt()` | ACTIVE |
| `assistant/wake_word.py` | 641 | Two-stage wake word (WebRTC VAD + Faster-Whisper) | ACTIVE |
| `assistant/providers/faster_whisper.py` | 103 | Default STT provider (local) | ACTIVE |
| `assistant/providers/deepgram.py` | 71 | Cloud STT (Deepgram Nova-3) | ACTIVE |
| `assistant/providers/azure_speech.py` | 70 | Cloud STT (Azure) | ACTIVE |
| `assistant/providers/kokoro_tts.py` | 34 | Default TTS provider (local) | ACTIVE |
| `assistant/providers/edge_tts_provider.py` | 33 | Edge TTS provider | ACTIVE |
| `assistant/edge_tts_module.py` | 41 | Edge TTS direct integration | ACTIVE |
| `assistant/tts_protocol.py` | 72 | `TTSProvider` ABC + registry | ACTIVE |
| `assistant/stt_protocol.py` | 73 | `STTProvider` ABC + registry | ACTIVE |
| `core/routes/voice.py` | 165 | FastAPI voice routes | ACTIVE |
| `core/plugins/voice.py` | 89 | `VoicePlugin` hooks | ACTIVE |
| `demo/voice_demo.py` | 100 | Legacy demo | LEGACY |

### Production Wiring

- `core/lifespan.py` lines 436-442: `VoiceLoop` started
- `core/lifespan.py` lines 251-280: TTS initialized for reminders

---

## 22. Automation (Autonomous Build)

**Canonical Owner:** `brain/automation/loop.py`
**Score:** 8/10 — Single monolithic autonomous build loop (2679 lines). All phases in one file.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `brain/automation/loop.py` | 2679 | `AutomationLoop` — full autonomous build pipeline: plan→generate→build→test→verify→runtime→finish | ACTIVE |
| `brain/automation/__init__.py` | 3 | Package export | ACTIVE |

### Phases (in loop.py)

1. `plan(tool_aware)` — tool-aware plan generation
2. `generate()` — code generation
3. `verify_gates()` — quality gates
4. `build()` — compiled build with `CompilerRepairEngine` + `FailureMemory`
5. `test()` — test execution
6. `verify()` — verification
7. `runtime_validation()` — runtime checks
8. `finish()` — completion

### Inner Classes (in loop.py)

- `FailureMemory` — SQLite pattern-based error matching
- `ArchitecturalMemory` — JSON-backed architectural lessons
- `RequirementTracker` — goal→requirements parsing
- `Watchdog` — build monitoring

### Bridge to tools

- `core/tools/automated_build.py` — wraps as sync tool
- `core/tools/build_tools.py` — creates `AutomationLoop` instances

---

## 23. EventBus

**Canonical Owner:** None — **DUPLICATED:** 3 parallel event bus systems.
**Score:** 4/10 — No single canonical bus. Fragmented between brain, core, and plugin systems.

### The Three Buses

| Bus | File | Lines | Mechanism | Used By | Status |
|-----|------|-------|-----------|---------|--------|
| **Brain EventBus** | `brain/events/event_bus.py` | 138 | Typed async-first, pattern subscription (`*`, `**`). Global `global_event_bus`. | Observers, learning engine, self-improvement, skill acquisition, goal generator | ACTIVE |
| **Core EventBus** | `core/event_bus.py` | 117 | Channel-based, sync/async/streaming, wildcard `*`. Global `event_bus`. | Settings store, document tools, skill tools | ACTIVE |
| **PluginEventBus** | `core/plugins/events.py` | 73 | Event type-based, passes through plugin hooks. Global singleton. | Voice pipeline, file agent, tiered memory, channels processor, SDK | ACTIVE |

### Event Types (`brain/events/event_types.py`)

179 lines of typed event payload dataclasses: `GoalCreated`, `GoalCompleted`, `GoalFailed`, `TaskCompleted`, `TaskFailed`, `MemoryStored`, `MemoryRetrieved`, `VerificationPassed/Failed`, `UserMessage`, `UserArrived`, `FileCreated/Modified/Deleted`, `EmailReceived`, `CalendarEvent`, `SystemDiskLow/CpuHigh/MemoryHigh`, `ObserverTick`, `LearningApplied`, `GoalAutoCreated`.

---

## 24. History

**Canonical Owner:** `core/database.py` (ChatHistory model)
**Score:** 6/10 — PARTIAL: ChatHistory (SQLAlchemy) is the canonical store for reads. `context_builder.py` reads from ChatHistory first, falls back to ConversationManager. WebSocket writes still go to ConversationManager (JSON).

### The Systems

| System | File | Storage | Scope | Status |
|--------|------|---------|-------|--------|
| **ChatHistory** (SQLAlchemy) | `core/database.py:159-169` | SQLAlchemy `chat_history` table | All chat messages, ORM-backed | CANONICAL |
| **ConversationManager** | `core/session.py` | JSON files (`~/.jarvis/sessions/`) | Chat session messages per session | ACTIVE |
| **WhatsAppHistory** | `integrations/whatsapp/history.py` | SQLite | WhatsApp conversations | DOMAIN-SPECIFIC |
| **Brain Memory** (4 types) | `brain/memory/` | SQLite (`data/workflow.db`) | Episodic, semantic, task, decision | DOMAIN-SPECIFIC |

### Context Builder

`core/context_builder.py:58` — `build_unified_context()` reads from ChatHistory (SQLAlchemy) first, falls back to ConversationManager (JSON) + semantic memory + RAG.

---

## 25. Projects

**Canonical Owner:** `core/project_manager.py`
**Score:** 8/10 — Clean multi-project queue manager with checkpoint/resume.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/project_manager.py` | 255 | Multi-project queue manager, checkpoint/resume, worker pools | ACTIVE |
| `core/project_state.py` | 231 | `ProjectState` — single source of truth per project | ACTIVE |
| `core/agent_orchestrator.py` | ~200 | `AgentOrchestrator` — manages project coding tasks | ACTIVE |
| `core/budget_controller.py` | 97 | `BudgetController` — per-project resource enforcement | ACTIVE |
| `core/tools/build_tools.py` | 132 | Bridges build tools → AutomationLoop | ACTIVE |
| `brain/goals/goal_manager.py` | ~200 | `GoalManager` — persistent goal tracking | ACTIVE |
| `brain/goals/goal.py` | ~80 | Goal data model | ACTIVE |
| `core/cloud/project_manager.py` | 243 | Cloud-backed (Supabase) project manager | ACTIVE |

### Production Wiring

- `core/lifespan.py` line 509-513: `project_manager.process_queue()` background task

---

## 26. Rules & Governance

**Canonical Owner:** `governance/`
**Score:** 6/10 — SPRAWL: MetaGovernor, GovernanceValidator, RuntimeGovernanceLayer, WorkQueue, PolicyEngine, ProductionGate — overlapping concerns.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `governance/MetaGovernor.py` | 463 | Continuous governance loop (observe→analyze→detect→decide→act→learn) | EXPERIMENTAL |
| `governance/GovernanceValidator.py` | 126 | Keyword blocklist + LLM semantic safety gate | ACTIVE |
| `governance/RuntimeGovernanceLayer.py` | 118 | Budget, concurrency, circuit breaker | ACTIVE |
| `governance/exceptions.py` | 25 | Exception definitions | ACTIVE |
| `governance/__init__.py` | 23 | Package exports | ACTIVE |
| `core/governance/work_queue.py` | 354 | `WorkQueue` — async priority queue with disk persistence | ACTIVE |
| `core/governance/task_router.py` | ~120 | `TaskRouter` — confidence-based routing | ACTIVE |
| `core/governance/resource_monitor.py` | ~100 | CPU/memory throttle detection | ACTIVE |
| `core/tools/policy.py` | 85 | `PolicyEngine` — tool availability against context | ACTIVE |
| `brain/production_gate.py` | 240 | Benchmark-based production gating | ACTIVE |
| `config/roles.yaml` | 32 | RBAC role definitions | ACTIVE |

### Production Wiring

- `core/lifespan.py` line 613-619: `work_queue.start()`
- `core/lifespan.py` line 632-635: `PolicyEngine` logged on import

---

## 27. Cron / Periodic Tasks

**Canonical Owner:** `core/cron.py`
**Score:** 8/10 — Clean persistent cron scheduler with interval + cron expression support.

### Files

| File | Lines | Role | Status |
|------|-------|------|--------|
| `core/cron.py` | — | `Scheduler` — persistent job scheduler, polls every 60s, `croniter` support | ACTIVE |
| `core/task_scheduler.py` | — | `compute_next_run()` — legacy utility (format strings) | LEGACY |

### Production Wiring

- `core/lifespan.py` lines 700-708: `scheduler.start()`
- `core/lifespan.py` lines 883-885: `scheduler.stop()`

---

## Cross-Cutting Concerns

### Duplication Index

| Concern | # of Implementations | Canonical |
|---------|---------------------|-----------|
| EventBus | 1 (`brain/events/event_bus.py` + 2 backward-compat shims) | `brain/events/event_bus.py` |
| Memory | 10+ (4 brain + 6 external + ChatHistory) | `brain/memory/memory_manager.py` |
| Configuration | 1 (`core/configuration/service.py` + delegation from `config_registry`) | `core/configuration/service.py` |
| Providers/LLM Routing | 2 routers (`llm_router` canonical + `model_providers/router`) + 1 provider shim (`model_router`) | `core/llm_router.py` + `core/providers/manager.py` |
| History | 2 (ChatHistory canonical, ConversationManager JSON fallback) | `core/database.py` (ChatHistory) |
| Health Monitoring | 3 (`monitors/services.py`, `core/health_monitor.py`, `core/environment_monitor.py`) | `monitors/services.py` |
| Desktop Control | 2 (`core/desktop/` canonical + deprecated `pc_agent`) | `core/desktop/` |
| Logging | 2 (`core/observability/logging.py`, `utils/logger.py`) | `core/observability/logging.py` |

### Dead Code Index

| File | Reason | Lines |
|------|--------|-------|
| `core/proactive_monitor.py` | Replaced by `monitors/alerts.py` | 38 |
| `tools/browser_tool.py` | Deprecated shim | 18 |
| `demo/voice_demo.py` | Legacy demo | 100 |
| `core/tools/settings_tools.py` | Settings writes hard-blocked (913 lines, partially dead) | 913 |

### Experimental Code Index

| File | Lines | What |
|------|-------|------|
| `governance/MetaGovernor.py` | 463 | Continuous governance loop |
| `core/scheduler/autonomous.py` | — | Opportunity→activity bridge |
| `pc_agent/` | 673 | Sandboxed PC control agent |
| `memory/mem0_adapter.py` | — | mem0 cloud memory |
| `memory/memobase_adapter.py` | — | Memobase memory |
| `memory/chromadb_memory.py` | — | ChromaDB vector memory |
| `memory/faiss_memory.py` | — | FAISS vector memory |
| `memory/tiered_memory.py` | — | Tiered memory |
| `automation/call_sync_server.py` | 214 | Desktop call notifications |
| `core/llm_failover.py` | 467 | `FailoverManager` (config-driven variant) |

### Codebase Summary

| Metric | Value |
|--------|-------|
| Total responsibility areas | 27 |
| Areas with single canonical owner | 15 (Startup, Workflow, Browser, Research, Voice, Automation Build, Projects, Plugins, Logging, Cron, Coding, Execution, EventBus, Configuration, History) |
| Areas with duplicated ownership | 6 (Providers, Memory, Desktop, Health Monitoring, Notifications, Rules) |
| Dead files | 5 (total ~1,100 dead/commented lines) |
| Experimental files | 10 |
| LEGACY files | 10 |
| Total tracked files | ~120 across all areas |
