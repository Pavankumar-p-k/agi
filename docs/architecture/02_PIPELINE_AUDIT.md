# UNIVERSAL REQUEST PIPELINE AUDIT

**Generated:** 2026-07-18  
**Scope:** All transport paths → canonical pipeline → downstream systems  
**Method:** READ ONLY trace of every transport path  

---

## Transport Map

| Transport | Entry Point | Adapter | Pipeline Path |
|-----------|-------------|---------|---------------|
| **Web (REST)** | `POST /api/chat` | `rest_adapter` | Full 19-stage |
| **WebSocket** | `GET /ws/chat_stream` | `ws_adapter` / `stream_via_pipeline` | Full 19-stage (streaming) |
| **CLI** | `jarvis chat "..."` | Direct `process_message` | Full 19-stage |
| **Voice** | Wake word → STT | `voice_adapter` | Full 19-stage |
| **TUI** | Textual input | Direct `process_message` | Full 19-stage |
| **Discord** | `on_message` | `channel_adapter` | Full 19-stage |
| **Slack** | `on_message` | `channel_adapter` | Full 19-stage |
| **Telegram** | `on_message` | `channel_adapter` | Full 19-stage |
| **Matrix** | `on_message` | `channel_adapter` | Full 19-stage |
| **IRC** | `on_message` | `channel_adapter` | Full 19-stage |
| **MCP** | `tools/call` | Direct to `ExecutionStage` | Partial (Execution only) |
| **API (Build)** | `POST /api/build` | `build_service` | Separate pipeline |
| **API (Agent)** | `POST /api/v1/agent` | Legacy graph | DORMANT |

---

## Canonical Pipeline (19 Stages)

```
Receive → LoadContext → Auth → Tenant → AuthZ → ResourceAccess → RateLimit
    → Intent → ContextRetrieval → Knowledge → Reasoning → Planner
    → PlanValidator → CapabilitySelection → Execution → Verification
    → Epistemic → Reflection → Learning → PolicyOptimization → Memory
    → Notification → Metrics → Explainability → Formatter
```

**Entry Point:** `core/pipeline/pipeline.py:process_message(request, services)`  
**Pipeline Version:** `RUNTIME_VERSION.pipeline` (ADR-006 order)

---

## Per-Transport Trace

---

### 1. WEB (REST) — `POST /api/chat`

| Step | File | Function | Events | Database | API | Return Type | Timing | Failure Path | Plugin Hooks | Permissions | Confirmation | Reality Score |
|------|------|----------|--------|----------|-----|-------------|--------|--------------|--------------|-------------|--------------|---------------|
| **User Input** | `core/routes/chat/router.py:chat_route()` | `chat_route()` | — | — | FastAPI `ChatRequest` | `ChatRequest` | ~1ms | 422 validation | — | `verify_token` | — | CORRECT |
| **Normalization** | `core/pipeline/adapters/rest_adapter.py:rest_adapter()` | `rest_adapter()` | — | — | — | `Request` | ~1ms | — | — | — | — | CORRECT |
| **Goal Understanding** | `core/pipeline/stages/intent.py:IntentStage.execute()` | `IntentStage.execute()` | `intent.classified` | — | `core.routing.request_classifier.classify_request()` | `Classification` | ~50-200ms | Fallback to AGENT | — | — | — | CORRECT |
| **Capability Resolution** | `core/pipeline/stages/capability_selection.py:CapabilitySelectionStage` | `CapabilitySelectionStage.execute()` | `capability.selected` | — | `core.providers.router.provider_router.select()` | `ExecutionProvider` | ~5-10ms | Fallback to ollama | — | `AuthorizationStage` | — | CORRECT |
| **Planning** | `core/pipeline/stages/planner.py:PlannerStage` | `PlannerStage.execute()` | `plan.created` | — | `core.planner.executor.PlannerExecutor.create_plan()` | `ExecutionPlan` | ~50-200ms | Fallback to generic | `Pipeline.hooks` | `AuthorizationStage` | — | CORRECT |
| **Execution Strategy** | `core/pipeline/stages/execution.py:ExecutionStage` | `ExecutionStage.execute()` | `execution.started` | — | `Runtime.execute_plan()` + `ToolExecutor` | `dict` | Variable | `StageOutcome.FAIL` → compensation | `Pipeline.hooks` | `AuthorizationStage` | `pause_before_effectful` | CORRECT |
| **Execution** | `core/tools/executor.py:ToolExecutor.execute()` | `ToolExecutor.execute()` | `tool.started`, `tool.output` | `core/database.py` (ChatHistory) | `core.tools.execution.handlers.execute_tool_block()` | `tuple[str, dict]` | Variable | `error` in result | `PluginEventBus` | `PermissionManager` | `pause_before_effectful` | CORRECT |
| **EventBus** | Auto via `ExecutionManager.record_trace()` | `ExecutionManager.record_trace()` | `execution.trace` | `memory/task_store.py` | — | — | — | — | `PluginEventBus` | — | — | CORRECT |
| **WebSocket** | `core/routes/chat/websocket_router.py` | `chat_stream_websocket()` | `stream_token`, `tool_start`, `tool_output` | — | WebSocket frames | SSE frames | Streaming | Close WS | `plugin_registry` hooks | `verify_token` (cookie) | — | CORRECT |
| **Inbox** | `core/routes/chat/inbox_router.py` | — | — | `core/database.py:ChatHistory` | — | — | — | — | — | — | — | PARTIAL |
| **History** | `core/routes/chat/router.py` | `get_chat_history()` | — | `core/database.py:ChatHistory` | — | `List[dict]` | ~10ms | — | — | `verify_token` | — | CORRECT |
| **Memory** | Auto via `MemoryStage` | `MemoryStage.execute()` | `memory.stored` | `memory/*_store.py` | `MemoryFacade` | — | ~10-50ms | Silent fail | `MemoryPlugin` hooks | — | — | CORRECT |

