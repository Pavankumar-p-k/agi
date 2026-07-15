# PHASE 5 — EventBus & Context Audit

---

## 1. EventBus Inventory

### 1a. Canonical `EventBus` (`core/event_bus.py`)

| Property | Value |
|----------|-------|
| **File** | `core/event_bus.py:73` |
| **Singleton** | `global_event_bus` at `core/event_bus.py:294` |
| **Event model** | `Event` dataclass (`type`, `source`, `payload`, `id`, `timestamp`, `priority`, `namespace`, `resource_scope`) |
| **Publish modes** | `publish()` (async), `publish_sync()` (sync + fire-and-forget) |
| **Legacy compat** | `emit()` accepts `MJEvent` or `Event` or `str` |
| **Streaming** | `subscribe_stream()` returns `asyncio.Queue` |
| **WebSocket** | `register_ws()`, `unregister_ws()`, `_broadcast()` |
| **History** | In-memory ring buffer of last 100 events |
| **Pattern matching** | fnmatch wildcards (`*`, `**`) |
| **Tenant isolation** | `resource_scope.tenant_id` + `Subscription.tenant_id` |

### 1b. Second `EventBus` (legacy `get_bus`)

| Property | Value |
|----------|-------|
| **File** | `core/event_bus.py:430-436` |
| **Singleton** | Module-level `_bus`, accessed via `get_bus()` |
| **Difference** | Same `EventBus` class, separate instance |
| **Used by** | `InboxStore`, `ExecutionTracker.emit_event()`, `progress_websocket` |
| **Relationship** | `get_bus()` creates a **second** EventBus instance — NOT `global_event_bus` |

**DUPLICATE** — `get_bus()` at line 433 creates a separate `EventBus()` instance that has zero subscriptions by default and is never wired to the canonical `global_event_bus`. Events published to `get_bus()` are invisible to `global_event_bus` subscribers and vice versa.

### 1c. `PluginEventBus` (deprecated)

| Property | Value |
|----------|-------|
| **File** | `core/event_bus.py:492` |
| **Singleton** | `PluginEventBus.instance()` |
| **Backend** | Wraps `global_event_bus` with `namespace="plugin"` |
| **Status** | **DORMANT** — marked deprecated, all handlers should use `global_event_bus.subscribe()` directly |
| **Callers** | `voice_pipeline.py:432`, `channels/processor.py:51`, `core/file_agent.py:104`, `memory/tiered_memory.py:151`, `tools/website_generator.py:780`, `core/agents/_sub_agent_base.py:127`, `core/plugins/base.py:673`, `core/plugins/loader.py:169` |

### 1d. `ObservationHub` (`core/observation/hub.py`)

| Property | Value |
|----------|-------|
| **File** | `core/observation/hub.py:19` |
| **Singleton** | `get_hub()` |
| **Backend** | Wraps `global_event_bus` |
| **Events** | `observation.observed`, `observation.created` |
| **Used by** | `core/distribution/observation.py`, `core/runtime/providers.py` |

---

## 2. Event Type Registry

### 2a. String constants in `core/event_bus.py:322-375`

| Group | Events | Published by |
|-------|--------|-------------|
| **config** | `config.changed`, `config.reloaded`, `config.validation_error` | `core/configuration/service.py`, `core/settings/store.py` |
| **rag** | `rag.documents_retrieved`, `rag.document_scored`, `rag.relevance_feedback` | (no publisher found) |
| **workflow** | `workflow.idempotency_hit` | `WorkflowStore` |
| **memory** | `memory.fact_conflict`, `memory.index_updated` | (no publisher found) |
| **database** | `database.connection_pooled` | (no publisher found) |
| **workflow step** | `workflow_started`, `step_started`, `step_completed`, `step_failed`, `workflow_completed`, `workflow_failed`, `workflow_cancelled`, `workflow_recovered` | `WorkflowStore.append_event()` |
| **compensation** | `compensation_started`, `compensation_step_started`, `compensation_step_completed`, `compensation_step_failed`, `workflow_compensated`, `compensation_failed`, `idempotency_hit` | `WorkflowStore.append_event()` |
| **goal** | `goal_created`, `goal_updated`, `goal_completed`, `goal_failed` | `ExecutionTracker.emit_event()` |
| **node** | `node_created`, `node_updated`, `node_completed`, `node_failed`, `node_skipped` | `ExecutionTracker.update_node()` |
| **other** | `artifact_created`, `confidence_updated`, `estimate_updated`, `need_input`, `warning`, `error`, `milestone`, `focus_changed` | `ExecutionTracker` |

