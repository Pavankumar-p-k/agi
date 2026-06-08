import time
import os
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from mem0 import Memory as Mem0Memory
except ImportError:
    Mem0Memory = None
try:
    from memory.embedding_memory import get_embedding_memory
    _get_embedding = get_embedding_memory
except Exception:
    _get_embedding = lambda: None


@dataclass
class Memory:
    type: str = "fact"
    value: str = ""
    summary: str = ""
    count: int = 1
    trigger: Optional[str] = None
    fix: Optional[str] = None
    input_pattern: Optional[str] = None
    outcome: Optional[str] = None
    embedding: Optional[list[float]] = None
    timestamp: float = 0.0
    metadata: Optional[dict] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Memory":
        content = d.get("content") or d.get("value") or d.get("text", "")
        meta = d.get("metadata") or {}
        return cls(
            type=meta.get("type", "fact"),
            value=content,
            summary=meta.get("summary", content[:200]),
            count=meta.get("count", 1),
            trigger=meta.get("trigger"),
            fix=meta.get("fix"),
            input_pattern=meta.get("input_pattern"),
            outcome=meta.get("outcome"),
            timestamp=d.get("timestamp", 0.0),
            metadata=meta,
        )


class TieredMemory:
    """
    Tiered memory system for JARVIS.
    Hot: RAM (recent turns)
    Warm: SQLite (session history)
    Cold: Semantic (long-term)
    """
    def __init__(self, user_id: str = "default_user"):
        self.user_id = user_id
        self.hot_tier: List[Dict] = []
        self.max_hot = 10
        self._embedding = None
        self.mem0 = None

        # Initialize Mem0 for warm/cold tiers with local Qdrant storage
        if Mem0Memory is not None:
            try:
                qdrant_path = os.path.join(os.getcwd(), "data", "qdrant_storage")
                os.makedirs(os.path.dirname(qdrant_path), exist_ok=True)
                config = {
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {
                            "path": qdrant_path,
                        }
                    }
                }
                self.mem0 = Mem0Memory.from_config(config)
            except Exception as e:
                print(f"[MEMORY] Qdrant unavailable — running without vector store: {e}")
                self.mem0 = None

    def remember(self, content: str, importance: float = 0.5, metadata: Dict = None):
        """
        Store a new memory.
        """
        # Add to Hot tier
        self.hot_tier.append({
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {}
        })
        if len(self.hot_tier) > self.max_hot:
            to_archive = self.hot_tier.pop(0)
            # Consolidate to Warm/Cold tier via Mem0
            if self.mem0:
                self.mem0.add(to_archive["content"], user_id=self.user_id, metadata=to_archive["metadata"])

        # If very important, store in semantic memory immediately
        if importance > 0.8 and self._embedding is not None:
            self._embedding.store(content, metadata)
        elif importance > 0.8:
            emb = _get_embedding()
            if emb is not None:
                self._embedding = emb
                self._embedding.store(content, metadata)

    def recall(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Recall memories across all tiers.
        """
        results = []

        # 1. Search Hot tier with word-overlap scoring
        query_words = set(query.lower().split())
        for m in reversed(self.hot_tier):
            content_words = set(m["content"].lower().split())
            if query_words and content_words:
                overlap = len(query_words & content_words) / max(len(query_words), len(content_words))
                if overlap >= 0.3:  # 30% word overlap threshold
                    m["_score"] = overlap
                    results.append(m)

        # Phase 3: Emit hook
        try:
            from core.plugins.events import PluginEventBus
            PluginEventBus.instance().emit("on_memory_recall", query=query, results=results)
        except Exception as exc:
            logger.debug("PluginEventBus.on_memory_recall failed: %s", exc)

        # 2. Search Warm/Cold tier via Mem0
        if self.mem0:
            try:
                mem0_results = self.mem0.search(query, user_id=self.user_id, limit=limit)
                results.extend(mem0_results)
            except Exception as e:
                print(f"[WARN] Mem0 search failed: {e}")

        # 3. Search Semantic tier
        if self._embedding is None:
            self._embedding = _get_embedding()
        if self._embedding is not None:
            semantic_result = self._embedding.semantic_search(query, top_k=limit)
            if semantic_result.is_err():
                logger.warning("[Memory] Semantic search failed: %s", semantic_result._error)
                semantic_results = []
            else:
                semantic_results = semantic_result.unwrap()
            results.extend(semantic_results)

        return results

    def recall_filtered(
        self,
        query: str,
        threshold: float = 0.6,
        max_results: int = 5,
    ) -> list[Memory]:
        """Returns only memories relevant to query, scored by cosine similarity."""
        raw = self.recall(query, limit=20)
        if not raw:
            return []

        candidates = [Memory.from_dict(d) for d in raw]
        if self._embedding is None:
            self._embedding = _get_embedding()
        if self._embedding is None:
            return candidates[:max_results]
        embed_result = self._embedding.embed(query)
        if embed_result.is_err():
            return []
        q_vec = embed_result.unwrap().tolist()

        scored = []
        for m in candidates:
            if m.embedding:
                sim = self._cosine(q_vec, m.embedding)
                scored.append((m, sim))
            else:
                # Include without cosine score (from hot/mem0 tiers)
                scored.append((m, threshold))

        filtered = [(m, s) for m, s in scored if s is not None and s > threshold]
        filtered.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in filtered[:max_results]]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        import numpy as np
        a, b = np.array(a), np.array(b)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        return float(np.dot(a, b) / denom) if denom > 0 else 0.0

    def format_for_context(self, memories: list[Memory], query: str = "") -> str:
        """Format memories as actionable context string for LLM injection."""
        if not memories:
            logger.warning("[MEMORY] format_for_context called with no memories")
            return ""
        lines = ["RELEVANT PAST CONTEXT:"]
        for m in memories:
            if m.type == "preference":
                lines.append(f"- User prefers {m.value} (confirmed {m.count}x)")
            elif m.type == "failure" and m.fix:
                trigger = m.trigger or "unknown trigger"
                lines.append(f"- Previous failure: {trigger} → resolution: {m.fix}")
            elif m.type == "strategy" and m.input_pattern:
                lines.append(f"- Successful strategy: {m.input_pattern} → {m.outcome or 'worked'}")
            else:
                summary = m.summary or m.value[:200]
                lines.append(f"- {summary}")
        return "\n".join(lines)

    def consolidate(self):
        """
        Maintenance: move warm to cold or cleanup.
        """
        # Mem0 handles much of this internally
        pass


# Instance
tiered_memory = TieredMemory()
