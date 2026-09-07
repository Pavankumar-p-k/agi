# EVENTBUS AND CONTEXT AUDIT — MJ Architecture

**Generated:** 2026-07-18  
**Scope:** Complete event system audit — every EventBus, every event, every publisher, every subscriber, every context write.

---

## 1. EVENT BUS INVENTORY

| Bus | File | Status | Purpose |
|-----|------|--------|---------|
| `global_event_bus` | `core/event_bus.py` | **CANONICAL** | Central async event bus for all system events |
| `PluginEventBus` | `core/event_bus.py:506` | **DEPRECATED** | Legacy adapter, routes to `global_event_bus` with `namespace="plugin"` |
| `get_bus()` / `get_bus()` | `core/event_bus.py:447` | **LEGACY** | Returns legacy singleton, use `global_event_bus` directly |
| `EventBus` (local) | `core/workflow/events.py` | **WORKFLOW-LOCAL** | Workflow-specific events, NOT connected to global bus |
| `ObservationHub` | `core/observation/hub.py` | **ACTIVE** | Publishes `observation.observed` via `global_event_bus` |
| `PluginEventBus` | `core/event_bus.py:506` | **DEPRECATED** | Legacy plugin event adapter |

---

## 2. EVENT TAXONOMY (All Event Types)

### Core System Events
| Event Type | Source | Namespace | Payload |
|---|---|---|---|
| `config.changed` | `ConfigurationService.set()` | `system` | `{key, value}` |
| `config.reloaded` | `ConfigurationService.load()` | `system` | `{}` |
| `config.validation_error` | `ConfigurationService` | `system` | `{key, error}` |

### RAG Events
| Event Type | Source | Namespace | Payload |
|---|---|---|---|
| `rag.documents_retrieved` | RAG pipeline | `system` | `{query, results, count}` |
| `rag.document_scored` | RAG pipeline | `system` | `{doc_id, score}` |
| `rag.relevance_feedback` | User feedback | `system` | `{doc_id, relevant}` |

### Workflow Events
| Event Type | Source | Namespace | Payload |
|---|---|---|---|
| `workflow.idempotency_hit` | `WorkflowEngine` | `system` | `{workflow_id, step_id, cached}` |

### Memory Events
| Event Type | Source | Namespace | Payload |
|---|---|---|---|
| `memory.fact_conflict` | `SemanticStore` | `system` | `{fact_id, old, new}` |
| `memory.index_updated` | `SemanticStore` | `system` | `{collection, count}` |

### Database Events
| Event Type | Source | Namespace | Payload |
|---|---|---|---|
| `database.connection_pooled` | DB pool | `system` | `{pool_size, active}` |

### Config Events
| Event Type | Source | Payload |
|---|---|---|
| `config.changed` | `ConfigurationService.set()` | `{key, value}` |
| `config.reloaded` | `ConfigurationService.load()` | `{}` |
| `config.validation_error` | Validation | `{key, error}` |

### Workflow Events (Legacy — `core/workflow/events.py`)
| Event Type | Trigger | Payload |
|---|---|---|
| `workflow_started` | `WorkflowEngine.start_workflow()` | `{workflow_type, step_count}` |
| `workflow_resumed` | `WorkflowEngine.resume_workflow()` | `{workflow_id}` |
| `step_started` | `_execute_step()` | `{step_id, tool_name}` |
| `step_completed` | `_execute_step()` success | `{step_id, tool_name}` |
| `step_failed` | `_execute_step()` error | `{step_id, tool_name, error}` |
| `workflow_completed` | `_run_workflow()` success | `{elapsed_seconds}` |
| `workflow_failed` | `_run_workflow()` error | `{step_index, tool_name, error}` |
| `workflow_cancelled` | `cancel_workflow()` | `{current_step}` |
| `workflow_recovered` | `recover_active_workflows()` | `{}` |
| `compensation_started` | `_compensate_workflow()` | `{step_count}` |
| `compensation_step_started` | `_compensate_workflow()` | `{step_id, tool_name}` |
| `compensation_step_completed` | compensation success | `{step_id, tool_name}` |
| `compensation_step_failed` | compensation error | `{step_id, tool_name, error}` |
| `workflow_compensated` | compensation complete | `{compensated_steps}` |
| `compensation_failed` | compensation error | `{step_id, error}` |
| `idempotency_hit` | `_execute_step()` cache hit | `{step_id, cached_step_id, tool_name}` |