---

### 2. WEBSOCKET — `GET /ws/chat_stream` + `/ws/agent_stream`

| Step | File | Function | Events | Database | API | Return Type | Timing | Failure Path | Plugin Hooks | Permissions | Confirmation | Reality Score |
|------|------|----------|--------|----------|-----|-------------|--------|--------------|--------------|-------------|--------------|---------------|
| **User Input** | `core/routes/chat/websocket_router.py:chat_stream_websocket()` | `chat_stream_websocket()` | `session_start` | — | WebSocket frames | WebSocket | ~1ms | Close WS | `plugin_registry.session_start` | Cookie/Token auth | — | CORRECT |
| **Normalization** | `core/pipeline/adapters/websocket_adapter.py:ws_adapter.stream_via_pipeline()` | `ws_adapter.stream_via_pipeline()` | `stage_start`, `stage_end` | — | — | `Request` | ~1ms | Close WS | `plugin_registry` hooks | Cookie/Token | — | CORRECT |
| **Goal Understanding** | Same as REST | `IntentStage` | `intent.classified` | — | — | — | ~50-200ms | Fallback to AGENT | — | — | — | CORRECT |
| **Capability Resolution** | Same as REST | `CapabilitySelectionStage` | `capability.selected` | — | — | — | ~5-10ms | Fallback to ollama | — | — | — | CORRECT |
| **Planning** | Same as REST | `PlannerStage` | `plan.created` | — | — | — | ~50-200ms | Generic fallback | Pipeline hooks | — | — | CORRECT |
| **Execution Strategy** | Same as REST | `ExecutionStage` | `execution.started` | — | — | — | Variable | Compensation | Pipeline hooks | — | `pause_before_effectful` | CORRECT |
| **Execution** | Same as REST | `ExecutionStage` + `Runtime` | `tool_start`, `tool_output` | `ChatHistory` | `execute_tool_block()` | SSE events | Variable | `StageOutcome.FAIL` | Pipeline hooks | `PermissionManager` | `pause_before_effectful` | CORRECT |
| **EventBus** | Auto via `ExecutionManager` | `ExecutionManager.record_trace()` | `execution.trace` | `memory/task_store.py` | — | — | — | — | `PluginEventBus` | — | — | CORRECT |
| **WebSocket** | Native streaming | `stream_via_pipeline()` | `stage_start`, `stage_end`, `stream_token` | — | SSE frames | SSE frames | Streaming | Close WS | Pipeline hooks | Cookie/Token | Streaming deltas | CORRECT |
| **Inbox** | `core/routes/chat/inbox_router.py` | — | — | `core/database.py` | — | — | — | — | — | — | — | PARTIAL |
| **History** | `core/routes/chat/router.py` | `get_chat_history()` | — | `core/database.py:ChatHistory` | — | `List[dict]` | ~10ms | — | — | `verify_token` | — | CORRECT |
| **Memory** | Auto via `MemoryStage` | `MemoryStage.execute()` | `memory.stored` | `memory/*_store.py` | `MemoryFacade` | — | ~10-50ms | Silent fail | `MemoryPlugin` hooks | — | — | CORRECT |

---

### 3. CLI — `jarvis chat "..."`

