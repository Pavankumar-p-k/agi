# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import time
from typing import Any, Callable, Optional


class CapabilityType(str, Enum):
    TOOL = "tool"
    SPECIALIST_ACTION = "specialist"
    CLI = "cli"
    SERVICE = "service"
    COMPOSITE = "composite"


class CapabilityHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class CapabilityStatus(str, Enum):
    AVAILABLE = "available"
    SANDBOXED = "sandboxed"
    PENDING_APPROVAL = "pending_approval"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class VerificationSpec:
    method: str = "standard"
    criteria: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReliabilityMetrics:
    total_invocations: int = 0
    successful_invocations: int = 0
    consecutive_failures: int = 0
    last_failure_reason: Optional[str] = None
    last_success_timestamp: Optional[float] = None

    @property
    def score(self) -> float:
        if self.total_invocations == 0:
            return 1.0
        return round(self.successful_invocations / self.total_invocations, 3)

    def record_success(self) -> None:
        self.total_invocations += 1
        self.successful_invocations += 1
        self.consecutive_failures = 0
        self.last_success_timestamp = time.time()

    def record_failure(self, reason: str | None = None) -> None:
        self.total_invocations += 1
        self.consecutive_failures += 1
        self.last_failure_reason = reason or "Execution failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_invocations": self.total_invocations,
            "successful_invocations": self.successful_invocations,
            "consecutive_failures": self.consecutive_failures,
            "last_failure_reason": self.last_failure_reason,
            "last_success_timestamp": self.last_success_timestamp,
            "reliability_score": self.score,
        }


@dataclass
class ToolResult:
    output: str = ""
    error: str | None = None
    retryable: bool = False

    def is_ok(self) -> bool:
        return self.error is None


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: str = "general"
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: Callable | None = None
    read_only: bool = False
    risk_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    permission: str | None = None
    capabilities: list[str] = field(default_factory=list)
    examples: list[dict] | None = None

    def to_capability_definition(self, owner_module: str = "Core") -> CapabilityDefinition:
        risk = RiskTier.LOW if self.read_only else (
            RiskTier.HIGH if any(t in self.risk_tags for t in ("destructive", "execute", "shell", "delete")) else RiskTier.MEDIUM
        )
        return CapabilityDefinition(
            name=self.name,
            type=CapabilityType.TOOL,
            owner_module=owner_module,
            description=self.description,
            inputs=dict(self.input_schema),
            outputs={},
            requirements=[],
            dependencies=[],
            risk=risk,
            risk_tags=list(self.risk_tags),
            required_scopes=[self.permission] if self.permission else [],
            verification=VerificationSpec(method="tool_return_ok"),
            health=CapabilityHealth.HEALTHY,
            reliability=ReliabilityMetrics(),
            version="1.0.0",
            source="builtin",
            status=CapabilityStatus.AVAILABLE,
            handler=self.handler,
            metadata=dict(self.metadata),
        )


@dataclass
class CapabilityDefinition:
    # 1. Identity & Classification
    name: str
    type: CapabilityType = CapabilityType.TOOL
    owner_module: str = "Core"
    version: str = "1.0.0"
    source: str = "builtin"

    # 2. Functional Interface
    description: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    handler: Callable | None = None

    # 3. Prerequisites & Environment
    requirements: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    # 4. Governance & Safety
    risk: RiskTier = RiskTier.LOW
    risk_tags: list[str] = field(default_factory=list)
    required_scopes: list[str] = field(default_factory=list)

    # 5. Operational Health & Reliability
    status: CapabilityStatus = CapabilityStatus.AVAILABLE
    health: CapabilityHealth = CapabilityHealth.UNKNOWN
    health_check: Callable[[], bool] | None = None
    reliability: ReliabilityMetrics = field(default_factory=ReliabilityMetrics)
    verification: VerificationSpec = field(default_factory=VerificationSpec)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_tool_definition(self) -> ToolDefinition:
        read_only = (self.risk == RiskTier.LOW)
        permission = self.required_scopes[0] if self.required_scopes else None
        return ToolDefinition(
            name=self.name,
            description=self.description,
            category=self.owner_module.lower().replace(" ", "_"),
            input_schema=dict(self.inputs),
            handler=self.handler,
            read_only=read_only,
            risk_tags=list(self.risk_tags),
            metadata={
                **dict(self.metadata),
                "capability_type": self.type.value,
                "version": self.version,
                "source": self.source,
                "health": self.health.value,
                "reliability_score": self.reliability.score,
                "requirements": list(self.requirements),
                "dependencies": list(self.dependencies),
            },
            permission=permission,
            capabilities=[self.name],
        )

    @classmethod
    def from_tool_definition(cls, tool: ToolDefinition, owner_module: str = "Core") -> CapabilityDefinition:
        return tool.to_capability_definition(owner_module=owner_module)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "owner_module": self.owner_module,
            "description": self.description,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "requirements": self.requirements,
            "dependencies": self.dependencies,
            "risk": self.risk.value,
            "risk_tags": self.risk_tags,
            "required_scopes": self.required_scopes,
            "status": self.status.value,
            "health": self.health.value,
            "reliability": self.reliability.to_dict(),
            "verification": self.verification.to_dict(),
            "version": self.version,
            "source": self.source,
            "metadata": self.metadata,
        }