### Build Events
| Event Type | Source | Payload |
|---|---|---|
| `build.started` | `BuildService._handle_build_started()` | `{goal, project}` |
| `build.completed` | `BuildService._run_project()` success | `{project, goal}` |
| `build.failed` | `BuildService._run_project()` error | `{project, goal, error}` |
| `build.fix_requested` | `BuildService` retry | `{project, goal}` |

### Execution Trace Events
| Event Type | Source | Payload |
|---|---|---|
| `execution.trace` | `ExecutionManager.record_trace()` | `{action_name, params, observation, success, duration_ms, task_id, tags, user_id}` |
| `execution.decision` | `ExecutionManager.record_decision()` | `{context, decision, outcome, success}` |

### Observation Events
| Event Type | Source | Payload |
|---|---|---|
| `observation.observed` | `ObservationHub.publish_observation()` | `Observation.to_dict()` |
| `observation.created` | `ObservationHub` | `Observation.to_dict()` |

### RAG Events
| Event Type | Source | Payload |
|---|---|---|
| `rag.documents_retrieved` | RAG pipeline | `{query, results, count}` |
| `rag.document_scored` | RAG pipeline | `{doc_id, score}` |
| `rag.relevance_feedback` | User feedback | `{doc_id, relevant}` |

### Build Events
| Event Type | Source | Payload |
|---|---|---|
| `build.started` | `BuildService._handle_build_started` | `{goal, project}` |
| `build.completed` | `BuildService._run_project()` success | `{project, goal}` |
| `build.failed` | `BuildService._run_project()` error | `{project, goal, error}` |
| `build.fix_requested` | `BuildService` retry | `{project, goal}` |

### Workflow Events (Unified)
| Event Type | Source | Payload |
|---|---|---|
| `workflow.started` | `WorkflowEngine.start_workflow()` | `{workflow_type, step_count}` |
| `workflow.resumed` | `WorkflowEngine.resume_workflow()` | `{workflow_id}` |
| `step.started` | `_execute_step()` | `{step_id, tool_name}` |
| `step.completed` | `_execute_step()` success | `{step_id, tool_name}` |
| `step.failed` | `_execute_step()` error | `{step_id, tool_name, error}` |
| `workflow.completed` | `_run_workflow()` success | `{elapsed_seconds}` |
| `workflow.failed` | `_run_workflow()` error | `{step_index, tool_name, error}` |
| `workflow.cancelled` | `cancel_workflow()` | `{current_step}` |
| `workflow.recovered` | `recover_active_workflows()` | `{}` |
| `compensation.started` | `_compensate_workflow()` | `{step_count}` |
| `compensation.step_started` | `_compensate_workflow()` | `{step_id, tool_name}` |
| `compensation.step_completed` | compensation success | `{step_id, tool_name}` |
| `compensation.step_failed` | compensation error | `{step_id, tool_name, error}` |
| `workflow.compensated` | compensation complete | `{compensated_steps}` |
| `compensation.failed` | compensation error | `{step_id, error}` |
| `idempotency_hit` | `_execute_step()` cache hit | `{step_id, cached_step_id, tool_name}` |

### Activity Events
| Event Type | Source | Payload |
|---|---|---|
| `activity.started` | `Scheduler._run_worker()` | `{activity_id, node_type, goal}` |
| `activity.resumed` | `ResumeEngine.mark_resumed()` | `activity_id` |
| `activity.executing` | `Scheduler._run_worker()` | `activity_id` |
| `activity.completed` | `Scheduler._run_worker()` success | `{activity_id, node_type, goal}` |
| `activity.failed` | `Scheduler._run_worker()` error | `{activity_id, error}` |
| `activity.resumed` | `ResumeEngine.mark_resumed()` | `activity_id` |
| `activity.cancelled` | task cancelled | `activity_id` |
| `scheduler.tick` | `Scheduler.tick()` | `{tick, activity_id, launched}` |

### Build Events
| Event Type | Source | Payload |
|---|---|---|
| `build.started` | `BuildService._handle_build_started` | `{goal, project}` |
| `build.completed` | `BuildService._run_project()` success | `{project, goal}` |
| `build.failed` | `BuildService._run_project()` error | `{project, goal, error}` |
| `build.fix_requested` | BuildService retry | `{project, goal}` |

