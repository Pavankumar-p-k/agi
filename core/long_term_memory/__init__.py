"""Long-Term Memory & Knowledge Consolidation.

Phase 9 — Converts activity history into durable knowledge that
influences planner, research, and coding decisions.

Four-layer condensation:
  1000 Activities → 100 Experiences → 50 KnowledgeItems → 10 Principles
"""

from core.long_term_memory.adapter import BehaviorAdapter
from core.long_term_memory.consolidator import Consolidator
from core.long_term_memory.extractor import ExperienceExtractor
from core.long_term_memory.models import (
    ExperienceSummary,
    KnowledgeItem,
    KnowledgeQuery,
)
from core.long_term_memory.store import KnowledgeStore
from core.long_term_memory.synthesizer import KnowledgeSynthesizer

__all__ = [
    "KnowledgeItem",
    "KnowledgeQuery",
    "ExperienceSummary",
    "KnowledgeStore",
    "ExperienceExtractor",
    "KnowledgeSynthesizer",
    "BehaviorAdapter",
    "Consolidator",
]