### 2b. Typed dataclass events in `core/event_types.py`

| Class | Fields | Used by |
|-------|--------|---------|
| `GoalCreated`, `GoalCompleted`, `GoalFailed` | goal_id, objective, ... | `brain/UnifiedBrain.py` |
| `TaskCompleted`, `TaskFailed` | goal_id, node_id, label, ... | `brain/UnifiedBrain.py` |
| `MemoryStored`, `MemoryRetrieved` | memory_type, memory_id, ... | (none found) |
| `VerificationPassed`, `VerificationFailed` | action, confidence, ... | (none found) |
| `UserMessage`, `UserArrived` | user_id, content, ... | (none found) |
| `FileCreated`, `FileModified`, `FileDeleted` | path, size_bytes | (none found) |
| `EmailReceived`, `CalendarEvent` | subject, sender, ... | (none found) |
| `SystemDiskLow`, `SystemCpuHigh`, `SystemMemoryHigh` | path, percent, ... | (none found) |
| `ObserverTick`, `LearningApplied`, `GoalAutoCreated` | observer_name, ... | (none found) |

**DRIFT** — `core/event_types.py` defines 20+ typed event dataclasses that are **never used** anywhere. No code imports or publishes them. They coexist alongside the string-based event constants in `core/event_bus.py`. The typed events have zero subscribers and zero publishers.

### 2c. Events published (but never defined as constants)

| Event string | Published at | Status |
|-------------|-------------|--------|
| `"on_voice_command"` | `assistant/voice_pipeline.py:432` via PluginEventBus | DORMANT — PluginEventBus deprecated |
| `"on_channel_message"` | `channels/processor.py:51` via PluginEventBus | DORMANT |
| `"on_agent_reply"` | `core/agents/_sub_agent_base.py:127` via PluginEventBus | DORMANT |
| `"on_file_saved"` | `core/file_agent.py:104` via PluginEventBus | DORMANT |
| `"on_memory_recall"` | `memory/tiered_memory.py:151` via PluginEventBus | DORMANT |
| `"on_website_generated"` | `tools/website_generator.py:780` via PluginEventBus | DORMANT |
| `"settings.changed"` | `core/settings/store.py:209` via `self.event_bus.publish()` | DRIFT — uses own EventBus ref, NOT `global_event_bus` |
| `"execution.workflow_started"` | `core/execution/manager.py:100` via `global_event_bus.publish_sync()` | CORRECT |
| `"execution.progress"` | `core/execution/manager.py:111` via `global_event_bus.publish_sync()` | CORRECT |
| `"execution.completed"` | `core/execution/manager.py:115` via `global_event_bus.publish_sync()` | CORRECT |
| `"execution.failed"` | `core/execution/manager.py:119` via `global_event_bus.publish_sync()` | CORRECT |
| `"execution.workflow_cancelled"` | `core/execution/manager.py:68` via `global_event_bus.publish_sync()` | CORRECT |
| `"execution.workflow_resumed"` | `core/execution/manager.py:79` via `global_event_bus.publish_sync()` | CORRECT |
| `"scheduler.tick"` | `core/scheduler/scheduler.py:449` via `global_event_bus` | CORRECT |
| `"observation.observed"` | `core/observation/hub.py:47` via `global_event_bus` | CORRECT |
| `"goal.created"`, `"goal.completed"`, `"goal.failed"`, `"task.completed"`, `"task.failed"`, `"system.disk_low"` | `brain/UnifiedBrain.py:146-151, 299-386` | CORRECT |

### 2d. Events subscribed (but never published)

