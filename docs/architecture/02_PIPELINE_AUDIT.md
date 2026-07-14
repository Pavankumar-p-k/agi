# 02 — Universal Request Pipeline Audit

> **Phase 2 of Source-of-Truth Audit.**  
> Every request path traced end-to-end from user input to final output.  
> Each arrow documents: file, function, events, database, API, return type, timing, failure path, plugin hooks, permissions, confirmation.  
> Status: **DRIFT** / **DUPLICATE** / **CORRECT** / **DORMANT** with Reality Score.

---

## Table of Contents

1. [Canonical Pipeline Architecture](#1-canonical-pipeline-architecture)
2. [HTTP/REST Path](#2-httprest-path)
3. [WebSocket Path](#3-websocket-path)
4. [Voice Path](#4-voice-path)
5. [Channel Path (Discord, Slack, Telegram, Matrix, IRC, Email)](#5-channel-path)
6. [CLI / TUI Path](#6-cli--tui-path)
7. [Legacy Paths & Bypasses](#7-legacy-paths--bypasses)
8. [Stage-by-Stage DRIFT Assessment](#8-stage-by-stage-drift-assessment)
9. [Discovery Summary](#9-discovery-summary)

---

## 1. Canonical Pipeline Architecture

### The Two Pipelines

There are **two distinct pipeline systems** with overlapping responsibility:

#### A. `core/pipeline/` — Canonical Stage Pipeline (NEW)

| Aspect | Detail |
|--------|--------|
| **File** | `core/pipeline/pipeline.py:131` |
| **Entry** | `process_message(request: Request) -> Response` at `core/pipeline/pipeline.py:67` |
| **Streaming entry** | `stream_pipeline(request: Request) -> AsyncGenerator[StreamEvent]` at `core/pipeline/stream.py:35` |
| **Stages** | 19 stages in ADR-007 order: receive → load_context → authentication → tenant_resolution → authorization → resource_access → rate_limit → intent → context_retrieval → reasoner → planner → plan_validator → capability_selection → execution → verification → epistemic → memory → metrics → formatter |
| **Defined in** | `core/pipeline/stages/__init__.py:44-64` |
| **Stage base** | `PipelineStage` at `core/pipeline/base.py` |
| **Outcomes** | CONTINUE, SHORT_CIRCUIT, RETRY, FAIL, DEFER, CANCELLED |
| **Failure model** | Per-stage retry (max 3), timeout per stage, short-circuit propagation |
| **Cancellation** | `Pipeline.cancel()` — sets flag checked between stages |
| **Observations** | Published to `ObservationHub` after each stage |
| **Version** | `RUNTIME_VERSION.pipeline` |
| **Status** | `CORRECT` (Reality: 8/10 — actively used by 4 adapters but coexists uneasily with legacy pipeline) |

#### B. `core/pipeline.py` — Legacy RuntimePipeline (OLD)

| Aspect | Detail |
|--------|--------|
| **File** | `core/pipeline.py:63` |
| **Entry** | `RuntimePipeline.execute() -> AsyncGenerator[str]` at `core/pipeline.py:109` |
| **Phases** | Knowledge Injection (A.8) → Planning (A.1) → Strategy (A.2) → Decision (A.3+A.4) → Provider (A.5) → Activity Recording (A.7) → Workflow (A.6) → Graph Execution → Activity Completion → Provider Memory Feedback (A.8.5) → Learning Feedback (A.9) |
| **Invoked by** | `core/agent_loop.py:stream_agent_loop()` (line 73) — wraps RuntimePipeline with legacy fallback |
| **Legacy fallback** | Direct `build_default_graph()` graph execution if pipeline disabled or errored |
| **Gate** | `_PIPELINE_ENABLED = True` global flag (line 35) |
| **Status** | `DRIFT` (Reality: 5/10 — should be superseded by canonical `core/pipeline/` but remains primary path for `stream_agent_loop`) |

#### C. Adapter Layer — The Glue

Four transport adapters bridge all entry points to the canonical pipeline:

| Adapter | File | Entry Called | Status |
|---------|------|-------------|--------|
| `rest_adapter` | `core/pipeline/adapters/rest_adapter.py:17` | `process_message()` | `CORRECT` |
| `ws_adapter` | `core/pipeline/adapters/websocket_adapter.py:23` | `process_message()` or `stream_pipeline()` | `CORRECT` |
| `channel_adapter` | `core/pipeline/adapters/channel_adapter.py:18` | `process_message()` | `CORRECT` |
| `voice_adapter` | `core/pipeline/adapters/voice_adapter.py:24` | `process_message()` | `CORRECT` |

**All four share the same `Request`/`Response` types** defined at `core/pipeline/messages.py:10` and `core/pipeline/messages.py:37`.

### Pipeline Request Flow (Simplified)

```
  User Input
      │
      ▼
  ┌─ Transport-Specific Handler ────────────────────┐
  │  (FastAPI route / WebSocket handler / CLI /     │
  │   Channel plugin / VoiceEngine.think)            │
  └──────────────────────┬──────────────────────────┘
                         │
                         ▼
  ┌─ Transport Adapter ──────────────────────────────┐
  │  Constructs Request(text, transport, user_id,    │
  │                    session_id, metadata)          │
  └──────────────────────┬──────────────────────────┘
                         │
                         ▼
  ┌─ process_message(request) ───────────────────────┐
  │  Creates PipelineContext                          │
  │  Identity → ResourceScope                         │
  │  Calls Pipeline.execute(ctx)                      │
  └──────────────────────┬──────────────────────────┘
                         │
                         ▼
  ┌─ 19 Pipeline Stages ────────────────────────────┐
  │  receive → load_context → auth → tenant →       │
  │  authz → resource → rate_limit → intent →       │
  │  context_retrieval → reasoner → planner →       │
  │  plan_validator → capability → execution →      │
  │  verification → epistemic → memory → metrics →  │
  │  formatter                                       │
  └──────────────────────┬──────────────────────────┘
                         │
                         ▼
  ┌─ Response ───────────────────────────────────────┐
  │  text + metadata + epistemic_tags + trace_id     │
  └──────────────────────┬──────────────────────────┘
                         │
                         ▼
  Transport-Specific Output
  (JSON / SSE / WebSocket text / TTS audio / Channel message)
```

---

## 2. HTTP/REST Path

### 2.1 POST /api/chat

```
  Client → POST /api/chat
      │
      ▼
  ┌─ Middleware Stack ─────────────────────────────────────────────────┐
  │ 1. rate_limit_middleware (core/main.py:171)                        │
  │    - Exempt paths: /health, /docs, /openapi.json, /redoc, /static │
  │    - Uses api_rate_limiter.check("api", ip) -> 429 if exceeded    │
  │                                                                      │
  │ 2. session_auth_middleware (core/main.py:189)                      │
  │    - Exempt paths + DEV_MODE bypass                                │
  │    - Validates session_token cookie or Authorization Bearer header │
  │    - Sets request.state.current_user                               │
  │                                                                      │
  │ 3. plugin_hook_middleware (core/main.py:205)                       │
  │    - Calls plugin_registry.run_hook("on_request", ...)             │
  │    - Calls plugin_registry.run_hook("on_response", ...)            │
  │                                                                      │
  │ 4. RequestIDMiddleware (core/request_id.py)                        │
  │    - Adds X-Request-ID header                                      │
  │                                                                      │
  │ 5. MetricsMiddleware (core/observability/metrics.py)               │
  │    - Records request duration, status code, path                   │
  └──────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
  ┌─ core/routes/chat.py:32 ──────────────────────────────────────────┐
  │  @router.post("/api/chat")                                        │
  │  async def chat_route(req, db, user)                               │
  │    user_id = req.session_id or "default_user"                      │
  │    result = await rest_adapter(message, user_id, ...)              │
  │    _persist_chat(req, result, response_text, db, user, user_id)    │
  │    return result                                                   │
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ core/pipeline/adapters/rest_adapter.py:17 ───────────────────────┐
  │  async def rest_adapter(message, user_id, session_id, context,    │
  │                         attachments):                              │
  │    request = Request(text=message, transport="rest", ...)          │
  │    response: Response = await process_message(request)            │
  │    return {response, intent, action, model, privacy_tier,         │
  │            epistemic_tags, format_used, multi_format}              │
  │    ERROR → returns {response: "Error: ...", intent, action, ...}  │
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ core/pipeline/pipeline.py:67 ────────────────────────────────────┐
  │  async def process_message(request, services):                     │
  │    ctx = PipelineContext(request_id, transport, user_id, ...)     │
  │    ctx.identity = get_identity_service().create_context(...)      │
  │    ctx.resource_scope = ResourceScope(tenant_id, ...)              │
  │    ctx = await get_pipeline().execute(ctx)                         │
  │    return Response(text=..., error=..., data=..., metadata=...)    │
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ Pipeline.execute  (19 stages) ──────────────────────────────────┐
  │  ...                                                              │
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ _persist_chat (core/routes/chat.py:52) ─────────────────────────┐
  │  db.add(ChatHistory(user_id, role="user", message, ...))          │
  │  db.add(ChatHistory(user_id, role="assistant", message, ...))    │
  │  await db.commit()                                                │
  │  Uses SQLAlchemy AsyncSession + SQLite                            │
  └───────────────────────────────────────────────────────────────────┘
```

**Arrow Details:**

| Property | Value |
|----------|-------|
| **File** | `core/routes/chat.py:33` |
| **Function** | `chat_route()` |
| **Events emitted** | None directly; pipeline stages emit via `EventBus` |
| **Database reads** | None at route level |
| **Database writes** | `ChatHistory` (user + assistant) via `_persist_chat()` at line 69-83 |
| **API calls** | `rest_adapter()` → `process_message()` → all pipeline stages |
| **Return type** | `dict` with keys: `response`, `intent`, `action`, `model`, `privacy_tier`, `epistemic_tags`, `format_used`, `multi_format` |
| **Timing** | Async, awaits entire pipeline |
| **Failure path** | Pipeline error → returns error dict with `intent: chat`, `action.executed: False` |
| **Plugin hooks** | Via middleware → `on_request`, `on_response` |
| **Permissions** | `verify_token` dependency → JWT token validation |
| **Confirmation** | None at route level |
| **Status** | `CORRECT` — canonical path |

### 2.2 POST /api/agent/stream

```
  Client → POST /api/agent/stream
      │
      ▼
  Middleware stack (same as /api/chat)
      │
      ▼
  ┌─ core/routes/chat.py:87 ──────────────────────────────────────────┐
  │  @router.post("/api/agent/stream")                                │
  │  async def agent_stream(req):                                      │
  │    endpoint_url = configuration.get("ollama.base_url")             │
  │    model = CHAT_MODEL                                              │
  │    messages = [system context?, user message]                      │
  │    return StreamingResponse(_generate(), media_type="text/event-stream")
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ core/agent_loop.py:34 ───────────────────────────────────────────┐
  │  async def stream_agent_loop(endpoint_url, model, messages, ...):  │
  │    if not _disable_pipeline:                                       │
  │      pipeline = RuntimePipeline()                                  │
  │      async for event in pipeline.execute(...):                     │
  │        yield event                                                 │
  │      return                                                        │
  │    # Legacy fallback:                                              │
  │    graph = build_default_graph()                                   │
  │    state = AgentState(...)                                         │
  │    async for event in graph.execute(state):                        │
  │      yield event                                                   │
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ core/pipeline.py:109 ────────────────────────────────────────────┐
  │  RuntimePipeline.execute():                                        │
  │    goal = _extract_goal(messages)                                  │
  │    Phase A.8: Knowledge Injection (BehaviorAdapter.for_planner)   │
  │    Phase A.1: Planning (PlannerExecutor.create_plan)               │
  │    Phase A.2: Strategy (StrategyGenerator → StrategySelector)     │
  │    Phase A.3+A.4: Decision (DecisionEvidence → UnifiedDecisionModel)
  │    Phase A.5: Provider (ProviderRouter.select per capability)      │
  │    Phase A.7: Activity Recording (ActivityManager)                │
  │    Phase A.6: Workflow (WorkflowEngine.start_workflow)            │
  │    build_default_graph().execute(state) — with pipeline_context   │
  │    Post: Provider Memory Feedback → CalibrationEngine             │
  │    Post: Learning Feedback (Consolidator.consolidate_once_async)  │
  └───────────────────────────────────────────────────────────────────┘
```

**Arrow Details:**

| Property | Value |
|----------|-------|
| **File** | `core/routes/chat.py:88` |
| **Function** | `agent_stream()` |
| **Events emitted** | SSE events: `data: {"delta": "text"}`, `tool_start`, `tool_output`, `agent_step`, `metrics`, `[DONE]` |
| **Database reads** | None at route level |
| **Database writes** | None (no persistence at route level) |
| **API calls** | `stream_agent_loop()` → `RuntimePipeline.execute()` → LLM calls via graph |
| **Return type** | `StreamingResponse` (SSE) |
| **Timing** | Async streaming generator |
| **Failure path** | `RuntimePipeline` exception → `agent_loop` logs warning → falls back to `graph.execute(state)` |
| **Plugin hooks** | Via middleware only |
| **Permissions** | No `verify_token` dependency (no auth on this route) |
| **Confirmation** | `pause_before_effectful` reads from config |
| **Status** | `DRIFT` — calls `RuntimePipeline` (legacy) instead of canonical `core/pipeline/`; `RuntimePipeline` duplicates pipeline stages |

### 2.3 POST /v1/chat/completions (OpenAI Compat)

```
  Client → POST /v1/chat/completions
      │
      ▼
  ┌─ core/routes/chat.py:122 ─────────────────────────────────────────┐
  │  @router.post("/v1/chat/completions")                              │
  │  async def openai_compat(body):                                    │
  │    result = await rest_adapter(message=last_msg, ...)              │
  │    return OpenAI-compatible JSON                                   │
  └───────────────────────────────────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| **Status** | `CORRECT` — uses `rest_adapter` → canonical pipeline |
| **Note** | Token counts are estimated (`len(msg) // 4`), not actual |

### 2.4 POST /api/agent/resume/{run_id}

```
  Client → POST /api/agent/resume/{run_id}
      │
      ▼
  ┌─ core/routes/chat.py:200 ─────────────────────────────────────────┐
  │  async def agent_resume(run_id, req):                              │
  │    state = checkpoint_store.load_agent_state(run_id)              │
  │    state.resume_action = action                                    │
  │    state.resume_feedback = feedback                                │
  │    return StreamingResponse(graph.execute(state))                 │
  └───────────────────────────────────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| **Status** | `DORMANT` — uses legacy `checkpoint_store` + `graph.execute()` directly, bypasses both pipelines |

---

## 3. WebSocket Path

### 3.1 /ws/chat_stream (Canonical Streaming WS)

```
  Client → WS /ws/chat_stream
      │
      ▼
  ┌─ core/routes/websocket.py:32 ─────────────────────────────────────┐
  │  @router.websocket("/ws/chat_stream")                              │
  │  async def chat_stream_websocket(ws):                               │
  │    await ws.accept()                                                │
  │    session_id = str(id(ws))                                         │
  │    plugin_registry.run_hook("session_start", ...)                  │
  │    loop:                                                            │
  │      raw = await ws.receive_text()                                  │
  │      msg = json.loads(raw)                                          │
  │      if msg_type == 'chat':                                         │
  │        await ws_adapter.stream_via_pipeline(                        │
  │          ws, text, user_id, session_id                              │
  │        )                                                            │
  │      elif msg_type == 'ping':                                       │
  │        send pong                                                    │
  │    on disconnect:                                                   │
  │      plugin_registry.run_hook("session_end", ...)                  │
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ core/pipeline/adapters/websocket_adapter.py:65 ──────────────────┐
  │  async def stream_via_pipeline(ws, text, ...):                     │
  │    request = Request(text=text, transport="websocket", ...)        │
  │    async for event in stream_pipeline(request):                    │
  │      if stage_start:  → ws.send_json({"type": "stage_start", ...}) │
  │      if stage_end:    → ws.send_json({"type": "stage_end", ...})   │
  │      if stage_error:  → ws.send_json({"type": "stage_error", ...}) │
  │      if pipeline_end: → extract response_text                     │
  │    # Word-token streaming of response:                             │
  │    for word in response_text.split():                              │
  │      ws.send_json({"type": "stream_token", "token": word+" ", ...})│
  └───────────────────────────────────────────────────────────────────┘
```

**Arrow Details:**

| Property | Value |
|----------|-------|
| **File** | `core/routes/websocket.py:33` |
| **Function** | `chat_stream_websocket()` |
| **Events emitted** | `stage_start`, `stage_end`, `stage_error`, `stream_token`, `stream_end` |
| **Database reads** | None |
| **Database writes** | `ConversationManager` via `_run_pipeline` path (non-streaming variant only) |
| **API calls** | `stream_pipeline()` → `Pipeline.execute()` → 19 stages |
| **Return type** | WebSocket JSON messages |
| **Timing** | Async streaming, per-word token delivery |
| **Failure path** | Catch-all exception handler → send `{"type": "error", "message": "..."}` → close |
| **Plugin hooks** | `plugin_registry.run_hook("session_start", ...)` on connect, `session_end` on disconnect |
| **Permissions** | None at WS level |
| **Confirmation** | None |
| **Status** | `CORRECT` — canonical WS streaming path |

### 3.2 /ws/agent_stream (Legacy WS with Project Context)

```
  Client → WS /ws/agent_stream
      │
      ▼
  ┌─ core/routes/websocket.py:151 ────────────────────────────────────┐
  │  @router.websocket("/ws/agent_stream")                             │
  │  async def agent_stream_websocket(ws):                              │
  │    await ws.accept()                                                │
  │    session_id = str(id(ws))                                         │
  │    cm = get_context_manager()                                       │
  │    loop:                                                            │
  │      raw = await ws.receive_text()                                  │
  │      msg = json.loads(raw)                                          │
  │      if msg_type == "session_init":  → store project context       │
  │      if msg_type == "context_update": → refresh project context    │
  │      if msg_type == "chat":                                        │
  │        result = await ws_adapter(text, ...)                        │
  │        conv.add_message("user", text)                               │
  │        conv.add_message("assistant", response_text)                │
  │        conv.save()                                                  │
  │        ws.send_json({"type": "stream_token", "token": response,    │
  │                      "complete": True})                            │
  │      if msg_type == "session_response": → resume                    │
  │      if msg_type == "ping": → pong                                  │
  └───────────────────────────────────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| **Status** | `DRIFT` — uses `ws_adapter()` (non-streaming) even though it's an "agent_stream" endpoint; no tool streaming, no step-by-step output; uses `ConversationManager` for persistence instead of `_persist_chat` |
| **Note** | `ConversationManager` at `core/session.py` is a JSON-file-based store, separate from SQLite `ChatHistory` |

### 3.3 /ws/mcp/bridge

```
  Client → WS /ws/mcp/bridge
      │
      ▼
  ┌─ core/routes/websocket.py:26 ─────────────────────────────────────┐
  │  @router.websocket("/ws/mcp/bridge")                               │
  │  async def mcp_bridge_websocket(websocket):                        │
  │    await mcp_server.handle_websocket(websocket)                    │
  └───────────────────────────────────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| **Status** | `CORRECT` — delegates directly to MCP server; no pipeline involvement |

### 3.4 /ws/logs

```
  Client → WS /ws/logs
      │
      ▼
  ┌─ core/routes/websocket.py:95 ─────────────────────────────────────┐
  │  @router.websocket("/ws/logs")                                     │
  │  async def log_stream_websocket(ws):                                │
  │    await ws.accept()                                                │
  │    tail_file("data/logs/jarvis.json.log")                          │
  │    for each line → ws.send_json({"type": "log_entry", ...})        │
  └───────────────────────────────────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| **Status** | `CORRECT` — passive log tailing, no pipeline involvement |

### 3.5 /ws/{device_id}/{user_id} (External Network WS)

```
  Client → WS /ws/{device_id}/{user_id}
      │
      ▼
  ┌─ core/routes/websocket.py:254 ────────────────────────────────────┐
  │  @router.websocket("/ws/{device_id}/{user_id}")                    │
  │  async def websocket_endpoint(ws, device_id, user_id):            │
  │    await connection_manager.connect(ws, device_id, user_id)       │
  │    send {"type": "connected", ...}                                 │
  │    loop:                                                           │
  │      raw = await ws.receive_text()                                 │
  │      await handle_message(ws, device_id, user_id, raw)             │
  │    on disconnect: connection_manager.disconnect(...)               │
  └───────────────────────────────────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| **Network file** | `network/websocket_server.py` |
| **Status** | `CORRECT` — external device bridge, delegates to `connection_manager` and `handle_message`; not a user-input pipeline path |
| **EventBus integration** | `connection_manager` used by `EventBus._broadcast()` at `core/event_bus.py:123` |

---

## 4. Voice Path

### 4.1 VoiceEngine.process_audio — Full Duplex Voice

```
  Microphone → audio bytes
      │
      ▼
  ┌─ assistant/voice_pipeline.py:421 ─────────────────────────────────┐
  │  async def process_audio(self, audio_bytes):                       │
  │    self.latency.start()                                            │
  │    emotion_context = await self._detect_emotion(audio_bytes)       │
  │    transcribed = await self.transcribe(audio_bytes)                │
  │    PluginEventBus.emit("on_voice_command", text=transcribed)      │
  │    response = await self.think(transcribed, emotion_context)       │
  │    audio_out = await self.speak(response)                          │
  │    self.metrics.record_metrics(stt_ms, think_ms, tts_ms, total_ms)│
  │    return audio_out                                                │
  └───┬───────────────┬───────────────┬───────────────┬───────────────┘
      │               │               │               │
      ▼               ▼               ▼               ▼
  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────┐
  │ Emotion  │  │   STT    │  │  Think       │  │   TTS    │
  │ Detector │  │(Faster-  │  │ voice_adapter│  │ (Kokoro  │
  │core.audio│  │ Whisper) │  │→ pipeline    │  │  /XTTS)  │
  │_emotion  │  │assistant │  │              │  │assistant │
  │          │  │/stt.py   │  │              │  │/tts.py   │
  └──────────┘  └──────────┘  └──────────────┘  └──────────┘
```

**Arrow Details:**

| Phase | File | Function | Timing |
|-------|------|----------|--------|
| Emotion | `core/audio_emotion.py` | `emotion_detector.analyze()` | Async, ~50-200ms |
| STT | `assistant/stt.py` | `stt.transcribe()` | Sync in executor, ~200-2000ms |
| Think | `core/pipeline/adapters/voice_adapter.py:24` | `voice_adapter()` → `process_message()` | Async, pipeline-dependent |
| TTS | `assistant/tts.py` | `tts.synthesize()` | Sync in executor, ~500-3000ms |
| Plugin | `brain/events.py` | `PluginEventBus.emit("on_voice_command")` | Fire-and-forget task |

**Think Phase Detail:**

```
  voice_adapter(text, user_id, metadata)
      │
      ▼
  Request(text=text, transport="voice", ...)
      │
      ▼
  process_message(request) → Pipeline.execute() → 19 stages
      │
      ▼
  Response.text or None on error
```

| Property | Value |
|----------|-------|
| **File** | `assistant/voice_pipeline.py:403` |
| **Function** | `VoiceEngine.think()` |
| **Events emitted** | `on_voice_command` via `PluginEventBus` |
| **Database reads** | Pipeline-dependent (e.g., `ContextRetrievalStage` may read memory) |
| **Database writes** | Pipeline-dependent (e.g., `MemoryStage` may persist) |
| **API calls** | `voice_adapter()` → `process_message()` → all 19 stages |
| **Return type** | `str` (response text) |
| **Timing** | Async, pipeline-dependent |
| **Failure path** | `voice_adapter` returns `None` → `think` returns `""` → `process_audio` says "Sorry, I'm having trouble thinking" |
| **Plugin hooks** | `PluginEventBus.emit("on_voice_command")` |
| **Permissions** | None |
| **Confirmation** | None |
| **Status** | `CORRECT` — voice_adapter goes through canonical pipeline |

### 4.2 VoiceEngine Modes

| Mode | Trigger | Entry | Status |
|------|---------|-------|--------|
| Wake Word | `WakeWordDetector` → `_wake_event.set()` → `VoiceLoop._on_wake()` | `assistant/voice_pipeline.py:600` | `CORRECT` |
| Continuous | VAD → `_process_continuous_chunk()` at line 825 | `assistant/voice_pipeline.py:825` | `CORRECT` |
| Push-to-Talk | `VoiceLoop._record_and_respond()` → `process_audio()` | `assistant/voice_pipeline.py:762` | `CORRECT` |

### 4.3 Voice Latency Tracking

```
  VoiceMetrics tracks 4 phases per command:
  ├─ stt_latency_ms    (microphone → text)
  ├─ think_latency_ms  (text → pipeline → response)
  ├─ tts_latency_ms    (response → audio bytes)
  └─ total_latency_ms  (full round-trip)
  Keeps rolling window of 1000 samples per metric
```

---

## 5. Channel Path

### 5.1 Channel Plugin Architecture

```
  Discord / Slack / Telegram / Matrix / IRC / Email
      │
      ▼
  ┌─ Channel-Specific Plugin ─────────────────────────────────────┐
  │  Each implements ChannelPlugin (channels/base.py)              │
  │  - start(brain): begins polling/listening                     │
  │  - stop(): tears down connection                              │
  │  - send(target, message): sends outgoing message              │
  │  - On message: calls channels/processor.py:process_message()  │
  └──────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
  ┌─ channels/processor.py:23 ──────────────────────────────────────┐
  │  async def process_message(text, source, channel_id,            │
  │                            user_id, user_name):                 │
  │    response_text = await channel_adapter(text, source, ...)    │
  │    _emit_hooks(text, source, channel_id, user_id, user_name,    │
  │               response_text)                                    │
  │    return response_text                                         │
  └──────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
  ┌─ core/pipeline/adapters/channel_adapter.py:18 ──────────────────┐
  │  async def channel_adapter(text, source, channel_id,            │
  │                            user_id, user_name):                 │
  │    request = Request(text=text, transport=source, ...)          │
  │    response: Response = await process_message(request)         │
  │    return response.text or f"Error: {response.error}"           │
  └─────────────────────────────────────────────────────────────────┘
```

**Arrow Details:**

| Property | Value |
|----------|-------|
| **Channel plugins** | `channels/discord_channel.py`, `channels/slack_channel.py`, `channels/telegram_channel.py`, `channels/matrix_channel.py`, `channels/irc_channel.py` |
| **Registration** | `core/lifespan.py:650-674` — ChannelController.register() for all 5 |
| **Startup** | `channel_controller.start_all(unified_brain)` in background task |
| **File (processor)** | `channels/processor.py:23` |
| **Function** | `process_message()` — canonical channel message handler |
| **Events emitted** | `on_channel_message` via `PluginEventBus.instance().emit()` at line 51 |
| **MCP bridge** | If MCP server running → enqueue user + assistant messages at line 63-79 |
| **Database reads** | Pipeline-dependent |
| **Database writes** | Pipeline-dependent |
| **API calls** | `channel_adapter()` → `process_message()` → all 19 stages |
| **Return type** | `str` |
| **Timing** | Async |
| **Failure path** | `channel_adapter` returns `"Error: ..."` → `process_message` returns error string |
| **Plugin hooks** | `on_channel_message` via `PluginEventBus`; MCP server events |
| **Permissions** | None at channel level |
| **Confirmation** | None |
| **Status** | `CORRECT` — canonical path through channel_adapter |

### 5.2 Channel Lifecycle

```
  core/lifespan.py:650 → channel_controller.register(...)
  core/lifespan.py:665 → asyncio.create_task(_start_channels())
      │
      ▼
  channels/controller.py:43
  async def start_all(self, brain):
    for channel in channels:
      await channel.start(brain)
      │
      ▼
      Each channel plugin starts its polling loop:
      - Discord: discord.Client.run() in thread
      - Telegram: polling
      - Slack: SocketModeHandler
      - Matrix: sync loop
      - IRC: socket connection
```

### 5.3 Channel Registration Map

| Channel | File | Registered At | Status |
|---------|------|--------------|--------|
| Discord | `channels/discord_channel.py` | `lifespan.py:652` | `CORRECT` |
| Slack | `channels/slack_channel.py` | `lifespan.py:653` | `CORRECT` |
| Telegram | `channels/telegram_channel.py` | `lifespan.py:654` | `CORRECT` |
| Matrix | `channels/matrix_channel.py` | `lifespan.py:655` | `CORRECT` |
| IRC | `channels/irc_channel.py` | `lifespan.py:656` | `CORRECT` |
| Email | `channels/email_channel.py` | NOT registered in controller (separate routing) | `DORMANT` |
| WhatsApp | `routers/whatsapp.py` | NOT registered in controller (separate REST endpoint) | `DORMANT` |

---

## 6. CLI / TUI Path

### 6.1 CLI Entry: `jarvis.py` → argparse dispatch

```
  Terminal → "jarvis chat" / "jarvis code" / "jarvis build" etc.
      │
      ▼
  ┌─ jarvis.py:254 ──────────────────────────────────────────────────┐
  │  def main():                                                      │
  │    args = parser.parse_args()                                     │
  │    # Dev-mode gate for DEV_COMMANDS                               │
  │    # First-run setup gate                                         │
  │    return args.func(args)                                         │
  └──────────────────────┬────────────────────────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ cmd_cli  │  │ cmd_code │  │ cmd_tui  │
   │(chat)    │  │(dev cmd) │  │(TUI)     │
   └────┬─────┘  └────┬─────┘  └────┬─────┘
        │             │             │
        ▼             ▼             ▼
   ┌─ jarvis-export/cli/cli_commands.py ────────────────────────────┐
   │  Each handler in jarvis-export/cli/cli_commands.py             │
   │  - cmd_cli: prompt_toolkit interactive session                 │
   │  - cmd_code / cmd_build: AgentOrchestrator.code/build()       │
   │  - cmd_tui: launches Textual TUI app                          │
   │  - cmd_web/cmd_server: starts uvicorn FastAPI server          │
   └────────────────────────────────────────────────────────────────┘
```

### 6.2 CLI Chat Path — Full Trace

```
  Terminal → "jarvis chat"
      │
      ▼
  ┌─ jarvis.py:179 ──────────────────────────────────────────────────┐
  │  p_chat.set_defaults(func=cmd_cli)                                │
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ jarvis-export/cli/cli_commands.py:51 ──────────────────────────┐
  │  def cmd_cli(args):                                               │
  │    ensure_local_stack_running(env)  # starts FastAPI if needed   │
  │    session = ConversationManager(session_id)    # JSON-file based │
  │    loop:                                                          │
  │      user_input = prompt_toolkit.PromptSession.prompt()          │
  │      if input starts with '/':  → handle_cli_slash_command()    │
  │      else:                                                        │
  │        result = stream_chat_ws(base_url, payload)                │
  │        # payload: { text, session_id, user_id, mode, ... }      │
  │        session.add_message("user", user_input)                   │
  │        session.add_message("assistant", result)                  │
  │        session.save()   # JSON to ~/.jarvis/history/ .json       │
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ jarvis-export/cli/cli_requests.py:260 ─────────────────────────┐
  │  def stream_chat_ws(base_url, payload) → str:                    │
  │    ws_url = base_url.replace("http://", "ws://") + "/ws/chat_stream"
  │    async with connect(ws_url) as ws:                              │
  │      ws.send(json.dumps(payload))                                 │
  │      while True:                                                  │
  │        msg = ws.recv()                                            │
  │        if type == "stream_token": print(token); full_reply += t  │
  │        if type == "stream_end": break                             │
  │        if type == "error": break                                  │
  │    return full_reply                                              │
  │    FAILURE → fallback to request_json(base_url, "/api/chat", ...)│
  │             → extract_reply(result) → str                         │
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ core/routes/websocket.py:33 ─────────────────────────────────────┐
  │  /ws/chat_stream → chat_stream_websocket()                        │
  │    → ws_adapter.stream_via_pipeline()                              │
  │    → stream_pipeline(request) → 19 canonical stages               │
  └───────────────────────────────────────────────────────────────────┘
```

**Arrow Details:**

| Arrow | File | Function | Norm. | Events | DB Read | DB Write | API | Return | Timing | Failure | Plugins | Perms | Confirm | Status |
|-------|------|----------|-------|--------|---------|----------|-----|--------|--------|---------|---------|-------|---------|--------|
| User→CLI | `jarvis.py:179` | `main()`→`cmd_cli()` | N/A | None | None | None | None | →handler | sync | argparse error | None | None | None | `CORRECT` |
| CLI→Session | `cli_commands.py:88` | `ConversationManager()` | N/A | None | JSON history file | None | None | `CliState.session` | sync | LoadError→empty session | None | None | None | `CORRECT` |
| CLI→WS | `cli_requests.py:260` | `stream_chat_ws()` | N/A | None | None | None | WS `/ws/chat_stream` | `str` | async await | fallback→POST `/api/chat` | None | None | None | `CORRECT` |
| WS→Pipeline | `websocket.py:33` | `chat_stream_websocket()` | N/A | `stage_start/end/error` | None | None | `stream_pipeline()` | WS JSON msgs | per-word streaming | send `{"type":"error"}` | `on_request` hook | None | None | `CORRECT` |

### 6.3 TUI Path — Full Trace

```
  Terminal → "jarvis tui"
      │
      ▼
  ┌─ cli_commands.py:2589 ──────────────────────────────────────────┐
  │  def cmd_tui(args):                                               │
  │    ensure_server_running(base_url)                                │
  │    from jarvis_tui.main import JarvisApp                          │
  │    app = JarvisApp()                                              │
  │    app.run()                                                      │
  └──────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
  ┌─ jarvis_tui/ (external package) ─────────────────────────────────┐
  │  Textual-based TUI application.                                   │
  │  Connects to local FastAPI server via HTTP and WebSocket.         │
  │  Uses same /ws/chat_stream and /api/chat endpoints as CLI.        │
  │  OR runs in standalone mode bypassing the server.                 │
  └───────────────────────────────────────────────────────────────────┘
```

| Arrow | Detail | Status |
|-------|--------|--------|
| User→TUI | `cli_commands.cmd_tui()` → `JarvisApp.run()` | `DORMANT` — jarvis_tui external package, not traced |
| TUI→Server | HTTP/WS to local FastAPI (same paths as CLI) | `DORMANT` — assumed but unconfirmed |
| Reality score | Unknown — external package, standalone mode may bypass pipeline entirely | 2/10 |

### 6.4 CLI Command Dispatch Table

| Command | Handler | File | Pipeline Path | Status | Reality |
|---------|---------|------|--------------|--------|---------|
| `chat` | `cmd_cli()` | `cli_commands.py:51` | WS `/ws/chat_stream` → canonical pipeline (fallback POST) | `CORRECT` | 8/10 |
| `code` | `cmd_code()` | `cli_commands.py` | `AgentOrchestrator.code()` → `AutomationLoop` | `DRIFT` | 5/10 — bypasses canonical pipeline |
| `build` | `cmd_build()` | `cli_commands.py` | `AgentOrchestrator.build()` → `AutomationLoop` | `DRIFT` | 5/10 |
| `run` | `cmd_run()` | `cli_commands.py` | Direct subprocess execution | `DRIFT` | 4/10 |
| `understand` | `cmd_understand()` | `cli_commands.py` | `RepositoryAnalyzer` | `DRIFT` | 4/10 |
| `workspace` | `cmd_workspace()` | `cli_commands.py` | File system operations | `DRIFT` | 4/10 |
| `doctor` | `cmd_doctor()` | `cli_commands.py` | Diagnostics | `CORRECT` | 7/10 |
| `tui` | `cmd_tui()` | `cli_commands.py:2589` | External Textual app → WS | `DORMANT` | 2/10 |
| `web` | `cmd_web()` | `cli_commands.py` | Starts uvicorn | `CORRECT` | 9/10 |
| `server` | `cmd_server()` | `cli_commands.py` | Starts uvicorn | `CORRECT` | 9/10 |
| `gui` | `cmd_gui()` | `cli_commands.py` | Flutter GUI | `DORMANT` | 1/10 |
| `advanced` | `cmd_advanced()` | `cli_commands.py` | Sub-dispatch to scheduler, etc. | `DRIFT` | 3/10 |

---

## 7. Legacy Paths & Bypasses

### 7.1 Legacy `routers/chat.py:chat_handler()` — DEPRECATED

```
  POST /api/chat → routers/chat.py → chat_handler()
      │
      ▼
  Direct intent classification → execute_action → LLM call
  NO canonical pipeline involvement
```

| Property | Value |
|----------|-------|
| **File** | `routers/chat.py` (separate from `core/routes/chat.py`) |
| **Status** | `DORMANT` — superseded by `core/routes/chat.py` |
| **Note** | Identified in Phase 1 as legacy, clearly marked as replaced |

### 7.2 Legacy `channels/processor.py:route_intent()` — DEPRECATED

Referenced by `core/main.py:749` in `execute_action()`. Falls back to `route_intent()` for "message" intent.

| Status | `DORMANT` — channel_adapter supersedes |
|--------|---------|

### 7.3 Legacy Graph Bypass

```
  stream_agent_loop()
      │
      ├── RuntimePipeline.execute() (PRIMARY)
      │       │
      │       └── graph.execute(state) ← WITH pipeline_context (A.1-A.9 phases)
      │
      └── graph.execute(state) ← LEGACY FALLBACK (direct, no pipeline phases)
```

| Property | Value |
|----------|-------|
| **Condition** | `_PIPELINE_ENABLED = False` or `RuntimePipeline` raises exception |
| **Status** | `DRIFT` — dual-path creates maintenance burden, 2 code paths for same logic |

### 7.4 Legacy `agent_runtime.py` — DORMANT

```
  AgentRuntime.run_task() / run_plan() — standalone task execution
  Uses core/llm_router.complete() directly, NO pipeline
```

| Property | Value |
|----------|-------|
| **File** | `core/agent_runtime.py:55` |
| **Status** | `DORMANT` — not wired into any active route; may be dead code |

---

## 8. Stage-by-Stage DRIFT Assessment

### 8.1 Canonical Pipeline Stages (`core/pipeline/stages/`)

| # | Stage | File | Purpose | Status | Reality |
|---|-------|------|---------|--------|---------|
| 1 | `receive` | `stages/receive.py` | Parse raw input, extract attachments | `CORRECT` | 9/10 |
| 2 | `load_context` | `stages/load_context.py` | Load session context, user prefs | `CORRECT` | 8/10 |
| 3 | `authentication` | `stages/auth.py` | Verify identity | `CORRECT` | 8/10 |
| 4 | `tenant_resolution` | `stages/tenant_resolution.py` | Resolve tenant from identity | `CORRECT` | 7/10 |
| 5 | `authorization` | `stages/authorization.py` | Check permissions | `CORRECT` | 7/10 |
| 6 | `resource_access` | `stages/resource_access.py` | Check resource-level access | `CORRECT` | 7/10 |
| 7 | `rate_limit` | `stages/rate_limit.py` | Rate limiting per user/tenant | `CORRECT` | 8/10 |
| 8 | `intent` | `stages/intent.py` | Classify user intent | `CORRECT` | 9/10 |
| 9 | `context_retrieval` | `stages/context_retrieval.py` | Retrieve relevant context/memory | `CORRECT` | 8/10 |
| 10 | `reasoner` | `stages/reasoner.py` | Reasoning/chain-of-thought | `DUPLICATE` | 6/10 — duplicates `brain/reasoning_engine.py` |
| 11 | `planner` | `stages/planner.py` | Create execution plan | `DUPLICATE` | 5/10 — duplicates `core/planner/` and `RuntimePipeline` planning |
| 12 | `plan_validator` | `stages/plan_validator.py` | Validate plan before execution | `CORRECT` | 7/10 |
| 13 | `capability_selection` | `stages/capability_selection.py` | Select capability/provider | `DUPLICATE` | 5/10 — duplicates `infer_capabilities()` in `core/pipeline.py:38` |
| 14 | `execution` | `stages/execution.py` | Execute LLM call with providers | `DUPLICATE` | 4/10 — duplicates `core/pipeline.py` + `core/graph/` execution; has 2 provider implementations (LiteLLM, OllamaFallback) |
| 15 | `verification` | `stages/verification/` | Verify output quality | `CORRECT` | 7/10 |
| 16 | `epistemic` | `stages/epistemic.py` | Tag epistemic status | `CORRECT` | 8/10 |
| 17 | `memory` | `stages/memory.py` | Persist to memory stores | `CORRECT` | 8/10 |
| 18 | `metrics` | `stages/metrics.py` | Record metrics | `CORRECT` | 9/10 |
| 19 | `formatter` | `stages/formatter.py` | Format final response | `CORRECT` | 9/10 |

### 8.2 Legacy RuntimePipeline Phases (`core/pipeline.py`)

| Phase | Name | File | Status | Reality |
|-------|------|------|--------|---------|
| A.8 | Knowledge Injection | `core/pipeline.py:161` | `DUPLICATE` | 5/10 — overlaps with `context_retrieval` stage |
| A.1 | Planning | `core/pipeline.py:173` | `DUPLICATE` | 4/10 — overlaps with `planner` stage |
| A.2 | Strategy | `core/pipeline.py:186` | `DRIFT` | 4/10 — no equivalent in canonical pipeline |
| A.3+A.4 | Decision | `core/pipeline.py:199` | `DRIFT` | 4/10 — no equivalent in canonical pipeline |
| A.5 | Provider Selection | `core/pipeline.py:216` | `DUPLICATE` | 5/10 — overlaps with `capability_selection` stage |
| A.7 | Activity Recording | `core/pipeline.py:238` | `DRIFT` | 5/10 — activity recording not in canonical pipeline |
| A.6 | Workflow | `core/pipeline.py:264` | `DRIFT` | 4/10 — workflow engine not in canonical pipeline |
| — | Graph Execution | `core/pipeline.py:326` | `DUPLICATE` | 4/10 — duplicates `execution` stage |
| A.8.5 | Provider Memory Feedback | `core/pipeline.py:411` | `DRIFT` | 5/10 — provider memory not in canonical pipeline |
| A.9 | Learning Feedback | `core/pipeline.py:456` | `DRIFT` | 5/10 — consolidation not in canonical pipeline |

### 8.3 DRIFT Summary (Counts)

| Category | Count | Action Required |
|----------|-------|-----------------|
| `CORRECT` | 20 | None — actively used, properly wired |
| `DRIFT` | 11 | Migrate to canonical pipeline or document intentional divergence |
| `DUPLICATE` | 10 | Consolidate into single implementation |
| `DORMANT` | 7 | Verify dead code, remove if confirmed unused |

---

## 9. Discovery Summary

### 9.1 Key Findings

1. **Two pipelines coexist**: `core/pipeline/` (19 stages, canonical) and `core/pipeline.py` (10 phases, legacy). Both are active.
2. **`stream_agent_loop` is the bridge**: It tries `RuntimePipeline` first, falls back to legacy graph. Neither uses the canonical 19-stage pipeline.
3. **4 adapters successfully bridge to canonical pipeline**: REST, WebSocket (streaming), Channel, Voice all use `process_message()` or `stream_pipeline()`.
4. **`/api/agent/stream` and `/ws/agent_stream` bypass canonical pipeline**: They go through `stream_agent_loop` → `RuntimePipeline` → legacy graph.
5. **CLI/TUI paths are untraced**: Need to read `cli_commands.py` to determine whether they use canonical pipeline or direct calls.
6. **Duplicate capability selection**: `infer_capabilities()` in `core/pipeline.py:38` is a keyword-based classifier that duplicates `core/routing/request_classifier.py` and the `intent` stage.
7. **Duplicate planning**: `RuntimePipeline` planning (A.1) duplicates `planner` stage.
8. **Strategy, Decision, Workflow, Activity Recording, Provider Memory, Learning Feedback**: These 6 phases exist only in `RuntimePipeline`, not in the canonical pipeline.
9. **No single request path traverses all 19 stages**: Different entry points hit different subsets.

### 9.2 Reality Scores

| Entry Point | Stages Executed | Reality Score |
|-------------|----------------|---------------|
| `POST /api/chat` | All 19 (canonical) | 9/10 |
| `POST /api/agent/stream` | 10 phases (legacy) + graph | 4/10 |
| `POST /v1/chat/completions` | All 19 (canonical) | 9/10 |
| `WS /ws/chat_stream` | All 19 (canonical, streaming) | 9/10 |
| `WS /ws/agent_stream` | Adapter (canonical, non-streaming) | 6/10 |
| Voice `process_audio` | All 19 (canonical) | 9/10 |
| Channel messages | All 19 (canonical) | 9/10 |
| CLI `jarvis chat` | Unknown | 3/10 |
| TUI | Unknown | 2/10 |

### 9.3 Recommended Actions (Phase 3)

1. **Deprecate `core/pipeline.py`** — migrate `RuntimePipeline` phases into canonical pipeline stages (Strategy, Decision, Workflow, Activity Recording, Provider Memory, Learning Feedback).
2. **Rewrite `stream_agent_loop`** to use `stream_pipeline()` from canonical pipeline instead of `RuntimePipeline`.
3. **Rewrite `/ws/agent_stream`** to use `stream_via_pipeline()` instead of non-streaming `ws_adapter()`.
4. **Trace CLI/TUI paths** fully — audit `cli_commands.py` and wire through canonical pipeline.
5. **Consolidate duplicate classifiers** — merge `request_classifier.py`, `infer_capabilities()`, and `intent` stage.
6. **Remove dead code** — `AgentRuntime.run_task()`, legacy `routers/chat.py`, `route_intent()`.
7. **Add 6 missing stages** to canonical pipeline: `strategy`, `decision`, `workflow`, `activity_recording`, `provider_memory_feedback`, `learning_feedback`.
