import logging
from typing import Any, Optional, Dict
from importlib import import_module


def _optional_import(module_path: str, symbol: str):
    try:
        module = import_module(module_path, package=__name__)
        return getattr(module, symbol)
    except (ImportError, AttributeError):
        return None


from .execution_context import BrainExecutionContext
from .reasoning_engine import ReasoningEngine
from .cognitive_patterns import PATTERNS
from .UnifiedBrain import UnifiedBrain

logger = logging.getLogger(__name__)