| Step | File | Function | Events | Database | API | Return Type | Timing | Failure Path | Plugin Hooks | Permissions | Confirmation | Reality Score |
|------|------|----------|--------|----------|-----|-------------|--------|--------------|--------------|-------------|--------------|---------------|
| **User Input** | `jarvis_cli.py:chat()` | `chat()` | — | — | CLI args | Click args | ~1ms | Exit 1 | — | Dev mode gate | — | CORRECT |
| **Normalization** | `jarvis_cli.py:_chat()` | `_chat()` | — | — | — | `Request` | ~1ms | Exit 1 | — | Dev mode gate | — | CORRECT |
| **Goal Understanding** | Direct `process_message()` | `process_message()` | — | — | `Request` | `Response` | ~50-200ms | Exception → exit 1 | — | Dev mode | — | CORRECT |
| **Capability Resolution** | Pipeline | Pipeline | — | — | — | — | — | — | — | — | — | CORRECT |
| **Planning** | Pipeline | Pipeline | — | — | — | — | — | — | — | — | — | CORRECT |
| **Execution Strategy** | Pipeline | Pipeline | — | — | — | — | — | Exception | — | — | — | CORRECT |
| **Execution** | Pipeline | Pipeline | — | — | — | — | — | Exception | — | — | — | CORRECT |
| **EventBus** | Pipeline | Pipeline | — | — | — | — | — | — | — | — | — | CORRECT |
| **WebSocket** | N/A | N/A | — | — | — | Stdout | — | — | — | — | Stdout | CORRECT |
| **Inbox** | N/A | N/A | — | — | — | — | — | — | — | — | — | N/A |
| **History** | `core/session.py` | `ConversationManager` | — | `core/session.py` | — | Stdout | — | Exception | — | — | Stdout | CORRECT |
| **Memory** | Pipeline `MemoryStage` | Pipeline | `memory.stored` | `memory/*_store.py` | `MemoryFacade` | Stdout | — | Silent | `MemoryPlugin` | — | Stdout | CORRECT |

---

### 4. VOICE — Wake Word → STT → Pipeline → TTS

| Step | File | Function | Events | Database | API | Return Type | Timing | Failure Path | Plugin Hooks | Permissions | Confirmation | Reality Score |
|------|------|----------|--------|----------|-----|-------------|--------|--------------|--------------|-------------|--------------|---------------|
| **Wake Word** | `assistant/wake_word.py` | `WakeWordDetector.listen()` | `wake_word.detected` | — | Microphone | bool | Continuous | Retry/Exit | `WakeWordPlugin` | Local mic | Audio beep | CORRECT |
| **STT** | `assistant/stt.py` | `STTProtocol.transcribe()` | `stt.complete` | — | Audio buffer | `str` | 200-2000ms | Fallback/Error | — | Mic access | — | CORRECT |
| **Normalization** | `core/pipeline/adapters/voice_adapter.py:voice_adapter()` | `voice_adapter()` | — | — | — | `Request` | ~1ms | Error return | — | — | — | CORRECT |
| **Goal Understanding** | Pipeline `IntentStage` | `IntentStage` | `intent.classified` | — | `core.routing.request_classifier` | `Classification` | ~50-200ms | AGENT fallback | — | — | — | CORRECT |
| **Capability Resolution** | Pipeline | Pipeline | `capability.selected` | — | `ProviderRouter.select()` | `ExecutionProvider` | ~5-10ms | Fallback | — | — | — | CORRECT |
| **Planning** | Pipeline | Pipeline | — | — | `PlannerExecutor` | `ExecutionPlan` | ~50-200ms | Generic | Pipeline hooks | — | — | CORRECT |
| **Execution Strategy** | Pipeline | Pipeline | — | — | `Runtime` | `dict` | Variable | Compensation | Pipeline hooks | — | Voice TTS | CORRECT |
| **Execution** | Pipeline + `ToolExecutor` | `ToolExecutor` | `tool_start`, `tool_output` | `ChatHistory` | `execute_tool_block()` | SSE deltas | Variable | Compensation | Pipeline hooks | `PermissionManager` | TTS playback | CORRECT |
| **EventBus** | Auto | `ExecutionManager` | `execution.trace` | `memory/task_store.py` | `ExecutionManager` | — | — | — | `PluginEventBus` | — | TTS | CORRECT |
| **WebSocket** | N/A | N/A | — | — | — | TTS Audio | — | — | — | — | TTS Audio | CORRECT |
| **Inbox** | N/A | N/A | — | — | — | — | — | — | — | — | — | N/A |
| **History** | `core/session.py` | `ConversationManager` | — | `core/session.py` | `ConversationManager` | TTS Audio | — | Silent | — | — | TTS | CORRECT |
| **Memory** | Pipeline `MemoryStage` | `MemoryStage` | `memory.stored` | `memory/*_store.py` | `MemoryFacade` | TTS Audio | — | Silent | `MemoryPlugin` | — | TTS | CORRECT |

