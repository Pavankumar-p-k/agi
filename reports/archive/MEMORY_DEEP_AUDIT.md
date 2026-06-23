# PHASE 7 — Memory Deep Audit

Complete trace of memory flow: storage → retrieval → prompt injection → persistence.
Every claim verified by reading actual code with file:line references.

---

## Architecture Overview

```
User Message
    │
    ├── 1. ConversationManager.add_message()
    │     → JSON file: ~/.jarvis/sessions/{session_id}.json
    │     → Survives restart? YES (JSON on disk)
    │
    ├── 2. MemoryFacade.store()
    │     → TieredMemory.remember()
    │       ├── Hot: RAM list (max 10) → LOST on restart
    │       ├── Warm: Mem0Adapter → ChromaDB at data/chroma/ → SURVIVES restart
    │       └── Cold: EmbeddingMemory → SQLite at data/jarvis_memory.db → SURVIVES restart
    │
    ├── 3. Database (if REST path)
    │     → SQLAlchemy → ChatHistory table → SURVIVES restart
    │
    └── 4. Brain memory (if automation path)
          → Brain/MemoryManager → SQLite at data/brain.db → SURVIVES restart
```

---

## All Memory Backends (14+ found)

| Backend | Storage | Location | Persists Restart? | Persists Reconnect? | Retention |
|---------|---------|----------|-------------------|--------------------|-----------|
| Conversation JSON | JSON file | `~/.jarvis/sessions/{id}.json` | ✅ YES | ✅ YES | Unlimited (manual `compact()`) |
| Hot Tier | RAM list | `TieredMemory.hot_tier` | ❌ NO | ✅ YES | FIFO, max 10 |
| Warm Tier (mem0) | ChromaDB | `data/chroma/` | ✅ YES | ✅ YES | Unlimited |
| Cold Tier (embedding) | SQLite | `data/jarvis_memory.db` | ✅ YES | ✅ YES | Unlimited |
| Preferences | SQLite | `~/.jarvis/preferences.db` | ✅ YES | ✅ YES | Unlimited (count-tracking) |
| Decision Memory | JSON file | `~/.jarvis/decision_memory.json` | ✅ YES | ✅ YES | Unlimited |
| Pattern Failures | JSON file | `~/.jarvis/pattern_failures.json` | ✅ YES | ✅ YES | Unlimited |
| Brain Memory | SQLite | `data/brain.db` | ✅ YES | ✅ YES | Episodic: 30-day summary; Semantic: decay 0.95 |
| Agent Checkpoints | SQLite | `~/.jarvis/agent_checkpoints.db` | ✅ YES | ✅ YES | 7-day GC, max 10/session |
| Quality Grades | SQLite | `~/.jarvis/constitutional_memory.db` | ✅ YES | ✅ YES | Unlimited |
| Cloud Memory | Supabase + SQLite | `ai_os_memory.db` + Supabase | ✅ YES | ✅ YES | Unlimited |
| Core Memory (JSON) | JSON file | `{data_dir}/memory.json` | ✅ YES | ✅ YES | Unlimited |
| Vector Memory | ChromaDB | `odysseus_memories` collection | ✅ YES | ✅ YES | Unlimited |
| Skills | JSON file | `{data_dir}/skills.json` | ✅ YES | ✅ YES | Unlimited |
| Project Context | RAM dict | `ContextManager._contexts` | ❌ NO | ❌ NO | N/A (re-scanned) |
| Active Sessions | RAM dict | `SessionManager._active` | ❌ NO | ❌ NO | N/A |

---

## Detailed Storage Analysis

### 1. ConversationManager (Primary Chat History)

**File:** `core/session.py:40-196`

**Storage:** JSON files at `~/.jarvis/sessions/{session_id}.json`

**Key code:**
- Line 54-55: `SESSION_DIR / f"{self.session_id}.json"`
- Line 75: `get_context(last_n=10)` — returns last 10 messages
- Line 81-92: `save()` — atomic write to JSON
- Line 94-104: `load()` — reads from JSON on init
- Line 141-145: `compact(keep_last=10)` — truncates to last 10

