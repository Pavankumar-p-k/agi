"""ExecutionProvider — capability-addressed execution backend contract.

These classes are the stable provider contract used by the pipeline
Execution stage, the capability negotiator, and provider_sdk adapters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ProviderHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ProviderHealth:
    status: ProviderHealthStatus = ProviderHealthStatus.UNKNOWN
    detail: str = ""
    latency_ms: Optional[float] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ProviderCapabilities:
    capability_names: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    features: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def has(self, capability: str) -> bool:
        return capability in self.capability_names


@dataclass
class ExecutionResult:
    success: bool = False
    output: str = ""
    error: str = ""
    exit_code: Optional[int] = None
    tokens: int = 0
    provider_id: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "tokens": self.tokens,
            "provider_id": self.provider_id,
            "metadata": dict(self.metadata),
        }


class ExecutionProvider:
    """Base class for execution providers.

    Subclasses declare ``provider_id``, ``name``, ``version`` and implement
    ``capabilities()``, ``health()`` and ``execute()``.
    """

    provider_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    priority: int = 50
    installed: bool = True
    _enabled: bool = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(capability_names=[])

    async def health(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderHealthStatus.UNKNOWN)

    async def execute(self, task: dict, context: Any = None) -> ExecutionResult:
        raise NotImplementedError

    # ── lifecycle helpers ────────────────────────────────────────────
    def is_enabled(self) -> bool:
        return bool(self._enabled)

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "name": self.name,
            "version": self.version,
            "priority": self.priority,
            "installed": self.installed,
            "enabled": self._enabled,
            "capabilities": list(self.capabilities().capability_names),
        }


__all__ = [
    "ExecutionProvider",
    "ExecutionResult",
    "ProviderCapabilities",
    "ProviderHealth",
    "ProviderHealthStatus",
]