| Event | Subscribed by | Published by | Status |
|-------|-------------|-------------|--------|
| `rag.documents_retrieved` | `register_default_subscribers()` (logger) | **never published** | **DISCONNECTED** |
| `rag.document_scored` | `register_default_subscribers()` (logger) | **never published** | **DISCONNECTED** |
| `rag.relevance_feedback` | `register_default_subscribers()` (logger) | **never published** | **DISCONNECTED** |
| `memory.fact_conflict` | `register_default_subscribers()` (logger) | **never published** | **DISCONNECTED** |
| `memory.index_updated` | `register_default_subscribers()` (logger) | **never published** | **DISCONNECTED** |
| `database.connection_pooled` | `register_default_subscribers()` (logger) | **never published** | **DISCONNECTED** |
| `config.validation_error` | `register_default_subscribers()` (logger) | **never published** | **DISCONNECTED** |
| `workflow.idempotency_hit` | `register_default_subscribers()` (logger) | Published as `"idempotency_hit"` (no dot) | **DRIFT** — event name mismatch |

---

## 3. Publisher Registry

### 3a. Components publishing to `global_event_bus`

| Component | File | Events | Via |
|-----------|------|--------|-----|
| `WorkflowStore.append_event()` | `core/workflow/storage.py:290` | `workflow.*`, `step_*`, `compensation_*`, `idempotency_hit` | `global_event_bus.publish_sync()` |
| `ExecutionManager._publish_event()` | `core/execution/manager.py:100` | `execution.*` | `global_event_bus.publish_sync()` |
| `Scheduler._fire_tick_callbacks()` | `core/scheduler/scheduler.py:449` | `scheduler.tick` | `global_event_bus.publish_sync()` |
| `ObservationHub` | `core/observation/hub.py:47` | `observation.observed` | `global_event_bus.publish_sync()` |
| `ConfigurationService` | `core/configuration/service.py:97` | `config.changed` | `global_event_bus.publish_sync()` |
| `brain/UnifiedBrain.py` | `brain/UnifiedBrain.py:299-386` | `goal.*`, `task.*`, `system.disk_low` | `self.events.publish()` (which IS `global_event_bus`) |
| `brain/goal_generator.py` | `brain/goal_generator.py:89` | (not specified) | `self.bus.publish()` (IS `global_event_bus`) |
| `brain/learning_engine.py` | `brain/learning_engine.py:88` | (not specified) | `global_event_bus.publish()` |
| `brain/skill_acquisition.py` | `brain/skill_acquisition.py:99` | (not specified) | `global_event_bus.publish()` |
| `brain/self_improvement.py` | `brain/self_improvement.py:186` | (not specified) | `global_event_bus.publish()` |

### 3b. Components publishing to `get_bus()` (legacy)

| Component | File | Events | Notes |
|-----------|------|--------|-------|
| `ExecutionTracker.emit_event()` | `core/workflow/tracker.py:108-270` | `goal_*`, `node_*`, `milestone`, `warning` | Uses `get_bus().emit()` → **wrong bus** |
| `InboxStore._subscribe_to_events()` | `core/inbox/store.py:108` | Subscribes via `bus.on()` → `get_bus()` | Subscribes to **wrong bus** |

**DRIFT** — `ExecutionTracker` publishes `goal_*` and `node_*` events to `get_bus()` (legacy instance), but `UnifiedBrain` subscribes to the same event patterns on `global_event_bus`. The two are completely disconnected.

### 3c. Components publishing to `PluginEventBus` (deprecated)

| File | Event | Line |
|------|-------|------|
| `assistant/voice_pipeline.py` | `on_voice_command` | 432 |
| `channels/processor.py` | `on_channel_message` | 51 |
| `core/agents/_sub_agent_base.py` | `on_agent_reply` | 127 |
| `core/file_agent.py` | `on_file_saved` | 104 |
| `memory/tiered_memory.py` | `on_memory_recall` | 151 |
| `tools/website_generator.py` | `on_website_generated` | 780 |
| `core/plugins/base.py` | (dynamic hooks) | 673 |

### 3d. Components publishing to own EventBus ref

| Component | File | Events | Notes |
|-----------|------|--------|-------|
| `SettingsStore` | `core/settings/store.py:209-227` | `settings.changed` | `self.event_bus.publish()` — has its own `event_bus` attribute, but it's only set in tests. When `self.event_bus is None`, publish is skipped. **DISCONNECTED** |

---

## 4. Subscriber Registry

### 4a. Subscribers on `global_event_bus`