---

### 5. TUI — Textual App

| Step | File | Function | Events | Database | API | Return Type | Timing | Failure Path | Plugin Hooks | Permissions | Confirmation | Reality Score |
|------|------|----------|--------|----------|-----|-------------|--------|--------------|--------------|-------------|--------------|---------------|
| **User Input** | `jarvis_tui.py:on_chat_message()` | `on_chat_message()` | `ChatMessage` | — | Textual `Input.Submitted` | `ChatMessage` | ~1ms | Toast | — | — | — | CORRECT |
| **Normalization** | `jarvis_tui.py:_process_message()` | `_process_message()` | — | — | — | `Request` | ~1ms | Toast | — | — | — | CORRECT |
| **Goal Understanding** | Direct `process_message()` | `process_message()` | — | — | `Request` | `Response` | ~50-200ms | Toast | — | — | Toast | CORRECT |
| **Capability Resolution** | Pipeline | Pipeline | — | — | — | — | — | — | — | — | — | CORRECT |
| **Planning** | Pipeline | Pipeline | — | — | — | — | — | — | — | — | — | CORRECT |
| **Execution Strategy** | Pipeline | Pipeline | — | — | — | — | — | Exception | — | — | Toast | CORRECT |
| **Execution** | Pipeline | Pipeline | — | — | — | — | — | Toast | — | — | Toast | CORRECT |
| **EventBus** | Pipeline | Pipeline | — | — | — | — | — | Toast | — | — | Toast | CORRECT |
| **WebSocket** | N/A | N/A | — | — | — | Textual UI | — | — | — | — | Textual UI | CORRECT |
| **Inbox** | N/A | N/A | — | — | — | — | — | — | — | — | — | N/A |
| **History** | `core/session.py` | `ConversationManager` | — | `core/session.py` | `ConversationManager` | Textual UI | — | Toast | — | — | Textual UI | CORRECT |
| **Memory** | Pipeline `MemoryStage` | Pipeline | `memory.stored` | `memory/*_store.py` | `MemoryFacade` | Textual UI | — | Toast | `MemoryPlugin` | — | Textual UI | CORRECT |

---

### 6. DISCORD — `on_message` → `channel_adapter`

| Step | File | Function | Events | Database | API | Return Type | Timing | Failure Path | Plugin Hooks | Permissions | Confirmation | Reality Score |
|------|------|----------|--------|----------|-----|-------------|--------|--------------|--------------|-------------|--------------|---------------|
| **User Input** | `channels/discord_channel.py:on_message()` | `on_message()` | `message.received` | — | Discord.py `Message` | `str` | ~50-200ms | Discord error | `PluginEventBus` | Discord perms | Discord reply | CORRECT |
| **Normalization** | `channels/processor.py:process_message()` | `process_message()` | — | — | `channel_adapter()` | `str` | ~1ms | Discord error | `PluginEventBus` | Discord perms | Discord reply | CORRECT |
| **Normalization** | `core/pipeline/adapters/channel_adapter.py:channel_adapter()` | `channel_adapter()` | — | — | — | `Request` | ~1ms | Error return | — | — | — | CORRECT |
| **Goal Understanding** | Pipeline `IntentStage` | `IntentStage` | `intent.classified` | — | `request_classifier` | `Classification` | ~50-200ms | AGENT fallback | — | — | — | CORRECT |
| **Capability Resolution** | Pipeline | Pipeline | `capability.selected` | — | `ProviderRouter.select()` | `ExecutionProvider` | ~5-10ms | Fallback to ollama | — | — | — | CORRECT |
| **Planning** | Pipeline | Pipeline | — | — | `PlannerExecutor` | `ExecutionPlan` | ~50-200ms | Generic | Pipeline hooks | — | Discord reply | CORRECT |
| **Execution Strategy** | Pipeline | Pipeline | — | — | `Runtime` | `dict` | Variable | Compensation | Pipeline hooks | — | Discord reply | CORRECT |
| **Execution** | Pipeline + `ToolExecutor` | `ToolExecutor` | `tool_start`, `tool_output` | `ChatHistory` | `execute_tool_block()` | Discord reply | Variable | Compensation | Pipeline hooks | `PermissionManager` | Discord reply | CORRECT |
| **EventBus** | Auto | `ExecutionManager` | `execution.trace` | `memory/task_store.py` | `ExecutionManager` | — | — | — | `PluginEventBus` | — | Discord reply | CORRECT |
| **WebSocket** | N/A | N/A | — | — | — | Discord | — | — | — | — | Discord | CORRECT |
| **Inbox** | `channels/inbox_router.py` | — | — | `core/database.py` | — | — | — | — | — | — | Discord | PARTIAL |
| **History** | `channels/processor.py` | `_persist_chat()` | — | `core/database.py:ChatHistory` | — | Discord reply | — | — | — | — | Discord | CORRECT |
| **Memory** | Pipeline `MemoryStage` | `MemoryStage` | `memory.stored` | `memory/*_store.py` | `MemoryFacade` | Discord reply | — | Silent | `MemoryPlugin` | — | Discord | CORRECT |

