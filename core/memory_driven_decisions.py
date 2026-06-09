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
"""core/memory_driven_decisions.py
Phase 4 (D3): Memory-Driven Decisions.
Uses decision_memory.py to actively shape agent/strategy selection at runtime.
"""
import logging

logger = logging.getLogger(__name__)


class MemoryDrivenRouter:
    """Reads past decisions to actively shape agent selection and strategy choice.
    Wraps DecisionMemory and provides runtime guidance.
    """
    def __init__(self):
        self._cache: dict[str, str | None] = {}

    def best_agent_for(self, task_type: str, memory) -> str | None:
        cache_key = f"agent_{task_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        best = memory.best_agent_for(task_type) if hasattr(memory, "best_agent_for") else None
        self._cache[cache_key] = best
        return best

    def worst_agent_for(self, task_type: str, memory) -> str | None:
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
