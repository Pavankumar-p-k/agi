"""Authoritative Capability Registry module for JARVIS.

This module re-exports the unified registry from tools.registry and
tools.base_tool per ADR-013 (single source of truth).
"""
from __future__ import annotations

from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    ReliabilityMetrics,
    RiskTier,
    ToolDefinition,
    ToolResult,
    VerificationSpec,
)
from tools.registry import (
    CapabilityRegistry,
    ToolRegistry,
    get_capability,
    get_tool,
    new_capability_registry,
    new_registry,
    _ensure_registry,
)

# Compatibility exports
def capability_registry(*args, **kwargs) -> CapabilityRegistry:
    return _ensure_registry()

async def async_capability_registry(*args, **kwargs) -> CapabilityRegistry:
    return _ensure_registry()

__all__ = [
    "CapabilityDefinition",
    "CapabilityHealth",
    "CapabilityStatus",
    "CapabilityType",
    "ReliabilityMetrics",
    "RiskTier",
    "ToolDefinition",
    "ToolResult",
    "VerificationSpec",
    "CapabilityRegistry",
    "ToolRegistry",
    "get_capability",
    "get_tool",
    "new_capability_registry",
    "new_registry",
    "capability_registry",
    "async_capability_registry",
]
