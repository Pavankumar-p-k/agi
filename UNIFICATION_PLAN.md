# JARVIS Unification Plan: "The One True Brain"

## 1. Consolidate API Entry Points
*   **DELETE** `/ai_os/*`, `/api/hybrid/*`, `/api/agi/*`.
*   **UNIFY** all chat/agent requests to `/api/agent/stream` (SSE) and `/ws/chat_stream` (WS).

## 2. Unify Execution Logic
*   Point both SSE and WS handlers to `core.agent_loop.stream_agent_loop`.
*   Remove the stateless `three_pass` chat handler in favor of a `StateGraph` that includes a "Critique Node".

## 3. Standardize Context Injection
*   Create a `core/context_builder.py` that handles:
    *   Loading `ConversationManager` session.
    *   Injecting `MemoryFacade` recall.
    *   Injecting `ragflow_search` results.
    *   Injecting `repomap` and workspace state.
*   Call this builder in every entry point.

## 4. Fix UI Wiring
*   **CLI:** Update `cli_requests.py` to handle the `complete` flag or `stream_end` message correctly.
*   **TUI:** Point `JarvisClient` to `/api/agent/stream` instead of the broken `/ai_os/execute`.
*   **Electron:** Keep specialized routes but ensure they use the unified context builder.

## 5. Cleanup
*   Remove `ai_os/`, `jarvis_os/` stubs, and legacy `api/` files.
