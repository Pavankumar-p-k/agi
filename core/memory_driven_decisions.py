"""core/memory_driven_decisions.py
Phase 4 (D3): Memory-Driven Decisions.
Uses decision_memory.py to actively shape agent/strategy selection at runtime.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MemoryDrivenRouter:
    """Reads past decisions to actively shape agent selection and strategy choice.
    Wraps DecisionMemory and provides runtime guidance.
    """
    def __init__(self):
        self._cache: dict[str, Optional[str]] = {}

    def best_agent_for(self, task_type: str, memory) -> Optional[str]:
        cache_key = f"agent_{task_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        best = memory.best_agent_for(task_type) if hasattr(memory, "best_agent_for") else None
        self._cache[cache_key] = best
        return best

    def worst_agent_for(self, task_type: str, memory) -> Optional[str]:
        return memory.worst_agent_for(task_type) if hasattr(memory, "worst_agent_for") else None

    def should_avoid(self, task_type: str, agent: str, memory) -> bool:
        avoid_key = f"avoid_{task_type}_{agent}"
        rules = memory._rules if hasattr(memory, "_rules") else {}
        return rules.get(avoid_key) == "true"

    def select_strategy(self, project_type: str, memory, goal: str = "") -> str:
        strategies = ["template_heavy", "minimal_custom", "full_featured"]
        scores = []
        for s in strategies:
            entries = [e for e in memory.entries
                       if s in e.get("task", "").lower() or s in e.get("goal", "").lower()]
            success_count = sum(1 for e in entries if e["success"])
            total = len(entries)
            score = (success_count / total) if total > 0 else 0.5
            scores.append((score, s))
        scores.sort(reverse=True)
        best = scores[0][1] if scores else "template_heavy"
        logger.info(f"[MDROUTER] Strategy select: {best} (based on {len(scores)} options)")
        return best

    def clear_cache(self):
        self._cache.clear()


memory_router = MemoryDrivenRouter()
