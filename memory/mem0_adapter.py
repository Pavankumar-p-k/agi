"""
memory/mem0_adapter.py
Wraps mem0 (Apache 2.0 — mem0ai/mem0) to give Jarvis persistent
cross-session user memory. Falls back gracefully if mem0 unavailable.
"""
from __future__ import annotations
import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger("jarvis.memory.mem0")

try:
    from mem0 import Memory
    _MEM0_AVAILABLE = True
except ImportError:
    _MEM0_AVAILABLE = False
    logger.warning("mem0 not installed — pip install mem0ai. Using no-op memory.")


def _get_mem0_config() -> dict:
    """Build mem0 config using existing Ollama LLM router."""
    return {
        "llm": {
            "provider": "ollama",
            "config": {
                "model": "llama3.1:8b",
                "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                "temperature": 0.1,
                "max_tokens": 2000,
            }
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text",
                "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            }
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "jarvis_memories",
                "path": os.getenv("CHROMA_PATH", "./data/chroma"),
            }
        },
        "version": "v1.1",
    }


class Mem0Adapter:
    """
    Persistent memory layer powered by mem0.
    Stores and retrieves user-specific memories across sessions.
    """

    def __init__(self):
        self._memory: Optional[Any] = None
        if _MEM0_AVAILABLE:
            try:
                self._memory = Memory.from_config(_get_mem0_config())
                logger.info("mem0 memory initialized")
            except Exception as e:
                logger.warning(f"mem0 init failed: {e}. Using no-op memory.")

    @property
    def available(self) -> bool:
        return self._memory is not None

    def add(self, messages: List[Dict], user_id: str, metadata: Optional[Dict] = None) -> List[Dict]:
        """Add memories from a conversation turn."""
        if not self._memory:
            return []
        try:
            result = self._memory.add(messages, user_id=user_id, metadata=metadata or {})
            return result.get("results", []) if isinstance(result, dict) else []
        except Exception as e:
            logger.error(f"mem0.add failed: {e}")
            return []

    def search(self, query: str, user_id: str, limit: int = 10) -> List[Dict]:
        """Search for relevant memories for a user."""
        if not self._memory:
            return []
        try:
            results = self._memory.search(query, user_id=user_id, limit=limit)
            return results.get("results", []) if isinstance(results, dict) else results or []
        except Exception as e:
            logger.error(f"mem0.search failed: {e}")
            return []

    def get_all(self, user_id: str) -> List[Dict]:
        """Get all memories for a user."""
        if not self._memory:
            return []
        try:
            results = self._memory.get_all(user_id=user_id)
            return results.get("results", []) if isinstance(results, dict) else results or []
        except Exception as e:
            logger.error(f"mem0.get_all failed: {e}")
            return []

    def delete_all(self, user_id: str) -> bool:
        """GDPR: delete all memories for a user."""
        if not self._memory:
            return False
        try:
            self._memory.delete_all(user_id=user_id)
            return True
        except Exception as e:
            logger.error(f"mem0.delete_all failed: {e}")
            return False

    def format_context(self, memories: List[Dict]) -> str:
        """Format memories as context for LLM prompts."""
        if not memories:
            return ""
        lines = ["## Relevant Memories About This User:"]
        for m in memories[:8]:  # Cap at 8 to save context
            text = m.get("memory", m.get("text", ""))
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines)


# Singleton
mem0_memory = Mem0Adapter()

__all__ = ["Mem0Adapter", "mem0_memory"]