| Subscriber | Pattern | File | Line |
|-----------|---------|------|------|
| `register_default_subscribers` | `rag.*`, `workflow.idempotency_hit`, `config.validation_error`, `memory.*`, `database.*` | `core/event_bus.py:307-318` | Logger stub |
| `brain/UnifiedBrain._on_goal_created` | `goal.created` | `brain/UnifiedBrain.py:146` | |
| `brain/UnifiedBrain._on_goal_completed` | `goal.completed` | `brain/UnifiedBrain.py:147` | |
| `brain/UnifiedBrain._on_goal_failed` | `goal.failed` | `brain/UnifiedBrain.py:148` | |
| `brain/UnifiedBrain._on_task_completed` | `task.completed` | `brain/UnifiedBrain.py:149` | |
| `brain/UnifiedBrain._on_task_failed` | `task.failed` | `brain/UnifiedBrain.py:150` | |
| `brain/UnifiedBrain._on_disk_low` | `system.disk_low` | `brain/UnifiedBrain.py:151` | |

### 4b. Subscribers on `get_bus()` (legacy)

| Subscriber | Pattern | File | Line |
|-----------|---------|------|------|
| `InboxStore` | `goal_completed`, `goal_failed`, `need_input`, `warning`, `error`, `milestone`, `node_failed`, `node_skipped` | `core/inbox/store.py:109-158` | **DISCONNECTED** — subscribes to wrong bus |
| `progress_websocket` | All events (via `register_ws`) | `core/routes/progress.py:222` | **DISCONNECTED** — registered on wrong bus |

### 4c. Subscribers on `PluginEventBus`

| Subscriber | Pattern | File | Line |
|-----------|---------|------|------|
| Plugin hooks (dynamic) | Plugin-defined patterns | `core/plugins/loader.py:174` | DORMANT — PluginEventBus deprecated |

---

## 5. WebSocket Matrix

### 5a. WebSocket Routes

| Route | File | Connected to | Events sent |
|-------|------|-------------|-------------|
| `/ws/{session_id}` | `core/routes/progress.py:214` | `get_bus().register_ws()` | All events from legacy bus (goal_*, node_*, milestone, etc.) |
| `/ws` (inbox) | `core/routes/inbox.py:117` | `_ws_clients` (own set) | `inbox_new` on POST /add |
| `/ws/chat_stream` | `core/routes/websocket.py:32` | Pipeline `ws_adapter.stream_via_pipeline()` | Streamed LLM tokens |
| `/ws/mcp/bridge` | `core/routes/websocket.py:26` | MCP server | MCP protocol messages |
| `/ws/logs` | `core/routes/websocket.py:95` | File tailer | Log entries |
| `/ws/agent_stream` | `core/routes/websocket.py:151` | ConversationManager + pipeline | `stream_token`, `stream_end`, `workspace_summary` |
| `/ws/{device_id}/{user_id}` | `core/routes/websocket.py:254` | `connection_manager` (network module) | Custom protocol |
| `/ws` (activity) | `core/routes/activity.py:482` | `_ws_subscriptions` (own set) | Activity lifecycle events |

### 5b. Independent WebSocket Systems

| System | Subscriber tracking | Integration with EventBus |
|--------|-------------------|--------------------------|
| EventBus WebSocket | `register_ws()` on `global_event_bus` | ✅ Direct — `_broadcast()` called from `publish()` |
| Legacy `get_bus()` WebSocket | `register_ws()` on legacy bus | ✅ Direct — but wrong bus |
| Inbox WebSocket | `_ws_clients` set in `core/routes/inbox.py` | ❌ Manual — only notifies on POST /add |
| Activity WebSocket | `_ws_subscriptions` dict in `core/routes/activity.py` | ❌ Manual — `_broadcast()` called from REST handlers |
| Scheduler WebSocket | `_broadcast_active()` → Activity module | ❌ Indirect — calls Activity's `_broadcast_active()` |

**DRIFT** — Five independent WebSocket broadcast systems. Inbox, Activity, and Scheduler each manage their own WebSocket client sets and broadcast manually. They do NOT use `EventBus.register_ws()` or `_broadcast()`.

---

## 6. Inbox Integration

### 6a. Auto-subscription (EventBus → InboxItem)

`InboxStore._subscribe_to_events()` subscribes to 8 event types via `bus.on()` on the **legacy `get_bus()`**:

