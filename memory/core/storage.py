"""Compatibility exports for the legacy ``memory.core.storage`` path."""
from memory.fact_store import FactStore, get_fact_store
try:
    from memory.episodic_store import EpisodicStore
    from memory.semantic_store import SemanticStore
    from memory.task_store import TaskStore
    from memory.decision_store import DecisionStore
except ModuleNotFoundError:
    EpisodicStore = SemanticStore = TaskStore = DecisionStore = None

__all__ = ["FactStore", "get_fact_store", "EpisodicStore", "SemanticStore", "TaskStore", "DecisionStore"]
