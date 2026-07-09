# ADR-009: MemoryFacade as Unified Memory API

**Status:** Proposed  
**Date:** 2026-07-09  
**Phase:** 4  

## Context

The system has three concurrent memory systems creating data fragmentation across 18+ persistent stores:

- **System A** (`memory/`): MemoryFacade, TieredMemory, Mem0Adapter, FactStore, EmbeddingMemory — user-facing memory
- **System B** (`brain/memory/`): MemoryManager, EpisodicMemory, SemanticMemory, TaskMemory, DecisionMemory — agent-facing memory
- **System C** (`core/memory.py`): deprecated JSON-based MemoryManager
- **System D** (`core/memory_vector.py`): ChromaDB vector store

Data from a single interaction ("I like Python") fans out to 6 independent stores (hot tier, Mem0, semantic memory, FactStore, session history, ChatHistory) with no cross-references. If the FactStore is rebuilt, facts are lost even though the same data exists in Mem0.

Embedding serialization is incompatible between FactStore (`struct.pack`) and EmbeddingMemory (`np.tobytes`).

## Decision

**MemoryFacade (`memory/memory_facade.py`) becomes the sole consumer-facing memory API.**

1. All `brain/memory/` stores (Episodic, Semantic, Task, Decision) are moved into the `memory/` package and registered as backends behind MemoryFacade.
2. `MemoryFacade.store()` fans out to all registered backends. `MemoryFacade.recall()` queries all backends, deduplicates, and reranks.
3. Embedding serialization is standardized on `struct.pack` (portable, cross-language).
4. `core/memory.py` and `core/memory_vector.py` are deprecated and scheduled for removal after all consumers migrate.

## Consequences

**Positive:**
- Single API for all memory operations — pipeline, brain, agents, tools all call the same `store()` and `recall()`
- Embedding data is portable across stores
- Eliminates data fragmentation — one write path means one source of truth
- Simplifies the migration path for System B deprecation

**Negative:**
- MemoryFacade becomes a coordination bottleneck if not designed for concurrent backends
- Existing System B consumers must be migrated (brain subsystems, agent memory)
- ChromaDB merge (2 instances → 1) requires data reindexing