| Event | Category | Trigger |
|-------|----------|---------|
| `goal_completed` | finished | Task completed |
| `goal_failed` | error | Task failed |
| `need_input` | approval | Needs user input |
| `warning` | error | Warning message |
| `error` | error | Error message |
| `milestone` | update | Milestone reached |
| `node_failed` | error | Step failed |
| `node_skipped` | update | Step skipped |

### 6b. Manual add (REST → InboxItem)

`POST /api/inbox/add` adds items directly and broadcasts `inbox_new` to `_ws_clients`.

### 6c. Disconnected paths

| Path | Issue |
|------|-------|
| `ExecutionTracker` publishes `goal_*`/`node_*` to `get_bus()` | InboxStore subscribes to `get_bus()` → ✅ works, but **only for ExecutionTracker events** |
| `UnifiedBrain` publishes `goal.*` (with dot) to `global_event_bus` | InboxStore subscribes to `goal_completed` (no dot) on `get_bus()` → **DISCONNECTED** |
| `WorkflowStore.append_event()` publishes `workflow.*` to `global_event_bus` | InboxStore does not subscribe to any `workflow.*` events → **DISCONNECTED** |
| `ExecutionManager` publishes `execution.*` to `global_event_bus` | InboxStore does not subscribe → **DISCONNECTED** |

---

## 7. Notification Chain

### 7a. `notifications/notifier.py` (`SupervisorNotifier`)

| Channel | When | Dependencies |
|---------|------|-------------|
| Event log | Every `notify()` call | Filesystem write to `.jarvis/projects/{name}/events.jsonl` |
| Email | `build_completed`, `task_failed` | SMTP_HOST, SMTP_USER, NOTIFY_EMAIL env vars |
| Push (ntfy) | `build_completed`, `build_started`, `task_failed` | NTFY_TOPIC env var |
| Push (Pushover) | `build_completed`, `build_started`, `task_failed` | PUSHOVER_USER, PUSHOVER_TOKEN env vars |

### 7b. Who calls `notifier.notify()`

| Caller | File | Events |
|--------|------|--------|
| `ControlLoop._notify()` | `core/control_loop.py:152-161` | build_started, goal_interpreted, build_complete, validation_complete, build_done, retry, build_failed |

**DISCONNECTED** — `SupervisorNotifier` is called directly by `ControlLoop._notify()`. It has its own `register_ws/unregister_ws` (line 103-107) that manages its own WS client list. **Zero integration with EventBus.** No subscriber exists that would auto-trigger notifications on events.

---

## 8. Context Systems Comparison

### 8a. All Context Stores

| System | Class | File | Storage | Scope |
|--------|-------|------|---------|-------|
| **Worflow Context** | `ExecutionContext` | `core/workflow/context.py:9` | `WorkflowStore` (SQLite) | Per-workflow execution |
| **Execution Context** | `ExecutionContext` | `core/execution/context.py` | Transient | Per-request execution |
| **Project Context** | `ProjectContext` | `core/routing/project_context.py:65` | Transient (code index) | Per-workspace |
| **Session Context** | `SessionMemory` | `core/routing/project_context.py:52` | Transient | Per-session |
| **Shared Context** | `SharedContext` | `core/shared_context.py:29` | Filesystem (SHARED_CONTEXT.md) | Per-project |
| **Conversation** | `ConversationManager` | `core/session.py:40` | Filesystem (JSON) | Per-session |
| **Focus Mode** | `FocusMode` | `core/workflow/tracker.py:39` | Transient | Global busy/queue state |

### 8b. Context System Interconnections

```
ExecutionManager.create_context()
  ─→ core/execution/context.py (lightweight DTO with workflow_id, request_id, phase, status)
  ─→ passed to WorkflowEngine.start_workflow() as metadata

WorkflowEngine.ContextManager.create_context()
  ─→ core/workflow/context.py (full ExecutionContext with variables, artifacts, metadata)
  ─→ persisted to WorkflowStore (SQLite)

ControlLoop
  ─→ Creates SharedContext(project_name) for file-based context
  ─→ Creates ExecutionManager context for event traces
  ─→ Never connects to WorkflowEngine's ContextManager

AutomationLoop
  ─→ Uses ExecutionManager.create_context() for traces
  ─→ Uses self.execution_manager.engine (WorkflowEngine) for step execution
  ─→ WorkflowEngine creates its own context internally

PlannerStateMachine
  ─→ Creates ExecutionContext nodes for agent execution (core/agents/parallel_executor.py:97)
  ─→ Never uses WorkflowEngine's ContextManager
```

