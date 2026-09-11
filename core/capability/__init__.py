"""
Module: core.capability.__init__
Capability subsystem re-exports.
"""
from __future__ import annotations
from typing import Any
import logging

logger = logging.getLogger(__name__)

from core.capability.registry import (
    CapabilityRegistry,
    ToolRegistry,
    capability_registry,
    async_capability_registry,
    new_capability_registry,
    get_capability,
    get_tool,
)
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
from core.capability.discovery import CapabilityDiscoveryService
from core.capability.selection import CapabilitySelector, CapabilityRecommendation, CapabilityGap
from core.capability.acquisition import (
    CapabilityAcquisitionPipeline,
    AcquisitionCandidate,
    QuarantineAudit,
    TrustTier,
    AcquisitionStage,
)
from core.capability.experience import CapabilityExperienceStore, CapabilityExperienceEntry
from core.capability.capability_ai import CapabilityAI

# Compatibility stubs for legacy models
from core.capability.models import Capability, _BUILTIN_CAPABILITIES
from core.capability.graph import CapabilityGraph, CapabilityNode, capability_graph
from core.capability.negotiation import CapabilityNegotiator, NegotiationResult, capability_negotiator
from core.capability.composition import CompositionEngine, CompositionPlan, CompositionStep, composition_engine

__all__ = [
    "CapabilityRegistry",
    "ToolRegistry",
    "capability_registry",
    "async_capability_registry",
    "new_capability_registry",
    "get_capability",
    "get_tool",
    "CapabilityDefinition",
    "CapabilityHealth",
    "CapabilityStatus",
    "CapabilityType",
    "ReliabilityMetrics",
    "RiskTier",
    "ToolDefinition",
    "ToolResult",
    "VerificationSpec",
    "CapabilityDiscoveryService",
    "CapabilitySelector",
    "CapabilityRecommendation",
    "CapabilityGap",
    "CapabilityAcquisitionPipeline",
    "AcquisitionCandidate",
    "QuarantineAudit",
    "TrustTier",
    "AcquisitionStage",
    "CapabilityExperienceStore",
    "CapabilityExperienceEntry",
    "CapabilityAI",
    "Capability",
    "_BUILTIN_CAPABILITIES",
    "CapabilityGraph",
    "CapabilityNode",
    "capability_graph",
    "CapabilityNegotiator",
    "NegotiationResult",
    "capability_negotiator",
    "CompositionEngine",
    "CompositionPlan",
    "CompositionStep",
    "composition_engine",
]
