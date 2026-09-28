"""KnowledgeResult — output of the knowledge stage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KnowledgeResult:
    knowledge_id: str = ""
    activity_id: str = ""
    entities: tuple = ()
    facts: tuple = ()
    edges: tuple = ()
    node_count: int = 0
    edge_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