**DUPLICATE** — Two `ExecutionContext` classes with identical purpose:
1. `core/execution/context.py` — used by `ExecutionManager`, `ControlLoop`, `AutomationLoop`
2. `core/workflow/context.py` — used by `WorkflowEngine`, `ParallelAgentExecutor`

They share the same name but are different dataclasses with different fields.

### 8c. Context writes that are never read back

| Write | File | Line | Read by | Status |
|-------|------|------|---------|--------|
| `SharedContext.append()` | `core/shared_context.py:50` | Only by `SharedContext.read()` (never called by any other component) | **DISCONNECTED** |
| `ConversationManager` files | `core/session.py` | Only read by `ConversationManager.load()` (called by `agent_stream` WS handler) | CORRECT (single caller) |

---

## 9. Disconnected Paths Summary

| # | Path | From | To | Status |
|---|------|------|----|--------|
| 1 | Event types defined in `core/event_types.py` | 20 dataclasses | Zero publishers, zero subscribers | **DEAD CODE** |
| 2 | `register_default_subscribers()` events | `rag.*`, `memory.*`, `database.*` | Zero publishers | **DEAD SUBSCRIPTIONS** |
| 3 | `workflow.idempotency_hit` subscriber | Log subscriber | Published as `idempotency_hit` (no dot) | **NAME MISMATCH** |
| 4 | `ExecutionTracker` → `get_bus()` | Tracker events (`goal_*`, `node_*`) | `get_bus()` not connected to `global_event_bus` | **WRONG BUS** |
| 5 | `InboxStore` → `get_bus()` | Subscribes to `goal_*`, `node_*` | `get_bus()` not connected to `global_event_bus` | **WRONG BUS** |
| 6 | `progress_websocket` → `get_bus()` | `/ws/{session_id}` | Registers on `get_bus()`, not `global_event_bus` | **WRONG BUS** |
| 7 | `UnifiedBrain` → `global_event_bus` | `goal.*` (dot) | InboxStore listens for `goal_completed` (no dot) on different bus | **DOUBLY DISCONNECTED** |
| 8 | `WorkflowEngine` events | `workflow.*`, `step_*` | InboxStore does not subscribe | **MISSING INBOX PATH** |
| 9 | `ExecutionManager` events | `execution.*` | InboxStore does not subscribe | **MISSING INBOX PATH** |
| 10 | `SupervisorNotifier` | Notifications | Zero EventBus integration | **MANUAL-ONLY** |
| 11 | `SettingsStore` | `settings.changed` | `self.event_bus` is None in production | **NEVER FIRES** |
| 12 | PluginEventBus events | `on_*` hooks | All deprecation-wrapped | **DORMANT** |
| 13 | Inbox WS clients | `_ws_clients` | Only notified on POST /add, not on auto-insert | **MISSING BROADCAST** |
| 14 | Activity WS clients | `_ws_subscriptions` | Only broadcast from REST handlers, not EventBus | **MANUAL-ONLY** |

---

## 10. Missing Awaits

| File | Line | Code | Issue |
|------|------|------|-------|
| `core/event_bus.py:240` | `asyncio.ensure_future(self.publish(event))` | In `publish_sync()`, fire-and-forget when loop is running | No `await`, no exception capture — events silently dropped on handler failure (but exception is logged in `publish()`) |
| `core/event_bus.py:244` | `asyncio.create_task(self.publish(event))` | In `publish_sync()`, third fallback | Same as above |
| `core/event_bus.py:475` | `global_event_bus.publish_sync(ev)` | In `fire_event()` | `publish_sync` uses `ensure_future`/`create_task` — fire-and-forget |
| `core/plugins/base.py:673` | `asyncio.ensure_future(PluginEventBus.instance().emit(hook, **kwargs))` | Plugin hook emission | Fire-and-forget, no error handling |
| `channels/processor.py:51` | `asyncio.create_task(PluginEventBus.instance().emit(...))` | Channel message hook | Fire-and-forget |
| `brain/observers/observer_manager.py:56` | `await self.bus.publish(event)` | Observer publishing | ✅ CORRECT |
| `core/execution/manager.py:100` | `self._bus.publish_sync(event)` | ExecutionManager event | ✅ Uses `publish_sync` (fire-and-forget by design) |
| `core/scheduler/scheduler.py:449` | `global_event_bus.publish_sync(event)` | Scheduler tick | ✅ Fire-and-forget by design |