### Execution Trace/Decision Events
| Event Type | Source | Payload |
|---|---|---|
| `execution.trace` | `ExecutionManager.record_trace()` | `{action_name, params, observation, success, duration_ms, task_id, tags, user_id}` |
| `execution.decision` | `ExecutionManager.record_decision()` | `{context, decision, outcome, success}` |

### Observation Events
| Event Type | Source | Payload |
|---|---|---|
| `observation.observed` | `ObservationHub.publish_observation()` | `Observation.to_dict()` |
| `observation.created` | `ObservationHub` | `Observation.to_dict()` |

### Activity Events
| Event Type | Source | Payload |
|---|---|---|
| `activity.started` | `Scheduler._run_worker()` | `{activity_id, node_type, goal}` |
| `activity.resumed` | `ResumeEngine.mark_resumed()` | `activity_id` |
| `activity.executing` | `Scheduler._run_worker()` | `{activity_id, node_type, goal}` |
| `activity.completed` | `_run_worker()` success | `{activity_id, node_type, goal}` |
| `activity.failed` | `_run_worker()` error | `{activity_id, error}` |
| `activity.resumed` | `ResumeEngine.mark_resumed()` | `activity_id` |

### Scheduler Events
| Event Type | Source | Payload |
|---|---|---|
| `scheduler.tick` | `Scheduler._fire_tick_callbacks()` | `{tick, activity_id, executed, launched, error, duration_ms, running_count}` |
| `scheduler.started` | `Scheduler.start()` | `{tick_interval, max_workers}` |
| `scheduler.paused` | `Scheduler.pause()` | `running_count` |
| `scheduler.resumed` | `Scheduler.resume()` | — |
| `scheduler.tick` | `_fire_tick_callbacks()` | `{tick, activity_id, launched}` |
| `activity.started` | `Scheduler._run_worker()` | `{activity_id, node_type, goal}` |
| `activity.executing` | `_run_worker()` | `{activity_id, node_type, goal}` |
| `activity.completed` | `_run_worker()` success | `{activity_id, node_type, goal}` |
| `activity.failed` | `_run_worker()` error | `{activity_id, error}` |
| `activity.resumed` | `ResumeEngine.mark_resumed()` | `activity_id` |
| `activity.cancelled` | Task cancelled | `activity_id` |

### RAG Events
| Event Type | Source | Payload |
|---|---|---|
| `rag.documents_retrieved` | RAG pipeline | `{query, results, count}` |
| `rag.document_scored` | RAG pipeline | `{doc_id, score}` |
| `rag.relevance_feedback` | User feedback | `{doc_id, relevant}` |

### Workflow Events (Unified)
| Event Type | Source | Payload |
|---|---|---|
| `workflow.started` | `WorkflowEngine.start_workflow()` | `{workflow_type, step_count}` |
| `workflow.resumed` | `WorkflowEngine.resume_workflow()` | `{workflow_id}` |
| `step.started` | `_execute_step()` | `{step_id, tool_name}` |
| `step.completed` | `_execute_step()` success | `{step_id, tool_name}` |
| `step.failed` | `_execute_step()` error | `{step_id, tool_name, error}` |
| `workflow.completed` | `_run_workflow()` success | `{elapsed_seconds}` |
| `workflow.failed` | `_run_workflow()` error | `{step_index, tool_name, error}` |
| `workflow.cancelled` | `cancel_workflow()` | `{current_step}` |
| `workflow.recovered` | `recover_active_workflows()` | `{}` |
| `compensation.started` | `_compensate_workflow()` | `{step_count}` |
| `compensation.step_started` | `_compensate_workflow()` | `{step_id, original_tool, compensation_tool}` |
| `compensation.step_completed` | compensation success | `{step_id, compensation_tool}` |
| `compensation.step_failed` | compensation error | `{step_id, compensation_tool, error}` |
| `workflow.compensated` | compensation complete | `{compensated_steps}` |
| `compensation.failed` | compensation error | `{step_id, compensation_tool, error}` |
| `idempotency_hit` | `_execute_step()` cache hit | `{step_id, cached_step_id, tool_name}` |

### Execution Trace/Decision Events
| Event Type | Source | Payload |
|---|---|---|
| `execution.trace` | `ExecutionManager.record_trace()` | `{action_name, params, observation, success, duration_ms, task_id, tags, user_id}` |
| `execution.decision` | `ExecutionManager.record_decision()` | `{context, decision, outcome, success}` |

