# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
memory/memory_facade.py
Unified store/recall interface over all memory backends.
Single import:
    from memory.memory_facade import memory
    memory.store(text, user_id)
    results = memory.recall(query, limit=5, user_id="default")
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class MemoryFacade:
    def __init__(self):
        self._mem0 = None
        self._tiered = None
        self._episodic = None
        self._semantic = None
        self._task = None
        self._decision = None

    # ------------------------------------------------------------------ #
    # Lazy backend accessors
    # ------------------------------------------------------------------ #

    @property
    def _mem0_adapter(self):
        if self._mem0 is None:
            try:
                from memory.mem0_adapter import mem0_memory
                self._mem0 = mem0_memory
            except Exception as exc:
                logger.debug("mem0 unavailable: %s", exc)
                self._mem0 = False
        return self._mem0 if self._mem0 is not False else None

    @property
    def _tiered_memory(self):
        if self._tiered is None:
            try:
                from memory.tiered_memory import tiered_memory
                self._tiered = tiered_memory
            except Exception as exc:
                logger.debug("tiered_memory unavailable: %s", exc)
                self._tiered = False
        return self._tiered if self._tiered is not False else None

    @property
    def _episodic_store(self):
        if self._episodic is None:
            try:
                from memory.episodic_store import EpisodicStore
                self._episodic = EpisodicStore()
            except Exception as exc:
                logger.debug("EpisodicStore unavailable: %s", exc)
                self._episodic = False
        return self._episodic if self._episodic is not False else None

    @property
    def _semantic_store(self):
        if self._semantic is None:
            try:
                from memory.semantic_store import SemanticStore
                self._semantic = SemanticStore()
            except Exception as exc:
                logger.debug("SemanticStore unavailable: %s", exc)
                self._semantic = False
        return self._semantic if self._semantic is not False else None

    @property
    def _task_store(self):
        if self._task is None:
            try:
                from memory.task_store import TaskStore
                self._task = TaskStore()
            except Exception as exc:
                logger.debug("TaskStore unavailable: %s", exc)
                self._task = False
        return self._task if self._task is not False else None

    @property
    def _decision_store(self):
        if self._decision is None:
            try:
                from memory.decision_store import DecisionStore
                self._decision = DecisionStore()
            except Exception as exc:
                logger.debug("DecisionStore unavailable: %s", exc)
                self._decision = False
        return self._decision if self._decision is not False else None

    # ------------------------------------------------------------------ #
    # Public API — Legacy (store/recall)
    # ------------------------------------------------------------------ #

    def store(self, text: str | list[dict], user_id: str = "default", metadata: dict | None = None) -> None:
        tiered = self._tiered_memory
        if tiered is not None:
            try:
                content = text[-1]["content"] if isinstance(text, list) else text
                tiered.remember(content, metadata=metadata or {}, user_id=user_id)
            except Exception as exc:
                logger.debug("tiered_memory.store failed: %s", exc)
        # Note: tiered_memory.remember() handles mem0 internally.
        # Do not call mem0.add() here to avoid duplicate writes.

    def recall(self, query: str, limit: int = 5, user_id: str = "default") -> list[dict]:
        seen = set()
        merged = []
        for backend_fn in [self._tiered_memory, self._mem0_adapter]:
            backend = backend_fn
            if backend is None:
                continue
            try:
                results = None
                if hasattr(backend, "recall"):
                    results = backend.recall(query, limit=limit, user_id=user_id)
                elif hasattr(backend, "search"):
                    results = backend.search(query, user_id=user_id, limit=limit)
                if results:
                    for r in results:
                        key = r.get("memory", r.get("text", r.get("content", "")))
                        if key and key not in seen:
                            seen.add(key)
                            merged.append(r)
            except Exception as exc:
                logger.debug("recall from %s failed: %s", type(backend).__name__, exc)
        merged.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return merged[:limit]

    def get_all(self, user_id: str) -> list[dict]:
        results = []
        tiered = self._tiered_memory
        if tiered is not None:
            try:
                hot = tiered.get_hot_memories()
                results.extend([{"memory": m, "tier": "hot"} for m in hot])
            except Exception as exc:
                logger.debug("tiered_memory.get_hot failed: %s", exc)

        mem0 = self._mem0_adapter
        if mem0 is not None:
            try:
                cold = mem0.get_all(user_id)
                results.extend(cold)
            except Exception as exc:
                logger.debug("mem0.get_all failed: %s", exc)
        return results

    def delete_all(self, user_id: str) -> bool:
        mem0 = self._mem0_adapter
        if mem0 is not None:
            try:
                return mem0.delete_all(user_id)
            except Exception as exc:
                logger.debug("mem0.delete_all failed: %s", exc)
        return False

    def search_all(self, query: str, limit: int = 5, user_id: str = "default") -> list[dict]:
        results = []
        backends = [
            ("tiered", self._tiered_memory),
            ("mem0", self._mem0_adapter),
        ]
        for source, backend in backends:
            if backend is None:
                continue
            try:
                items = None
                if hasattr(backend, "recall"):
                    items = backend.recall(query, limit=limit, user_id=user_id)
                elif hasattr(backend, "search"):
                    items = backend.search(query, user_id=user_id, limit=limit)
                if items:
                    for item in items:
                        item["_source"] = source
                    results.extend(items)
            except Exception as exc:
                logger.debug("search_all %s failed: %s", source, exc)
        return results

    def consolidate_all(self):
        backends = [("tiered", self._tiered_memory)]
        for source, backend in backends:
            if backend is None:
                continue
            try:
                if hasattr(backend, "consolidate"):
                    backend.consolidate()
                    logger.info("consolidated backend: %s", source)
            except Exception as exc:
                logger.debug("consolidate %s failed: %s", source, exc)

    def format_context(self, memories: list[dict]) -> str:
        if not memories:
            return ""
        mem0 = self._mem0_adapter
        if mem0 is not None and hasattr(mem0, "format_context"):
            try:
                return mem0.format_context(memories)
            except Exception as exc:
                logger.debug("mem0.format_context failed: %s", exc)
        lines = ["## Relevant Memories:"]
        for m in memories[:8]:
            text = m.get("memory", m.get("text", m.get("content", "")))
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Public API — Episodic
    # ------------------------------------------------------------------ #

    def store_episode(self, goal: str, actions: list[dict],
                      context: dict | None = None,
                      result: dict | None = None,
                      episode_type: str = "task",
                      tags: list[str] | None = None,
                      user_id: str = "default") -> str:
        store = self._episodic_store
        if store is not None:
            return store.store(goal, actions, context, result, episode_type, tags, user_id)
        return ""

    def retrieve_episodes(self, query: str, top_k: int = 5,
                          min_importance: float = 0.0,
                          user_id: str = "default") -> list[dict]:
        store = self._episodic_store
        if store is not None:
            return store.retrieve(query, top_k, min_importance, user_id)
        return []

    def get_recent_episodes(self, limit: int = 20, user_id: str = "default") -> list[dict]:
        store = self._episodic_store
        if store is not None:
            return store.get_recent(limit, user_id)
        return []

    # ------------------------------------------------------------------ #
    # Public API — Semantic (facts)
    # ------------------------------------------------------------------ #

    def store_fact(self, fact: str, category: str = "general",
                   confidence: float = 1.0, source: str = "inference",
                   tags: list[str] | None = None,
                   user_id: str = "default") -> str:
        store = self._semantic_store
        if store is not None:
            return store.store(fact, category, confidence, source, tags, user_id)
        return ""

    def retrieve_facts(self, query: str, top_k: int = 8,
                       min_confidence: float = 0.0,
                       categories: list[str] | None = None,
                       user_id: str = "default") -> list[dict]:
        store = self._semantic_store
        if store is not None:
            return store.retrieve(query, top_k, min_confidence, categories, user_id)
        return []

    def get_facts_by_category(self, category: str, limit: int = 50,
                              user_id: str = "default") -> list[dict]:
        store = self._semantic_store
        if store is not None:
            return store.get_by_category(category, limit, user_id)
        return []

    # ------------------------------------------------------------------ #
    # Public API — Task (action traces)
    # ------------------------------------------------------------------ #

    def store_trace(self, action_name: str, action_params: dict | None = None,
                    observation: str = "", success: bool = False,
                    duration_ms: float = 0.0, task_id: str = "",
                    context: dict | None = None,
                    tags: list[str] | None = None,
                    user_id: str = "default") -> str:
        store = self._task_store
        if store is not None:
            return store.store(action_name, action_params, observation,
                               success, duration_ms, task_id, context, tags, user_id)
        return ""

    def get_task_traces(self, task_id: str, user_id: str = "default") -> list[dict]:
        store = self._task_store
        if store is not None:
            return store.get_task_traces(task_id, user_id)
        return []

    def get_recent_traces(self, limit: int = 50, user_id: str = "default") -> list[dict]:
        store = self._task_store
        if store is not None:
            return store.get_recent(limit, user_id)
        return []

    # ------------------------------------------------------------------ #
    # Public API — Decision
    # ------------------------------------------------------------------ #

    def store_decision(self, context: str, decision: str,
                       alternatives: list[str] | None = None,
                       outcome: str = "", lesson: str = "",
                       success: bool = False,
                       tags: list[str] | None = None,
                       user_id: str = "default") -> str:
        store = self._decision_store
        if store is not None:
            return store.store(context, decision, alternatives,
                               outcome, lesson, success, tags, user_id)
        return ""

    def retrieve_decisions(self, query_context: str, top_k: int = 5,
                           user_id: str = "default") -> list[dict]:
        store = self._decision_store
        if store is not None:
            return store.retrieve_similar(query_context, top_k, user_id)
        return []

    def get_failures(self, limit: int = 20, user_id: str = "default") -> list[dict]:
        store = self._decision_store
        if store is not None:
            return store.get_failures(limit, user_id)
        return []

    def get_lessons(self, limit: int = 20, user_id: str = "default") -> list[dict]:
        store = self._decision_store
        if store is not None:
            return store.get_lessons(limit, user_id)
        return []

    # ------------------------------------------------------------------ #
    # Vector store (ChromaDB)
    # ------------------------------------------------------------------ #

    def search_vectors(self, query: str, limit: int = 8,
                       collection: str = "odysseus_memories") -> list[dict]:
        """Unified vector search across ChromaDB collections."""
        try:
            from memory.vector_store import search_collection
            return search_collection(collection, query, k=limit)
        except Exception as e:
            logger.debug("search_vectors failed: %s", e)
            return []

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    def summarize(self, user_id: str = "default") -> dict:
        return {
            "episodic_count": self._episodic_store.count(user_id) if self._episodic_store else 0,
            "semantic_count": self._semantic_store.count(user_id) if self._semantic_store else 0,
            "task_count": self._task_store.count(user_id) if self._task_store else 0,
            "decision_count": self._decision_store.count(user_id) if self._decision_store else 0,
        }


memory = MemoryFacade()
