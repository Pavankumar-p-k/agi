# CANONICAL CHAT PATH SELECTION

## The Selection: `core.agent_loop.stream_agent_loop`

### Rationale
To align with modern AI architectures (LangGraph/OpenDevin), the **StateGraph** path is the only one capable of handling the complexity of autonomous agents, multi-step tool verification, and reality-checking.

| Feature | `UnifiedBrain` (Legacy) | `StateGraph` (Canonical) |
| :--- | :--- | :--- |
| **Streaming** | Pass-through only. | Token-by-token native. |
| **Tool Use** | Single-pass or three-pass. | Iterative (Agentic). |
| **State** | Stateless or JSON-based. | Persistent `AgentState`. |
| **Verification** | Assumed success. | Node-based validation. |

### Canonical Components
*   **Route:** `/api/agent/stream` (and `/ws/chat_stream` mapped to it).
*   **Service:** `core.agent_loop.stream_agent_loop`.
*   **Orchestrator:** `core.graph.StateGraph`.
*   **Memory:** `ConversationManager` + `MemoryFacade`.

### Migration Goal
All UIs (Web, CLI, TUI, Mobile) must send messages to the `StateGraph` via either a unified REST streaming endpoint or a unified WebSocket.
