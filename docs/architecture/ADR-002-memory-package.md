# ADR-002: Memory Package Replaces core.memory

**Status:** Accepted  
**Date:** 2026-07-05  
**Phase:** 1d  

## Context

Memory operations were scattered across:
- `core/memory.py` (MemoryManager — JSON-file CRUD)
- `core/memory_vector.py` (MemoryVectorStore — ChromaDB, broken import)
- `core/memory_driven_decisions.py` (MemoryDrivenRouter — used by control_loop)
- `core/pattern_failure_memory.py` (PatternFailureMemory — error pattern matching)
- `brain/memory/memory_manager.py` (Brain memory manager)
- `memory/memory_facade.py` (new unified facade)

These had inconsistent APIs, overlapping responsibilities, and no clear hierarchy.

## Decision

**`memory/` package (specifically `memory.memory_facade.MemoryFacade`) is the canonical memory API.**

1. `memory/memory_facade.py` is the public API for store/recall/search/delete
2. Backends live in `memory/mem0_adapter.py`, `memory/tiered_memory.py`, `memory/embedding_memory.py`
3. `core/memory.py` is a deprecated shim (emits DeprecationWarning)
4. `brain/memory/memory_manager.py` — 7 production callers, migrated when possible

## Consequences

**Positive:**
- Single facade API: `.store(text)`, `.recall(query)`, `.get_all(user_id)`, `.delete_all(user_id)`
- Lazy backend initialization (no import-time side effects)
- Clear tiered architecture: Hot (tiered) → Warm (embedding) → Cold (mem0)

**Negative:**
- `MemoryFacade` does not expose the low-level CRUD API (`load()`, `save()`, `add_entry()`) used by MCP memory server and chat tools — these remain on the legacy path
- `core/memory_vector.py` has broken imports from non-existent `src.` modules
- 7 files still import `MemoryManager` from `brain.memory.memory_manager` (migration deferred)

**Known gaps (Phase 2):**
- MCP memory server needs `MemoryManager`-level CRUD exposed through facade
- `core/control_loop.py` uses `core.memory_driven_decisions` — needs alternative API
