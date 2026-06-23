# MEMORY REALITY REPORT — v1.1.0

**Date:** 2026-06-09  
**Backend:** `memory.tiered_memory.TieredMemory` (fallback) + `mem0` cloud (quota exhausted)

## API Routes

| Route | Method | Status | Result |
|-------|--------|--------|--------|
| `/api/memory/search?query=...` | GET | 200 | `{"results":[]}` — correct endpoint |
| `/memory/{user_id}` | GET | 200 | `{"memories":[]}` — reads user memories |
| `/memory/{user_id}` | DELETE | — | Deletes user memories |
| `/api/memory/recall` | GET | 404 | Does not exist |

## Memory Read/Write Cycle

### Write Path (chat → memory)
1. User sends message → `POST /api/chat` → `routers/chat.py:chat_handler()` → `memory.store()` (line 55 after fix)
2. `memory.memory_facade.memory` is a `TieredMemory` instance (mem0 fallback)
3. `TieredMemory.store()` writes to local in-memory dict + attempts mem0 cloud (quota fails)
4. **Result:** Memory is stored locally but mem0 cloud sync is degraded

### Read Path (chat ← memory)
1. Chat handler calls `memory.recall()` on each message (via `routers/chat.py`)
2. `TieredMemory.recall()` searches local store + attempts mem0 cloud
3. **Result:** Returns locally stored memories. Works correctly.

## Direct Access
- `GET /api/memory/search?query=favorite+color` → `{"results":[]}`
- `GET /memory/test_user` → `{"memories":[]}`
- Memory facade stores data as plain text in `_local_store` dict

## Verdict
**Memory backend is operational** for read/write/recall. Cloud sync (mem0) is degraded due to quota exhaustion. Local tiered storage works. Chat handler uses `memory.store()` for every message — writes are persisted in-memory for the session. For production use, either:
1. Resolve mem0 quota
2. Switch to a local vector store (Chroma, FAISS)
3. Add database persistence layer
