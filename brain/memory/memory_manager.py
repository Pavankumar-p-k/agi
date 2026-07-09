from __future__ import annotations

import json
import logging
import os
from typing import Any

from .base import MemoryProvider
from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .task import TaskMemory
from .decision import DecisionMemory

logger = logging.getLogger(__name__)

# Canonical memory facade — all memory operations eventually route here.
_MEMORY_FACADE = None


def _ensure_memory_facade():
    global _MEMORY_FACADE
    if _MEMORY_FACADE is not None:
        return
    try:
        from memory.memory_facade import memory
        _MEMORY_FACADE = memory
        logger.debug("[MemoryManager] using MemoryFacade as canonical backend")
    except Exception:
        logger.debug("[MemoryManager] MemoryFacade not available")
        _MEMORY_FACADE = False


class MemoryManager:
    """Orchestrates all memory subsystems.

    Provides a unified API for storing, retrieving, and managing
    episodic, semantic, task, and decision memories. All operations
    are mirrored to the canonical ``MemoryFacade`` (memory/ package)
    in addition to the local brain memory stores.

    External providers can be registered via register_provider().
    """

    _MEMORY_USER = "brain"

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data",
            )
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "brain.db")

        self.db_path = db_path
        self.episodic = EpisodicMemory(db_path)
        self.semantic = SemanticMemory(db_path)
        self.task = TaskMemory(db_path)
        self.decision = DecisionMemory(db_path)
        self._providers: dict[str, MemoryProvider] = {
            "episodic": self.episodic,
            "semantic": self.semantic,
            "task": self.task,
            "decision": self.decision,
        }
        _ensure_memory_facade()
        logger.info("[MemoryManager] initialized at %s (facade=%s)", db_path, _MEMORY_FACADE is not None and _MEMORY_FACADE is not False)

    @property
    def providers(self) -> dict[str, MemoryProvider]:
        return dict(self._providers)

    def register_provider(self, name: str, provider: MemoryProvider):
        """Register an external memory provider."""
        self._providers[name] = provider
        setattr(self, name, provider)
        logger.info("[MemoryManager] registered provider: %s", name)

    # ------------------------------------------------------------------
    # Episodic
    # ------------------------------------------------------------------

    def store_episode(self, goal: str, actions: list[dict],
                      context: dict | None = None,
                      result: dict | None = None,
                      episode_type: str = "task",
                      tags: list[str] | None = None) -> str:
        mem_id = self.episodic.store(goal, actions, context, result, episode_type, tags)
        self._mirror_to_facade("episode", {
            "goal": goal, "actions": actions, "context": context,
            "result": result, "episode_type": episode_type, "tags": tags,
        })
        return mem_id

    def retrieve_episodes(self, query: str, top_k: int = 5,
                          min_importance: float = 0.0) -> list[dict]:
        return self.episodic.retrieve(query, top_k, min_importance)

    # ------------------------------------------------------------------
    # Semantic
    # ------------------------------------------------------------------

    def store_fact(self, fact: str, category: str = "general",
                   confidence: float = 1.0, source: str = "inference",
                   tags: list[str] | None = None) -> str:
        fact_id = self.semantic.store(fact, category, confidence, source, tags)
        self._mirror_to_facade("fact", {
            "fact": fact, "category": category, "confidence": confidence,
            "source": source, "tags": tags,
        })
        return fact_id

    def retrieve_facts(self, query: str, top_k: int = 8,
                       min_confidence: float = 0.0,
                       categories: list[str] | None = None) -> list[dict]:
        return self.semantic.retrieve(query, top_k, min_confidence, categories)

    # ------------------------------------------------------------------
    # Task traces
    # ------------------------------------------------------------------

    def store_trace(self, action_name: str, action_params: dict | None = None,
                    observation: str = "", success: bool = False,
                    duration_ms: float = 0.0, task_id: str = "",
                    context: dict | None = None,
                    tags: list[str] | None = None) -> str:
        trace_id = self.task.store(action_name, action_params, observation,
                                   success, duration_ms, task_id, context, tags)
        self._mirror_to_facade("trace", {
            "action_name": action_name, "action_params": action_params,
            "observation": observation, "success": success,
            "duration_ms": duration_ms, "task_id": task_id,
            "context": context, "tags": tags,
        })
        return trace_id

    def get_task_traces(self, task_id: str) -> list[dict]:
        return self.task.get_task_traces(task_id)

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def store_decision(self, context: str, decision: str,
                       alternatives: list[str] | None = None,
                       outcome: str = "", lesson: str = "",
                       success: bool = False,
                       tags: list[str] | None = None) -> str:
        dec_id = self.decision.store(context, decision, alternatives,
                                     outcome, lesson, success, tags)
        self._mirror_to_facade("decision", {
            "context": context, "decision": decision,
            "alternatives": alternatives, "outcome": outcome,
            "lesson": lesson, "success": success, "tags": tags,
        })
        return dec_id

    def retrieve_decisions(self, query_context: str, top_k: int = 5) -> list[dict]:
        return self.decision.retrieve_similar(query_context, top_k)

    # ------------------------------------------------------------------
    # Reflection
    # ------------------------------------------------------------------

    def reflect_on_task(self, task_goal: str, task_result: dict,
                        actions_taken: list[dict]) -> dict:
        """Self-reflection: analyze what happened and store lessons in DecisionMemory."""
        success = task_result.get("success", False)
        error = task_result.get("error", "")

        if success:
            lesson = f"Approach worked for: {task_goal[:100]}"
        else:
            lesson = f"Failed for: {task_goal[:100]}. Error: {error[:200]}"

        decision_id = self.store_decision(
            context=f"Task: {task_goal}",
            decision="execute_task",
            outcome=task_result.get("summary", str(task_result)),
            lesson=lesson,
            success=success,
            tags=["task_reflection", "auto"],
        )

        return {
            "decision_id": decision_id,
            "success": success,
            "lesson": lesson,
        }

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def summarize(self) -> dict:
        """Return a summary of all memory stores."""
        return {
            "episodic_count": self.episodic.count(),
            "semantic_count": self.semantic.count(),
            "task_count": self.task.count(),
            "decision_count": self.decision.count(),
            "db_path": self.db_path,
        }

    def decay_all(self, factor: float = 0.95):
        """Apply importance decay across all memory types."""
        self.semantic.decay(factor)

    def cleanup_old_episodes(self, before_days: int = 30):
        """Summarize old episodes to save space."""
        self.episodic.summarize_old(before_days)

    # ------------------------------------------------------------------
    # Canonical mirror
    # ------------------------------------------------------------------

    def _mirror_to_facade(self, memory_type: str, payload: dict) -> None:
        """Mirror a write to the canonical ``MemoryFacade``."""
        if _MEMORY_FACADE is None or _MEMORY_FACADE is False:
            return
        try:
            text = json.dumps({"type": memory_type, **payload}, default=str)
            _MEMORY_FACADE.store(
                text,
                user_id=self._MEMORY_USER,
                metadata={"source": "brain", "memory_type": memory_type},
            )
        except Exception as exc:
            logger.debug("[MemoryManager] facade mirror failed: %s", exc)


memory_manager = MemoryManager()