### Observation Events
| Event Type | Source | Payload |
|---|---|---|
| `observation.observed` | `ObservationHub.publish_observation()` | `Observation.to_dict()` |
| `observation.created` | `ObservationHub` | `Observation.to_dict()` |

### Activity Events
| Event Type | Source | Payload |
|---|---|---|
| `activity.started` | `Scheduler._run_worker()` | `{activity_id, node_type, goal}` |
| `activity.resumed` | `ResumeEngine.mark_resumed()` | `activity_id` |
| `activity.executing` | `_run_worker()` | `{activity_id, node_type, goal}` |
| `activity.completed` | `_run_worker()` success | `{activity_id, node_type, goal}` |
| `activity.failed` | `_run_worker()` error | `{activity_id, error}` |
| `activity.resumed` | `ResumeEngine.mark_resumed()` | `activity_id` |
| `activity.cancelled` | Task cancelled | `activity_id` |

### Scheduler Events
| Event Type | Source | Payload |
|---|---|---|
| `scheduler.tick` | `Scheduler._fire_tick_callbacks()` | `{tick, activity_id, launched}` |
| `scheduler.started` | `Scheduler.start()` | `{tick_interval, max_workers}` |
| `scheduler.paused` | `Scheduler.pause()` | `running_count` |
| `scheduler.resumed` | `Scheduler.resume()` | — |
| `activity.started` | `Scheduler._run_worker()` | `{activity_id, node_type, goal}` |
| `activity.executing` | `_run_worker()` | `{activity_id, node_type, goal}` |
| `activity.completed` | `_run_worker()` success | `{activity_id, node_type, goal}` |
| `activity.failed` | `_run_worker()` error | `{activity_id, error}` |
| `activity.resumed` | `ResumeEngine.mark_resumed()` | `activity_id` |
| `activity.cancelled` | Task cancelled | `activity_id` |

### Build Events
| Event Type | Source | Payload |
|---|---|---|
| `build.started` | `BuildService._handle_build_started` | `{goal, project}` |
| `build.completed` | `BuildService._run_project()` success | `{project, goal}` |
| `build.failed` | `BuildService._run_project()` error | `{project, goal, error}` |
| `build.fix_requested` | `BuildService` retry | `{project, goal}` |

### Agent Events
| Event Type | Source | Payload |
|---|---|---|
| `agent.started` | `AgentManager` | `{agent_id, goal}` |
| `agent.completed` | Agent finish | `{agent_id, result}` |
| `agent.failed` | Agent error | `{agent_id, error}` |

### Memory Events
| Event Type | Source | Payload |
|---|---|---|
| `memory.fact_conflict` | `SemanticStore` | `{fact_id, old, new}` |
| `memory.index_updated` | `SemanticStore` | `{collection, count}` |

### Database Events
| Event Type | Source | Payload |
|---|---|---|
| `database.connection_pooled` | DB pool | `{pool_size, active}` |

---

## 3. EVENT BUS INSTANCES & PUBLISHERS

### Canonical Bus: `global_event_bus` (`core/event_bus.py`)
- **Singleton**: `global_event_bus = EventBus()`
- **Publish Methods**: `publish()` (async), `publish_sync()` (sync)
- **Subscriptions**: Pattern-based, priority, namespace, tenant filtering
- **Streaming**: `subscribe_stream()` → `asyncio.Queue`
- **WebSocket**: `register_ws()`, `unregister_ws()`, `_broadcast()`
- **History**: Ring buffer (100 events)
- **Sync Publish**: `publish_sync()` → `asyncio.ensure_future()` or `run_until_complete()`

### Subscribers (from code search)
| File | Subscription | Handler |
|---|---|---|
| `core/event_bus.py:307` | `register_default_subscribers()` | Logs all events |
| `core/multi_run.py:69-75` | `BUILD_COMPLETED`, `BUILD_FAILED` | `MultiRunExecutor._on_build_completed/failed` |
| `core/build/service.py:68` | `BUILD_STARTED` | `BuildService._handle_build_started` |
| `core/scheduler/scheduler.py:443` | `scheduler.tick` | `EventBus.publish_sync()` |
| `core/routes/chat/websocket_router.py:56` | `session_start` | `plugin_registry.run_hook` |
| `core/routes/chat/websocket_router.py:186` | `message_sent` | `plugin_registry.run_hook` |
| `core/plugins/base.py:672` | `run_hook()` | `PluginEventBus.emit()` |
| `core/observation/hub.py:80` | `observation.observed` | `ObservationHub.subscribe()` |
| `core/activity/recorder.py` | `goal_created`, `goal_completed`, `task_failed` | `ActivityRecorder` |
| `core/scheduler/scheduler.py:443` | `scheduler.tick` | `global_event_bus.publish_sync()` |

