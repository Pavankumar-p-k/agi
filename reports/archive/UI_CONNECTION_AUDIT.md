# UI Connection Audit

Traced: UI → API Route → Handler → Tool → Result

## Summary

| Status | Count | % |
|--------|-------|---|
| **CONNECTED** | ~225 | 96% |
| **PARTIAL** | 2 | 1% |
| **BROKEN** | 2 | 1% |
| **FAKE** | 2 | 1% |

## BROKEN Routes — FIXED

### 1. `POST /api/system/test-alert` ✅
- **File:** `core/routes/admin.py:107`
- **Fix:** Created `core/proactive_monitor.py` with `Alert` dataclass and `ProactiveMonitor` class + registered `init_proactive_monitor()` in `core/lifespan.py`

### 2. `POST /build/overnight` ✅
- **File:** `core/routes/cowork.py:111`
- **Fix:** Created `core/agent_executor.py` wrapping `core.agent_orchestrator.build()`

## FAKE Routes — FIXED

### 1. `GET /auth/status` ✅
- **File:** `core/routes/auth.py:42`
- **Fix:** Now returns real data from `get_auth_manager()` — configured, user_count, providers, signup_enabled

### 2. `GET /mcp/tools` ✅
- **File:** `core/routes/mcp.py:18`
- **Fix:** Now dynamically queries `mcp_server.get_tool_definitions()`

## PARTIAL Routes

### 1. `POST /api/chat`
- **File:** `core/routes/chat.py:41`
- **Issue:** Only registered if `routers.chat.chat_handler` imports successfully (conditional registration)

### 2. `POST /stt/local`
- **File:** `core/routes/voice.py:38`
- **Issue:** Exact duplicate of `POST /stt` — same handler, no distinct behavior

## Disabled Tools (10)

Registered in descriptions/index but blocked at execution layer (`BROKEN_TOOLS` set in `core/tools/execution.py:40`):

`chat_with_model`, `create_session`, `list_sessions`, `send_to_session`, `pipeline`, `manage_session`, `manage_memory`, `list_models`, `ui_control`, `ask_teacher`

## Tool Execution Chain (Working)

```
WebSocket /ws/agent_stream
  → classify_request()
  → stream_agent_loop()
    → StateGraph (setup → think → tool_call → verify → route)
      → execute_tool_block() in core/tools/execution.py:1301
        → _TOOL_HANDLERS[74 handlers]
          → browser_tools (12) ✅
          → vision_tools (1) ✅
          → skill_tools (4) ✅
          → settings_tools (4) ✅
          → document_tools (5) ✅
          → admin_tools (4) ✅
          → cookbook_tools (14) ✅
          → file/edit tools (7, inline) ✅
        → MCP tool fallback (bash, python, read_file, etc.) ✅
      → format_tool_result() → SSE event → WebSocket
```

## Classification

| Layer | Status |
|-------|--------|
| UI → WS endpoint | ✅ CONNECTED (8 WS endpoints) |
| WS → Agent Loop | ✅ CONNECTED |
| Agent Loop → Graph | ✅ CONNECTED |
| Graph → Tool Execution | ✅ CONNECTED (74 handlers) |
| Tool → Implementation | ✅ CONNECTED (12 browser tools just added) |
| REST API → Handler | ✅ 225/235 CONNECTED |
| Handler → Logic | ❌ 2 BROKEN (proactive_monitor, agent_executor) |
| Admin → Fake | ❌ 2 FAKE (auth/status, mcp/tools) |
