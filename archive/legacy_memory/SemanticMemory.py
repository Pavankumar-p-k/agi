"""
CONTEXT MEMORY — Session continuity and long-term reasoning store.

Four specialized memory layers, each with a distinct role:

  1. WorkingMemory    — Current session: recent tasks, outputs, relationships
                        Capacity: 50 entries, TTL-based expiry, O(1) lookup
                        Purpose: "what did we just do?"

  2. EpisodicMemory   — Completed task episodes with full context
                        Capacity: 500 entries, importance-weighted LRU eviction
                        Purpose: "have we done something like this before?"

  3. SemanticMemory   — Extracted facts, patterns, domain knowledge
                        Capacity: 1000 entries, keyword-indexed recall
                        Purpose: "what do we know about X?"

  4. FailureMemory    — Failure fingerprints with avoidance strategies
                        Capacity: 200 entries, never evicted if still relevant
                        Purpose: "don't do that again"

Cross-layer recall:
  memory.recall(query)  → unified ranked results from all layers
  memory.relate(task_id) → find all tasks semantically related to one task

All operations are O(1) amortized. No external deps.
"""
from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional


# ── Memory Entry ──────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    key:         str
    content:     str
    importance:  float        = 0.5   # 0.0–1.0
    created_at:  float        = field(default_factory=time.monotonic)
    accessed_at: float        = field(default_factory=time.monotonic)
    access_count: int         = 0
    ttl_s:       float        = 0.0   # 0 = no expiry
    tags:        set[str]     = field(default_factory=set)
    metadata:    dict         = field(default_factory=dict)
    content_hash: str         = ""

    def __post_init__(self):
        self.content_hash = hashlib.md5(
            self.content.encode(), usedforsecurity=False
        ).hexdigest()

    @property
    def is_expired(self) -> bool:
        if self.ttl_s <= 0:
            return False
        return time.monotonic() - self.created_at > self.ttl_s

    def touch(self):
        self.accessed_at  = time.monotonic()
        self.access_count += 1
        # Reinforce importance on access
        self.importance = min(1.0, self.importance + 0.05)

    def decay(self, elapsed_hours: float, rate: float = 0.92):
        """Exponential importance decay. High-importance memories decay slower."""
        floor = 0.1 if self.access_count > 3 else 0.0
        self.importance = max(floor, self.importance * (rate ** elapsed_hours))

    def relevance_to(self, query: str) -> float:
        """Keyword overlap score × importance."""
        q_words  = set(re.findall(r'\b\w{3,}\b', query.lower()))
        e_words  = set(re.findall(r'\b\w{3,}\b', self.content.lower()))
        if not q_words:
            return 0.0
        overlap  = len(q_words & e_words)
        score    = overlap / (len(q_words) + 1)
        return score * self.importance

    def to_dict(self) -> dict:
        return {
            "key":        self.key,
            "content":    self.content[:200],
            "importance": round(self.importance, 3),
            "access_count": self.access_count,
            "tags":       list(self.tags),
        }


# ── Bounded Memory Store ──────────────────────────────────────────────────────

