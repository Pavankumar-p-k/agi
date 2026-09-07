# Event Flow Audit — Phase 5 (Document 12)

> **Purpose:** Catalog every event type, publisher, subscriber, and event bus in the system. Identify dropped events, duplicate event types, and subscription failures.
>
> **Scope:** All event systems: canonical EventBus (`core/event_bus.py`), PluginEventBus (`plugin_system/core.py`), Runtime protocol (`core/runtime.py`), and ad-hoc event-like callbacks.

---

## Table of Contents

1. [Event Bus Architectures Overview](#1-event-bus-architectures-overview)
2. [Canonical EventBus (core/event_bus.py)](#2-canonical-eventbus-coreevent_buspy)
3. [PluginEventBus (plugin_system/core.py)](#3-plugineventbus-plugin_systemcorepy)
4. [Runtime Protocol (core/runtime.py)](#4-runtime-protocol-coreruntimepy)
5. [Event Catalog](#5-event-catalog)
6. [Publisher Inventory](#6-publisher-inventory)
7. [Subscriber Inventory](#7-subscriber-inventory)
8. [Dropped Event Analysis](#8-dropped-event-analysis)
9. [Duplicate Event Analysis](#9-duplicate-event-analysis)
10. [Findings & Recommendations](#10-findings--recommendations)

---

## 1. Event Bus Architectures Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        THREE EVENT BUSES                             │
├─────────────────┬───────────────────┬───────────────────────────────┤
│  Canonical      │  PluginEventBus   │  Runtime protocol             │
│  EventBus       │                   │                               │
├─────────────────┼───────────────────┼───────────────────────────────┤
│ Location:       │ Location:         │ Location:                     │
│ core/event_bus  │ plugin_system/    │ core/runtime.py               │
│ .py             │ core.py           │                               │
│                 │                   │                               │
│ Pattern:        │ Pattern:          │ Pattern:                      │
│ Observer        │ Adapter           │ Direct call                   │
│                 │ (wraps EventBus   │ (lifecycle hooks)             │
│                 │ for plugin        │                               │
│                 │ isolation)        │                               │
│                 │                   │                               │
│ Subscription:   │ Subscription:     │ Subscription:                 │
│ event_bus.on    │ plugin.on(        │ RuntimeProtocol               │
│ ("event.*",     │ "event", cb)      │ .on_start, .on_stop,         │
│ callback)       │                   │ .on_config_change             │
│                 │ (no wildcard)     │                               │
│                 │                   │                               │
│ Wildcard:       │ Wildcard:         │ Wildcard:                     │
│ Supported       │ NOT supported     │ N/A (explicit event types)    │
│ (*, **)         │                   │                               │
└─────────────────┴───────────────────┴───────────────────────────────┘
```

---

## 2. Canonical EventBus (`core/event_bus.py`)

### Architecture

```python
class Event:
    type: str          # "memory.stored", "workflow.started", etc.
    data: dict         # Event payload
    timestamp: float   # time.time()
    source: str        # Module name or "system"
    id: str            # uuid4 hex
    correlation_id: str|None  # For chaining related events

class EventBus:
    _subscribers: dict[str, list[Callable]]  # topic → [subscriber, ...]
    _global_subscribers: list[Callable]       # Subscribe to ALL events
    _wildcard_cache: dict[str, list[str]]     # Cache compiled wildcard matches
```

### Subscription Pattern

```
subscribe("memory.stored", cb)      → Direct match
subscribe("memory.*", cb)           → Wildcard, matches memory.{anything}
subscribe("memory.**", cb)          → Multi-level wildcard
subscribe("*", cb)                  → ALL events (added to _global_subscribers)
```

### Publishing Pattern

```python
event_bus.emit("memory.stored", {"memory_id": id, "content": text, ...})
  → locks _subscribers → finds matching topics (direct + wildcard) → notifies all
  → locks _global_subscribers → notifies all
```

### Known Issues

1. **No async support** — callbacks are synchronous. A slow subscriber blocks all others.
2. **No error isolation** — one subscriber exception kills the entire emit sequence.
3. **No delivery guarantees** — fire-and-forget. If no subscriber is registered at emit time, the event is lost.
4. **No ordering guarantee** — subscriber iteration order is dict insertion order, which depends on registration order.

---

## 3. PluginEventBus (`plugin_system/core.py`)

### Architecture

```python
class PluginEventBus:
    _bus: EventBus            # Wraps canonical EventBus
    _plugin_subscribers: dict  # plugin_id → [(event_type, callback)]

    def emit(self, event_type: str, data: dict, source_plugin: str = None):
        self._bus.emit(event_type, data)  # Delegates to canonical bus

    def subscribe_plugin(self, plugin_id: str, event_type: str, callback: Callable):
        managed callback with plugin_id → lifecycle cleanup
```

### Key Difference from Canonical EventBus

- **Plugin isolation**: subscriptions are tracked per plugin. When a plugin is unloaded, all its subscribers are automatically removed.
- **No wildcard support**: plugin events must match exact topic strings.
- **Purpose**: shields the canonical EventBus from plugin lifecycle side effects.

### Known Issues

1. **Plugin events mixed with system events** on the same canonical bus — no namespace isolation.
2. **No wildcard** makes it harder for plugins to subscribe broadly.

---

## 4. Runtime Protocol (`core/runtime.py`)

### Architecture

```python
class RuntimeProtocol(Protocol):
    def on_start(self, runtime: "AppRuntime") -> None: ...
    def on_stop(self, runtime: "AppRuntime") -> None: ...
    def on_config_change(self, runtime: "AppRuntime", key: str, value: Any) -> None: ...

class AppRuntime:
    _protocols: list[RuntimeProtocol]
    start() → for p in _protocols: p.on_start(self)
    stop()  → for p in _protocols: p.on_stop(self)
    _process_config_change(key, value) → for p in _protocols: p.on_config_change(self, key, value)
```

### Relationship to EventBus

- `Runtime.on_config_change()` is called **before** the canonical EventBus emits `"config.changed"`.
- The Runtime protocol is for **critical lifecycle hooks** (start/stop); EventBus is for **operational events** (stored, completed).
- There is **no defined ordering** between Runtime protocol notification and EventBus event for the same change.

---

## 5. Event Catalog

### 5.1 Conversation/RAG Events (8 events)

| Event Type | Publisher | Payload | Subscribers |
|-----------|-----------|---------|-------------|
| `chat.requested` | process_message() | {input, user_id, session_id, request_id} | Telemetry, AuditLogger, usage tracking |
| `chat.completed` | process_message() | {request_id, duration_ms, tokens, output_length} | Telemetry, AuditLogger |
| `chat.failed` | process_message() | {request_id, error, stage} | Telemetry, AuditLogger |
| `rag.documents_retrieved` | RAGContext.get_relevant() | {query, documents, scores} | Telemetry |
| `rag.document_scored` | RAGSystem._score_doc() | {doc_id, score, reason} | Telemetry |
| `rag.relevance_feedback` | External feedback endpoint | {query, doc_id, rating} | LearningSystem |
| `conversation.started` | SessionService.create() | {session_id, user_id, timestamp} | Session tracking |
| `conversation.ended` | SessionService.close() | {session_id, duration, message_count} | Session tracking |

### 5.2 Memory Events (8 events)

| Event Type | Publisher | Payload | Subscribers |
|-----------|-----------|---------|-------------|
| `memory.stored` | MemoryFacade.store() | {memory_id, content, user_id, memory_type} | IndexUpdate, FactExtraction |
| `memory.facts_extracted` | FactExtraction pipeline | {fact_ids, memory_id, count} | FactIndex |
| `memory.consolidation.requested` | Memory Consolidator | {memory_id, target_tier} | Memory tiers |
| `memory.consolidation.completed` | Memory tiers | {memory_id, source, target} | Monitoring |
| `memory.index_updated` | IndexService | {index_name, entries_added, entries_removed} | SearchIndex |
| `memory.pruned` | MemoryPruner | {tier, entries_removed, bytes_freed} | Monitoring, Telemetry |
| `memory.fact_stored` | FactStore.store_facts() | {fact_ids, category, count} | PreferenceProfile, Telemetry |
| `memory.fact_conflict` | FactStore._dedup() | {existing_fact, incoming_fact, resolution} | AuditLogger |

### 5.3 Workflow Events (10 events)

| Event Type | Publisher | Payload | Subscribers |
|-----------|-----------|---------|-------------|
| `workflow.started` | WorkflowEngine.start() | {workflow_id, type, input, user_id} | AuditLogger, Telemetry, Scheduler |
| `workflow.completed` | WorkflowEngine.complete() | {workflow_id, output, duration, steps_completed} | AuditLogger, Telemetry, Notification |
| `workflow.failed` | WorkflowEngine.fail() | {workflow_id, error, failed_step} | AuditLogger, Telemetry, Notification |
| `workflow.step_started` | WorkflowEngine._execute() | {workflow_id, step_id, step_name} | AuditLogger, ProgressTracker |
| `workflow.step_completed` | WorkflowEngine._step_done() | {workflow_id, step_id, result, duration} | AuditLogger, ProgressTracker |
| `workflow.step_failed` | WorkflowEngine._step_error() | {workflow_id, step_id, error, retry_count} | AuditLogger, RetryHandler |
| `workflow.paused` | WorkflowEngine.pause() | {workflow_id, reason, current_step} | Scheduler, Notification |
| `workflow.resumed` | WorkflowEngine.resume() | {workflow_id, previous_state} | Scheduler |
| `workflow.cancelled` | WorkflowEngine.cancel() | {workflow_id, reason, steps_completed} | Scheduler, Notification |
| `workflow.idempotency_hit` | WorkflowEngine.check() | {workflow_id, idempotency_key, cached_result} | Monitoring |

### 5.4 Goal/Plan Events (6 events)

| Event Type | Publisher | Payload | Subscribers |
|-----------|-----------|---------|-------------|
| `goal.created` | GoalService.create_goal() | {goal_id, description, user_id} | Planner, Notifications |
| `goal.decomposed` | GoalDecomposer.decompose() | {goal_id, sub_goal_count, tree_depth} | Planner |
| `goal.completed` | GoalService.complete_goal() | {goal_id, result, duration} | Notifications, AuditLogger |
| `goal.failed` | GoalService.fail_goal() | {goal_id, error, partial_results} | Notifications, AuditLogger |
| `goal.assigned` | PlannerExecutor | {goal_id, agent_id, steps} | AgentRuntime |
| `plan.created` | PlanStore.create_plan() | {plan_id, goal_id, step_count, root_node} | ExecutionEngine |

### 5.5 Identity/Auth Events (7 events)

| Event Type | Publisher | Payload | Subscribers |
|-----------|-----------|---------|-------------|
| `auth.user_created` | AuthManager.init() | {user_id, username, timestamp} | AuditLogger, Notification |
| `auth.user_authenticated` | AuthManager.validate() | {user_id, session_id, roles} | AuditLogger, Telemetry |
| `auth.user_authorized` | AuthorizationEngine | {user_id, scope, resource, decision} | AuditLogger |
| `auth.authorization_failed` | AuthorizationEngine | {user_id, scope, resource, reason} | AuditLogger |
| `auth.session_created` | AuthManager.validate() | {session_id, user_id, expiry} | Telemetry |
| `auth.session_expired` | AuthManager.validate() | {session_id, user_id} | CleanupService |
| `auth.token_revoked` | AuthManager.revoke() | {session_id, user_id, reason} | AuditLogger |

### 5.6 Configuration Events (4 events)

| Event Type | Publisher | Payload | Subscribers |
|-----------|-----------|---------|-------------|
| `config.changed` | ConfigurationService.set() | {key, old_value, new_value, source} | SettingsStore, PluginManager, RuntimeProtocol |
| `config.reloaded` | ConfigurationService.load() | {config_file, keys_count} | Monitoring |
| `config.validation_error` | ConfigurationService.validate() | {key, value, error} | AuditLogger |
| `config.schema_changed` | ConfigSchema.update() | {schema_name, version, changes} | MigrationService |

### 5.7 Plugin Events (6 events)

| Event Type | Publisher | Payload | Subscribers |
|-----------|-----------|---------|-------------|
| `plugin.loaded` | PluginManager._load() | {plugin_id, name, version, dependencies} | Registry, DependencyResolver |
| `plugin.unloaded` | PluginManager._unload() | {plugin_id, reason} | Registry, CleanupService |
| `plugin.enabled` | PluginManager.enable() | {plugin_id} | Registry |
| `plugin.disabled` | PluginManager.disable() | {plugin_id} | Registry |
| `plugin.error` | PluginManager._exec() | {plugin_id, error, context} | AuditLogger, Monitoring |
| `plugin.event_emitted` | PluginEventBus.emit() | {plugin_id, event_type, data} | PluginEventBus (logging) |

### 5.8 System Events (12 events)

| Event Type | Publisher | Payload | Subscribers |
|-----------|-----------|---------|-------------|
| `system.startup` | AppRuntime.start() | {startup_time, version, plugins_count} | All protocol handlers, Monitoring |
| `system.shutdown` | AppRuntime.stop() | {uptime, reason, active_workflows} | All protocol handlers, Monitoring |
| `system.health_check` | HealthService.check() | {status, components, latency} | Monitoring |
| `system.component_failed` | HealthService.monitor() | {component, error, recovery_action} | AuditLogger, Notification |
| `system.component_recovered` | HealthService.monitor() | {component, downtime_ms} | AuditLogger, Notification |
| `system.resource_warning` | ResourceMonitor | {resource, usage_pct, threshold} | ScalingService, Notification |
| `system.resource_critical` | ResourceMonitor | {resource, usage_pct} | AlertService |
| `system.task_scheduled` | Scheduler | {task_id, cron, next_run} | AuditLogger |
| `system.task_executed` | Scheduler | {task_id, duration, success} | AuditLogger |
| `system.error` | Global error handler | {error_type, module, traceback} | AuditLogger, Telemetry |
| `system.warning` | Global warning handler | {warning_type, module, message} | AuditLogger |
| `system.metrics` | MetricsCollector | {metric_name, value, tags} | Telemetry |

### 5.9 Tool/Execution Events (10 events)

| Event Type | Publisher | Payload | Subscribers |
|-----------|-----------|---------|-------------|
| `tool.execution_started` | tool_factory | {tool_name, input, agent_id} | AuditLogger, Telemetry |
| `tool.execution_completed` | tool_factory | {tool_name, output, duration, success} | AuditLogger, Telemetry |
| `tool.execution_failed` | tool_factory | {tool_name, error, stage} | AuditLogger, RetryHandler |
| `tool.blocklisted` | execution.py | {tool_name, reason, user_id} | AuditLogger |
| `tool.capability_checked` | CapabilityRegistry | {tool_name, capability, allowed} | AuditLogger |
| `tool.timeout` | execution.py | {tool_name, timeout_seconds} | AuditLogger, Telemetry |
| `tool.retry` | RetryHandler | {tool_name, attempt, max_retries} | AuditLogger |
| `tool.compensation` | CompensationHandler | {tool_name, compensation, result} | AuditLogger |
| `pipeline.stage_started` | pipeline.py | {stage_name, request_id, timestamp} | Telemetry |
| `pipeline.stage_completed` | pipeline.py | {stage_name, request_id, duration_ms} | Telemetry |

### 5.10 Storage Events (8 events)

| Event Type | Publisher | Payload | Subscribers |
|-----------|-----------|---------|-------------|
| `database.connection_pooled` | DatabaseManager | {db_name, pool_size, active_connections} | Monitoring |
| `database.migration_run` | Alembic runner | {migration_id, revision, tables_affected} | AuditLogger |
| `database.migration_failed` | Alembic runner | {migration_id, revision, error} | AuditLogger |
| `database.backup_started` | BackupService | {db_name, target_path} | Monitoring |
| `database.backup_completed` | BackupService | {db_name, target_path, size_mb} | Monitoring |
| `database.backup_failed` | BackupService | {db_name, error} | AuditLogger |
| `database.cleanup_started` | CleanupService | {db_name, older_than_days} | Monitoring |
| `database.cleanup_completed` | CleanupService | {db_name, rows_removed, bytes_freed} | Monitoring |

---

## 6. Publisher Inventory

| Module | Events Published | to Which Bus |
|--------|-----------------|--------------|
| `core/pipeline.py` | `chat.requested`, `chat.completed`, `chat.failed`, `pipeline.stage_*` | Canonical EventBus |
| `core/event_bus.py` | System-level events | Canonical EventBus |
| `memory/memory_facade.py` | `memory.stored`, `memory.consolidation.*` | Canonical EventBus |
| `memory/fact_store.py` | `memory.fact_stored`, `memory.fact_conflict` | Canonical EventBus |
| `workflow/engine.py` | `workflow.*`, `workflow.step_*`, `workflow.idempotency_hit` | Canonical EventBus |
| `planner/service.py` | `goal.*`, `plan.created` | Canonical EventBus |
| `auth/manager.py` | `auth.*` | Canonical EventBus |
| `configuration/service.py` | `config.changed` | Canonical EventBus |
| `plugin_system/core.py` | `plugin.*`, `plugin.event_emitted` | Canonical EventBus |
| `core/tools/execution.py` | `tool.*`, `tool.blocklisted`, `tool.capability_checked` | Canonical EventBus |
| `core/runtime.py` | `system.startup`, `system.shutdown` (via protocol) | RuntimeProtocol + EventBus |
| `core/monitoring/` | `system.resource_*`, `system.metrics` | Canonical EventBus |
| `core/scheduler/` | `system.task_*` | Canonical EventBus |
| `core/database/` | `database.*` | Canonical EventBus |
| `RAGContext` | `rag.*` | Canonical EventBus |
| `SessionService` | `conversation.*` | Canonical EventBus |

---

## 7. Subscriber Inventory

| Module | Events Subscribed | Purpose |
|--------|------------------|---------|
| AuditLogger | `auth.*`, `workflow.*`, `goal.*`, `system.error`, `system.warning`, `tool.*` | Persist audit trail |
| Telemetry | `chat.*`, `pipeline.stage_*`, `memory.*`, `workflow.*`, `tool.*`, `auth.*` | Metrics collection |
| NotificationService | `workflow.completed`, `workflow.failed`, `goal.*`, `system.resource_*` | User/operator alerts |
| Scheduler | `workflow.started`, `workflow.paused`, `workflow.resumed` | Workflow lifecycle management |
| CleanupService | `auth.session_expired` | Clean expired sessions |
| IndexService | `memory.stored` | Update search index |
| Memory Consolidator | `memory.consolidation.requested` | Move between tiers |
| PreferenceProfile | `memory.fact_stored` (category=preference) | Rebuild preferences |
| FactExtraction pipeline | `memory.stored` | Extract facts from stored memory |
| Plugin loading... | Events | Lifecycle management |
| RetryHandler | `workflow.step_failed`, `tool.execution_failed` | Automatic retries |
| ProgressTracker | `workflow.step_started`, `workflow.step_completed` | Real-time progress |
| ScalingService | `system.resource_warning` | Auto-scaling decisions |
| AlertService | `system.resource_critical` | Pager/alert routing |
| SettingsStore | `config.changed` | Persist config changes |
| MigrationService | `config.schema_changed` | Data migration triggers |
| RuntimeProtocol handlers | `system.startup`, `system.shutdown`, `config.changed` | Lifecycle |
| LearningSystem | `rag.relevance_feedback` | Learning from feedback |
| Registry | `plugin.*` | Plugin registry maintenance |

---

## 8. Dropped Event Analysis

Events that are published but have **zero subscribers**:

| Event Type | Publisher | Why It's Dropped |
|-----------|-----------|-----------------|
| `rag.documents_retrieved` | RAGContext | No subscriber registered — telemetry doesn't subscribe to this |
| `rag.document_scored` | RAGSystem | No subscriber registered |
| `rag.relevance_feedback` | External endpoint | No subscriber registered — LearningSystem doesn't exist yet |
| `workflow.idempotency_hit` | WorkflowEngine | No subscriber registered |
| `config.validation_error` | ConfigurationService | No subscriber registered — worth monitoring |
| `memory.fact_conflict` | FactStore | No subscriber registered — AuditLogger missing this subscription |
| `memory.index_updated` | IndexService | No subscriber registered — Telemetry should track this |
| `database.connection_pooled` | DatabaseManager | No subscriber registered |

### Impact of Dropped Events

- **`rag.*` events**: Telemetry gaps for RAG performance monitoring. Cannot diagnose slow retrievals.
- **`workflow.idempotency_hit`**: No visibility into how often idempotency keys prevent duplicate execution.
- **`config.validation_error`**: Silent config errors. If a user sets an invalid value, nobody knows.
- **`memory.fact_conflict`**: Silent fact dedup conflicts. Resolution logic may break without notification.

---

## 9. Duplicate Event Analysis

Events that overlap in meaning with different names:

| Event A | Event B | Difference | Should Merge? |
|---------|---------|-----------|---------------|
| `memory.stored` | `memory.consolidation.completed` | Different trigger points | Keep separate |
| `workflow.completed` | `goal.completed` | Different granularity (workflow vs goal) | Keep separate |
| `chat.requested` | `conversation.started` | Chat is request-level, conversation is session-level | Keep separate |
| `auth.session_created` | `auth.user_authenticated` | Fired simultaneously for same action | **Yes — merge into `auth.session_established`** |
| `auth.session_expired` | `auth.token_revoked` | Different triggers (timeout vs manual) | Keep separate |
| `system.error` | `tool.execution_failed` | Different scope (global vs tool) | Keep separate |
| `pipeline.stage_started` + `pipeline.stage_completed` | Not duplicated | Unique pair | Keep |

---

## 10. Findings & Recommendations

### F-1: Three Event Systems Must Be Unified

The canonical EventBus, PluginEventBus, and Runtime protocol represent three different approaches to the same problem. PluginEventBus is a thin adapter over the canonical bus.

**R-1:** Standardize on the canonical EventBus. Fold PluginEventBus into it with a `namespace` concept (`system.*`, `plugin.*`). Make Runtime protocol handlers register as normal EventBus subscribers for startup/shutdown/config events. This eliminates the ordering ambiguity between Runtime protocol and EventBus configuration notification.

### F-2: No Error Isolation in EventBus

A single subscriber exception crashes the entire emit sequence, dropping events for all other subscribers of the same topic.

**R-2:** Wrap each subscriber call in a try/except. Log the exception but continue iterating. Add a `subscriber_error` metric.

### F-3: No Delivery Guarantees

Events are fire-and-forget. If an event is emitted before a subscriber registers, or while a subscriber is processing a previous event, the event is lost.

**R-3:** Implement an internal event queue. Use `asyncio` for async subscriber dispatch. This also solves the synchronous-blocking problem.

### F-4: No Event Schema Validation

Payload data is untyped `dict`. There's no enforcement that `workflow.started` carries a `workflow_id` string.

**R-4:** Define typed Pydantic models for each event type. Validate payload on both emission and subscription sides.

### F-5: 8 Events Currently Dropped

`rag.*`, `workflow.idempotency_hit`, `config.validation_error`, `memory.fact_conflict`, `memory.index_updated`, `database.connection_pooled` are published but have zero subscribers.

**R-5:** Register subscribers for these events. At minimum: Telemetry for `rag.*`, `workflow.idempotency_hit`, `memory.index_updated`; AuditLogger for `config.validation_error`, `memory.fact_conflict`; Monitoring for `database.connection_pooled`.

### F-6: `auth.session_created` + `auth.user_authenticated` Fire Simultaneously

These two events fire at the same call site with the same payload. This creates unnecessary event noise.

**R-6:** Merge into `auth.session_established`.

### F-7: Plugin Events Pollute System Event Namespace

`plugin.event_emitted` and system events like `workflow.started` share the same EventBus with no namespace isolation. A plugin could subscribe to `workflow.*` and receive system workflow events.

**R-7:** Implement namespace prefixes enforced by the EventBus: `system.workflow.started`, `plugin.{plugin_id}.event_type`. Prevent plugins from subscribing to `system.*` events by default.

### F-8: Runtime Protocol and EventBus Dual Notification for Config Changes

`config.changed` fires twice: once through Runtime protocol (`on_config_change`) and once through EventBus (`config.changed`). The order is Runtime → EventBus, but there's no guarantee this won't change.

**R-8:** Unify into EventBus only. Make Runtime protocol handlers subscribe to `config.changed` on the canonical EventBus.
