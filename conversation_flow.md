# JARVIS Conversation Flow Discovery

## Actual Runtime Flow

Currently, JARVIS has at least **four** distinct runtime flows for handling user messages, depending on the entry point and mode. This fragmentation is the root cause of inconsistent behavior and context loss.

### 1. The "Simple Chat" Flow (REST)
**Used by:** `/api/chat`, CLI in "chat" mode.
**Path:**
User Message -> `core/routes/chat.py` -> `routers/chat.py` -> `UnifiedBrain.three_pass` -> `ReasoningEngine` -> Response.
*   **State:** Stateless.
*   **Context:** Only current message + semantic RAG recall. **No linear history.**

### 2. The "WebSocket Chat" Flow
**Used by:** `/ws/chat_stream` (Web UI).
**Path:**
User Message -> `core/routes/websocket.py` -> Inline logic -> `execute_action` -> Response.
*   **State:** Stateless.
*   **Context:** Re-implements semantic RAG. **No linear history.**

### 3. The "Agentic Graph" Flow
**Used by:** `/api/agent/stream`, `/os/agents/run` (occasionally CLI).
**Path:**
User Message -> `core/agent_loop.py` -> `core/graph (StateGraph)` -> `think_node` -> `tool_call_node` -> `verify_node` -> Response.
*   **State:** Stateful (within a single run).
*   **Context:** Takes a message list, but callers often pass only the current message.

### 4. The "Hybrid Orchestrator" Flow
**Used by:** High-level autonomous goals.
**Path:**
User Message -> `HybridOrchestrator.execute_goal` -> Strategic Planning -> Decomposition -> Parallel Execution -> Synthesis -> Response.
*   **State:** Task-based state tracking.

---

## Desired Runtime Flow

To achieve modern stateful AI behavior (LangGraph/OpenDevin style), all message paths must converge into a single, state-aware orchestrator.

```
User Message
↓
Session Manager (Load full linear history)
↓
Context Builder (History + Semantic Memory + RAG + Workspace State)
↓
StateGraph Orchestrator (LangGraph Style)
    ├─ Intent Analysis & Routing
    ├─ Planning & Decomposition
    ├─ Tool Execution Loop
    └─ Reality Verification
↓
State Update (Save session, Persist memories, Update task status)
↓
Unified Response Dispatcher (Stream/REST/WebSocket)
```

## Verdict
JARVIS behaves like a "collection of stateless message handlers" because it **is** a collection of stateless message handlers. The "Brain" is fragmented across multiple modules with redundant and inconsistent logic.
