"""Resource and visibility scope models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_TENANT_ID = "default"
SYSTEM_TENANT_ID = "SYSTEM_TENANT_ID"


@dataclass
class ResourceScope:
    tenant_id: str = DEFAULT_TENANT_ID
    resource_id: str = ""
    permissions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.permissions = list(self.permissions or [])
        self.metadata = dict(self.metadata or {})


@dataclass(frozen=True)
class Visibility:
    value: str = "private"

    def __str__(self) -> str:
        return self.value
