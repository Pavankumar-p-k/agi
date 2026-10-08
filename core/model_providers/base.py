"""core.model_providers.base — shared contract for all model providers.

Rebuilt from the committed contracts:

- tests/unit/test_docker_readiness.py      (OllamaProvider._base_url env order)
- tests/unit/test_phase5_reliability.py    (provider.embeddings() / .complete())
- tests/architecture/test_phase5_hybrid_router.py (router.health_check shape)
- jarvis-export/cli/cli_commands.py        (doctor "Model Provider Health" table:
                                            router.health_check() -> {name: status}
                                            with .available / .healthy / .latency_ms)

ProviderStatus is the health object doctor reads attributes off. ModelResult is
the plain result envelope returned by OllamaProvider.complete().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ProviderState(str, Enum):
    """Coarse lifecycle state for a model provider."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    DISABLED = "disabled"


@dataclass
class ProviderStatus:
    """Health snapshot doctor's table renders (doctor reads .available,
    .healthy, .latency_ms)."""

    provider: str = ""
    available: bool = False
    healthy: bool = False
    latency_ms: float = 0.0
    models: list[str] = field(default_factory=list)
    error: str = ""
    state: ProviderState = ProviderState.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "available": self.available,
            "healthy": self.healthy,
            "latency_ms": self.latency_ms,
            "models": list(self.models),
            "error": self.error,
            "state": self.state.value,
        }


@dataclass
class ModelResult:
    """Plain result envelope for a single completion."""

    success: bool
    text: str = ""
    model: str = ""
    error: str = ""
    tokens_used: int = 0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelProvider:
    """Base class for all model providers.

    Subclasses set `provider_id` and implement `health()` plus at least one of
    `complete()` / `embeddings()`. Base defaults exist so partial providers can
    be constructed and probed by the router's health_check().
    """

    provider_id: str = "base"
    local: bool = False

    def __init__(self, base_url: str = "", model: str = "", **kwargs: Any) -> None:
        self.base_url = base_url
        self.model = model
        for key, value in kwargs.items():
            setattr(self, key, value)

    def health(self) -> ProviderStatus:
        """Default health snapshot: unknown. Subclasses override."""
        return ProviderStatus(provider=self.provider_id)

    def complete(self, prompt: str, *, system: str = "", temperature: float = 0.1,
                 max_tokens: Optional[int] = None, model: str = "",
                 **kwargs: Any) -> ModelResult:
        raise NotImplementedError(f"{type(self).__name__}.complete not implemented")

    def embeddings(self, model: str, inputs: list[str]) -> list[list[float]]:
        raise NotImplementedError(f"{type(self).__name__}.embeddings not implemented")

    @property
    def name(self) -> str:
        return self.provider_id

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} provider={self.provider_id!r} local={self.local}>"


__all__ = ["ModelProvider", "ModelResult", "ProviderState", "ProviderStatus"]