---

## 2. CONTEXT PROPAGATION

### Context Flow Through Pipeline
```
Transport Adapter (REST/WS/CLI/Voice/Channel)
        ↓
Request → Request (core/pipeline/messages.py)
        ↓
PipelineContext (core/pipeline/context.py)
        ↓
Pipeline.execute() → 19 stages
        ↓
PipelineContext carries:
  - request_id, transport, user_id, session_id
  - raw_input, attachments, metadata
  - activity_id, resource_scope (tenant_id, workspace_id, owner_id, visibility)
  - plan, selected_capabilities, execution_result
  - outcome, error, formatted_response
  - metrics, epistemic_tags, trace_id, activity_id
```

### Context Propagation Path
```
Transport Adapter (rest_adapter/ws_adapter/channel_adapter/voice_adapter)
    → process_message() / stream_via_pipeline() / voice_adapter()
    → core.pipeline.process_message(Request)
        → PipelineContext(request_id, transport, user_id, session_id, raw_input, ...)
        → Pipeline.execute(context)
            → Stage.execute(context) for each of 19 stages
            → context carries: raw_input, plan, selected_capabilities, execution_result, verification_result, epistemic_tags, reflection, learning, memory_refs, etc.
            → FormatterStage → Response
```

### Context Object (`core/pipeline/context.py:PipelineContext`)
```python
PipelineContext:
  request_id: str
  transport: str
  user_id: str
  session_id: str
  raw_input: str
  attachments: list[dict]
  metadata: dict
  activity_id: str
  resource_scope: ResourceScope  # tenant_id, workspace_id, owner_id, visibility
  raw_input: str
  plan: dict
  selected_capabilities: dict[int, list]
  execution_result: dict
  outcome: Outcome
  error: str
  formatted_response: dict
  metrics: dict
  epistemic_tags: list[str]
  reflection: str
  learning: str
  memory_refs: list
  trace_id: str
  activity_id: str
```

---

## 3. CONTEXT PROPAGATION THROUGH PIPELINE STAGES

| Stage | Reads From Context | Writes To Context | Events Published |
|-----|---|---|---|
| `ReceiveStage` | `raw_input`, `transport`, `session_id` | `raw_input` | `request.received` |
| `LoadContextStage` | `session_id` | `conversation_history`, `user_prefs` | `context.loaded` |
| `AuthenticationStage` | `transport`, `headers` | `user_id`, `tenant_id` | `auth.verified` |
| `TenantResolutionStage` | `user_id` | `tenant_id`, `workspace_id` | `tenant.resolved` |
| `AuthorizationStage` | `user_id`, `resource_scope` | `permissions` | `authz.granted/denied` |
| `ResourceAccessStage` | `permissions` | `resource_grants` | `resource.granted` |
| `RateLimitStage` | `user_id`, `transport` | `rate_limit_remaining` | `rate.limited` |
| `IntentStage` | `raw_input` | `classification`, `confidence`, `entities` | `intent.classified` |
| `ContextRetrievalStage` | `intent`, `entities` | `relevant_memories`, `relevant_docs` | `context.retrieved` |
| `KnowledgeStage` | `intent`, `entities` | `knowledge_refs`, `facts` | `knowledge.retrieved` |
| `ReasoningStage` | `intent`, `context` | `reasoning_chain`, `confidence` | `reasoning.complete` |
| `PlannerStage` | `reasoning`, `intent` | `plan`, `steps` | `plan.created` |
| `PlanValidatorStage` | `plan` | `validated_plan`, `issues` | `plan.validated` |
| `CapabilitySelectionStage` | `plan`, `intent` | `selected_capabilities` | `capability.selected` |
| `ExecutionStage` | `plan`, `capabilities` | `execution_result`, `tool_outputs` | `execution.started/completed` |
| `VerificationStage` | `execution_result` | `verification_result`, `confidence` | `verification.complete` |
| `EpistemicTaggingStage` | `execution_result` | `epistemic_tags`, `confidence` | `epistemic.tagged` |
| `ReflectionStage` | `epistemic_tags` | `reflection`, `improvements` | `reflection.complete` |
| `LearningStage` | `reflection` | `learning_signals` | `learning.recorded` |
| `PolicyOptimizationStage` | `learning_signals` | `policy_updates` | `policy.optimized` |
| `MemoryStage` | `execution_result`, `reflection` | `memory_refs` | `memory.stored` |
| `NotificationStage` | `outcome`, `verification` | `notifications` | `notification.sent` |
| `MetricsStage` | `all_stages` | `stage_timings`, `token_counts` | `metrics.recorded` |
| `ExplainabilityStage` | `all_stages` | `explanation`, `trace` | `explanation.generated` |
| `FormatterStage` | `all_context` | `formatted_response` | `response.formatted` |

