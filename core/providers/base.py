"""ExecutionProvider base models and abstract class.

Completed from the committed contract in tests/unit/test_provider_ecosystem.py:

- ProviderCapabilities: capability_names / languages / frameworks lists
- ProviderHealthStatus: HEALTHY / DEGRADED / DOWN / UNKNOWN
- ProviderHealth: status, latency_ms, error
- ExecutionResult: success, output, error, duration_ms (+ cost, tokens, meta)
- ExecutionProvider (ABC): identity attrs, enable/disable lifecycle,
  supports(), available() from health cache, async execute(), and default
  stream/cancel/estimate_cost/estimate_latency/diagnostics hooks.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)


class ProviderHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass
class ProviderCapabilities:
    capability_names: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)  # SDK manifest features

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_names": list(self.capability_names),
            "languages": list(self.languages),
            "frameworks": list(self.frameworks),
        }


@dataclass
class ProviderHealth:
    status: ProviderHealthStatus = ProviderHealthStatus.UNKNOWN
    latency_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value if isinstance(self.status, ProviderHealthStatus) else str(self.status),
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


@dataclass
class ExecutionResult:
    success: bool = False
    output: str = ""
    error: Optional[str] = None
    duration_ms: float = 0.0
    cost: float = 0.0
    tokens_used: int = 0
    exit_code: Optional[int] = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "cost": self.cost,
            "tokens_used": self.tokens_used,
            "exit_code": self.exit_code,
            "artifacts": dict(self.artifacts),
            "metadata": dict(self.metadata),
        }


class ExecutionProvider(ABC):
    """Abstract base for every JARVIS execution provider (connector adapter).

    A provider is the concrete "how" behind a capability: forge (internal),
    claude_code / codex (external CLIs), browser/automation/email/github
    adapters, and so on.  Identity is declarative; execution is async.
    """

    provider_id: str = ""
    name: str = ""
    version: str = "1.0"
    priority: int = 100          # lower = more important
    installed: bool = False
    _enabled: bool = True

    def __init__(self) -> None:
        self._health_cache: ProviderHealth = ProviderHealth()
        self._health_checked_at: float = 0.0

    # -- lifecycle -------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled and self.installed

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    # -- capability contract ---------------------------------------------

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Declare what this provider can do."""
        ...

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities().capability_names

    # -- health ------------------------------------------------------------

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Probe live health (implementations should cache via _cache_health)."""
        ...

    def _cache_health(self, health: ProviderHealth) -> ProviderHealth:
        self._health_cache = health
        self._health_checked_at = time.time()
        return health

    def available(self) -> bool:
        """Enabled AND last known health not DOWN."""
        if not self.enabled:
            return False
        return self._health_cache.status != ProviderHealthStatus.DOWN

    # -- execution -----------------------------------------------------------

    @abstractmethod
    async def execute(self, task: dict[str, Any], context: Optional[dict[str, Any]] = None) -> ExecutionResult:
        """Execute a task dict; returns an honest ExecutionResult."""
        ...

    async def stream(self, task: dict[str, Any], context: Optional[dict[str, Any]] = None) -> AsyncIterator[str]:
        """Default streaming: yield empty header then raise (contract)."""
        yield ""
        raise NotImplementedError(f"{self.provider_id} does not support streaming")

    async def cancel(self, execution_id: str) -> bool:
        return False

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 0.0

    async def diagnostics(self) -> dict[str, Any]:
        health = self._health_cache
        return {
            "provider_id": self.provider_id,
            "name": self.name,
            "version": self.version,
            "installed": self.installed,
            "enabled": self.enabled,
            "health": health.to_dict(),
            "capabilities": self.capabilities().to_dict(),
        }
