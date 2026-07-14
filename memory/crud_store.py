"""memory/crud_store.py — JSON-file CRUD for flat dict memories.

Replaces ``core.memory.MemoryManager`` and ``core.memory_vector.MemoryVectorStore``.

Usage:
    from memory.crud_store import CrudStore
    store = CrudStore(DATA_DIR)
    store.add("some text", source="user", category="fact")
    store.list_all() -> list[dict]
    store.search("query") -> list[dict]
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import Any

from memory.similarity import get_text_similarity

logger = logging.getLogger(__name__)


class CrudStore:
    """Flat JSON-file-backed memory store with relevance search.

    API parity with the deprecated ``core.memory.MemoryManager`` so that
    consumers (MCP server, chat tools, etc.) can migrate with minimum churn.
    """

    def __init__(self, data_dir: str) -> None:
        self._file = os.path.join(data_dir, "memory.json")
        self._ensure_file()

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _ensure_file(self) -> None:
        if not os.path.exists(self._file):
            os.makedirs(os.path.dirname(self._file), exist_ok=True)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def load_all(self) -> list[dict]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, encoding="utf-8") as f:
                data = json.load(f)
            return self._validate(data) if isinstance(data, list) else []
        except (json.JSONDecodeError, PermissionError) as e:
            logger.error("Error loading %s: %s", self._file, e)
            return []

    def save(self, entries: list[dict]) -> None:
        for entry in entries:
            entry.setdefault("id", str(uuid.uuid4()))
            entry.setdefault("timestamp", int(time.time()))
            entry.setdefault("source", "user")
            entry.setdefault("category", "fact")
        tmp = self._file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._file)

    @staticmethod
    def _validate(entries: list[dict]) -> list[dict]:
        out = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            e.setdefault("id", str(uuid.uuid4()))
            e.setdefault("timestamp", int(time.time()))
            e.setdefault("source", "unknown")
            e.setdefault("category", "fact")
            e.setdefault("uses", 0)
            out.append(e)
        return out

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, text: str, source: str = "user",
            category: str = "fact", owner: str | None = None) -> dict:
        if not text.strip():
            raise ValueError("Memory text cannot be empty")
        entry: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "text": text.strip(),
            "timestamp": int(time.time()),
            "source": source,
            "category": category,
            "uses": 0,
        }
        if owner:
            entry["owner"] = owner
        return entry

    def list_all(self, category: str = "", owner: str | None = None,
                 limit: int = 0) -> list[dict]:
        entries = self.load_all()
        if category:
            entries = [e for e in entries
                       if e.get("category", "").lower() == category.lower()]
        if owner is not None:
            entries = [e for e in entries if e.get("owner") == owner]
        if limit and len(entries) > limit:
            entries = entries[:limit]
        return entries

    def update(self, memory_id: str, **updates: Any) -> dict | None:
        entries = self.load_all()
        for entry in entries:
            if entry.get("id", "").startswith(memory_id):
                for k, v in updates.items():
                    entry[k] = v
                entry["timestamp"] = int(time.time())
                self.save(entries)
                return entry
        return None

    def delete(self, memory_id: str) -> bool:
        entries = self.load_all()
        new_entries = [e for e in entries
                       if not e.get("id", "").startswith(memory_id)]
        if len(new_entries) == len(entries):
            return False
        self.save(new_entries)
        return True

    def increment_uses(self, ids: list[str]) -> None:
        if not ids:
            return
        id_set = set(ids)
        entries = self.load_all()
        changed = False
        for e in entries:
            if e.get("id") in id_set:
                e["uses"] = int(e.get("uses", 0) or 0) + 1
                changed = True
        if changed:
            self.save(entries)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def get_relevant_memories(self, query: str, memories: list[dict] | None = None,
                              threshold: float = 0.05, max_items: int = 8) -> list[dict]:
        if not query.strip():
            return []
        if memories is None:
            memories = self.load_all()
        if not memories:
            return []

        query_lower = query.lower()
        query_type = self._classify_query(query_lower)

        identity_memories: list[dict] = []
        other_memories: list[dict] = []
        for mem in memories:
            if self._is_identity_memory(mem):
                identity_memories.append(mem)
            else:
                other_memories.append(mem)

        scored: list[tuple[float, dict]] = []
        if query_type == "identity" and identity_memories:
            for mem in identity_memories:
                scored.append((0.9, mem))

        for mem in other_memories:
            score = get_text_similarity(query, mem.get("text", ""))
            score = self._apply_boosts(score, query_type, mem.get("text", ""))
            if query_lower in mem.get("text", "").lower():
                score = max(score, 0.8)
            if score >= threshold:
                scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [mem for _, mem in scored[:max_items]]

    # ------------------------------------------------------------------
    # Vector search (delegates to ChromaDB wrapper)
    # ------------------------------------------------------------------

    def vector_add(self, entry_id: str, text: str,
                   collection: str = "odysseus_memories") -> None:
        try:
            from memory.vector_store import add_to_collection
            add_to_collection(collection, [entry_id], [text])
        except Exception as e:
            logger.debug("vector_add failed: %s", e)

    def vector_remove(self, entry_id: str,
                      collection: str = "odysseus_memories") -> None:
        try:
            from memory.vector_store import delete_from_collection
            delete_from_collection(collection, [entry_id])
        except Exception as e:
            logger.debug("vector_remove failed: %s", e)

    @property
    def vector_healthy(self) -> bool:
        try:
            from memory.vector_store import get_chroma_collection
            get_chroma_collection("odysseus_memories")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_query(text: str) -> str | None:
        identity = ["name", "who", "i", "am", "called", "identity", "myself", "me", "my"]
        contact = ["phone", "email", "address", "contact", "number", "where", "located", "reach"]
        pref = ["like", "prefer", "favorite", "want", "love", "hate", "dislike", "enjoy", "interested"]
        task = ["todo", "task", "remind", "meeting", "appointment", "schedule", "deadline"]
        fact = ["what", "when", "where", "how", "why", "explain", "describe", "information", "know"]
        if any(w in text for w in identity):
            return "identity"
        if any(w in text for w in contact):
            return "contact"
        if any(w in text for w in pref):
            return "preference"
        if any(w in text for w in task):
            return "task"
        if any(w in text for w in fact):
            return "fact"
        return None

    @staticmethod
    def _is_identity_memory(mem: dict) -> bool:
        text = mem.get("text", "")
        if re.search(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', text):
            return True
        lower = text.lower()
        return any(w in lower for w in
                   ["name is", "i'm", "i am", "called", "my name", "named", "call me"])

    @staticmethod
    def _apply_boosts(score: float, query_type: str | None, memory_text: str) -> float:
        if query_type == "contact":
            has = any(w in memory_text for w in ["@gmail.com", "@", ".com",
                                                  "phone", "number", "address",
                                                  "http", "www", "tel:"])
            if has:
                score *= 1.4
        elif query_type == "preference":
            has = any(w in memory_text for w in ["like", "love", "hate", "dislike",
                                                  "prefer", "favorite", "enjoy", "interested"])
            if has:
                score *= 1.3
        elif query_type == "task":
            has = any(w in memory_text for w in ["todo", "task", "remind", "meeting",
                                                  "appointment", "schedule", "deadline", "need to"])
            if has:
                score *= 1.3
        return score
