import time
import os
from typing import List, Dict, Any, Optional
from mem0 import Memory
from memory.embedding_memory import embedding_memory

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
        
        # Initialize Mem0 for warm/cold tiers with local Qdrant storage
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
            self.mem0 = Memory.from_config(config)
        except Exception as e:
            print(f"[WARN] Qdrant unavailable, TieredMemory running without vector store: {e}")
            self.mem0 = None

    def remember(self, content: str, importance: float = 0.5, metadata: Dict = None):
        """
        Store a new memory.
        """
        # Add to Hot tier
        self.hot_tier.append({
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata
        })
        if len(self.hot_tier) > self.max_hot:
            to_archive = self.hot_tier.pop(0)
            # Consolidate to Warm/Cold tier via Mem0
            if self.mem0:
                self.mem0.add(to_archive["content"], user_id=self.user_id, metadata=to_archive["metadata"])
        
        # If very important, store in semantic memory immediately
        if importance > 0.8:
            embedding_memory.store(content, metadata)

    def recall(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Recall memories across all tiers.
        """
        results = []
        
        # 1. Search Hot tier
        for m in reversed(self.hot_tier):
            if query.lower() in m["content"].lower():
                results.append(m)
        
        # 2. Search Warm/Cold tier via Mem0
        if self.mem0:
            try:
                mem0_results = self.mem0.search(query, user_id=self.user_id, limit=limit)
                results.extend(mem0_results)
            except Exception as e:
                print(f"[WARN] Mem0 search failed: {e}")
        
        # 3. Search Semantic tier
        semantic_results = embedding_memory.semantic_search(query, top_k=limit)
        results.extend(semantic_results)
        
        return results

    def consolidate(self):
        """
        Maintenance: move warm to cold or cleanup.
        """
        # Mem0 handles much of this internally
        pass

# Instance
tiered_memory = TieredMemory()
