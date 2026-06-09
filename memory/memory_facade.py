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

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def store(self, text: str | list[dict], user_id: str = "default", metadata: dict | None = None) -> None:
        tiered = self._tiered_memory
        if tiered is not None:
            try:
                content = text[-1]["content"] if isinstance(text, list) else text
                tiered.remember(content, metadata=metadata or {})
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
                    results = backend.recall(query, limit=limit)
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
        mem0 = self._mem0_adapter
        if mem0 is not None:
            try:
                return mem0.get_all(user_id)
            except Exception as exc:
                logger.debug("mem0.get_all failed: %s", exc)
        return []

    def delete_all(self, user_id: str) -> bool:
        mem0 = self._mem0_adapter
        if mem0 is not None:
            try:
                return mem0.delete_all(user_id)
            except Exception as exc:
                logger.debug("mem0.delete_all failed: %s", exc)
        return False

    def search_all(self, query: str, limit: int = 5, user_id: str = "default") -> list[dict]:
        """Search all memory backends and tag results with source."""
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
                    items = backend.recall(query, limit=limit)
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
        """Consolidate memories across all available backends."""
        backends = [
            ("tiered", self._tiered_memory),
        ]
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


memory = MemoryFacade()
