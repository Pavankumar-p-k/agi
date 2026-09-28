"""ArchitectureMetrics — per-request architecture snapshot (Sprint 5.5D)."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Optional


def _runtime_version_dict() -> dict:
    from core.runtime_version import RUNTIME_VERSION
    return RUNTIME_VERSION.to_dict()


@dataclass
class ArchitectureMetrics:
    reasoning_complexity: str = "unknown"
    plan_steps: int = 0
    selected_capabilities: int = 0
    observations: int = 0
    verifiers: int = 0
    memory_operations: int = 0
    activity_depth: int = 0
    retries: int = 0
    execution_state: str = "pending"
    pipeline_version: str = "1.0"
    tenant_id: str = ""
    workspace_id: str = ""
    runtime_version: dict = field(default_factory=_runtime_version_dict)

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def to_snapshot_dict(self) -> dict:
        return self.to_dict()

    @classmethod
    def from_context(cls, ctx: Any) -> "ArchitectureMetrics":
        """Derive the metrics snapshot from a (post-execution) context."""
        plan = getattr(ctx, "plan", None)
        steps = plan.get("steps", []) if isinstance(plan, dict) else []
        sel = getattr(ctx, "selected_capabilities", None)
        sel_count = (
            len(sel) if isinstance(sel, dict)
            else (len(sel) if isinstance(sel, (list, tuple)) else 0)
        )
        outcome = getattr(ctx, "outcome", None)
        obs = list(getattr(outcome, "observations", []) or []) if outcome else []
        verif = getattr(ctx, "verification_result", None) or {}
        verdicts = verif.get("verdicts", []) if isinstance(verif, dict) else []
        mem = getattr(ctx, "store_decision", None)
        rr = getattr(ctx, "reasoning_result", None)
        # Tenant/workspace: from resource_scope (Rule 30), falling back to
        # the explicit context fields.
        scope = getattr(ctx, "resource_scope", None)
        tenant = getattr(ctx, "tenant_id", None) or getattr(scope, "tenant_id", "") or ""
        workspace = getattr(scope, "workspace_id", None) or ""

        try:
            from core.pipeline.deterministic import DeterministicServices  # noqa: F401
        except Exception:  # pragma: no cover
            pass

        m = cls(
            reasoning_complexity=str(getattr(rr, "complexity", "") or "unknown"),
            plan_steps=len(steps),
            selected_capabilities=sel_count,
            observations=len(obs),
            verifiers=len(verdicts),
            memory_operations=1 if mem is not None else 0,
            retries=int(getattr(ctx, "metrics", {}).get("_retries", 0)),
            execution_state=str(getattr(ctx, "execution_state", "pending")),
            pipeline_version=str(getattr(ctx, "pipeline_version", "1.0")),
            tenant_id=str(tenant),
            workspace_id=str(workspace),
        )
        return m


__all__ = ["ArchitectureMetrics"]