**FINDING:** All `publish_sync()` usages are intentionally fire-and-forget. The only concern is `PluginEventBus.emit()` calls that use `asyncio.create_task()` — these can be silently lost if the handler raises before the task runs.

---

## 11. Duplicate Bus Instances

| Instance | Singleton | Created at | Used by |
|----------|-----------|------------|---------|
| `global_event_bus` | `core/event_bus.py:294` | Import time | ExecutionManager, Scheduler, WorkflowStore, ObservationHub, ConfigurationService, UnifiedBrain, goal_generator, learning_engine, skill_acquisition, self_improvement, observers |
| `get_bus()` (legacy) | `core/event_bus.py:433` | First call | ExecutionTracker, InboxStore, progress_websocket |
| `PluginEventBus.instance()` | `core/event_bus.py:507` | First call | voice_pipeline, channels/processor, file_agent, sub_agent_base, memory/tiered_memory, website_generator, plugins/base, plugins/loader |

**Impact:**
- Events published to `global_event_bus` (WorkflowEngine, ExecutionManager) never reach `InboxStore`
- Events published to `get_bus()` (ExecutionTracker) never reach `UnifiedBrain`
- `progress_websocket` only sees events from `get_bus()`, missing all `workflow.*` and `execution.*` events
- `PluginEventBus` wraps `global_event_bus` but also maintains `_direct_handlers` — a second subscription system outside the canonical event bus

---

## 12. Cross-Cutting Summary

### Reality Scores

| Component | Score | Status |
|-----------|-------|--------|
| `WorkflowStore.append_event()` publishing | 10/10 | CORRECT |
| `global_event_bus` implementation | 9/10 | CORRECT |
| `ObservationHub` | 8/10 | CORRECT |
| `ExecutionManager` event publishing | 8/10 | CORRECT |
| `Scheduler` event publishing | 8/10 | CORRECT |
| `UnifiedBrain` subscriptions | 6/10 | CORRECT (self-contained) |
| `InboxStore` | 4/10 | DISCONNECTED (wrong bus) |
| `ExecutionTracker` | 4/10 | DISCONNECTED (wrong bus) |
| `core/event_types.py` | 1/10 | DEAD CODE |
| `get_bus()` legacy instance | 2/10 | DORMANT |
| `PluginEventBus` | 2/10 | DORMANT |
| `SupervisorNotifier` | 3/10 | DISCONNECTED |
| `SettingsStore` events | 2/10 | NEVER FIRES |
| Inbox WebSocket | 3/10 | MANUAL-ONLY |
| Activity WebSocket | 3/10 | MANUAL-ONLY |

### Priority Fix Candidates

1. **Kill `get_bus()`** — replace all `get_bus()` calls with `global_event_bus`. Affects: `ExecutionTracker`, `InboxStore`, `progress_websocket`, `workflow/events.py:emit`.

2. **Merge `ExecutionTracker` events** — publish `goal_*`/`node_*` to `global_event_bus` instead of `get_bus()`.

3. **Wire InboxStore to `global_event_bus`** — after #1 and #2, InboxStore automatically receives all workflow + execution events.

4. **Remove `core/event_types.py`** — all 20 dataclasses are unused dead code.

5. **Fix `register_default_subscribers()` event name** — `WORKFLOW_IDEMPOTENCY_HIT` is `"workflow.idempotency_hit"` but WorkflowStore publishes `"idempotency_hit"`.

6. **Wire SupervisorNotifier to EventBus** — add a subscriber that calls `notifier.notify()` on relevant events.

7. **Wire Inbox/Activity WebSockets through EventBus** — replace manual `_ws_clients`/`_ws_subscriptions` with `EventBus.register_ws()`.