**Limits:** No automatic compact. Token count tracked but not enforced.

---

### 2. TieredMemory (Hot/Warm/Cold)

**File:** `memory/tiered_memory.py`

**Hot Tier (RAM):**
- Line 75: `self.max_hot = 10`
- Line 103-109: FIFO capped at 10 entries
- **Lost on restart**

**Warm Tier (mem0 → ChromaDB):**
- `memory/mem0_adapter.py:54-60`: ChromaDB at `./data/chroma/`, collection `jarvis_memories`
- Uses Ollama for embeddings (nomic-embed-text)
- **Survives restart**

**Cold Tier (SQLite + Ollama embeddings):**
- `memory/embedding_memory.py:36`: `data/jarvis_memory.db`
- Line 94-118: Full-scan cosine similarity (O(n), no vector index)
- **Survives restart**

---

### 3. Brain Memory (Autonomous Loop)

**File:** `brain/memory/memory_manager.py`

**Storage:** Single SQLite file at `data/brain.db` (line 29)

**4 sub-stores in one database:**

| Store | Table | File:Line | Key Features |
|-------|-------|-----------|--------------|
| Episodic | `episodic_memories` | `episodic.py:30-63` | Importance scoring, 30-day summarization |
| Semantic | `semantic_memories` | `semantic.py:30-61` | Confidence tracking, decay factor 0.95 |
| Task | `task_memories` | `task.py:28-62` | Pattern extraction (min 3 samples) |
| Decision | `decision_memories` | `decision.py:29-63` | Failure-lesson boost (+0.15) |

**Decay:** `decay_all()` at `memory_manager.py:117-119` — reduces importance by 0.95 for unaccessed facts.

**Cleanup:** `cleanup_old_episodes()` at `memory_manager.py:121-123` — summarizes episodes older than 30 days.

---

### 4. MemoryFacade (Unified API)

**File:** `memory/memory_facade.py`

**Key functions:**
| Function | Line | What it does |
|----------|------|-------------|
| `store()` | 62-71 | Writes to TieredMemory only (comment warns against duplicate writes) |
| `recall()` | 73-95 | Merges TieredMemory + Mem0Adapter results, deduplicates by content |
| `search_all()` | 127-165 | Same as recall with `_source` tag |
| `format_context()` | 166-181 | Formats as `## Relevant Memories:` block, capped at 8 |

---

### 5. Context Builder (Prompt Injection)

**File:** `core/context_builder.py` (58 lines)

**The critical pipeline for memory → prompt injection:**

| Step | Line | Source | Limit |
|------|------|--------|-------|
| 1. Recent history | 34 | `ConversationManager.get_context(last_n=10)` | Last 10 messages |
| 2. Semantic memory | 40 | `MemoryFacade.recall(message, limit=5)` | 5 memories |
| 3. RAG context | 44 | `ragflow_search(message, top_k=5)` | 5 chunks |
| 4. Extra context | 50 | Optional (files, skills, etc.) | Variable |

**Final string** is prefixed to system prompt. All sections are independently formatted with markdown headers.

---

## Retrieval Quality Assessment

| Aspect | Quality | Evidence |
|--------|---------|----------|
| Recall relevance | Medium | Keyword + cosine similarity; threshold=0.05 (very low) — `core/memory.py:316` |
| Deduplication | None | `context_builder.py` concatenates history + memory + RAG with no dedup |
| Importance ranking | Good | Brain memory uses importance + access_count + success_rate |
| Vector search | Variable | ChromaDB semantic search, but `embedding_memory.py` does full SQLite scan |
| Failure boost | Good | Decision memories boost failure lessons by +0.15 — `brain/memory/decision.py:127-132` |
| Decay | Good | Semantic decay (0.95) prevents memory bloat |

---

## Session-Level Limits

