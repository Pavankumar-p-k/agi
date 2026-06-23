# PHASE 3 — Execution Path Audit

Trace actual execution flow from CLI input to response. Every step verified by reading actual code.

---

## Flow 1: CLI Chat (`jarvis.py chat`)

### Step-by-step

```
User runs: python jarvis.py chat --new-session
```

| Step | File:Line | What Happens | Status |
|------|-----------|-------------|--------|
| 1 | `jarvis.py:89-95` | `main()` parses args, dispatches to `args.func(args)` which is `cmd_cli` | VERIFIED |
| 2 | `cli_commands.py:48-52` | `cmd_cli()` calls `ensure_local_stack_running()` | VERIFIED |
| 3 | `cli_server.py:193-195` | `ensure_local_stack_running()` starts Ollama + FastAPI server | VERIFIED |
| 4 | `cli_commands.py:60-65` | Creates `ConversationManager` (session) + loads config | VERIFIED |
| 5 | `cli_commands.py:78-85` | Enters `prompt_toolkit` loop, reads user input | VERIFIED |
| 6 | `cli_commands.py:142-150` | Calls `stream_agent_ws()` with user message | VERIFIED |
| 7 | `cli_requests.py:336-440` | `stream_agent_ws()` connects to `ws://localhost:8000/ws/agent_stream` | VERIFIED |
| 8 | `core/routes/websocket.py:287` | WebSocket handler receives connection | VERIFIED |
| 9 | `core/routes/websocket.py:380-400` | Calls `stream_agent_loop()` from `core/agent_loop.py` | VERIFIED |
| 10 | `core/agent_loop.py:31-87` | Creates StateGraph via `build_default_graph()`, executes with AgentState | VERIFIED |
| 11 | `core/graph/graph.py:43-88` | StateGraph executes nodes in sequence, yields SSE events | VERIFIED |
| 12 | `core/graph/nodes.py:71-250` | `setup_node()` — MCP setup, tool selection, system prompt | VERIFIED |
| 13 | `core/graph/nodes.py:251-488` | `think_node()` — LLM call via `stream_llm_with_fallback()` | VERIFIED |
| 14 | `core/graph/nodes.py:489-632` | `route_node()` — tool block resolution, loop detection | VERIFIED |
| 15 | `core/graph/nodes.py:729-878` | `tool_call_node()` — concurrent tool execution | VERIFIED |
| 16 | `core/tools/execution.py:1600-1652` | `_TOOL_HANDLERS` dispatch to actual tool handlers | VERIFIED |
| 17 | Streams back through WebSocket → CLI display | VERIFIED |

**Complete execution path exists.** All steps connected end-to-end.

---

## Flow 2: FastAPI Chat (`POST /api/chat`)

```
HTTP POST /api/chat {"message": "hello", "session_id": "..."}
```

| Step | File:Line | What Happens | Status |
|------|-----------|-------------|--------|
| 1 | `core/main.py:192-511` | Route registration — mount `core/routes/chat.py` router | VERIFIED |
| 2 | `core/routes/chat.py:40-73` | `chat_handler()` — receives POST, validates auth | VERIFIED |
| 3 | `core/routes/chat.py:60-65` | Calls `memory.store()` via `MemoryFacade` | VERIFIED |
| 4 | `core/routes/chat.py:68-71` | Calls `llm_router.generate()` for response | VERIFIED |
| 5 | Response returned as JSON | VERIFIED |

**Path exists.** But note: `/api/chat` is used as fallback when WebSocket fails (cli_requests.py:290).

---

## Flow 3: WebSocket Chat (`/ws/chat_stream`)

```
WebSocket ws://localhost:8000/ws/chat_stream
```

| Step | File:Line | What Happens | Status |
|------|-----------|-------------|--------|
| 1 | `core/main.py:142` | `/ws/` prefix is in `AUTH_EXEMPT_PREFIXES` — no auth | VERIFIED |
| 2 | `core/routes/websocket.py:32` | `websocket_chat_endpoint()` receives connection | VERIFIED |
| 3 | `core/routes/websocket.py:43-50` | Receives JSON with `message` field | VERIFIED |
| 4 | `core/routes/websocket.py:67-71` | Calls `build_unified_context()` with 8s timeout | VERIFIED |
| 5 | `core/context_builder.py:34-40` | Gathers conversation history + memory recall | VERIFIED |
| 6 | `core/routes/websocket.py:83-101` | Calls `execute_action()` with intent classification + 15s timeout | VERIFIED |
| 7 | `core/main.py:581-670` | `execute_action()` routes to handlers for open_url, play_media, web_search, etc. | VERIFIED |
| 8 | Falls back to `llm_router.generate()` for unclassified messages | VERIFIED |
| 9 | Streams tokens via `stream_token` events | VERIFIED |

**Path exists.** `execute_action()` has branches for 7 intent types.

---

## Flow 4: WebSocket Agent Stream (`/ws/agent_stream`)

```
WebSocket ws://localhost:8000/ws/agent_stream
```

