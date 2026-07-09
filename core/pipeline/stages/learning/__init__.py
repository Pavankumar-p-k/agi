"""Learning stage — canonical post-reflection learning.

Consumes ``ReflectionResult`` and produces ``LearningRecord`` for the
Memory stage to persist.  Integrates the legacy
``brain/learning_engine.py`` and ``memory/decision_memory.py`` paths.
"""
from __future__ import annotations

from core.pipeline.stages.learning.stage import LearningStage

__all__ = [
    "LearningStage",
]
