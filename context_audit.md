# JARVIS Context Audit

## Component Status

| Component | Status | Reason |
| :--- | :--- | :--- |
| **Prior Conversation Reading** | **MISSING** | Most handlers (`/api/chat`, `/ws/chat_stream`) only take the current message and don't load session history from `ConversationManager`. |
| **History Injection** | **PARTIAL** | Only semantic (RAG) history is injected. If keywords don't match, recent context is lost. |
| **Memory Retrieval** | **WORKING** | Vector-based recall is functional but over-relied upon. |
| **Memory Storage** | **WORKING** | Messages are stored in both `ConversationManager` (JSON) and `MemoryFacade` (Vector). |
| **Context Truncation** | **BROKEN** | No consistent sliding window strategy across handlers. |

## Why JARVIS forgets context?
1. **Semantic Drift:** Because it uses RAG to find "relevant" memories instead of a linear conversation window, if you say "Tell me more about that", the word "that" has no semantic meaning in the vector DB, so it fails to retrieve the previous message.
2. **Disconnected Sessions:** `ConversationManager` tracks history on the CLI side, but the server-side brain doesn't load it for `/api/chat` requests.

## Recommendations
*   Replace `memory.recall` in the main loop with a tiered approach: `Recent History (Linear)` + `Long-term Memory (Semantic)`.
*   Ensure every entry point loads the `ConversationManager` session.
