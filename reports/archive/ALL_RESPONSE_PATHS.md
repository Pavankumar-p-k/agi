# JARVIS All Response Generation Paths

## 1. The "Stateful REST" Path
**File:** `core/routes/chat.py`
**Entry Point:** `POST /api/chat`
**Logic:** `routers/chat.py:chat_handler`
**Features:** 
*   Uses `ConversationManager` (Linear History)
*   Uses `MemoryFacade` (Semantic Recall)
*   Uses `ragflow_search` (RAG)
*   Uses `UnifiedBrain.three_pass` (Critique Loop)
**Status:** **ACTIVE** - Used by WebUI (fallback) and Flutter App.

## 2. The "Agentic Streaming" Path
**File:** `core/routes/chat.py`
**Entry Point:** `POST /api/agent/stream`
**Logic:** `core/agent_loop.py:stream_agent_loop` -> `core/graph`
**Features:**
*   Uses `StateGraph` (Agentic Loops)
*   Multi-round tool execution.
**Status:** **ACTIVE** - Used by advanced WebUI features.

## 3. The "WebSocket Stream" Path
**File:** `core/routes/websocket.py`
**Entry Point:** `WS /ws/chat_stream`
**Logic:** `stream_agent_loop` + Custom Inline Completion
**Features:**
*   Redundant history/memory/RAG injection.
*   Direct `LiteLLM` calls + `complete_vision`.
**Status:** **ACTIVE** - Used by CLI and WebUI.

## 4. The "Broken AI OS" Path
**File:** `api/ai_os_routes.py`
**Entry Point:** `POST /ai_os/execute`
**Logic:** `AIOrchestrator.run`
**Features:**
*   Relies on missing `jarvis_os`.
**Status:** **BROKEN** - Used by TUI.

## 5. The "Hybrid Shadow" Path
**File:** `api/hybrid_integration.py`
**Entry Point:** `POST /api/hybrid/chat`
**Logic:** `hybrid_orchestrator.execute_goal`
**Features:**
*   Independent model fallback.
*   OpenClaw executor.
**Status:** **PARTIAL** - Not used by main UI.

## 6. The "Legacy Server" Path
**File:** `api/server.py`
**Entry Point:** `POST /chat`
**Logic:** `UnifiedBrain.three_pass`
**Features:**
*   Stateless.
**Status:** **LEGACY** - Not included in `core/main.py`.

## 7. The "Sub-Agent" Path
**File:** `api/agent_routes.py`
**Entry Point:** `POST /api/v1/{agent_name}/run`
**Logic:** `AgentRegistry`
**Status:** **ACTIVE** - Used for specific agent tasks.
