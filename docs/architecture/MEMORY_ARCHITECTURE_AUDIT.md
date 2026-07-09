# Memory Architecture Audit — Phase 1 (Document 4)

> **Purpose:** Trace every memory system in the codebase — what data each stores, where it lives, who owns it, how it persists, and how the systems overlap or conflict.
>
> **Scope:** All storage systems labeled "memory" plus every persistence store that functions as memory (conversation, session, checkpoint, provider evidence, activity, plan, workflow, knowledge, pattern failure, constitutional).

---

## Table of Contents

1. [Executive Summary: Three Concurrent Memory Systems](#1-executive-summary-three-concurrent-memory-systems)
2. [System A: `memory/` Package (User-Facing Facade)](#2-system-a-memory-package-user-facing-facade)
3. [System B: `brain/memory/` Package (Agent-Facing Manager)](#3-system-b-brainmemory-package-agent-facing-manager)
4. [System C: `core/` Memory Modules (Deprecated + Specialized)](#4-system-c-core-memory-modules-deprecated--specialized)
5. [Specialized Memory Stores Outside the Three Systems](#5-specialized-memory-stores-outside-the-three-systems)
6. [Conversation & Session Memory](#6-conversation--session-memory)
7. [Checkpoint & Recovery as Memory](#7-checkpoint--recovery-as-memory)
8. [Vector Stores & Embeddings](#8-vector-stores--embeddings)
9. [Memory in the Pipeline](#9-memory-in-the-pipeline)
10. [Memory Ownership Matrix](#10-memory-ownership-matrix)
11. [Duplication Analysis](#11-duplication-analysis)
12. [Thread Safety Audit](#12-thread-safety-audit)
13. [Persistence Map](#13-persistence-map)
14. [Integration Points](#14-integration-points)
15. [Findings](#15-findings)
16. [Recommendations](#16-recommendations)

---

## 1. Executive Summary: Three Concurrent Memory Systems

The codebase contains **four independent memory systems** plus **~15 specialized stores** that each function as memory. Systems A, B, and C are the three general-purpose systems; System D is the vector-store subsystem.

| System | Package | Orchestrator | Backends | Consumers | Status |
|--------|---------|-------------|----------|-----------|--------|
| **A** | `memory/` | `MemoryFacade` | RAM hot tier + Mem0 (ChromaDB) + EmbeddingMemory (SQLite) + FactStore (SQLite) | Pipeline stages, API routes, MCP server | Active — recommended future |
| **B** | `brain/memory/` | `MemoryManager` | SQLite (single `brain.db`, 4 tables) | Brain subsystems (learning, automation, self-improvement, world model) | Active — agent-facing |
| **C** | `core/memory.py` | `MemoryManager` (deprecated) | JSON file (`memory.json`) | Legacy chat tools, MCP memory server | **DEPRECATED** (v3.2, removal v4.0) |
| **D** | `core/memory_vector.py` | `MemoryVectorStore` | ChromaDB (`odysseus_memories` collection) | Semantic search clients | Active — shared embedding pipeline |

**Critical finding:** Systems A and B are completely independent — they do not share data, backends, or schemas. The deprecated System C references System A as its replacement, but System A does not provide feature parity. The same user `"default"` can have disjoint memories split across A, B, C, and each specialized store.

---

## 2. System A: `memory/` Package (User-Facing Facade)

### 2.1 Structure

```
memory/
├── __init__.py              — Exports: ExtractedFact, FactStore, extract_facts, get_fact_store
├── memory_facade.py          — MemoryFacade (singleton facade)
├── tiered_memory.py          — TieredMemory (hot/warm/cold tiers)
├── decision_memory.py        — DecisionMemory (action→outcome learning)
├── embedding_memory.py       — EmbeddingMemory (SQLite + Ollama embeddings)
├── fact_store.py             — FactStore (SQLite RDF triples)
├── extraction.py             — Regex fact extraction (no storage)
├── preference_profile.py     — PreferenceProfile (aggregates from FactStore)
├── mem0_adapter.py           — Mem0Adapter (ChromaDB vector store via mem0 library)
└── reranker.py               — ReRanker (multi-factor scoring, no storage)
```

### 2.2 Class Inventory

| Class | Lines | Singleton | Backend | Tables/Collections |
|-------|-------|-----------|---------|-------------------|
| `MemoryFacade` | 183 | `memory = MemoryFacade()` | Lazy delegates to TieredMemory + Mem0Adapter | — |
| `TieredMemory` | 254 | `tiered_memory = TieredMemory()` | RAM + Mem0 (Qdrant) + EmbeddingMemory | Hot: RAM list (max 10). Warm: Qdrant. Cold: SQLite `semantic_memory` |
| `Mem0Adapter` | 143 | `mem0_memory = Mem0Adapter()` | ChromaDB via mem0 library | `jarvis_memories` collection |
| `EmbeddingMemory` | 127 | Lazy via `get_embedding_memory()` | SQLite + Ollama | `semantic_memory` table in `data/jarvis_memory.db` |
| `FactStore` | 505 | Lazy via `get_fact_store()` | SQLite | `facts` table in `data/jarvis_memory.db` (19 columns) |
| `DecisionMemory` | 215 | `decision_memory = DecisionMemory()` | JSON file | `~/.jarvis/decision_memory.json` |
| `PreferenceProfile` | 119 | Per-instance (no singleton) | Facade over FactStore | — |
| `ReRanker` | 147 | Per-instance (no singleton) | None (computation) | — |

### 2.3 Public Interface Summary

**MemoryFacade** (the primary consumer API):
- `store(text, user_id, metadata)` → delegates to `TieredMemory.remember()`
- `recall(query, limit, user_id)` → queries tiered + mem0, deduplicates by content
- `get_all(user_id)` → hot tier contents + mem0 `get_all()`
- `delete_all(user_id)` → mem0 only (hot tier NOT deleted)
- `search_all(query, limit, user_id)` → like recall but tags `_source`
- `consolidate_all()` → delegates to tiered `consolidate()`
- `format_context(memories)` → LLM-readable string

**TieredMemory:**
- `remember(content, importance, metadata)` → hot tier + mem0 + optionally semantic (>0.8)
- `recall(query, limit, user_id)` → hot (word≥30%) + mem0 (vector) + semantic
- `recall_filtered(query, threshold)` → cosine-similarity filter
- `format_for_context(memories, query)` → structured LLM context
- `consolidate()` → no-op (mem0 handles its own)

**FactStore:**
- `store_facts(facts, user_id, tenant_id, force)` → dedup by `(s,p,o,user,tenant)`, updates confidence
- `search_facts(query, user_id, tenant_id, limit)` → embedding or keyword
- `find_contradictions(new_facts, user_id, tenant_id, threshold)` → same s+p, different o
- `consolidate(user_id, tenant_id, min_similarity)` → merges near-duplicates by word overlap
- 5 additional read/update/delete methods

**DecisionMemory:**
- `record(goal, task, agents_tried, winner, duration, success, error, ...)` → logs action
- `best_agent_for(task_type)` → highest success rate
- `has_pattern(task_type, error)` → known-error lookup
- `best_fix_for(issue_type)` → best fix strategy

### 2.4 Data Flow

```
External write (pipeline MemoryStage, API):
  [Message pair] → MemoryFacade.store()
                   → TieredMemory.remember()
                      → Hot tier RAM (max 10, FIFO)
                      → Mem0Adapter.add() → ChromaDB (Qdrant)
                      → if importance > 0.8: EmbeddingMemory.store() → SQLite
                   → FactStore.store_facts() → SQLite (for extraction module)
                   → DecisionMemory.record() → JSON (for decision module)

External read (pipeline ContextRetrievalStage, API):
  [Query] → MemoryFacade.recall()
            → TieredMemory.recall()
               → Hot tier (word overlap ≥ 30%)
               → Mem0Adapter.search() → ChromaDB vector search
               → EmbeddingMemory.semantic_search() → SQLite brute-force cosine
            → ReRanker.rerank() (similarity×0.5 + recency×0.3 + confidence×0.1 + preference×0.1)
            → PreferenceProfile.build() → FactStore (category=preference)
            → format_context() → LLM prompt
```

---

## 3. System B: `brain/memory/` Package (Agent-Facing Manager)

### 3.1 Structure

```
brain/memory/
├── __init__.py              — Exports: MemoryProvider, MemoryManager, EpisodicMemory, SemanticMemory, TaskMemory, DecisionMemory
├── base.py                  — MemoryProvider (ABC): count(), clear(), get_recent(), maintenance()
├── memory_manager.py        — MemoryManager (orchestrator, singleton)
├── episodic.py              — EpisodicMemory (goal-driven action sequences)
├── semantic.py              — SemanticMemory (facts, knowledge, concepts)
├── task.py                  — TaskMemory (execution traces, action patterns)
└── decision.py              — DecisionMemory (decisions, outcomes, lessons)
```

### 3.2 Class Inventory

| Class | Lines | Singleton | Backend | Tables |
|-------|-------|-----------|---------|--------|
| `MemoryManager` | ~150 | `memory_manager = MemoryManager()` | Delegates to 4 sub-memories | — |
| `EpisodicMemory` | ~120 | Instance via Manager | SQLite | `episodic_memories` in `data/brain.db` |
| `SemanticMemory` | ~130 | Instance via Manager | SQLite | `semantic_memories` in `data/brain.db` |
| `TaskMemory` | ~100 | Instance via Manager | SQLite | `task_memories` in `data/brain.db` |
| `DecisionMemory` | ~110 | Instance via Manager | SQLite | `decision_memories` in `data/brain.db` |

### 3.3 Public Interface Summary

**MemoryManager:**
- `store_episode(goal, actions, context, result, episode_type, tags)` → returns UUID
- `retrieve_episodes(query, top_k, min_importance)` → similarity search
- `store_fact(fact, category, confidence, source, tags)` → returns UUID
- `retrieve_facts(query, top_k, min_confidence, categories)` → similarity search
- `store_trace(action_name, action_params, observation, success, duration_ms, task_id, context)` → UUID
- `get_task_traces(task_id)` → all traces for a task
- `store_decision(context, decision, alternatives, outcome, lesson, success, tags)` → UUID
- `retrieve_decisions(query_context, top_k)` → similarity search (failures boosted +0.15)
- `reflect_on_task(goal, result, actions)` → auto-generate decision + lesson
- `summarize()` → counts per type
- `decay_all(factor)` → semantic memory importance decay
- `cleanup_old_episodes(before_days)` → summarization + delete

### 3.4 Similarity Mechanism

All three similarity-based retrievals (Episodic, Semantic, Decision) use the same pattern:
1. Fetch `top_k * 3` candidates from SQLite ordered by DB-level `importance DESC` / `access_count DESC`
2. Re-rank in Python using `get_text_similarity()` from `core.memory` (deprecated module)
3. `get_text_similarity()` tries embedding-based cosine similarity (Ollama), falls back to Jaccard

This means System B depends on the deprecated System C's utility function for its core retrieval logic.

### 3.5 Main Consumers

| Consumer | File | Usage Pattern |
|----------|------|--------------|
| `brain/learning_engine.py` | Constructor param | `memory_manager.decision.get_lessons()` |
| `brain/automation/loop.py` | Constructor param | `.store_trace()`, `.store_decision()`, `.reflect_on_task()` |
| `brain/skill_acquisition.py` | Constructor param | `.semantic.store()` |
| `brain/self_improvement.py` | Constructor param | `.decision.get_lessons()`, `.store_decision()` |
| `brain/world_model.py` | Constructor param | `.semantic.store()`, `.semantic.retrieve()` |
| `core/agent_orchestrator.py` | Lazy import | Instantiates `MemoryManager(data/brain.db)`, passes to `AutomationLoop` |
| `core/tools/build_tools.py` | Lazy import | Same pattern as agent_orchestrator |

---

## 4. System C: `core/` Memory Modules (Deprecated + Specialized)

### 4.1 `core/memory.py` — Deprecated MemoryManager

| Aspect | Detail |
|--------|--------|
| **Class** | `MemoryManager(data_dir)` — stores entries as dicts in JSON |
| **Backend** | `memory.json` flat file |
| **Singleton** | No (per-instance) |
| **Methods** | `extract_memory_from_chat()`, `process_inline_memory_command()`, `load_all()`, `save()`, `add_entry()`, `get_relevant_memories()`, `categorize_memory_by_relevance()` |
| **Status** | **DEPRECATED** since v3.2, to be removed after v4.0. Notice says "use `memory.memory_facade.MemoryFacade`" |
| **Still-used utility** | `get_text_similarity()` — used by all 3 similarity-based retrievals in System B |

### 4.2 `core/memory_vector.py` — MemoryVectorStore

| Aspect | Detail |
|--------|--------|
| **Class** | `MemoryVectorStore(data_dir)` — ChromaDB collection `"odysseus_memories"` |
| **Backend** | ChromaDB (persistent vector DB) |
| **Singleton** | No (per-instance) |
| **Methods** | `add(id, text)`, `remove(id)`, `search(query, k)`, `find_similar(text, threshold)`, `count()`, `rebuild(memories)` |
| **Embedding** | Shares `core.embeddings.get_embedding_client()` with RAG subsystem |
| **Consumers** | Direct callers (not through MemoryFacade) |

### 4.3 `core/pattern_failure_memory.py` — PatternFailureMemory

| Aspect | Detail |
|--------|--------|
| **Class** | `PatternFailureMemory()` — generalized error pattern store |
| **Backend** | JSON file at `~/.jarvis/pattern_failures.json` |
| **Singleton** | `pattern_memory = PatternFailureMemory()` (module-level) |
| **Methods** | `match(failure_text)`, `match_all()`, `record()`, `record_success()`, `record_failure()`, `get_stats()` |
| **Scoring** | `success_rate × 0.5 + recency × 0.2 + cost_bonus × 0.1` |
| **Generalization** | Replaces identifiers/numbers/strings/paths with wildcards |
| **Consumers** | `MemoryAgent`, `KnowledgeSynthesizer`, `coding/build_benchmark.py` |

### 4.4 `core/providers/memory.py` — ProviderMemory

| Aspect | Detail |
|--------|--------|
| **Class** | `ProviderMemory()` — Bayesian provider success evidence |
| **Backend** | JSON file at `~/.jarvis/provider_memory/memory.json` |
| **Singleton** | `provider_memory = ProviderMemory()` (module-level) |
| **Methods** | `record(result)`, `get_distribution()`, `get_expected_score()`, `get_confidence()`, `get_top_providers()`, `get_failure_profile()` |
| **Statistics** | Beta-Binomial posterior (alpha, beta) per `(provider, capability, task_type, model, language)` tuple. 9-level fallback chain. |
| **Consumers** | ProviderRouter for data-driven provider selection |

### 4.5 `core/memory_driven_decisions.py` — MemoryDrivenRouter

| Aspect | Detail |
|--------|--------|
| **Class** | `MemoryDrivenRouter()` — agent/strategy selection cache |
| **Backend** | In-memory LRU cache dict |
| **Singleton** | `memory_router = MemoryDrivenRouter()` (module-level) |
| **Methods** | `best_agent_for()`, `worst_agent_for()`, `should_avoid()`, `select_strategy()`, `clear_cache()` |
| **Consumers** | Agent router, strategy selector |

### 4.6 `core/cloud/cloud_memory.py` — CloudMemory

| Aspect | Detail |
|--------|--------|
| **Class** | `CloudMemory(user_id, local_db_path)` — async cloud-synced K/V store |
| **Backend** | Supabase (`jarvis_memories` table) + SQLite fallback (`ai_os_memory.db`) |
| **Methods** | `get(key)`, `set(key, value)`, `delete(key)`, `list(prefix)`, `search(query)`, `sync_from_local()`, `sync_to_local()` |
| **Consumers** | Cloud sync API routes |

### 4.7 `core/quality_grader.py` — ConstitutionalMemory

| Aspect | Detail |
|--------|--------|
| **Class** | `ConstitutionalMemory()` — grading history and failure patterns |
| **Backend** | SQLite at `~/.jarvis/constitutional_memory.db` |
| **Table** | `grade_history` (output_type, criterion_id, passed, score, correction_applied, created_at) |
| **Methods** | `log(grade, correction)`, `failure_patterns(output_type, min_entries)` |
| **Consumers** | Quality grader for constitutional AI feedback |

### 4.8 `core/plugins/memory.py` — MemoryPlugin

| Aspect | Detail |
|--------|--------|
| **Class** | `MemoryPlugin(Plugin)` — hook-based extensibility for external memory backends |
| **Hooks** | `on_store(memory)`, `on_recall(query, limit)`, `on_consolidate()` |
| **Backend** | None — delegates to registered third-party hooks |
| **Consumers** | Plugin system |

---

## 5. Specialized Memory Stores Outside the Three Systems

### 5.1 KnowledgeStore (Long-Term Memory)

| Aspect | Detail |
|--------|--------|
| **File** | `core/long_term_memory/store.py` |
| **Class** | `KnowledgeStore` — durable knowledge items with categories |
| **Backend** | SQLite — `data/workflow.db`, tables: `knowledge_items`, `experience_summaries` |
| **Categories** | pattern, principle, heuristic, factoid, warning |
| **Adapter** | `BehaviorAdapter` — bridges knowledge into planner/research/coding prompts |
| **Synthesizer** | `KnowledgeSynthesizer` — detects cross-activity patterns from ActivityStore |

### 5.2 PlanStore

| Aspect | Detail |
|--------|--------|
| **File** | `core/planner/store.py` |
| **Class** | `PlanStore` — goal decomposition tree persistence |
| **Backend** | SQLite — `data/workflow.db`, table: `plans` (id, goal, status, root_node, timestamps) |
| **Lifecycle** | draft → approved → executing → completed/failed |

### 5.3 ActivityStore

| Aspect | Detail |
|--------|--------|
| **File** | `core/activity/storage.py` |
| **Class** | `ActivityStore` — activity graph (nodes + edges) |
| **Backend** | SQLite — `data/workflow.db`, tables: `activity_nodes`, `activity_edges` |
| **Manager** | `ActivityManager` — wraps with domain operations, `resume_candidates()` |
| **Replay** | `ReplayAssembler` — reconstructs activity trees for audit |

### 5.4 WorkflowStore

| Aspect | Detail |
|--------|--------|
| **File** | `core/workflow/storage.py` |
| **Class** | `WorkflowStore` — workflow instance state |
| **Backend** | SQLite — `data/workflow.db`, 5 tables: instances, steps, events, contexts, artifacts |
| **Status** | Full lifecycle with compensation, retry, heartbeat |

### 5.5 WorkflowHistoryStore / WorkflowCalibrationStore

| Aspect | Detail |
|--------|--------|
| **File** | `core/workflow/learning_store.py` |
| **Backend** | SQLite — `~/.jarvis/workflow_learning.db` (separate DB) |
| **History** | Append-only `WorkflowOutcome` records |
| **Calibration** | Cached success_rate, avg_duration, avg_cost per fingerprint |

### 5.6 CheckpointStore

| Aspect | Detail |
|--------|--------|
| **File** | `core/persistence/store.py` |
| **Class** | `CheckpointStore` — agent checkpoint snapshots |
| **Backend** | SQLite — `~/.jarvis/agent_checkpoints.db`, tables: `checkpoints`, `node_checkpoints` |
| **TTL** | `delete_old()` garbage collection, max per session compaction |

### 5.7 GraphCheckpointer + GraphRecovery

| Aspect | Detail |
|--------|--------|
| **File** | `core/distribution/graph/checkpoint.py`, `core/distribution/graph/recovery.py` |
| **Backend** | JSON files at `~/.jarvis/graph_checkpoints/<graph_id>.json` |
| **Recovery** | Rebuilds `DistributedGraph` from snapshot, resets RUNNING/FAILED to PENDING |

### 5.8 CheckpointManager

| Aspect | Detail |
|--------|--------|
| **File** | `core/checkpoint_manager.py` |
| **Backend** | JSON files at `~/.jarvis/checkpoints/<project>/cp_<step_id>/checkpoint.json` |
| **Methods** | `save_checkpoint()`, `rollback()`, `restore_state()`, `snapshot_files()` |
| **Consumer** | `UnifiedBrain.save_checkpoint()` / `resume_project()` |

### 5.9 AgentState Snapshot (session_db)

| Aspect | Detail |
|--------|--------|
| **File** | `core/session_db.py` |
| **Backend** | SQLite — `~/.jarvis/agent_state.db`, table: `agent_state_snapshots` |
| **Content** | Full `AgentState.to_dict()` per tool-call round |
| **Consumer** | Agent graph `setup_node` for session resumption |

---

## 6. Conversation & Session Memory

### 6.1 ConversationManager

| Aspect | Detail |
|--------|--------|
| **File** | `core/session.py` |
| **Backend** | JSON files at `~/.jarvis/sessions/{session_id}.json` |
| **Schema** | `messages: list[{"role", "content", "timestamp"}]` |
| **Methods** | `add_message()`, `get_context(last_n)`, `save()`, `load()`, `fork()`, `compact()`, `export_transcript()` |
| **Token counting** | Approximate: word count + 3 per message |
| **Hierarchy** | `HierarchicalSession` / `SessionManager` — parent-child session scoping for sub-agents |

### 6.2 ChatHistory (SQLAlchemy)

| Aspect | Detail |
|--------|--------|
| **File** | `core/database.py` |
| **Model** | `ChatHistory` — SQLAlchemy ORM |
| **Table** | `chat_history` (id, user_id, role, message, intent, session_id, timestamp) |
| **Backend** | SQLAlchemy-managed database (separate from all other SQLite databases) |

### 6.3 SessionMemory (Routing)

| Aspect | Detail |
|--------|--------|
| **File** | `core/routing/project_context.py` |
| **Class** | `SessionMemory` — per-session routing state |
| **Fields** | session_id, cwd, last_commands, recent_files, current_task, browser history |
| **Backend** | In-memory dict (via `ContextManager` singleton) |
| **Lifetime** | Process-lifetime |

### 6.4 Session Database

| Aspect | Detail |
|--------|--------|
| **File** | `core/session_db.py` |
| **Backend** | SQLite — `~/.jarvis/sessions.db` (separate from agent_state.db) |
| **Purpose** | Session metadata and message lookup |

---

## 7. Checkpoint & Recovery as Memory

### 7.1 The Four Checkpoint Systems

| System | Location | Backend | Granularity | Purpose |
|--------|----------|---------|-------------|---------|
| **CheckpointManager** | `core/checkpoint_manager.py` | JSON files | Per-project, multi-day | User-facing project persistence |
| **CheckpointStore** | `core/persistence/store.py` | SQLite | Per-agent-state, per-node | Agent graph pause/resume |
| **GraphCheckpointer** | `core/distribution/graph/checkpoint.py` | JSON files | Per-distributed-graph | DAG execution recovery |
| **WorkflowRecovery** | `core/workflow/recovery.py` | SQLite (WorkflowStore) | Per-workflow-instance | Workflow engine resume |

### 7.2 Redundancy

CheckpointManager and CheckpointStore both store agent execution state but use different backends (JSON vs SQLite) and are consumed by different subsystems (UnifiedBrain vs agent graph). There is no coordination between them — saving in one does not save in the other.

WorkflowRecovery is the only checkpoint system designed for automatic recovery at startup (scans for RUNNING/RECOVERING/COMPENSATING workflows). The other three require explicit save/load calls.

---

## 8. Vector Stores & Embeddings

### 8.1 Embedding Providers

| Provider | Module | Model | Endpoint |
|----------|--------|-------|----------|
| Ollama | `memory/embedding_memory.py` | `nomic-embed-text` | `http://localhost:11434/api/embed` |
| Ollama (via mem0) | `memory/mem0_adapter.py` | `llm.embedding_model` (config reg) | Ollama API |
| Ollama (via core) | `core/embeddings.py` | `get_embedding_client()` | Config-driven |

### 8.2 Vector Databases

| Database | System | Data | Location | Access Pattern |
|----------|--------|------|----------|---------------|
| ChromaDB | System D (`MemoryVectorStore`) | `odysseus_memories` collection | `./data/chroma/` | Direct API calls |
| ChromaDB (via mem0) | System A (`Mem0Adapter`) | `jarvis_memories` collection | `./data/chroma/` | Via mem0 library |
| Qdrant | System A (`TieredMemory`) | mem0-managed | `./data/qdrant_storage/` | Via mem0 library |
| SQLite (brute-force) | System A (`EmbeddingMemory`) | `semantic_memory` table | `data/jarvis_memory.db` | Full-scan cosine similarity |

**Critical finding:** ChromaDB is used by two independent systems (System D and System A via mem0) with **different collection names**. The mem0 library configures its own ChromaDB client, while System D uses a separate ChromaDB client from `core/chroma_client.py`. This means there are **three vector stores** (one Qdrant + two ChromaDB) operating independently, storing potentially overlapping data.

---

## 9. Memory in the Pipeline

### 9.1 Write Path: MemoryStage

| Property | Value |
|----------|-------|
| **File** | `core/pipeline/stages/memory.py` |
| **Stage position** | After verification (stage ~17) |
| **Classification** | Keyword-based: preference/project/fact/conversation |
| **Storage targets** | `MemoryFacade.store()` → TieredMemory + Mem0, then `FactStore.store_facts()` |
| **Contradiction detection** | `FactStore.find_contradictions()` before storing |
| **Output** | `StoreDecision(action, store_type, reason, confidence, fact_count, contradictions, memory_refs)` |

### 9.2 Read Path: ContextRetrievalStage

| Property | Value |
|----------|-------|
| **File** | `core/pipeline/stages/context_retrieval.py` |
| **Stage position** | Before planning (stage 9) |
| **Timeout** | 5 seconds (thread pool executor) |
| **Recall** | `MemoryFacade.recall()` → query all backends |
| **Re-ranking** | `ReRanker.rerank()` — similarity (0.5) + recency (0.3) + confidence (0.1) + preference (0.1) |
| **Preferences** | `PreferenceProfile.build()` from FactStore |
| **Output** | `context.retrieved_context.memories`, `.formatted_context`, `.preferences` |

### 9.3 Other Pipeline Stages Interacting with Memory

| Stage | Interaction | How |
|-------|-------------|-----|
| **ReceiveStage** | None | Pure transport |
| **LoadContextStage** | Loads `ProjectContext` (which has `SessionMemory`) | From `ContextManager` |
| **IntentStage** | None | Rule-based classification |
| **PlannerStage** | Reads `KnowledgeStore` via `BehaviorAdapter.for_planner()` | Injects learned knowledge |
| **CapabilitySelectionStage** | Reads `MemoryDrivenRouter` | `best_agent_for()` / `should_avoid()` |
| **FormatStage** | None | Pure response formatting |

---

## 10. Memory Ownership Matrix

| Memory Component | Owner | Creator | Reader | Writer | Destroyer | Persistence | Lifetime |
|---|---|---|---|---|---|---|---|
| **MemoryFacade** (System A) | `memory.memory_facade` | Module import | Pipeline stages, API | MemoryStage, API | Process death | Delegates to backends | Process |
| **TieredMemory hot** | `memory.tiered_memory` | Module import | recall() | remember() | Process death / FIFO eviction | None (volatile) | Process |
| **Mem0Adapter** | `memory.mem0_adapter` | Module import | search(), get_all() | add() | delete_all(), process death | ChromaDB | Persistent |
| **EmbeddingMemory** | `memory.embedding_memory` | Lazy getter | semantic_search() | store() | Process death | SQLite | Persistent |
| **FactStore** | `memory.fact_store` | Lazy getter | search, get, count | store_facts(), update() | delete, mark_inactive | SQLite | Persistent |
| **DecisionMemory** (memory/) | `memory.decision_memory` | Module import | best_agent_for(), has_pattern() | record() | clear() | JSON file | Persistent |
| **MemoryManager** (System B) | `brain.memory.memory_manager` | Module import | Pipeline stages, brain modules | Pipeline stages, brain modules | Process death | SQLite | Persistent |
| **EpisodicMemory** | `brain.memory.episodic` | Manager constructor | retrieve(), get_recent() | store(), update_result() | clear() | SQLite (brain.db) | Persistent |
| **SemanticMemory** | `brain.memory.semantic` | Manager constructor | retrieve(), get_by_category() | store() | clear() | SQLite (brain.db) | Persistent |
| **TaskMemory** | `brain.memory.task` | Manager constructor | get_task_traces(), get_action_patterns() | store() | clear() | SQLite (brain.db) | Persistent |
| **DecisionMemory** (brain/) | `brain.memory.decision` | Manager constructor | retrieve_similar(), get_lessons() | store() | clear() | SQLite (brain.db) | Persistent |
| **MemoryManager** (System C) | `core.memory` | Per-instance | load(), get_relevant() | add_entry(), save() | Process death | JSON file | Process |
| **MemoryVectorStore** (System D) | `core.memory_vector` | Per-instance | search() | add(), remove(), rebuild() | Process death | ChromaDB | Persistent |
| **PatternFailureMemory** | `core.pattern_failure_memory` | Module import | match(), match_all() | record() | clear() | JSON file | Persistent |
| **ProviderMemory** | `core.providers.memory` | Module import | get_distribution(), get_score() | record() | Process death | JSON file | Persistent |
| **CloudMemory** | `core.cloud.cloud_memory` | Per-instance | get(), list(), search() | set() | delete() | Supabase + SQLite | Persistent |
| **ConstitutionalMemory** | `core.quality_grader` | Per-instance by lazy import | failure_patterns() | log() | Not implemented | SQLite | Persistent |
| **KnowledgeStore** | `core.long_term_memory.store` | Per-instance | query, search | store() | Not implemented | SQLite (workflow.db) | Persistent |
| **PlanStore** | `core.planner.store` | Per-instance | get(), list_all() | create(), update_status() | delete() | SQLite (workflow.db) | Persistent |
| **ActivityStore** | `core.activity.storage` | Per-instance | get_tree(), get_timeline() | create_node(), update_node() | prune_stale() | SQLite (workflow.db) | Persistent |
| **WorkflowStore** | `core.workflow.storage` | Per-instance | get_status(), list() | create, update_step, complete | cancel() | SQLite (workflow.db) | Persistent |
| **WorkflowHistoryStore** | `core.workflow.learning_store` | Per-instance | query history | record_outcome() | Not implemented | SQLite | Persistent |
| **ConversationManager** | `core.session` | Module import | get_context() | add_message() | Process death | JSON files | Process |
| **ChatHistory (SQLAlchemy)** | `core.database` | Module import | Query via ORM | ORM insert | ORM delete | SQLAlchemy DB | Persistent |
| **SessionMemory** | `core.routing.project_context` | Module import | All routing code | All routing code | Process death | In-memory | Process |
| **CheckpointManager** | `core.checkpoint_manager` | Module import | list_checkpoints() | save_checkpoint() | Not implemented | JSON files | Persistent |
| **CheckpointStore** | `core.persistence.store` | Per-instance | load_latest() | save(), save_agent_state() | delete_old() | SQLite | Persistent |
| **GraphCheckpointer** | `core.distribution.graph.checkpoint` | Per-instance | load | save | Not implemented | JSON files | Persistent |

---

## 11. Duplication Analysis

### 11.1 General-Purpose Memory Systems (3x overlap)

| Dimension | System A (`memory/`) | System B (`brain/memory/`) | System C (`core/memory.py`) |
|-----------|---------------------|--------------------------|---------------------------|
| **What it stores** | User conversation memories + facts | Agent task episodes + facts + traces + decisions | Chat memories (flat entries) |
| **Backend** | RAM + ChromaDB + Qdrant + SQLite | SQLite (single file) | JSON file |
| **Fact storage** | `FactStore` (19-col SQLite) | `SemanticMemory` (9-col SQLite) | `memory.json` (flat) |
| **Decision memory** | `DecisionMemory` (JSON, agent selection) | `DecisionMemory` (SQLite, task reflection) | None |
| **Feature parity** | Has contradiction detection, re-ranking, preference aggregation | Has importance decay, auto-summarization, pattern extraction | Has relevance categorization, inline commands |
| **Status** | Recommended future | Agent-facing, no migration planned | Deprecated (v3.2) |

**Impact:** A fact stored in System A's FactStore is not visible to System B's SemanticMemory, and vice versa. The deprecated System C notice says to migrate to System A, but System B consumers have no migration path.

### 11.2 Fact Stores (2x overlap)

| Aspect | `memory/fact_store.py` (System A) | `brain/memory/semantic.py` (System B) |
|--------|-----------------------------------|---------------------------------------|
| What it stores | RDF triples with 19 metadata fields | Fact strings with category/confidence |
| Backend | SQLite `facts` table | SQLite `semantic_memories` table |
| DB file | `data/jarvis_memory.db` | `data/brain.db` |
| Retrieval | Embedding or keyword | `get_text_similarity()` |
| Dedup | By `(s, p, o, user, tenant)` with confidence update | By exact `fact` string match |
| Contradictions | Explicit `find_contradictions()` | None |
| Consumers | Pipeline MemoryStage, PreferenceProfile | brain subsystems |

**Impact:** Two independent fact stores in two separate SQLite files, with different schemas and different dedup strategies.

### 11.3 Decision Memory (2x overlap)

| Aspect | `memory/decision_memory.py` (System A) | `brain/memory/decision.py` (System B) |
|--------|----------------------------------------|---------------------------------------|
| What it stores | Agent selection outcomes | Decision/outcome/lesson |
| Backend | JSON file (`~/.jarvis/decision_memory.json`) | SQLite (`brain.db`) |
| Consumers | `core/control_loop.py` | `brain/automation/loop.py` |
| Purpose | Which agent to use for each task type | What was learned from each decision |

**Impact:** Two decision memory stores with no overlap. The System A version is used by the core control loop for agent routing; the System B version is used by brain automation for self-reflection.

### 11.4 Checkpoint Systems (4x overlap)

See Section 7.1. Four checkpoint systems serving overlapping purposes (agent state persistence) but with incompatible formats and no coordination.

### 11.5 Vector Stores (2x overlap + 1 independent)

Three vector stores (Qdrant via mem0, ChromaDB via mem0, ChromaDB via core) with different data and no bridging.

### 11.6 Session/Conversation Stores (3x overlap)

| System | Backend | Schema | Consumer |
|--------|---------|--------|----------|
| `ConversationManager` | JSON files | `[{role, content, timestamp}]` | Legacy chat |
| `ChatHistory` (SQLAlchemy) | SQLAlchemy DB | `(id, user_id, role, message, intent, session_id, timestamp)` | ORM queries |
| `memory/` (via MemoryStage) | RAM + ChromaDB | Message pairs | Pipeline |

---

## 12. Thread Safety Audit

| Component | Thread Safe? | Mechanism | Risk |
|-----------|-------------|-----------|------|
| **MemoryFacade** | Partial | No explicit lock; delegates to backends | Concurrent calls to lazy-loaded backends could double-initialize |
| **TieredMemory** | No | No lock on hot_tier list | Concurrent `remember()`/`recall()`: race on hot_tier append/read, two writers interleave |
| **Mem0Adapter** | No | No lock | Concurrent `add()` / `search()` via mem0 library — mem0's own thread safety is unknown |
| **EmbeddingMemory** | No | No lock on SQLite connection | Concurrent stores interleave on `execute()` |
| **FactStore** | **Yes** | `threading.Lock()` (reentrant) | Proper lock around all DB operations |
| **DecisionMemory** (memory/) | **Yes** | `threading.Lock()` | Proper lock around all file operations |
| **MemoryManager** (System B) | **Yes** | Each sub-memory has `threading.Lock()` | Proper per-instance locks |
| **EpisodicMemory** | **Yes** | `threading.Lock()` | Proper lock around all DB operations |
| **SemanticMemory** | **Yes** | `threading.Lock()` | Proper lock around all DB operations |
| **TaskMemory** | **Yes** | `threading.Lock()` | Proper lock around all DB operations |
| **DecisionMemory** (brain/) | **Yes** | `threading.Lock()` | Proper lock around all DB operations |
| **MemoryManager** (System C) | No | No lock | Concurrent `save()`: .tmp file race |
| **PatternFailureMemory** | **Yes** | `threading.Lock()` | Proper lock around all file operations |
| **ProviderMemory** | **Yes** | `threading.Lock()` | Proper lock around all file operations |
| **CloudMemory** | No | No lock | Async concurrent access to local SQLite |
| **ConstitutionalMemory** | No | No lock | Concurrent `log()` interleaves |
| **KnowledgeStore** | No | No lock | Concurrent writes interleave |
| **PlanStore** | **Yes** | `threading.Lock()` | Proper lock |
| **ActivityStore** | **Yes** | `threading.Lock()` | Proper lock |
| **WorkflowStore** | **Yes** | `threading.Lock()` | Proper lock |
| **ConversationManager** | No | No lock | `_sessions` dict access races |
| **SessionMemory** | No | No lock | `_contexts` dict access races |
| **CheckpointStore** | **Yes** | `threading.Lock()` | Proper lock |
| **GraphCheckpointer** | No | No lock | File write races |

**Summary:** 12 of 23 components have no thread safety. System B and the shared `workflow.db` stores are consistently thread-safe. System A is inconsistent — FactStore and DecisionMemory are safe, but TieredMemory, EmbeddingMemory, and Mem0Adapter are not.

---

## 13. Persistence Map

### 13.1 Database Files

| Database File | Path | Tables | Owned By | Also Used By |
|--------------|------|--------|----------|-------------|
| `jarvis_memory.db` | `data/jarvis_memory.db` | `facts`, `semantic_memory` | FactStore, EmbeddingMemory | — |
| `brain.db` | `data/brain.db` | `episodic_memories`, `semantic_memories`, `task_memories`, `decision_memories` | MemoryManager (System B) | — |
| `workflow.db` | `data/workflow.db` | `plans`, `activity_nodes`, `activity_edges`, `workflow_instances`, `workflow_steps`, `workflow_events`, `workflow_contexts`, `workflow_artifacts`, `knowledge_items`, `experience_summaries` | PlanStore, ActivityStore, WorkflowStore, KnowledgeStore | **6 subsystems share this DB** |
| `agent_checkpoints.db` | `~/.jarvis/agent_checkpoints.db` | `checkpoints`, `node_checkpoints` | CheckpointStore | — |
| `agent_state.db` | `~/.jarvis/agent_state.db` | `agent_state_snapshots` | session_db | — |
| `constitutional_memory.db` | `~/.jarvis/constitutional_memory.db` | `grade_history` | ConstitutionalMemory | — |
| `workflow_learning.db` | `~/.jarvis/workflow_learning.db` | `workflow_history` | WorkflowHistoryStore, WorkflowCalibrationStore | — |
| `ai_os_memory.db` | `./ai_os_memory.db` (configurable) | `jarvis_memories` | CloudMemory | — |
| (SQLAlchemy) | Configurable | `chat_history`, `users`, etc. | SQLAlchemy Base | API server |

### 13.2 JSON File Stores

| File | Path | Stored By | Schema |
|------|------|-----------|--------|
| `memory.json` | `{data_dir}/memory.json` | System C MemoryManager | `[{id, text, source, category, owner, created_at, ...}]` |
| `decision_memory.json` | `~/.jarvis/decision_memory.json` | System A DecisionMemory | `{entries: [...], rules: {...}}` |
| `pattern_failures.json` | `~/.jarvis/pattern_failures.json` | PatternFailureMemory | `{patterns: [{pattern, regex, strategies, ...}]}` |
| `provider_memory/memory.json` | `~/.jarvis/provider_memory/memory.json` | ProviderMemory | `{evidence: {...}, records: {...}}` |
| Session files | `~/.jarvis/sessions/{id}.json` | ConversationManager | `[{role, content, timestamp}]` |
| Checkpoint files | `~/.jarvis/checkpoints/{project}/` | CheckpointManager | `checkpoint.json` + `files/` |
| Graph checkpoints | `~/.jarvis/graph_checkpoints/{id}.json` | GraphCheckpointer | `{graph_id, nodes, state, ...}` |

### 13.3 Vector Stores

| Store | Path | Owned By | Data |
|-------|------|----------|------|
| ChromaDB (`jarvis_memories`) | `./data/chroma/` | mem0 library (via Mem0Adapter) | Memory embeddings |
| ChromaDB (`odysseus_memories`) | `./data/chroma/` (same) | MemoryVectorStore (System D) | Memory embeddings |
| Qdrant | `./data/qdrant_storage/` | mem0 library (via TieredMemory) | Warm/cold tier vectors |

### 13.4 Total Databases: **9 SQLite + 6 JSON + 2 ChromaDB + 1 Qdrant = 18 persistent stores**

---

## 14. Integration Points

### 14.1 Pipeline Integration

```
ReceiveStage → LoadContextStage → ... → ContextRetrievalStage → IntentStage → PlannerStage → ...
                                               │                      │             │
                                               ▼                      ▼             ▼
                                        MemoryFacade.recall()   (no memory)   BehaviorAdapter
                                        FactStore.query()                      .for_planner()
                                        PreferenceProfile.build()
                                               │
                                        CapabilitySelectionStage → ... → ExecutionStage → MemoryStage
                                               │                                          │
                                               ▼                                          ▼
                                        MemoryDrivenRouter                        MemoryFacade.store()
                                        .best_agent_for()                         FactStore.store_facts()
```

### 14.2 API Integration

```
GET  /api/memory          ─→ MemoryFacade.get_all("default")
GET  /api/memory/stats    ─→ MemoryFacade.get_all("default") → count stats
GET  /api/memory/{user}   ─→ MemoryFacade.get_all(user_id)
DELETE /api/memory/{user} ─→ MemoryFacade.delete_all(user_id) [mem0 only]
POST /cloud/sync          ─→ CloudMemory.sync_from_local()
POST /cloud/pull          ─→ CloudMemory.sync_to_local()
```

### 14.3 MCP Integration

```
mcp/server.py ─→ MemoryFacade.recall() (tool: "recall_memories")
mcp/memory_server.py ─→ System C MemoryManager (deprecated, TODO: migrate)
```

### 14.4 Brain Integration

```
brain/automation/loop.py     ─→ MemoryManager (System B) — store_trace, store_decision, reflect_on_task
brain/learning_engine.py     ─→ MemoryManager (System B) — decision.get_lessons
brain/skill_acquisition.py   ─→ MemoryManager (System B) — semantic.store
brain/self_improvement.py    ─→ MemoryManager (System B) — decision.get_lessons, store_decision
brain/world_model.py         ─→ MemoryManager (System B) — semantic.store, semantic.retrieve
```

### 14.5 Cross-System Dependencies

```
System B (brain/memory/)
  └── retrieval uses get_text_similarity() from System C (core/memory.py) [DEPRECATED]

System A (memory/)
  └── TieredMemory uses EmbeddingMemory (same system)  
  └── FactStore uses EmbeddingMemory (same system)

System D (core/memory_vector.py)
  └── shares core.embeddings.get_embedding_client() with RAG subsystem
```

---

## 15. Findings

### F-1: Three General-Purpose Memory Systems with No Data Sharing
Systems A, B, and C store overlapping types of data (facts, decisions, conversation memories) but share no backends, schemas, or synchronization. A fact learned by System B's SemanticMemory is invisible to System A's FactStore and vice versa.

### F-2: Two Independent Fact Stores with Different Schemas
`FactStore` (19 columns, RDF triples, embedding search, contradiction detection) and `SemanticMemory` (9 columns, flat facts, text similarity retrieval) both store factual knowledge with no bridging.

### F-3: Two Decision Memory Stores with Different Purposes
System A's `DecisionMemory` (agent selection for task types) and System B's `DecisionMemory` (decision/outcome/lesson for self-reflection) share a name but completely different schemas and consumers.

### F-4: Three Vector Stores Operating Independently
Two ChromaDB collections (`jarvis_memories` via mem0, `odysseus_memories` via core) plus one Qdrant store (via mem0 as warm/cold tier). All store semantic memory embeddings, none share data.

### F-5: Four Checkpoint Systems for Overlapping Purpose
Agent execution state is persisted in `CheckpointManager` (JSON), `CheckpointStore` (SQLite), `GraphCheckpointer` (JSON), and `session_db` (SQLite). No coordination between them.

### F-6: Six Systems Sharing `workflow.db` (Tight Coupling)
PlanStore, ActivityStore, WorkflowStore, and KnowledgeStore all share `data/workflow.db`. While this simplifies transactions within the workflow domain, it creates a coupling risk — schema changes in one affect all.

### F-7: System C Marked Deprecated but Still Core to System B
`core/memory.py` `get_text_similarity()` is the retrieval backbone for all three similarity-based searches in System B. Deprecating/removing it would break System B's core retrieval.

### F-8: MemoryFacade.delete_all() Is Incomplete
The API DELETE endpoint only clears mem0 cold storage. Hot tier memories remain. There is no mechanism to clear all tiers for a user.

### F-9: No Write API Endpoint
Despite 4 memory API endpoints, none accepts a POST/PUT to add memories. Memory creation is only possible through the pipeline (MemoryStage) or programmatic calls.

### F-10: Thread Safety Is Inconsistent
System B is fully thread-safe. System A is partially thread-safe (FactStore and DecisionMemory have locks; TieredMemory, EmbeddingMemory, Mem0Adapter do not). ConversationManager and ContextManager have no thread safety at all.

### F-11: Six Different SQLite Databases with Different Connection Patterns
Each database file uses its own connection management (some open/close per-op, some use connection pooling). There is no centralized database management.

### F-12: Session/Conversation Memory Split Across 3 Systems
ConversationManager (JSON files), ChatHistory (SQLAlchemy), and MemoryStage + MemoryFacade (vector + SQLite) all store conversation data. A conversation's user messages may be in any combination of these stores depending on code path.

### F-13: EmbeddingMemory Uses Brute-Force Full-Scan Similarity
`semantic_search()` loads all embeddings from SQLite and computes cosine similarity in Python. For datasets beyond ~10,000 entries this will become a performance bottleneck.

### F-14: PreferenceProfile Is Read-Only
`PreferenceProfile` builds from FactStore but has no methods to directly add or update preferences. All preference mutations must go through FactStore.store_facts(), which requires the extraction pipeline.

### F-15: No Memory Health Monitoring
None of the 18 persistent stores have health check endpoints, integrity verification, or corruption detection.

---

## 16. Recommendations

### R-1: (Critical) Unify Memory Systems A and B
Design a single memory architecture that serves both user-facing (System A) and agent-facing (System B) consumers. Options:
- **Absorb B into A**: Extend MemoryFacade to support task traces, episodes, and decisions
- **Absorb A into B**: Extend MemoryManager with facades for user memory storage
- **Bridge**: Add bi-directional sync (worst option — adds complexity without consolidation)

**Priority:** Before implementing any new memory features.

### R-2: (High) Consolidate Fact Stores
Merge `memory/fact_store.py` (RDF triples, contradiction detection, embedding search) and `brain/memory/semantic.py` (category filtering, importance decay) into a single fact store with union of capabilities.

### R-3: (High) Consolidate Decision Memories
Merge `memory/decision_memory.py` (agent routing) and `brain/memory/decision.py` (self-reflection) into a single decision store that serves both agent selection and lesson learning.

### R-4: (High) Reduce from 3 Vector Stores to 1
Choose one vector store (ChromaDB is the most widely used) and migrate both System A and System D to a single shared instance. Eliminate Qdrant and the duplicate ChromaDB collection.

### R-5: (High) Formalize MemoryFacade as The Single Memory API
Complete the migration away from System C and integrate System B consumers into MemoryFacade. Remove the deprecation notice on System C only after System B's dependency on `get_text_similarity()` is resolved.

### R-6: (Medium) Add Thread Safety to System A Hot Path
Add locks to `TieredMemory` (hot_tier list), `EmbeddingMemory` (SQLite connection), and `Mem0Adapter` (delegation). The hot tier is the most frequently accessed memory path.

### R-7: (Medium) Add Memory Write API Endpoint
Expose `POST /api/memory` for programmatic memory storage, completing the REST API for CRUD operations on user memory.

### R-8: (Medium) Fix MemoryFacade.delete_all() to Clear All Tiers
Hot tier memories should also be cleared during user data deletion for GDPR compliance.

### R-9: (Medium) Remove Dependency of System B on System C
Implement `get_text_similarity()` directly in `brain/memory/` or in a shared utility module, allowing System C (`core/memory.py`) to be safely removed.

### R-10: (Low) Add PreferenceProfile Write Methods
Implement `add_preference()` and `update_preference()` on PreferenceProfile so preferences can be managed without going through the full extraction pipeline.

### R-11: (Low) Add Memory Health Endpoints
Expose `GET /api/memory/health` that verifies each backend (SQLite connectivity, vector store count, JSON file integrity).

### R-12: (Low) Consider Embedding Index for Semantic Search
Replace brute-force cosine similarity in EmbeddingMemory with an approximate nearest neighbor (ANN) index (e.g., ChromaDB integration) for scalability beyond 10,000 entries.

### R-13: (Low) Consolidate Checkpoint Systems
Design a unified checkpoint interface with one SQLite-backed implementation and phase out the JSON-based checkpoints. The CheckpointStore (agent graph) and WorkflowRecovery (workflow engine) are the strongest candidates for merging.
