from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class WorkerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DRAINING = "draining"


@dataclass(frozen=True)
class CapabilityDescriptor:
    id: str
    name: str | None = None
    version: str = "1.0"


@dataclass(frozen=True)
class ExecutionAffinity:
    tenant_id: str | None = None
    capability: str | None = None
    worker_id: str | None = None


@dataclass(frozen=True)
class VersionCheck:
    compatible: bool
    reason: str | None = None


@dataclass
class WorkerRequest:
    runtime_context: Any = None
    request: Any = None
    pipeline_version: str = "1.0"
    runtime_spec_version: str = "1.0"
    worker_protocol_version: str = "1.0"


@dataclass
class WorkerResponse:
    outcome: Any = None
    observations: tuple[Any, ...] = field(default_factory=tuple)
    metrics: Any = None
    error: str | None = None
