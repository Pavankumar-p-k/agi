"""Long-term memory data models."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ExperienceSummary:
    """Condensed record of a completed (or failed) past activity."""

    activity_id: str
    goal: str = ""
    domain: str = ""
    status: str = ""
    node_count: int = 0
    success: bool = False
    tools_used: List[str] = field(default_factory=list)
    duration_seconds: Optional[float] = None
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_days(self) -> float:
        if self.duration_seconds:
            return float(self.duration_seconds) / 86400.0
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.timestamp is not None:
            data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperienceSummary":
        data = dict(data)
        ts = data.get("timestamp")
        if isinstance(ts, str):
            try:
                data["timestamp"] = datetime.fromisoformat(ts)
            except ValueError:
                data["timestamp"] = None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class KnowledgeItem:
    """A durable, synthesised piece of knowledge."""

    knowledge_id: str
    category: str = ""
    claim: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.5
    domain: str = ""
    evidence_count: int = 0
    source: str = ""
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.created_at is not None:
            data["created_at"] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeItem":
        data = dict(data)
        ts = data.get("created_at")
        if isinstance(ts, str):
            try:
                data["created_at"] = datetime.fromisoformat(ts)
            except ValueError:
                data["created_at"] = None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class KnowledgeQuery:
    """A query against the knowledge store."""

    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    text: str = ""
    limit: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