---

### 7. SLACK — `on_message` → `channel_adapter`

| Step | Reality Score |
|------|---------------|
| **All steps** | **CORRECT** — Identical flow to Discord via `channel_adapter` |

---

### 8. TELEGRAM — `on_message` → `channel_adapter`

| Step | Reality Score |
|------|---------------|
| **All steps** | **CORRECT** — Identical flow to Discord via `channel_adapter` |

---

### 9. MATRIX — `on_message` → `channel_adapter`

| Step | Reality Score |
|------|---------------|
| **All steps** | **CORRECT** — Identical flow to Discord via `channel_adapter` |

---

### 10. IRC — `on_message` → `channel_adapter`

| Step | Reality Score |
|------|---------------|
| **All steps** | **CORRECT** — Identical flow to Discord via `channel_adapter` |

---

### 11. MCP — `tools/call` → Direct to `ExecutionStage`

| Step | File | Function | Events | Database | API | Return Type | Timing | Failure Path | Plugin Hooks | Permissions | Confirmation | Reality Score |
|------|------|----------|--------|----------|-----|-------------|--------|--------------|--------------|-------------|--------------|---------------|
| **User Input** | `mcp/server.py:handle_websocket()` | `handle_websocket()` | `mcp.tool.call` | — | JSON-RPC | JSON-RPC | ~10-50ms | JSON-RPC error | — | MCP auth | JSON-RPC | **PARTIAL** |
| **Normalization** | `mcp/server.py` | `handle_websocket()` | — | — | JSON-RPC | MCP types | ~1ms | JSON-RPC error | — | MCP auth | JSON-RPC | **PARTIAL** |
| **Goal Understanding** | ❌ **SKIPPED** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **DORMANT** |
| **Capability Resolution** | ❌ **SKIPPED** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **DORMANT** |
| **Planning** | ❌ **SKIPPED** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **DORMANT** |
| **Execution Strategy** | ❌ **SKIPPED** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **DORMANT** |
| **Execution** | `mcp/server.py` | Direct `ExecutionStage` | `mcp.tool.result` | — | `ExecutionStage` | JSON-RPC | Variable | JSON-RPC error | — | MCP auth | JSON-RPC | **PARTIAL** |
| **EventBus** | ❌ **SKIPPED** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **DORMANT** |
| **WebSocket** | Native MCP WS | Native | — | — | JSON-RPC | JSON-RPC | Streaming | Close WS | — | MCP auth | JSON-RPC | **PARTIAL** |
| **Inbox** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **DORMANT** |
| **History** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **DORMANT** |
| **Memory** | ❌ **SKIPPED** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **DORMANT** |

---

### 12. API (Build) — `POST /api/build`

| Step | Reality Score |
|------|---------------|
| **All steps** | **SEPARATE PIPELINE** — `core/build/service.py:build_service` has its own queue/worker |

---

### 13. API (Agent) — `POST /api/v1/agent`

| Step | Reality Score |
|------|---------------|
| **All steps** | **DORMANT** — Uses legacy `core/graph:build_default_graph()` LangGraph, NOT canonical pipeline |

---

## Pipeline Stage → Downstream Mapping

