"""Standard contract and base interface for Specialist AI modules.

Specialist modules (Desktop AI, Coding AI, etc.) execute actions in bounded
domains and verify outcomes. They export their capabilities to the authoritative
CapabilityRegistry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from tools.base_tool import CapabilityDefinition, CapabilityHealth, ReliabilityMetrics


@dataclass
class SpecialistResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    verified: bool = False
    verification_reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "verified": self.verified,
            "verification_reason": self.verification_reason,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class SpecialistModule(ABC):
    """Abstract base class for all JARVIS Specialist AI modules."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the specialist module (e.g. 'Desktop AI', 'Coding AI')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of the specialist domain and boundary."""
        ...

    @abstractmethod
    def get_capabilities(self) -> list[CapabilityDefinition]:
        """Return the authoritative list of capabilities exported by this specialist."""
        ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Probe the live health of this specialist module."""
        ...

    @abstractmethod
    def execute_capability(
        self,
        capability_name: str,
        params: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> SpecialistResult:
        """Execute a capability belonging to this specialist."""
        ...

    @abstractmethod
    def verify(self, capability_name: str, result: SpecialistResult) -> tuple[bool, str]:
        """Verify the deterministic outcome of a capability execution."""
        ...