---

## 2. WEBSOCKET CONNECTIONS

| WebSocket Endpoint | File | Adapter | Pipeline Integration |
|---|---|---|---|
| `/ws/chat_stream` | `core/routes/chat/websocket_router.py` | `ws_adapter.stream_via_pipeline()` | Full pipeline streaming |
| `/ws/agent_stream` | `core/routes/chat/websocket_router.py` | `ws_adapter()` (non-streaming) | Pipeline via `ws_adapter()` |
| `/ws/mcp/bridge` | `core/routes/chat/websocket_router.py` | `mcp_server.handle_websocket()` | MCP protocol, NOT pipeline |
| `/ws/logs` | `core/routes/chat/websocket_router.py` | Tail log files | No pipeline |
| `/ws/{device_id}/{user_id}` | `core/routes/chat/websocket_router.py` | `network.websocket_server` | Legacy device protocol |

### WebSocket Streaming (`ws_adapter.stream_via_pipeline()`)
```
ws_adapter.stream_via_pipeline(ws, text, user_id, session_id, metadata)
  → stream_pipeline(request)
    → async for event in stream_pipeline(request):
        → yield "stage_start", "stage_end", "stream_token", "pipeline_end", "pipeline_error", "pipeline_cancelled"
        → ws.send_json({type, stage, data})
```

---

## 3. INBOX UPDATES

### InboxStore (`core/inbox/store.py`)
**Subscribes to EventBus** in `__init__`:
```python
bus.on(GOAL_COMPLETED, ...)    → "Task completed: {goal}"
bus.on(GOAL_FAILED, ...)       → category="error"
bus.on(NEED_INPUT, ...)        → category="approval"
bus.on(WARNING, ...)           → category="error"
bus.on(ERROR, ...)             → category="error"
bus.on(MILESTONE, ...)         → category="update"
bus.on(NODE_FAILED, ...)       → category="error"
bus.on(NODE_SKIPPED, ...)      → category="update"
```

**Storage**: SQLite (`SYSTEM_DB` → `inbox_items` table)
**Categories**: `finished`, `approval`, `error`, `suggestion`, `update`

**API**: `InboxStore.add()`, `list()`, `get()`, `mark_read()`, `unread_count()`, `delete()`

---

## 4. NOTIFICATION SYSTEM

### SupervisorNotifier (`notifications/notifier.py`)
```python
async def notify(project: str, event: str, data: dict):
    # Always: write event log
    # If email enabled + event in (build_completed, task_failed): send email
    # If push enabled + event in (build_completed, build_started, task_failed): push
    # WebSocket: register_ws() / unregister_ws()
```

**Triggers**: 
- `build_completed`, `build_started`, `task_failed` → email + push
- All events → JSONL log at `~/.jarvis/projects/{project}/events.jsonl`

---

## 5. HISTORY / CONVERSATION

### ConversationHistoryService (`core/history/service.py`)
- `add_message(session_id, role, content, metadata)` → `history.message.added` event
- `get_history(session_id, limit, session_id)` → queries SQLite
- `list_sessions()` → session list with counts

**Storage**: SQLite (`core/database.py:ChatHistory`)

---

## 6. CONVERSATION / CHAT FLOW

