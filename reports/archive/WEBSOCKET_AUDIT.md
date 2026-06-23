# PHASE 8 — WebSocket Audit

Every WebSocket endpoint verified against actual implementation.
Produced with file:line evidence for every finding.

---

## WebSocket Endpoint Inventory

| # | Path | File:Line | Type | Auth | Streaming | Callers |
|---|------|-----------|------|------|-----------|---------|
| 1 | `/ws/chat_stream` | `websocket.py:32` | Chat | None | Token-by-token | Web UI, CLI |
| 2 | `/ws/agent_stream` | `websocket.py:287` | Agent | None | SSE events | CLI, Electron |
| 3 | `/ws/logs` | `websocket.py:231` | Logs | None | 300ms poll | Web UI |
| 4 | `/ws/mcp/bridge` | `websocket.py:26` | MCP | None | Delegated | MCP clients |
| 5 | `/ws/terminal` | `terminal.py:13` | Shell | None | stdout/stderr | Web UI |
| 6 | `/voice` | `voice.py:145` | Audio | None | Binary audio | Electron |
| 7 | `/tts/stream` | `voice.py:123` | TTS | None | Binary WAV | Unknown |
| 8 | `/{device_id}/{user_id}` | `websocket.py:714` | Device | None | JSON messages | Device clients |

---

## Endpoint 1: `/ws/chat_stream`

**File:** `core/routes/websocket.py:32`

**Registration:** 
- `core/main.py:142` — `/ws/` prefix in `AUTH_EXEMPT_PREFIXES`
- Router mounted at `core/main.py` line 370

**Handler:** `websocket_chat_endpoint()` (line 32-222)

**Message types:**
| Direction | Type | Format | Line |
|-----------|------|--------|------|
| Client→Server | `chat` | JSON `{"message": "..."}` | 43 |
| Client→Server | `ping` | JSON `{"type": "ping"}` | 47 |
| Server→Client | `stream_token` | JSON `{"type": "stream_token", "text": "..."}` | 129 |
| Server→Client | `stream_tokens` | JSON `{"type": "stream_tokens", "tokens": [...]}` | 120 |
| Server→Client | `pong` | JSON `{"type": "pong"}` | 50 |
| Server→Client | `error` | JSON `{"type": "error", "message": "..."}` | 197 |

**Timeout configuration:**
| Operation | Timeout | Line |
|-----------|---------|------|
| Context building | 8s | 71 |
| Intent extraction | 15s | 90 |
| Action execution | 15s | 101 |
| Ollama HTTPX | 30s | 151 |

**Reconnect behavior:** No server-side reconnect. On disconnect, runs `plugin_registry.session_end()` (line 213).

**Authentication:** NONE — exempt from session auth middleware.

---

## Endpoint 2: `/ws/agent_stream`

**File:** `core/routes/websocket.py:287`

**Handler:** `agent_stream_endpoint()` (line 287-566)

**Session flow:**
1. Client sends `session_init` → server returns `workspace_summary` (lines 295-300)
2. Client sends `chat` → server creates AgentState, runs `stream_agent_loop()` (lines 380-400)

**Message types:**
| Direction | Type | Description | Line |
|-----------|------|-------------|------|
| Client→Server | `session_init` | Initialize session with project context | 295 |
| Client→Server | `context_update` | Update project context | 320 |
| Client→Server | `chat` | Send user message | 380 |
| Client→Server | `ping` | Keepalive | 560 |
| Server→Client | `workspace_summary` | Project summary after init | 305 |
| Server→Client | `classification` | Intent classification result | 400 |
| Server→Client | `phase_change` | Agent phase transition | 410 |
| Server→Client | `stream_token` | Individual token | 420 |
| Server→Client | `tool_start` | Tool execution started | 430 |
| Server→Client | `tool_end` | Tool execution completed | 450 |
| Server→Client | `tool_confirm` | Safety confirmation requested | 470 |
| Server→Client | `stream_end` | Stream complete | 500 |
| Server→Client | `error` | Error occurred | 530 |

**Timeout configuration:**
- Tool execution: 120s subprocess timeout (line 653)
- No WebSocket-level timeout (beyond the server-wide 60s ping interval)

**Reconnect behavior:** None server-side. Client-side auto-reconnect in web UI (3s delay).

**Authentication:** NONE — exempt from session auth middleware.

---

## Endpoint 3: `/ws/logs`

**File:** `core/routes/websocket.py:231`

**Handler:** `log_stream_endpoint()` (line 231-280)

**Behavior:**
- Unidirectional (server→client only)
- Polls `data/logs/jarvis.json.log` every 300ms (line 261)
- Sends `log_entry` events with `message`, `severity`, `timestamp`

**Authentication:** NONE.

---

## Endpoint 4: `/ws/mcp/bridge`

**File:** `core/routes/websocket.py:26`

**Handler:** Delegates to `mcp_server.handle_websocket()` (imported from `mcp._common`)

**Behavior:** Full duplex — forwards WebSocket messages to MCP server.

