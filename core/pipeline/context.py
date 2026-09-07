"""Pipeline execution context."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.identity.models import AuthenticationState, IdentityContext


@dataclass
class PipelineContext:
    request_id: str = ""
    transport: str = ""
    raw_input: Any = None
    classification: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    identity: IdentityContext | None = None
    authentication_result: Any = None
    authorization_result: Any = None
    services: Any = None
    state: dict[str, Any] = field(default_factory=dict)
    pipeline_version: str = "1.0"
    activity_id: str = ""
    execution_state: str = "pending"

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})
        self.state = dict(self.state or {})
        self.classification = dict(self.classification or {})
        if self.identity is None:
            self.identity = IdentityContext(authentication_state=AuthenticationState.ANONYMOUS)
