"""Structural generalization data models."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class _StrEnum(str, Enum):
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value == value:
                    return member
        return None


class PropertySource(_StrEnum):
    STATIC = "static"
    DERIVED = "derived"
    INFERRED = "inferred"


class PropertyValueType(_StrEnum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STR = "str"


class SystemType(_StrEnum):
    TOOL = "tool"
    AGENT = "agent"
    SERVICE = "service"
    WORKFLOW = "workflow"


class PrincipleStatus(_StrEnum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProposalStatus(_StrEnum):
    GENERATED = "generated"
    APPROVED = "approved"
    EXPERIMENTING = "experimenting"
    PROMOTED = "promoted"
    REJECTED = "rejected"


class CausalStatus(_StrEnum):
    LIKELY_CAUSAL = "likely_causal"
    LIKELY_CONFOUNDED = "likely_confounded"
    INSUFFICIENT_DATA = "insufficient_data"


def _enum_value(value):
    return getattr(value, "value", value)


@dataclass
class StructuralProperty:
    property_id: str
    name: str
    category: str = ""
    value_type: PropertyValueType = PropertyValueType.BOOL
    source: PropertySource = PropertySource.STATIC
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property_id": self.property_id,
            "name": self.name,
            "category": self.category,
            "value_type": _enum_value(self.value_type),
            "source": _enum_value(self.source),
            "description": self.description,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StructuralProperty":
        return cls(
            property_id=data.get("property_id", ""),
            name=data.get("name", ""),
            category=data.get("category", ""),
            value_type=PropertyValueType(data.get("value_type", "bool")),
            source=PropertySource(data.get("source", "static")),
            description=data.get("description", ""),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class SystemProfile:
    system_id: str
    system_type: SystemType = SystemType.TOOL
    properties: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: Any = None) -> Any:
        return self.properties.get(name, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_id": self.system_id,
            "system_type": _enum_value(self.system_type),
            "properties": dict(self.properties),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemProfile":
        return cls(
            system_id=data.get("system_id", ""),
            system_type=SystemType(data.get("system_type", "tool")),
            properties=dict(data.get("properties", {}) or {}),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class PrincipleDataPoint:
    point_id: str
    system_id: str
    system_type: SystemType = SystemType.TOOL
    success: bool = False
    properties: Dict[str, Any] = field(default_factory=dict)
    domain: str = ""
    session_id: str = ""
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.point_id,
            "system_id": self.system_id,
            "system_type": _enum_value(self.system_type),
            "success": self.success,
            "properties": dict(self.properties),
            "domain": self.domain,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PrincipleDataPoint":
        created = data.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except ValueError:
                created = None
        return cls(
            point_id=data.get("point_id", ""),
            system_id=data.get("system_id", ""),
            system_type=SystemType(data.get("system_type", "tool")),
            success=bool(data.get("success", False)),
            properties=dict(data.get("properties", {}) or {}),
            domain=data.get("domain", ""),
            session_id=data.get("session_id", ""),
            created_at=created,
        )


@dataclass
class PrincipleCandidate:
    principle_id: str
    property_name: str
    category: str = ""
    support_rate: float = 0.0
    control_rate: float = 0.0
    discrimination: float = 0.0
    sample_size: int = 0
    support_count: int = 0
    control_count: int = 0
    domains: List[str] = field(default_factory=list)
    confidence: float = 0.0
    status: PrincipleStatus = PrincipleStatus.CANDIDATE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "principle_id": self.principle_id,
            "property_name": self.property_name,
            "category": self.category,
            "support_rate": self.support_rate,
            "control_rate": self.control_rate,
            "discrimination": self.discrimination,
            "sample_size": self.sample_size,
            "support_count": self.support_count,
            "control_count": self.control_count,
            "domains": list(self.domains),
            "confidence": self.confidence,
            "status": _enum_value(self.status),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PrincipleCandidate":
        return cls(
            principle_id=data.get("principle_id", ""),
            property_name=data.get("property_name", ""),
            category=data.get("category", ""),
            support_rate=float(data.get("support_rate", 0.0)),
            control_rate=float(data.get("control_rate", 0.0)),
            discrimination=float(data.get("discrimination", 0.0)),
            sample_size=int(data.get("sample_size", 0)),
            support_count=int(data.get("support_count", 0)),
            control_count=int(data.get("control_count", 0)),
            domains=list(data.get("domains", []) or []),
            confidence=float(data.get("confidence", 0.0)),
            status=PrincipleStatus(data.get("status", "candidate")),
        )


@dataclass
class Principle:
    principle_id: str
    property_name: str
    category: str = ""
    support_rate: float = 0.0
    control_rate: float = 0.0
    discrimination: float = 0.0
    sample_size: int = 0
    support_count: int = 0
    control_count: int = 0
    domains: List[str] = field(default_factory=list)
    confidence: float = 0.0
    status: PrincipleStatus = PrincipleStatus.CANDIDATE
    evidence_point_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "principle_id": self.principle_id,
            "property_name": self.property_name,
            "category": self.category,
            "support_rate": self.support_rate,
            "control_rate": self.control_rate,
            "discrimination": self.discrimination,
            "sample_size": self.sample_size,
            "support_count": self.support_count,
            "control_count": self.control_count,
            "domains": list(self.domains),
            "confidence": self.confidence,
            "status": _enum_value(self.status),
            "evidence_point_ids": list(self.evidence_point_ids),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Principle":
        return cls(
            principle_id=data.get("principle_id", ""),
            property_name=data.get("property_name", ""),
            category=data.get("category", ""),
            support_rate=float(data.get("support_rate", 0.0)),
            control_rate=float(data.get("control_rate", 0.0)),
            discrimination=float(data.get("discrimination", 0.0)),
            sample_size=int(data.get("sample_size", 0)),
            support_count=int(data.get("support_count", 0)),
            control_count=int(data.get("control_count", 0)),
            domains=list(data.get("domains", []) or []),
            confidence=float(data.get("confidence", 0.0)),
            status=PrincipleStatus(data.get("status", "candidate")),
            evidence_point_ids=list(data.get("evidence_point_ids", []) or []),
        )


@dataclass
class ImprovementProposal:
    proposal_id: str
    target_system: str
    proposal_type: str
    principle_id: str
    title: str
    rationale: str
    expected_improvement: float = 0.0
    confidence: float = 0.0
    status: ProposalStatus = ProposalStatus.GENERATED
    experiment_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "target_system": self.target_system,
            "proposal_type": self.proposal_type,
            "principle_id": self.principle_id,
            "title": self.title,
            "rationale": self.rationale,
            "expected_improvement": self.expected_improvement,
            "confidence": self.confidence,
            "status": _enum_value(self.status),
            "experiment_id": self.experiment_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImprovementProposal":
        return cls(
            proposal_id=data.get("proposal_id", ""),
            target_system=data.get("target_system", ""),
            proposal_type=data.get("proposal_type", ""),
            principle_id=data.get("principle_id", ""),
            title=data.get("title", ""),
            rationale=data.get("rationale", ""),
            expected_improvement=float(data.get("expected_improvement", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            status=ProposalStatus(data.get("status", "generated")),
            experiment_id=data.get("experiment_id", ""),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class CausalAnalysis:
    property_name: str
    raw_discrimination: float = 0.0
    adjusted_discrimination: float = 0.0
    confounders_checked: List[str] = field(default_factory=list)
    confounded_by: List[str] = field(default_factory=list)
    status: CausalStatus = CausalStatus.INSUFFICIENT_DATA
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property_name": self.property_name,
            "raw_discrimination": self.raw_discrimination,
            "adjusted_discrimination": self.adjusted_discrimination,
            "confounders_checked": list(self.confounders_checked),
            "confounded_by": list(self.confounded_by),
            "status": _enum_value(self.status),
            "confidence": self.confidence,
        }
