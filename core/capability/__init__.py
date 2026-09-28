"""Capability — capability-addressed execution layer."""
from core.capability.models import (
    Capability,
    CapabilityNode,
    Subgraph,
    _BUILTIN_CAPABILITIES,
    BUILTIN_CAPABILITY_IDS,
)
from core.capability.registry import CapabilityRegistry, capability_registry
from core.capability.graph import CapabilityGraph, capability_graph
from core.capability.negotiation import (
    CandidateScore,
    CapabilityNegotiator,
    NegotiationResult,
    capability_negotiator,
)
from core.capability.composition import (
    CompositionEngine,
    CompositionPlan,
    CompositionStep,
    composition_engine,
)

__all__ = [
    "Capability",
    "CapabilityNode",
    "Subgraph",
    "_BUILTIN_CAPABILITIES",
    "BUILTIN_CAPABILITY_IDS",
    "CapabilityRegistry",
    "capability_registry",
    "CapabilityGraph",
    "capability_graph",
    "CandidateScore",
    "CapabilityNegotiator",
    "NegotiationResult",
    "capability_negotiator",
    "CompositionEngine",
    "CompositionPlan",
    "CompositionStep",
    "composition_engine",
    "CapabilityAI",
    "CapabilityGap",
    "CapabilityHealth",
    "CapabilityRegistry",
    "CapabilityStatus",
    "CapabilityType",
    "RiskTier",
    "TrustTier",
    "AcquisitionCandidate",
    "AcquisitionStage",
    "new_capability_registry",
]


def __getattr__(name: str):
    # Lazy imports keep the pipeline-light modules import-cheap.
    lazy = {
        "CapabilityAI": ("core.capability.capability_ai", "CapabilityAI"),
        "CapabilityGap": ("core.capability.capability_ai", "CapabilityGap"),
        "CapabilityHealth": ("tools.base_tool", "CapabilityHealth"),
        "CapabilityStatus": ("tools.base_tool", "CapabilityStatus"),
        "CapabilityType": ("tools.base_tool", "CapabilityType"),
        "RiskTier": ("tools.base_tool", "RiskTier"),
        "TrustTier": ("core.capability.capability_ai", "TrustTier"),
        "AcquisitionCandidate": ("core.capability.capability_ai", "AcquisitionCandidate"),
        "AcquisitionStage": ("core.capability.capability_ai", "AcquisitionStage"),
        "new_capability_registry": ("tools.registry", "new_capability_registry"),
    }
    if name in lazy:
        module_name, attr = lazy[name]
        import importlib
        module = importlib.import_module(module_name)
        return getattr(module, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