| Limit | Value | File:Line |
|-------|-------|-----------|
| Conversation history injected | Last 10 | `core/context_builder.py:34` |
| Memory recall for prompt | 5 entries | `core/context_builder.py:40` |
| Format context cap | 8 entries | `memory/memory_facade.py:176` |
| RAG context top_k | 5 | `core/context_builder.py:44` |
| Session compact | Keep last 10 | `core/session.py:141` |
| Agent checkpoint GC | 7 days | `core/persistence/store.py:173` |
| Agent checkpoint compact | 10/session | `core/persistence/store.py:203` |
| Brain episodic summarization | 30 days | `brain/memory/episodic.py:167` |
| Brain semantic decay | 0.95 | `brain/memory/semantic.py:199` |

---

## Triple-Write Problem

When a user sends a message via the REST API path:
```
1. MemoryFacade.store()  →  TieredMemory (RAM + ChromaDB + SQLite)
2. ConversationManager.add_message() + save()  →  JSON file
3. db.add(ChatHistory)  →  SQLAlchemy database
```

Same data stored in up to 4 different backends. No cross-reference between them.
Estimated storage overhead: 3-5x the actual data size.

---

## Per-Message Flow Trace

```
User: "Hello, my name is Alice"
    │
    ├── cli_requests.py:stream_agent_ws("Hello, my name is Alice")
    │     → WS connect to /ws/agent_stream
    │
    ├── core/routes/websocket.py:380
    │     → stream_agent_loop(messages=[user_msg])
    │
    ├── core/agent_loop.py:31
    │     → StateGraph.build_default_graph()
    │
    ├── core/graph/nodes.py:setup_node
    │     → core/context_builder.py:build_unified_context()
    │       ├── Last 10 messages from ConversationManager (JSON)
    │       ├── 5 relevant memories from MemoryFacade (ChromaDB + SQLite)
    │       └── 5 RAG chunks
    │
    ├── core/graph/nodes.py:think_node
    │     → LLM generates response with all context injected
    │
    ├── core/routes/websocket.py (response streaming)
    │     → Streams tokens back via WebSocket
    │
    ├── After response: memory storage
    │     ├── ConversationManager.add_message("user", msg) + save()
    │     │     → ~/.jarvis/sessions/{id}.json
    │     ├── ConversationManager.add_message("assistant", response) + save()
    │     │     → ~/.jarvis/sessions/{id}.json
    │     └── MemoryFacade.store([user_msg, assistant_msg])
    │           → TieredMemory: RAM → ChromaDB → SQLite
    │
    └── User disconnects
          → Conversation JSON persists
          → ChromaDB persists
          → SQLite persists
          → Hot tier (RAM) cleared
```

---

## Survivability Matrix

| Event | JSON Sessions | ChromaDB | SQLite | RAM Hot Tier |
|-------|--------------|----------|--------|-------------|
| User closes terminal | ✅ Survives | ✅ Survives | ✅ Survives | ✅ Survives (same process) |
| User reconnects (same session) | ✅ Survives | ✅ Survives | ✅ Survives | ✅ Survives |
| Server restart | ✅ Survives | ✅ Survives | ✅ Survives | ❌ Lost |
| Day boundary | ✅ Survives | ✅ Survives | ✅ Survives | ❌ Lost (if process restarted) |
| Full system reboot | ✅ Survives | ✅ Survives | ✅ Survives | ❌ Lost |
| Database compaction | ✅ Survives (unless specifically deleted) | ✅ Survives | ✅ Survives | N/A |
| Session deletion | ❌ Lost | ✅ Survives (stale entries) | ✅ Survives (stale entries) | N/A |

**Key finding:** Only the RAM hot tier is lost on restart. All long-term storage backends are persistent.
There is **no garbage collection** for stale entries in ChromaDB/SQLite when a session is deleted.

---

## Recommendations

1. **Eliminate triple-write**: Choose one primary memory backend and route all writes through it
2. **Add vector index** to `embedding_memory.py` (currently O(n) full scan)
3. **Deduplicate context injection**: Prevent same information appearing in both history and memory sections
4. **Auto-compact sessions** beyond a token threshold (e.g., auto-trim to last 50 messages when exceeding 8K tokens)
5. **Add memory size metrics** to the diagnostics API for observability