### REST Chat (`POST /api/chat`)
```
POST /api/chat → chat_route()
  → rest_adapter(message, user_id, session_id, context)
    → process_message(Request) → pipeline
    → Response {text, intent, action, model, ...}
    → _persist_chat() → ChatHistory (SQLite)
    → return result
```

### WebSocket Chat (`/ws/chat_stream`)
```
WS connect → ws_adapter.stream_via_pipeline()
  → stream_pipeline(Request) → async for PipelineEvent
    → yield stage_start, stage_end, stream_token, pipeline_end
    → WS send_json({type, stage, data})
```

### Agent Stream (`/ws/agent_stream`)
```
WS connect → session_init (project context)
  → chat message → ws_adapter() (non-streaming)
    → process_message() → ConversationManager
  → agent_stream → streaming via pipeline
```

---

## 7. MEMORY FLOW

### MemoryFacade (`memory/memory_facade.py:MemoryFacade`)
```python
# Store
memory.store(text, user_id, metadata) 
  → tiered_memory.remember() → mem0 + tiered
  → vector_store.search()

# Recall
memory.recall(query, limit, user_id)
  → tiered.recall() + mem0.search() + semantic_store.retrieve()
  → merged + reranked

# Fact storage
memory.store_fact(fact, category, confidence, source)
memory.retrieve_facts(query, top_k, min_confidence)

# Episodic
memory.store_episode(goal, actions, context, result)
memory.retrieve_episodes(query, top_k)

# Task traces
memory.store_trace(action_name, params, observation, success, duration, task_id)
memory.get_task_traces(task_id)

# Decisions
memory.store_decision(context, decision, outcome, success)
memory.retrieve_decisions(query_context)
```

---

## 8. NOTIFICATION FLOW

```
Event occurs (build.completed, task_failed, etc.)
    ↓
SupervisorNotifier.notify(project, event, data)
    ├── _write_event_log() → ~/.jarvis/projects/{project}/events.jsonl
    ├── if email enabled + event in [build_completed, task_failed] → SMTP
    ├── if push enabled + event in [build_completed, build_started, task_failed]
    │    → ntfy.sh + Pushover
    └── WebSocket broadcast to registered clients
```

---

## 9. CONVERSATION HISTORY

```
POST /api/chat → chat_route()
  → rest_adapter(message, user_id, session_id, context)
    → process_message(Request) → pipeline
    → Response {text, intent, action, model, ...}
    → _persist_chat() → ChatHistory (SQLite)
    → return result

WebSocket /ws/chat_stream:
  ws_adapter.stream_via_pipeline() → pipeline events → WS frames

WebSocket /ws/agent_stream
  session_init → project context
  chat → ws_adapter (non-streaming) → process_message → ConversationManager
  session_response → tool confirmation via WS
```

---

## 10. CONTEXT PROPAGATION SUMMARY

```
Transport Adapter
    → Request(text, transport, user_id, session_id, metadata)
          ↓
    process_message(Request)
          ↓
    PipelineContext(request_id, transport, user_id, session_id, 
                    raw_input, attachments, metadata)
          ↓
    Pipeline.execute(context) → 19 stages
          Each stage: reads context → writes context → publishes events
          ↓
    FormatterStage → Response(text, error, data, metadata)
          ↓
    Transport Adapter → Response
```

---

## MISSING / DISCONNECTED PATHS

| Path | Issue |
|---|---|
| `WorkflowEvent` vs `Event` | Two parallel event systems (`WorkflowEvent` vs `Event`) |
| `PluginEventBus` | Deprecated, routes to `global_event_bus` but with deprecation warnings |
| `get_bus()` / `get_bus()` | Legacy singleton, use `global_event_bus` directly |
| `WorkflowEvent` vs `Event` | Two parallel event hierarchies |
| `InboxStore` | Uses legacy `get_bus()` instead of `global_event_bus` |
| `ActivityRecorder` | Uses `WorkflowEvent`, not `Event` |
| `WorkflowExecutionRecorder` | Uses `WorkflowEvent`, not `Event` |
| `core/graph/` (StateGraph) | Legacy fallback in `agent_loop.py:_disable_pipeline` |
| `core/agent_loop.py` fallback | `_disable_pipeline=True` bypasses canonical pipeline |

---

## MISSING AWAITS / DISCONNECTED PATHS

