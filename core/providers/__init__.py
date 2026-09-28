"""Providers — capability-addressed execution backends.

Real modules: base (contract classes), registry (ProviderRegistry),
router (ProviderRouter), memory (ProviderMemory). The orchestration and
adapter subpackages own their own exports.
"""
from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)
from core.providers.registry import (
    ProviderRegistry,
    get_provider_registry,
    provider_registry,
)
from core.providers.router import ProviderRouter, provider_router
from core.providers.memory import (
    EvidenceRecord,
    ProviderMemory,
    provider_memory,
)

__all__ = [
    "ExecutionProvider",
    "ExecutionResult",
    "ProviderCapabilities",
    "ProviderHealth",
    "ProviderHealthStatus",
    "ProviderRegistry",
    "provider_registry",
    "get_provider_registry",
    "ProviderRouter",
    "provider_router",
    "ProviderMemory",
    "EvidenceRecord",
    "provider_memory",
]