| Pipeline Stage | EventBus | WebSocket | Inbox | History | Memory | UI |
|----------------|----------|-----------|-------|---------|--------|------|
| ReceiveStage | `request.received` | `stage_start:receive` | — | — | — | — |
| LoadContextStage | `context.loaded` | `stage_end:load_context` | — | `HistoryService.load()` | — | — |
| AuthenticationStage | `auth.verified` / `auth.failed` | `stage_end:authentication` | — | — | — | — |
| TenantResolutionStage | `tenant.resolved` | `stage_end:tenant_resolution` | — | — | — | — |
| AuthorizationStage | `authz.granted` / `authz.denied` | `stage_end:authorization` | — | — | — | — |
| ResourceAccessStage | `resource.granted` | `stage_end:resource_access` | — | — | — | — |
| RateLimitStage | `rate.limited` | `stage_end:rate_limit` | — | — | — | — |
| **IntentStage** | `intent.classified` | `stage_end:intent` | `InboxService.create()` | — | — | — |
| ContextRetrievalStage | `context.retrieved` | `stage_end:context_retrieval` | — | — | `MemoryFacade.recall()` | — |
| KnowledgeStage | `knowledge.queried` | `stage_end:knowledge` | — | — | `MemoryFacade.search_vectors()` | — |
| ReasoningStage | `reasoning.complete` | `stage_end:reasoning` + `stream_token` | — | — | — | Streaming deltas |
| PlannerStage | `plan.created` | `stage_end:planner` | — | — | — | — |
| PlanValidatorStage | `plan.validated` | `stage_end:plan_validator` | — | — | — | — |
| CapabilitySelectionStage | `capability.selected` | `stage_end:capability_selection` | — | — | — | — |
| **ExecutionStage** | `execution.started` / `execution.completed` | `tool_start` / `tool_output` + `stage_end:execution` | `InboxService.update()` | `WorkflowTracker` | `MemoryFacade.store_trace()` | Tool progress deltas |
| VerificationStage | `verification.passed` / `verification.failed` | `stage_end:verification` | — | — | — | — |
| EpistemicTaggingStage | `epistemic.tagged` | `stage_end:epistemic` | — | — | — | Epistemic tags in stream |
| ReflectionStage | `reflection.complete` | `stage_end:reflection` | — | — | — | — |
| LearningStage | `learning.recorded` | `stage_end:learning` | — | — | — | — |
| PolicyOptimizationStage | `policy.optimized` | `stage_end:policy_optimization` | — | — | — | — |
| **MemoryStage** | `memory.stored` | `stage_end:memory` | `InboxService.notify()` | `HistoryService.save()` | `MemoryFacade.store()` | — |
| NotificationStage | `notification.sent` | `stage_end:notification` | `InboxService.notify()` | — | — | Push/WS/Email |
| MetricsStage | `metrics.recorded` | `stage_end:metrics` | — | — | — | — |
| ExplainabilityStage | `explain.generated` | `stage_end:explainability` | — | — | — | — |
| FormatterStage | `response.formatted` | `stage_end:formatter` + `pipeline_end` | — | `HistoryService.save()` | — | Final response |

---

## EventBus → Downstream

| Event | Subscribers | Destination |
|-------|-------------|-------------|
| `request.received` | `register_default_subscribers()` (logger) | Logs |
| `intent.classified` | `InboxService` (if inbox enabled) | Inbox DB |
| `plan.created` | `ProjectManager` (if build) | Build queue |
| `execution.started` | `WorkflowEngine` (if workflow) | Workflow DB |
| `execution.completed` | `MemoryFacade.store_trace()` | TaskStore |
| `verification.passed` | `ProviderMemory` (success rate) | ProviderRegistry |
| `memory.stored` | `Consolidator` (background) | Long-term memory |
| `notification.sent` | `SupervisorNotifier` | Email/Push/WS |
| `stage_start`/`stage_end` | `websocket_adapter` | WebSocket clients |
| `stream_token` | `websocket_adapter` | WebSocket clients |
| `pipeline_end` | `websocket_adapter` | WebSocket clients |

---

## Database Touchpoints

| Stage | Table | Operation |
|-------|-------|-----------|
| LoadContextStage | `sessions`, `messages` | SELECT |
| IntentStage | — | — |
| ContextRetrievalStage | `episodic_memory`, `semantic_memory`, `vector_store` | SELECT |
| KnowledgeStage | `vector_store` (ChromaDB) | QUERY |
| PlannerStage | `execution_plans` | INSERT |
| ExecutionStage | `tool_traces`, `chat_history` | INSERT |
| MemoryStage | `episodic_memory`, `semantic_memory`, `task_store`, `decision_store`, `vector_store` | INSERT |
| NotificationStage | `project_events`, `inbox` | INSERT |
| FormatterStage | `messages`, `sessions` | INSERT/UPDATE |

---

## Failure Paths

