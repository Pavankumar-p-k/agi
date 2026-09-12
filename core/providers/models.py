"""ExecutionResult / provider models for JARVIS v3 providers.

This adapter module predates ``core.providers.base``; it re-exports the
canonical dataclasses so older importers keep working.
"""
from __future__ import annotations

from core.providers.base import (
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

__all__ = [
    "ExecutionResult",
    "ProviderCapabilities",
    "ProviderHealth",
    "ProviderHealthStatus",
]