| Location | Issue |
|---|---|
| `core/lifespan.py:196` | `register_default_subscribers()` not awaited |
| `core/history/service.py:71` | `await asyncio.sleep(0.1)` — fake async wait |
| `core/history/service.py:127` | `await asyncio.sleep(0.1)` — fake async wait |
| `core/agent_loop.py:114` | `raise RuntimeError(response.error)` — loses traceback |
| `core/agent_loop.py:143` | `graph.execute(state)` — legacy graph, not pipeline |
| `core/pipeline/stages/notification.py:39` | `await global_event_bus.publish()` — OK |
| `core/pipeline/stages/memory.py:67` | `memory.store()` — sync call in async context |
| `core/pipeline/stages/notification.py:39` | `await global_event_bus.publish()` — OK |
| `core/history/service.py:71` | `await asyncio.sleep(0.1)` — polling hack |

---

## REALITY SCORES

| Component | Score | Notes |
|---|---|---|
| EventBus Core | 10/10 | Robust, async-first, tenant-aware |
| Pipeline Integration | 9/10 | All 19 stages connected |
| WebSocket Streaming | 8/10 | Good, but dual WS endpoints confusing |
| Legacy Graph Fallback | 3/10 | DORMANT, `_disable_pipeline` flag |
| PluginEventBus | 3/10 | DEPRECATED, still used in plugins |
| WorkflowEvent vs Event | 4/10 | Two parallel event systems |
| InboxStore | 7/10 | Uses legacy `get_bus()` |
| WorkflowEvent vs Event | 4/10 | Two parallel event hierarchies |
| Legacy Graph Fallback | 3/10 | DORMANT code path |
| Legacy Config Shim | 6/10 | `core/config.py` shim |

---

## DUPLICATE / DRIFT / DORMANT MARKING

| Component | Status | Evidence |
|---|---|---|
| `core/graph/` (StateGraph) | **DORMANT** | Only used by `agent_loop.py` fallback |
| `core/agent_loop.py` fallback | **DRIFT** | `_disable_pipeline` flag |
| `api/agent_routes.py` | **DORMANT** | Uses `build_default_graph()` |
| `core/graph/` | **DORMANT** | LangGraph fallback only |
| `automation/pc_automation.py` | **DEPRECATED** | Header says "Use core/desktop/controller.py" |
| `automation/routes.py` | **DUPLICATE** | Legacy HTTP routes |
| `brain/UnifiedBrain.py` | **DUPLICATE** | Duplicates Intent/Planner/Execution/Memory |
| `core/event_bus.py:PluginEventBus` | **DEPRECATED** | Warnings on every use |
| `core/event_bus.py:get_bus()` | **LEGACY** | Use `global_event_bus` |
| `core/event_bus.py:emit_event()` | **LEGACY** | Use `global_event_bus.publish()` |
| `core/config.py` | **DEPRECATED** | Shim → `ConfigurationService` |
| `automation/pc_automation.py` | **DEPRECATED** | Header says "Use core/desktop/controller.py" |
| `automation/routes.py` | **DUPLICATE** | Legacy HTTP routes |
| `core/plugins/automation.py` | **LEGACY** | Old plugin interface |
| `core/llm_calls.py` | **DEAD** | Unused, imports `llm_router` |

---

## CRITICAL FIXES NEEDED

1. **Unify Event Systems**: Merge `WorkflowEvent` → `Event`, retire `WorkflowEvent`
2. **Remove Legacy Graph**: Delete `core/graph/`, `core/agent_loop.py` fallback
3. **Unify Event Bus**: Remove `PluginEventBus`, `get_bus()`, `emit_event()`
4. **Fix InboxStore**: Use `global_event_bus` directly
5. **Remove Legacy Graph**: Delete `core/graph/`, `core/agent_loop.py` fallback
5. **Fix InboxStore**: Use `global_event_bus` directly
6. **Remove Legacy Config Shim**: Delete `core/config.py`
7. **Remove Legacy Graph**: Delete `core/graph/`, `core/agent_loop.py` fallback
7. **Remove Legacy Config Shim**: Delete `core/config.py`
8. **Register STT/TTS Providers** with `ProviderRegistry`
9. **Unify Schedulers**: Merge `core/cron.py` + `core/scheduler/scheduler.py`
10. **Fix Missing Awaits**: `register_default_subscribers()`, `asyncio.sleep(0.1)` hacks

---

*End of EVENTBUS AND CONTEXT AUDIT*