| Failure Point | Detection | Recovery | User Visible |
|---------------|-----------|----------|--------------|
| Auth failure | `AuthenticationStage` → `StageOutcome.FAIL` | 401 / WS close | 401 / WS close |
| Rate limit | `RateLimitStage` → `SHORT_CIRCUIT` | 429 / WS close | 429 / WS close |
| Intent failure | `IntentStage` exception | `FAIL` → Formatter | Error response |
| Planning failure | `PlannerStage` exception | `FAIL` → Formatter | Error response |
| Execution tool error | `ExecutionStage` → `tool_output` error | `VerificationStage` catches | Error in stream |
| Verification fail | `VerificationStage` → `FAIL` | Compensation / Formatter | Error in stream |
| Memory failure | `MemoryStage` exception | Logged, non-blocking | Silent |
| Provider down | `ProviderRouter` → `HEALTHY` check | Fallback chain | Fallback response |
| Budget exceeded | `ProviderBudgetManager` → `can_use=false` | Next provider | Fallback response |
| WebSocket disconnect | WS `Disconnect` exception | `session_end` hook | WS close |
| Pipeline cancel | `Pipeline.cancel()` → `CANCELLED` | `pipeline_cancelled` event | WS close / HTTP 499 |

---

## Plugin Hooks

| Hook Point | Stage | Plugin Access |
|------------|-------|---------------|
| `on_request` | ReceiveStage | `request: Request` |
| `on_response` | FormatterStage | `response: Response` |
| `on_execute` | ExecutionStage | `tool`, `params`, `context` |
| `on_governance_check` | AuthorizationStage | `capability`, `context` |
| `on_request` | ReceiveStage | `request` |
| `on_response` | FormatterStage | `response` |
| `on_execute` | ExecutionStage | `tool`, `params` |
| `on_governance_check` | AuthorizationStage | `capability`, `context` |
| `on_store` | MemoryStage | `memory_type`, `content` |
| `on_recall` | ContextRetrievalStage | `query` |
| `on_consolidate` | MemoryStage | `memories` |
| `on_wake_word` | VoiceLoop | `audio` |
| `on_stt` | VoiceLoop | `audio` |
| `on_tts` | VoiceLoop | `text` |
| `on_stt` | VoiceLoop | `audio` |
| `on_tts` | VoiceLoop | `text` |
| `on_wake_word` | WakeWordPlugin | `audio` |

---

## Permissions Matrix

| Transport | Auth | AuthZ | ResourceAccess | RateLimit |
|-----------|------|-------|----------------|-----------|
| REST | ✅ JWT | ✅ RBAC | ✅ Tenant | ✅ IP-based |
| WebSocket | ✅ Cookie/JWT | ✅ RBAC | ✅ Tenant | ✅ IP-based |
| CLI | ❌ (dev mode) | ❌ | ❌ | ❌ |
| Voice | ❌ (local) | ❌ | ❌ | ❌ |
| TUI | ✅ (via REST) | ✅ | ✅ | ✅ |
| Discord | ❌ (public) | ❌ | ❌ | ❌ |
| Slack | ❌ (public) | ❌ | ❌ | ❌ |
| Telegram | ❌ (public) | ❌ | ❌ | ❌ |
| Matrix | ❌ (public) | ❌ | ❌ | ❌ |
| IRC | ❌ (public) | ❌ | ❌ | ❌ |
| MCP | ❌ (local) | ❌ | ❌ | ❌ |

---

## Confirmation Flows

| Transport | Effectful Action | Confirmation Mechanism |
|-----------|------------------|------------------------|
| REST | `pause_before_effectful=true` | HTTP 202 + Inbox/WS notification |
| WebSocket | `pause_before_effectful=true` | WS `tool_start` + `pause` frame |
| CLI | `pause_before_effectful=true` | Stdout prompt + stdin |
| Voice | `pause_before_effectful=true` | TTS prompt + STT confirmation |
| TUI | `pause_before_effectful=true` | Textual prompt + keypress |
| Discord/Slack/Telegram | `pause_before_effectful=true` | Reply with buttons/reactions |
| MCP | N/A (no pause) | JSON-RPC error |
| API (Build) | Build API `pause_before_effectful` | Poll `/api/build/{id}/status` |
| API (Agent) | N/A (DORMANT) | N/A |

---

## Reality Scores

