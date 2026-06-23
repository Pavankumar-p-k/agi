# MEMORY REALITY MATRIX — Runtime Audit

**Method:** API requests to running server  
**Date:** 2026-06-10

## Memory Tier Status

| Tier | Backend | Persists Restart? | Actually Written? | Actually Read? | Status |
|------|---------|------------------|-------------------|----------------|--------|
| **Hot** | RAM (Python list) | NO | YES (last 10 turns) | YES (by TieredMemory) | WORKING but VOLATILE |
| **Warm** | SQLite (chat_history) | YES | **NO** — core/routes/chat.py does NOT write | NO | BROKEN |
| **Cold** | Qdrant/Chroma | YES | PARTIAL (after 10 turns archive) | PARTIAL (if embedder works) | PARTIAL |
| **Persistent** | jarvis.db (Notes/Reminders) | YES | YES (by their routes) | YES | WORKING |

## Runtime Test Results

**Endpoint: GET /memory/user_1**
`{"memories": []}`

The memory API returns empty. No memories stored for the test user.

## Settings (from /api/settings)

| Setting | Value | Impact |
|---------|-------|--------|
| memory.provider | mem0 | Uses mem0 adapter for semantic search |
| memory.recall_limit | 10 | Max 10 results returned |
| memory.auto_prune | true | Old memories auto-deleted |

## Key Finding

**Chat history is NOT persisted.** When a user sends a message through `POST /api/chat`, the handler (`chat_endpoint()` in `core/routes/operations.py` or `chat_route()` in `core/routes/chat.py`) does NOT write to SQLite. The `chat_history` table exists in `jarvis.db` but is never populated by the chat endpoints. A server restart wipes all conversation context from RAM.

The only memory that persists are Notes and Reminders, stored by their dedicated API routes — separate from the chat flow.