| Step | File:Line | What Happens | Status |
|------|-----------|-------------|--------|
| 1 | `core/routes/websocket.py:287` | `agent_stream_endpoint()` receives connection | VERIFIED |
| 2 | `core/routes/websocket.py:295-300` | Handles `session_init` → sends `workspace_summary` | VERIFIED |
| 3 | `core/routes/websocket.py:380-400` | Calls `stream_agent_loop()` with user message | VERIFIED |
| 4 | `core/agent_loop.py:31-87` | StateGraph execution starts | VERIFIED |
| 5 | SSE events stream back through WebSocket | VERIFIED |

**Path exists.** This is the primary path used by CLI chat.

---

## Flow 5: Autonomous Build (`cmd_build`)

```
python jarvis.py build
```

| Step | File:Line | What Happens | Status |
|------|-----------|-------------|--------|
| 1 | `jarvis.py:29-86` | Parser dispatches to `cmd_build` | VERIFIED |
| 2 | `cli_commands.py:2302-2331` | `cmd_build()` calls `AgentOrchestrator.build()` | VERIFIED |
| 3 | `core/agent_orchestrator.py:107-152` | `build()` ensures automation running | VERIFIED |
| 4 | `core/agent_orchestrator.py:46-53` | `_ensure_automation()` lazy-imports `brain.*` modules | VERIFIED |
| 5 | `brain/automation/loop.py:1086-1191` | `_phase_build()` executes build command | VERIFIED |
| 6 | `brain/automation/loop.py:2548-2600` | `_repair()` — LLM-mediated repair on failure | VERIFIED |
| 7 | `brain/repair_modules/*.py` | Deterministic fix functions (imports, layouts, manifest, etc.) | VERIFIED |

**Path exists.** Full autonomous pipeline from CLI to repair modules.

---

## Dead Branches & Unreachable Code

### 1. `core/main.py:260-265` — Commented-out route mounts
```python
# app.include_router(hybrid_integration.router, prefix="/api/hybrid", tags=["hybrid"])
# app.include_router(hybrid_integration.mobile_router, prefix="/api/mobile", tags=["mobile"])
```
**Status:** DEAD — `/api/hybrid/*` and `/api/mobile/*` routes never mounted.

### 2. `core/main.py:227-239` — Commented-out OS routes
```python
# app.include_router(os_routes.router, ...)
# app.include_router(ai_os_router, ...)
```
**Status:** DEAD — `/api/os/` and `/api/ai-os/` routes never mounted. The `jarvis_os/` package is only accessible through local runtime fallback in `cli_requests.py`.

### 3. `api/hybrid_integration.py` — Full route file with 7 endpoints
**Status:** DEAD — the module is never imported (mounts are commented out in main.py).

### 4. `routers/dot_routes.py` — `/api/dot/stocks` and `/api/dot/news`
**Status:** ALIVE — mounted in main.py. These are Yahoo Finance / BBC RSS proxies.

### 5. Never-called API endpoints (~30 endpoints defined in `api.ts` but no page calls them)
**Status:** DEAD — listed in UI_CONNECTION_AUDIT.md.

---

## Two Parallel Execution Systems

The codebase has **two distinct execution pipelines** with overlapping functionality:

### Pipeline 1: Legacy `core/tools/` (used by CLI chat)
```
cli_requests.py → stream_agent_ws()
  → core/routes/websocket.py (agent_stream)
    → core/agent_loop.py
      → core/graph/ (StateGraph, 10 nodes)
        → core/tools/execution.py (_TOOL_HANDLERS)
```
**Used for:** All CLI chat interactions, Web UI chat.

### Pipeline 2: Brain Autonomous (used by code/build/run)
```
cli_commands.py → cmd_code()/cmd_build()/cmd_run()
  → core/agent_orchestrator.py
    → brain/automation/loop.py (2652 lines)
      → brain/executor/executor.py
        → brain/tools/tool_registry.py
          → core/tools/implementations.py (core/tools bridge)
```
**Used for:** Autonomous code generation, build automation, project analysis.

### Bridge between systems
`brain/tools/tool_registry.py` bridges Pipeline 2 → Pipeline 1 by importing `core/tools/implementations.py` functions and wrapping them as async tools for the brain executor.

---

## Key Finding: Unreachable Code

| Code | File:Line | Reason Unreachable |
|------|-----------|-------------------|
| `do_manage_tokens` | `core/tools/admin_tools.py` | Registered in `_TOOL_HANDLERS` but `manage_tokens` is in `BROKEN_TOOLS` — returns DISABLED |
| `do_manage_webhooks` | `core/tools/admin_tools.py` | Same — in BROKEN_TOOLS |
| `do_manage_endpoints` | `core/tools/admin_tools.py` | Same — in BROKEN_TOOLS |
| `do_manage_mcp` | `core/tools/admin_tools.py` | Same — in BROKEN_TOOLS |
| `_parse_manage_memory` | `core/tools/execution.py:383` | Parser exists but `manage_memory` is in BROKEN_TOOLS |
| `build_repomap` prompt entry | `core/agent_prompts.py:49` | No handler registered anywhere |
| `code_graph` prompt entry | `core/agent_prompts.py:51` | No handler registered anywhere |