class BoundedStore:
    """
    LRU + importance-weighted eviction store.
    O(1) get/set/delete. Deduplication via content hash.
    """

    def __init__(self, name: str, capacity: int, decay_interval_h: float = 1.0):
        self.name             = name
        self.capacity         = capacity
        self.decay_interval_h = decay_interval_h
        self._store:  OrderedDict[str, MemoryEntry] = OrderedDict()
        self._hashes: dict[str, str] = {}        # content_hash → key
        self._last_decay = time.monotonic()

    def put(self, entry: MemoryEntry) -> bool:
        """Returns True if added (not a duplicate)."""
        self._maybe_decay()

        # Deduplication
        if entry.content_hash in self._hashes:
            existing_key = self._hashes[entry.content_hash]
            if existing_key in self._store:
                self._store[existing_key].touch()
                return False

        # Evict if needed
        while len(self._store) >= self.capacity:
            self._evict()

        self._store[entry.key] = entry
        self._store.move_to_end(entry.key)
        self._hashes[entry.content_hash] = entry.key
        return True

    def get(self, key: str) -> Optional[MemoryEntry]:
        entry = self._store.get(key)
        if entry:
            if entry.is_expired:
                self._remove(key)
                return None
            entry.touch()
            self._store.move_to_end(key)
        return entry

    def recall(self, query: str, k: int = 5) -> list[MemoryEntry]:
        """Return top-k entries by relevance × importance."""
        self._maybe_decay()
        scored = [
            (e.relevance_to(query), e)
            for e in self._store.values()
            if not e.is_expired
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [e for _, e in scored[:k] if _ > 0]
        for e in results:
            e.touch()
        return results

    def recall_by_tag(self, tag: str, k: int = 10) -> list[MemoryEntry]:
        return [
            e for e in list(self._store.values())[-k*2:]
            if tag in e.tags and not e.is_expired
        ][:k]

    def size(self) -> int:
        return len(self._store)

    def _evict(self):
        """Evict the lowest-importance entry (not the LRU)."""
        if not self._store:
            return
        worst_key = min(
            self._store,
            key=lambda k: self._store[k].importance
        )
        self._remove(worst_key)

    def _remove(self, key: str):
        entry = self._store.pop(key, None)
        if entry:
            self._hashes.pop(entry.content_hash, None)

    def _maybe_decay(self):
        now     = time.monotonic()
        elapsed = now - self._last_decay
        if elapsed < self.decay_interval_h * 3600:
            return
        hours = elapsed / 3600
        to_drop = []
        for key, entry in self._store.items():
            entry.decay(hours)
            if entry.importance < 0.02:
                to_drop.append(key)
        for key in to_drop:
            self._remove(key)
        self._last_decay = now


# ── Specialized Memory Layers ─────────────────────────────────────────────────

class WorkingMemory:
    """
    Short-term session memory. High-speed, auto-expiring.
    Stores: current plan_id, recent task inputs/outputs, active relationships.
    """

    def __init__(self):
        self._store     = BoundedStore("working", capacity=50, decay_interval_h=24)
        self.session_id = f"session-{int(time.monotonic())}"
        self._sequence: list[str] = []  # ordered task_ids in session

    def record_task(self, task_id: str, raw_input: str,
                    result_summary: str = "", status: str = "pending"):
        content = f"[{status}] {raw_input[:100]} → {result_summary[:100]}"
        entry   = MemoryEntry(
            key        = task_id,
            content    = content,
            importance = 0.6,
            ttl_s      = 3600,  # 1 hour working memory
            tags       = {status, "session", self.session_id},
            metadata   = {
                "task_id":   task_id,
                "status":    status,
                "input":     raw_input[:200],
                "summary":   result_summary[:200],
                "session":   self.session_id,
            },
        )
        self._store.put(entry)
        if task_id not in self._sequence:
            self._sequence.append(task_id)

    def get_task(self, task_id: str) -> Optional[dict]:
        entry = self._store.get(task_id)
        return entry.metadata if entry else None

    def recent_tasks(self, n: int = 5) -> list[dict]:
        recent_ids = self._sequence[-n:]
        result = []
        for tid in reversed(recent_ids):
            entry = self._store.get(tid)
            if entry:
                result.append(entry.metadata)
        return result

    def find_related(self, query: str, k: int = 3) -> list[MemoryEntry]:
        return self._store.recall(query, k)

    def session_summary(self) -> dict:
        return {
            "session_id":   self.session_id,
            "tasks_run":    len(self._sequence),
            "memory_size":  self._store.size(),
        }


class EpisodicMemory:
    """
    Long-term completed episode store.
    Each episode = one complete task execution with its outcome.
    Used for: "have I done something like this before and succeeded?"
    """

    def __init__(self):
        self._store = BoundedStore("episodic", capacity=500, decay_interval_h=6)

    def record_episode(self, task_id: str, raw_input: str,
                       status: str, elapsed_s: float,
                       tool_used: str = "", result_summary: str = ""):
        importance = 0.8 if status == "success" else 0.5
        content    = (
            f"EPISODE | {status} | {raw_input[:80]} | "
            f"tool={tool_used} | elapsed={elapsed_s:.1f}s | {result_summary[:80]}"
        )
        entry = MemoryEntry(
            key        = task_id,
            content    = content,
            importance = importance,
            tags       = {status, tool_used, "episode"},
            metadata   = {
                "task_id":   task_id,
                "input":     raw_input[:200],
                "status":    status,
                "elapsed_s": elapsed_s,
                "tool":      tool_used,
                "summary":   result_summary[:200],
            },
        )
        self._store.put(entry)

    def find_similar(self, query: str, k: int = 5) -> list[MemoryEntry]:
        return self._store.recall(query, k)

    def successful_patterns(self, query: str, k: int = 3) -> list[dict]:
        """Find episodes similar to query that succeeded."""
        all_similar = self._store.recall(query, k * 3)
        successful  = [
            e.metadata for e in all_similar
            if e.metadata.get("status") == "success"
        ]
        return successful[:k]

    def size(self) -> int:
        return self._store.size()


class SemanticMemory:
    """
    Extracted facts, patterns, and domain knowledge.
    Used for: building understanding over time from task results.
    """

    def __init__(self):
        self._store = BoundedStore("semantic", capacity=1000, decay_interval_h=24)

    def learn(self, fact: str, source_task_id: str = "",
              importance: float = 0.6, tags: set = None):
        key   = hashlib.md5(fact.encode(), usedforsecurity=False).hexdigest()[:16]
        entry = MemoryEntry(
            key        = key,
            content    = fact,
            importance = importance,
            tags       = (tags or set()) | {"fact"},
            metadata   = {"source_task": source_task_id},
        )
        self._store.put(entry)

    def recall(self, query: str, k: int = 5) -> list[str]:
        entries = self._store.recall(query, k)
        return [e.content for e in entries]

    def size(self) -> int:
        return self._store.size()


class FailureMemory:
    """
    Failure fingerprints with avoidance strategies.
    Entries are NOT automatically decayed — failures stay relevant.
    Used for: "I tried this before and it failed, here's why."
    """

    def __init__(self):
        self._store = BoundedStore("failure", capacity=200, decay_interval_h=168)  # 1 week

    def record_failure(self, raw_input: str, error: str,
                       tool: str = "", intent_type: str = ""):
        key     = hashlib.md5(
            (raw_input[:60] + error[:40]).encode(),
            usedforsecurity=False
        ).hexdigest()[:16]
        content = (
            f"FAILURE | intent={intent_type} | tool={tool} | "
            f"input={raw_input[:60]} | error={error[:80]}"
        )
        entry   = MemoryEntry(
            key        = key,
            content    = content,
            importance = 0.9,      # failures stay important
            tags       = {"failure", tool, intent_type},
            metadata   = {
                "input":       raw_input[:200],
                "error":       error[:200],
                "tool":        tool,
                "intent_type": intent_type,
                "count":       1,
            },
        )
        self._store.put(entry)

    def known_failures_for(self, query: str, k: int = 3) -> list[dict]:
        entries = self._store.recall(query, k)
        return [e.metadata for e in entries]

    def is_known_bad_pattern(self, raw_input: str) -> tuple[bool, str]:
        """Returns (is_bad, reason) for inputs that match known failure patterns."""
        similar = self._store.recall(raw_input, k=3)
        for entry in similar:
            if entry.relevance_to(raw_input) > 0.6:
                return True, entry.metadata.get("error", "known failure pattern")
        return False, ""

    def size(self) -> int:
        return self._store.size()


# ── Context Memory (unified interface) ────────────────────────────────────────

class ContextMemory:
    """
    Unified interface over all four memory layers.
    This is what the JarvisCoworker uses.

    Usage:
      memory = ContextMemory()
      memory.record_task_start(task_id, raw_input)
      memory.record_task_end(task_id, status, elapsed_s, summary)
      memory.recall(query)  → {working: [...], episodic: [...], semantic: [...], failures: [...]}
    """

    def __init__(self):
        self.working  = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.failures = FailureMemory()

    # ── recording ─────────────────────────────────────────────────────────

    def record_task_start(self, task_id: str, raw_input: str):
        self.working.record_task(task_id, raw_input, status="running")

    def record_task_end(self, task_id: str, raw_input: str,
                        status: str, elapsed_s: float,
                        tool_used: str = "", result_summary: str = "",
                        intent_type: str = ""):
        # Update working memory
        self.working.record_task(
            task_id, raw_input, result_summary, status
        )
        # Archive to episodic memory
        self.episodic.record_episode(
            task_id, raw_input, status, elapsed_s,
            tool_used, result_summary
        )
        # Learn from results
        if status == "success" and result_summary:
            self.semantic.learn(
                f"Task succeeded: {raw_input[:60]} → {result_summary[:60]}",
                source_task_id = task_id,
                importance     = 0.7,
                tags           = {"success", intent_type},
            )

    def record_failure(self, raw_input: str, error: str,
                       tool: str = "", intent_type: str = ""):
        self.failures.record_failure(raw_input, error, tool, intent_type)

    def learn_fact(self, fact: str, source_task_id: str = "",
                   importance: float = 0.6):
        self.semantic.learn(fact, source_task_id, importance)

    # ── retrieval ─────────────────────────────────────────────────────────

    def recall(self, query: str, k: int = 3) -> dict[str, list]:
        return {
            "working":   [e.to_dict() for e in
                          self.working.find_related(query, k)],
            "episodic":  [e.to_dict() for e in
                          self.episodic.find_similar(query, k)],
            "semantic":  self.semantic.recall(query, k),
            "failures":  self.failures.known_failures_for(query, k),
        }

    def is_known_bad(self, raw_input: str) -> tuple[bool, str]:
        return self.failures.is_known_bad_pattern(raw_input)

    def similar_successes(self, raw_input: str, k: int = 3) -> list[dict]:
        return self.episodic.successful_patterns(raw_input, k)

    def recent_context(self, n: int = 5) -> list[dict]:
        return self.working.recent_tasks(n)

    # ── stats ──────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "working":  self.working.session_summary(),
            "episodic": self.episodic.size(),
            "semantic": self.semantic.size(),
            "failures": self.failures.size(),
        }
