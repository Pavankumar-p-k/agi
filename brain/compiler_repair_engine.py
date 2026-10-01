"""CompilerRepairEngine — turns javac diagnostics into source repairs.

Currently handles the ``type_mismatch`` category by delegating to
``StructuralTransformationEngine`` (structural expression rewrites, not casts).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from brain.structural_transformer import StructuralTransformationEngine

logger = logging.getLogger(__name__)


@dataclass
class JavacError:
    """One parsed javac diagnostic."""

    file: str = ""
    line: int = 0
    category: str = ""
    symbol: str = ""
    message: str = ""
    column: int = 0
    code: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def location(self) -> str:
        return f"{self.file}:{self.line}"

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "category": self.category,
            "symbol": self.symbol,
            "message": self.message,
            "code": self.code,
        }


class CompilerRepairEngine:
    """Applies targeted repairs for compiler errors within a project root."""

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = project_root
        self.transformer = StructuralTransformationEngine()

    # ── routing ──────────────────────────────────────────────────────
    def repair(self, error: JavacError,
               project_root: Optional[str] = None) -> bool:
        category = str(getattr(error, "category", "") or "")
        if category == "type_mismatch":
            return self._fix_type_mismatch(error, project_root or self.project_root)
        logger.debug("[repair] no repair for category %r", category)
        return False

    # ── fixes ────────────────────────────────────────────────────────
    def _fix_type_mismatch(self, error: JavacError,
                           project_root: Optional[str] = None) -> bool:
        return self.transformer.fix_type_mismatch(
            error, project_root or self.project_root)

    def get_stats(self) -> dict:
        return self.transformer.get_stats()


compiler_repair_engine = CompilerRepairEngine()


__all__ = ["CompilerRepairEngine", "JavacError", "compiler_repair_engine"]