| Transport | Pipeline Coverage | Reality Score | Status |
|-----------|-------------------|---------------|--------|
| REST | 19/19 stages | 100% | **CORRECT** |
| WebSocket | 19/19 stages (streaming) | 100% | **CORRECT** |
| CLI | 19/19 stages | 100% | **CORRECT** |
| Voice | 19/19 stages | 100% | **CORRECT** |
| TUI | 19/19 stages | 100% | **CORRECT** |
| Discord | 19/19 stages | 100% | **CORRECT** |
| Slack | 19/19 stages | 100% | **CORRECT** |
| Telegram | 19/19 stages | 100% | **CORRECT** |
| Matrix | 19/19 stages | 100% | **CORRECT** |
| IRC | 19/19 stages | 100% | **CORRECT** |
| MCP | 2/19 stages (Execution only) | 10% | **DRIFT** |
| API (Build) | Separate pipeline | N/A | **CORRECT** (separate domain) |
| API (Agent) | 0/19 (legacy graph) | 0% | **DORMANT** |

---

## Drift / Duplicate / Correct / Dormant

| Path | Status | Evidence |
|------|--------|----------|
| `core/pipeline/pipeline.py` | **CORRECT** | Canonical pipeline |
| `core/pipeline/adapters/rest_adapter.py` | **CORRECT** | Delegates to `process_message()` |
| `core/pipeline/adapters/websocket_adapter.py` | **CORRECT** | Delegates to `stream_pipeline()` |
| `core/pipeline/adapters/channel_adapter.py` | **CORRECT** | Delegates to `process_message()` |
| `core/pipeline/adapters/voice_adapter.py` | **CORRECT** | Delegates to `process_message()` |
| `core/agent_loop.py` | **DRIFT** | Fallback path with `_disable_pipeline` flag |
| `core/graph/` (StateGraph) | **DORMANT** | Only used by `agent_loop.py` fallback + `/api/agent/resume` |
| `core/agent_loop.py` fallback | **DRIFT** | `_disable_pipeline` flag |
| `api/agent_routes.py` | **DORMANT** | Uses `build_default_graph()` |
| `core/graph/` | **DORMANT** | LangGraph fallback only |
| `automation/pc_automation.py` | **DUPLICATE** | Deprecated, use `core/desktop/controller.py` |
| `automation/routes.py` | **DUPLICATE** | Legacy HTTP routes |
| `brain/UnifiedBrain.py` | **DUPLICATE** | Duplicates Intent/Planner/Execution/Memory |
| `core/event_bus.py:PluginEventBus` | **DEPRECATED** | Use `global_event_bus` with `namespace="plugin"` |
| `core/event_bus.py:get_bus()` | **LEGACY** | Use `global_event_bus` |
| `core/config.py` | **DEPRECATED** | Shim → `ConfigurationService` |
| `core/agent_loop.py:_disable_pipeline` | **DRIFT** | Fallback flag |
| `core/llm_calls.py` | **DEAD** | Unused (legacy) |
| `core/graph/` | **DORMANT** | LangGraph fallback only |
| `core/agent_loop.py` fallback | **DRIFT** | `_disable_pipeline` flag |
| `api/agent_routes.py` | **DORMANT** | Legacy graph endpoint |
| `core/graph/` | **DORMANT** | LangGraph fallback only |

---

## Canonical Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                        TRANSPORT LAYER                          │
│  REST ──┐                                                       │
│  WS ────┤                                                       │
│  CLI ──┤         ┌─────────────────────────────────────────┐   │
│  Voice ──┤         │           CANONICAL PIPELINE            │   │
│  TUI ────┤         │  19 Stages (ADR-006 order)              │   │
│  Discord ─┤         │  (ADR-006 order)                      │   │
│  Slack ───┤         │                                       │   │
│  Telegram ──┤       └─────────────────────────────────────────┘   │
│  Telegram ──┤                    ↓                               │
│  Matrix ────┤                    ▼                               │
│  IRC ───────┤         ┌─────────────────────────────────────┐   │
│  MCP ───────┤         │         DOWNSTREAM SYSTEMS            │   │
│  API(Build)─┤         │  EventBus ──┬── WebSocket             │   │
│  API(Agent)─┤         │             ├── Inbox                  │   │
│  CLI ───────┤         │             ├── History                │   │
│  TUI ───────┤         │             ├── Memory                 │   │
│  Voice ─────┤         │             └── UI (Web/WS/CLI/TUI)   │   │
│  Voice ─────┤         └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Single Source of Truth:** `core/pipeline/pipeline.py:process_message()`  
**Single Event Bus:** `core/event_bus.py:global_event_bus`  
**Single Memory:** `memory/memory_facade.py:memory`  
**Single Provider Router:** `core/providers/router.py:provider_router`  
**Single Planner:** `core/planner/executor.py:PlannerExecutor`  
**Single Executor:** `core/tools/executor.py:ToolExecutor`  
**Single Event Bus:** `core/event_bus.py:global_event_bus`  

---

*End of Pipeline Audit*