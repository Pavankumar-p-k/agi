"""Phase 14.0 — Structural Property Registry & Principle Models.

Data model for generalizing across experimental evidence:
  StructuralProperty → SystemProfile → PrincipleCandidate → Principle
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PropertyValueType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    ENUM = "enum"


class PropertySource(str, Enum):
    STATIC = "static"      # declared by developer
    DERIVED = "derived"    # computed from ActivityGraph / runtime data


class SystemType(str, Enum):
    TOOL = "tool"
    AGENT = "agent"
    WORKFLOW = "workflow"
    STRATEGY = "strategy"


class PrincipleStatus(str, Enum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProposalStatus(str, Enum):
    GENERATED = "generated"
    APPROVED = "approved"
    EXPERIMENTING = "experimenting"
    PROMOTED = "promoted"
    REJECTED = "rejected"


class CausalStatus(str, Enum):
    LIKELY_CAUSAL = "likely_causal"
    LIKELY_CONFOUNDED = "likely_confounded"
    INSUFFICIENT_DATA = "insufficient_data"


# ── Core models ──────────────────────────────────────────────────


@dataclass
class StructuralProperty:
    """Defines a measurable structural property of a system component."""

    property_id: str
    name: str
    category: str              # execution_model, memory, verification, reasoning, collaboration
    value_type: PropertyValueType
    source: PropertySource
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "property_id": self.property_id,
            "name": self.name,
            "category": self.category,
            "value_type": self.value_type.value,
            "source": self.source.value,
            "description": self.description,
        }


@dataclass
class SystemProfile:
    """Architectural description of a system component (tool, agent, workflow, strategy)."""

    system_id: str
    system_type: SystemType
    properties: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: Any = None) -> Any:
        return self.properties.get(name, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_id": self.system_id,
            "system_type": self.system_type.value,
            "properties": dict(self.properties),
        }


@dataclass
class PrincipleDataPoint:
    """A single experimental data point feeding principle discovery.

    Each data point links a system profile (properties) to an outcome (success).
    """

    point_id: str
    system_id: str
    system_type: SystemType
    success: bool
    properties: dict[str, Any]
    domain: str = ""
    session_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "system_id": self.system_id,
            "system_type": self.system_type.value,
            "success": self.success,
            "properties": dict(self.properties),
            "domain": self.domain,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PrincipleCandidate:
    """A candidate principle discovered by correlating properties with outcomes.

    A candidate must pass the Validator before becoming an accepted Principle.
    """

    principle_id: str
    property_name: str
    category: str

    support_rate: float    # P(success | property=True)
    control_rate: float    # P(success | property=False)
    discrimination: float  # support_rate - control_rate

    sample_size: int       # total experiments across both groups
    support_count: int     # N with property=True
    control_count: int     # N with property=False
    domains: list[str] = field(default_factory=list)
    confidence: float = 0.0

    status: PrincipleStatus = PrincipleStatus.CANDIDATE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "principle_id": self.principle_id,
            "property_name": self.property_name,
            "category": self.category,
            "support_rate": round(self.support_rate, 3),
            "control_rate": round(self.control_rate, 3),
            "discrimination": round(self.discrimination, 3),
            "sample_size": self.sample_size,
            "support_count": self.support_count,
            "control_count": self.control_count,
            "domains": list(self.domains),
            "confidence": round(self.confidence, 3),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Principle:
    """An accepted principle that has passed validation.

    This is the durable record of a generalization.
    """

    principle_id: str
    property_name: str
    category: str

    support_rate: float
    control_rate: float
    discrimination: float

    sample_size: int
    support_count: int
    control_count: int
    domains: list[str]
    confidence: float

    status: PrincipleStatus = PrincipleStatus.ACCEPTED
    accepted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    evidence_point_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "principle_id": self.principle_id,
            "property_name": self.property_name,
            "category": self.category,
            "support_rate": round(self.support_rate, 3),
            "control_rate": round(self.control_rate, 3),
            "discrimination": round(self.discrimination, 3),
            "sample_size": self.sample_size,
            "support_count": self.support_count,
            "control_count": self.control_count,
            "domains": list(self.domains),
            "confidence": round(self.confidence, 3),
            "status": self.status.value,
            "accepted_at": self.accepted_at.isoformat(),
            "evidence_point_ids": list(self.evidence_point_ids),
        }


# ── Phase 14.3 — Causal models ────────────────────────────────────


@dataclass
class CausalAnalysis:
    """Result of confounder-controlled analysis for a candidate principle.

    Answers: "Is the observed discrimination causal, or is it driven
    by a hidden confounder?"

    Checks each other boolean property: if controlling for it collapses
    the discrimination, that property is a likely confounder.
    """

    property_name: str
    raw_discrimination: float
    adjusted_discrimination: float
    confounders_checked: list[str]
    confounded_by: list[str]
    status: CausalStatus
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "property_name": self.property_name,
            "raw_discrimination": round(self.raw_discrimination, 3),
            "adjusted_discrimination": round(self.adjusted_discrimination, 3),
            "confounders_checked": list(self.confounders_checked),
            "confounded_by": list(self.confounded_by),
            "status": self.status.value,
            "confidence": round(self.confidence, 3),
        }


# ── Phase 14.1 — Proposal models ─────────────────────────────────


@dataclass
class ImprovementProposal:
    """A proposal for an architectural improvement derived from an accepted Principle.

    A proposal is not a recommendation — it is an executable, measurable,
    traceable object. It answers: "What should we change?"

    Knowledge is evidence. A proposal is action.
    """

    proposal_id: str
    target_system: str
    proposal_type: str
    principle_id: str
    title: str
    rationale: str
    expected_improvement: float
    confidence: float
    status: ProposalStatus = ProposalStatus.GENERATED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "target_system": self.target_system,
            "proposal_type": self.proposal_type,
            "principle_id": self.principle_id,
            "title": self.title,
            "rationale": self.rationale,
            "expected_improvement": round(self.expected_improvement, 3),
            "confidence": round(self.confidence, 3),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
        }
