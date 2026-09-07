"""Tenant resolution helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TenantResolutionResult:
    tenant_id: str = "default"
    resolved: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})


class TenantResolver:
    def resolve(self, tenant_id: str | None = None, **kwargs: Any) -> TenantResolutionResult:
        resolved_id = tenant_id or "default"
        return TenantResolutionResult(tenant_id=resolved_id, metadata=dict(kwargs))


class DefaultTenantResolver(TenantResolver):
    def resolve(self, tenant_id: str | None = None, **kwargs: Any) -> TenantResolutionResult:
        return super().resolve(tenant_id or "default", **kwargs)
