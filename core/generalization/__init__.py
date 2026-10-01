"""Structural generalization package."""
from __future__ import annotations

from core.generalization.causal import CausalFilter
from core.generalization.derived import DerivedPropertyExtractor
from core.generalization.executor import ProposalExecutor
from core.generalization.extractor import PrincipleExtractor
from core.generalization.models import (
    CausalAnalysis,
    CausalStatus,
    ImprovementProposal,
    Principle,
    PrincipleCandidate,
    PrincipleDataPoint,
    PrincipleStatus,
    PropertySource,
    PropertyValueType,
    ProposalStatus,
    StructuralProperty,
    SystemProfile,
    SystemType,
)
from core.generalization.prioritizer import ProposalPrioritizer
from core.generalization.proposals import ProposalEngine
from core.generalization.registry import StructuralPropertyRegistry
from core.generalization.store import PrincipleStore
from core.generalization.validator import PrincipleValidator

__all__ = [
    "CausalAnalysis",
    "CausalFilter",
    "CausalStatus",
    "DerivedPropertyExtractor",
    "ImprovementProposal",
    "Principle",
    "PrincipleCandidate",
    "PrincipleDataPoint",
    "PrincipleExtractor",
    "PrincipleStatus",
    "PrincipleStore",
    "PrincipleValidator",
    "ProposalEngine",
    "ProposalExecutor",
    "ProposalPrioritizer",
    "ProposalStatus",
    "PropertySource",
    "PropertyValueType",
    "StructuralProperty",
    "StructuralPropertyRegistry",
    "SystemProfile",
    "SystemType",
]
