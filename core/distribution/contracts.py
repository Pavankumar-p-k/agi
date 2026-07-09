from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Literal

from core.identity.resource_scope import ResourceScope
from core.pipeline.messages import Request
from core.pipeline.observation import Observation
from core.pipeline.outcome import Outcome
from core.pipeline.architecture_metrics import ArchitectureMetrics
from core.runtime import RuntimeContext


class WorkerStatus(Enum):
    ONLINE = auto()
    DEGRADED = auto()
    OFFLINE = auto()


class HealthStatus(Enum):
    HEALTHY = auto()
    DEGRADED = auto()
    UNHEALTHY = auto()


@dataclass(frozen=True)
class VersionCheck:
    compatible: bool
    reason: str | None = None


@dataclass(frozen=True)
class CapabilityDescriptor:
    id: str
    name: str
    version: str = "1.0"
    metadata: dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


@dataclass(frozen=True)
class ExecutionAffinity:
    tenant_id: str
    preferred_worker: str | None = None
    locality: Literal["local", "same_host", "remote", "any"] = "any"
    gpu_required: bool = False


@dataclass(frozen=True)
class WorkerRequest:
    runtime_context: RuntimeContext
    request: Request
    pipeline_version: str
    runtime_spec_version: str
    worker_protocol_version: str
    signature: str | None = None
    nonce: str = ""
    issued_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_context": {
                "identity": str(self.runtime_context.identity),
                "authentication": str(self.runtime_context.authentication),
                "authorization": str(self.runtime_context.authorization),
                "tenant": str(self.runtime_context.tenant),
                "resource_scope": self.runtime_context.resource_scope.to_dict() if self.runtime_context.resource_scope else None,
                "resource_grant": str(self.runtime_context.resource_grant),
                "activity_id": self.runtime_context.activity_id,
                "request_id": self.runtime_context.request_id,
            },
            "request": {
                "text": self.request.text,
                "transport": self.request.transport,
                "user_id": self.request.user_id,
                "session_id": self.request.session_id,
                "agent_type": self.request.agent_type,
                "metadata": self.request.metadata,
            },
            "pipeline_version": self.pipeline_version,
            "runtime_spec_version": self.runtime_spec_version,
            "worker_protocol_version": self.worker_protocol_version,
            "signature": self.signature,
            "nonce": self.nonce,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkerRequest:
        from core.identity.models import IdentityContext
        from core.identity.resource_scope import ResourceScope
        from core.identity.tenant_resolver import TenantResolutionResult
        from core.pipeline.authentication_result import AuthenticationResult
        from core.pipeline.authorization_result import AuthorizationResult
        from core.pipeline.resource_grant import ResourceGrant

        rc_data = data["runtime_context"]
        scope = None
        if rc_data.get("resource_scope"):
            scope = ResourceScope.from_dict(rc_data["resource_scope"])  # type: ignore[arg-type]

        ctx = RuntimeContext(
            identity=IdentityContext.__new__(IdentityContext),
            authentication=AuthenticationResult.__new__(AuthenticationResult),
            authorization=AuthorizationResult.__new__(AuthorizationResult),
            tenant=TenantResolutionResult.__new__(TenantResolutionResult),
            resource_scope=scope,
            resource_grant=ResourceGrant.__new__(ResourceGrant),
            activity_id=rc_data["activity_id"],
            request_id=rc_data["request_id"],
        )
        req_data = data["request"]
        req = Request(
            text=req_data.get("text", ""),
            transport=req_data.get("transport", "distribution"),
            user_id=req_data.get("user_id"),
            session_id=req_data.get("session_id"),
            agent_type=req_data.get("agent_type"),
            metadata=req_data.get("metadata", {}),
        )
        issued = None
        if data.get("issued_at"):
            issued = datetime.fromisoformat(data["issued_at"])
        return cls(
            runtime_context=ctx,
            request=req,
            pipeline_version=data["pipeline_version"],
            runtime_spec_version=data["runtime_spec_version"],
            worker_protocol_version=data["worker_protocol_version"],
            signature=data.get("signature"),
            nonce=data.get("nonce", ""),
            issued_at=issued,
        )


@dataclass(frozen=True)
class WorkerResponse:
    outcome: Outcome
    observations: tuple[Observation, ...]
    metrics: ArchitectureMetrics
