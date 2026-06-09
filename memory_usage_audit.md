# JARVIS Memory Audit

## Memory Types & Usage

| Memory Type | Usage | Backend |
| :--- | :--- | :--- |
| **Short-term** | Active session history | `ConversationManager` (JSON) |
| **Working** | Context for current turn | Semantic Recall (Vector) |
| **Long-term** | Facts and preferences | `mem0` / `tiered_memory` |
| **Task Memory** | Step-by-step progress | **MISSING** in Chat mode |

## Verdict on Memory Usage
The system writes to all memory types but **ignores** the Short-term (linear) memory during runtime in favor of Working (semantic) memory. This is fundamentally flawed for conversation.
