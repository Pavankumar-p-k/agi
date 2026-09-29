"""PipelineContext — shared mutable state passed through pipeline stages.

Canonical context for ADR-006/007/009. Carries request identity plus all
typed stage fields (ownership map: core.pipeline.base.STAGE_OWNERSHIP).

Two construction styles are supported:
  PipelineContext(request_id="r1", transport="test", raw_input="...", ...)
  PipelineContext()                      # bare — fields default
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PipelineContext:
    # Request identity
    request_id: str = ""
    transport: str = "unknown"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    raw_input: str = ""
    attachments: list = field(default_factory=list)
    messages: list = field(default_factory=list)

    # Generic buckets
    metadata: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)

    # Typed stage fields (schema snapshot contract)
    parsed_request: Optional[dict] = None
    classification: Optional[dict] = None
    authentication_result: Any = None
    authorization_result: Any = None
    resource_access_result: Any = None
    resource_grant: Any = None
    rate_limit_result: Any = None
    resource_scope: Any = None
    tenant_id: Optional[str] = None
    tenant_resolution_result: Any = None
    retrieved_context: Any = None
    knowledge_result: Any = None
    reasoning_assessment: Optional[dict] = None
    reasoning_result: Any = None
    plan: Any = None
    plan_validated: Optional[bool] = None
    planner_result: Any = None
    selected_capabilities: Any = None
    execution_state: str = "pending"
    execution_result: Any = None
    verification_result: Any = None
    epistemic_tags: Any = None
    memory_refs: Any = None
    store_decision: Any = None
    activity_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_stack: list = field(default_factory=list)
    reflection_result: Any = None
    learning_result: Any = None
    policy_result: Any = None
    notification_result: Any = None
    explainability_result: Any = None
    formatted_response: Optional[dict] = None
    error: Optional[str] = None
    pipeline_version: str = "1.0"

    # Runtime outcome (trace validation)
    outcome: Any = None
    # Injectable deterministic primitives (ids/time)
    services: Any = None
    # Architecture metrics snapshot (populated by ArchitectureMetrics)
    architecture_metrics: Any = None
    # Identity snapshot (authentication/authorization stages)
    identity: Any = None

    @property
    def security(self) -> Any:
        """Aggregated security snapshot (tenant + scope), always current."""
        from core.pipeline.security_context import SecurityContext
        return SecurityContext(
            identity=self.identity,
            authentication=self.authentication_result,
            authorization=self.authorization_result,
            resource_scope=self.resource_scope,
            resource_access=self.resource_access_result,
            resource_grant=self.resource_grant,
            tenant_resolution=self.tenant_resolution_result,
        )

    # ── dict-like helpers ────────────────────────────────────────────────
    def get(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, getattr(self, key, default))

    def set(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def set_stage_field(self, stage: str, field_name: str, value: Any) -> None:
        """Set a context field with stage-ownership validation (ADR-006)."""
        from core.pipeline.base import STAGE_OWNERSHIP as _OWN
        owned = _OWN.get(stage)
        common = {"metadata", "error", "metrics", "messages", "attachments"}
        if owned is not None and field_name not in owned and field_name not in common:
            raise ValueError(f"stage '{stage}' does not own field '{field_name}'")
        setattr(self, field_name, value)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for f in self.__dataclass_fields__:
            v = getattr(self, f)
            if v is not None and f != "services":
                d[f] = v
        return d


__all__ = ["PipelineContext"]
