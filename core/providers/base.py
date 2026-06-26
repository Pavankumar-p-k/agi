from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class ProviderHealthStatus(Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class ProviderHealth:
    status: ProviderHealthStatus = ProviderHealthStatus.UNKNOWN
    latency_ms: float = 0.0
    error: str = ""
    last_checked: float = 0.0


@dataclass
class ProviderCapabilities:
    capability_names: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    success: bool = False
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    exit_code: int = 0
    artifacts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionProvider(ABC):
    provider_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    priority: int = 100
    installed: bool = True
    _enabled: bool = True

    def __init__(self):
        self._health_cache: ProviderHealth = ProviderHealth()
        self._last_health_check: float = 0.0
        self._health_ttl: float = 10.0

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        ...

    @abstractmethod
    async def health(self) -> ProviderHealth:
        ...

    @abstractmethod
    async def execute(self, task: dict[str, Any], context: dict[str, Any] | None = None) -> ExecutionResult:
        ...

    async def stream(self, task: dict[str, Any], context: dict[str, Any] | None = None) -> AsyncIterator[str]:
        yield ""
        raise NotImplementedError(f"{self.provider_id} does not support streaming")

    async def cancel(self, execution_id: str) -> bool:
        return False

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 0.0

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities().capability_names

    async def diagnostics(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "enabled": self._enabled}

    @property
    def enabled(self) -> bool:
        return self._enabled and self.installed

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    async def cached_health(self) -> ProviderHealth:
        now = time.time()
        if now - self._last_health_check > self._health_ttl:
            try:
                self._health_cache = await self.health()
            except Exception as e:
                self._health_cache = ProviderHealth(
                    status=ProviderHealthStatus.DOWN,
                    error=str(e),
                    last_checked=now,
                )
            self._last_health_check = now
        return self._health_cache

    def available(self) -> bool:
        if not self._enabled or not self.installed:
            return False
        return self._health_cache.status in (
            ProviderHealthStatus.HEALTHY,
            ProviderHealthStatus.DEGRADED,
            ProviderHealthStatus.UNKNOWN,
        )
