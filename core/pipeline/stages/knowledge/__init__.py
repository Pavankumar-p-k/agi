"""Knowledge stage — canonical knowledge graph entry point.

Wraps the existing ``core/research/`` KnowledgeGraph and GraphStore
engines behind a pipeline-compatible adapter.  Contains almost no
business logic — all graph operations live in the wrapped engines.
"""
from __future__ import annotations

from core.pipeline.stages.knowledge.stage import KnowledgeStage

__all__ = [
    "KnowledgeStage",
]