**Authentication:** `core/gateway/auth.py:22` — `BridgeAuth` checks `MCP_BRIDGE_TOKEN` env var.
- If token configured: checks query param or `Authorization` header
- If no token: allows all connections

---

## Endpoint 5: `/ws/terminal`

**File:** `core/routes/terminal.py:13`

**Handler:** `terminal_endpoint()` (line 13-88)

**Behavior:**
- Receives `command` messages, sends `output` messages with `stream` field ("stdout"/"stderr")
- Creates persistent subprocess (powershell/bash) per connection
- Subprocess persists until WebSocket disconnect

**Timeout:** None — subprocess runs until disconnect.

**Authentication:** NONE.

---

## Endpoint 6: `/voice`

**File:** `core/routes/voice.py:145`

**Handler:** `voice_websocket_endpoint()` (line 145-185)

**Behavior:**
- Binary audio-in (WAV), binary audio-out (WAV)
- Minimum 1024-byte threshold before processing (line 156)
- Delegates to `VoicePipeline.process_audio()` (line 169)

**Authentication:** NONE — no dependency on `verify_token`.

---

## Endpoint 7: `/tts/stream`

**File:** `core/routes/voice.py:123`

**Handler:** `tts_stream_endpoint()` (line 123-142)

**Behavior:**
- Receives JSON `{"text": "..."}` 
- Returns binary WAV audio bytes
- Blocking per-utterance (not true streaming)

**Authentication:** NONE.

---

## Endpoint 8: `/{device_id}/{user_id}`

**File:** `core/routes/websocket.py:714`

**Handler:** `websocket_endpoint()` (line 714-770)

**Behavior:**
- Receives `ping`, `chat`, and other message types
- `chat` messages routed through `llm_router.acompletion()` with 30s timeout
- All unknown messages echo'd back
- Tracks connections in `ConnectionManager` dict (`network/websocket_server.py:27`)

**Authentication:** NONE.

---

## Authentication Gap Analysis

| WS Endpoint | Local Only | LAN Safe | Internet Safe |
|-------------|------------|----------|---------------|
| `/ws/chat_stream` | ✅ Safe | ⚠️ No auth but local IP | ❌ DANGEROUS |
| `/ws/agent_stream` | ✅ Safe | ⚠️ No auth but local IP | ❌ DANGEROUS |
| `/ws/logs` | ✅ Safe | ⚠️ No auth — exposes logs | ❌ DANGEROUS |
| `/ws/mcp/bridge` | ✅ Safe | ⚠️ Token-based (if configured) | ⚠️ Token-based |
| `/ws/terminal` | ✅ Safe | ⚠️ Shell access with no auth | ❌ FULL RCE |
| `/voice` | ✅ Safe | ⚠️ Voice processing | ❌ DANGEROUS |
| `/tts/stream` | ✅ Safe | ⚠️ Voice processing | ❌ DANGEROUS |
| `/{device_id}/{user_id}` | ✅ Safe | ⚠️ No auth but local IP | ❌ DANGEROUS |

**Summary:** 7/8 endpoints are unauthenticated. `/ws/mcp/bridge` has optional token auth.

---

## Streaming Implementation

| Endpoint | Method | Chunk Size | Format | Backpressure |
|----------|--------|-----------|--------|-------------|
| `/ws/chat_stream` | WebSocket push | Word-by-word | JSON events | None |
| `/ws/agent_stream` | SSE via WebSocket | Token-by-token | SSE events | None |
| `/ws/logs` | Polling (300ms) | Line-by-line | JSON events | Client ignores |
| `/ws/terminal` | WebSocket push | stdout lines | JSON events | None |
| `/voice` | WebSocket binary | Chunked WAV | Binary | None |
| `/tts/stream` | WebSocket binary | Full utterance | Binary WAV | None |

**No backpressure** implemented anywhere. Fast-generating models could overflow client buffers.

---

## Timeout Configuration

| Component | Timeout | Configurable via | File:Line |
|-----------|---------|-----------------|-----------|
| Server ping interval | 60s | `ws_ping_interval` | `main.py:715` |
| Server ping timeout | 30s | `ws_ping_timeout` | `main.py:716` |
| Context building | 8s | Hardcoded | `websocket.py:71` |
| Intent extraction | 15s | Hardcoded | `websocket.py:90` |
| Action execution | 15s | Hardcoded | `websocket.py:101` |
| Ollama API | 30s | Hardcoded | `websocket.py:151` |
| Shell command | 120s | Hardcoded | `websocket.py:653` |
| Device WS LLM | 30s | Hardcoded | `network/websocket_server.py:84` |

---

## Recommendations

1. **Add authentication to ALL WebSocket endpoints.** At minimum, require token for `/ws/terminal` (direct shell access).
2. **Implement WebSocket-level timeouts** per-connection (max session duration, idle timeout).
3. **Add backpressure handling** — if client buffer is full, slow token emission.
4. **Reconnection tokens** — allow resuming interrupted sessions with a reconnect token.
5. **Rate limiting per WebSocket connection** — limit messages/sec to prevent abuse.
6. **Remove or secure `/ws/mcp/bridge`** — MCP bridge should always require the token.
