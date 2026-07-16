from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext

if TYPE_CHECKING:
    from core.capability.registry import CapabilityRegistry

logger = logging.getLogger(__name__)


# Risk-level mapping for capability filtering per policy profile.
# Higher-index profiles allow higher-risk capabilities.
_PROFILE_RISK_ORDER: dict[str, int] = {
    "strict": 0,
    "developer": 1,
    "autonomous": 2,
}


class CapabilitySelectionStage(PipelineStage):
    def __init__(self, capability_registry: CapabilityRegistry | None = None) -> None:
        if capability_registry is not None:
            self._registry = capability_registry
        else:
            from core.capability.registry import capability_registry as _default_registry
            self._registry = _default_registry

    @property
    def name(self) -> str:
        return "capability_selection"

    async def execute(self, context: PipelineContext) -> StageResult:
        plan = context.plan
        if plan is None:
            context.selected_capabilities = {}
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        steps = plan.get("steps", [])
        bindings: dict[int, list[Any]] = {}

        profile_risk = _PROFILE_RISK_ORDER.get(context.policy_profile, 1)

        for i, step in enumerate(steps):
            intent = step.get("intent", "")
            capabilities = self._registry.resolve_intent(intent)
            if capabilities:
                filtered = _filter_by_profile(capabilities, profile_risk)
                if filtered:
                    bindings[i] = filtered

        context.selected_capabilities = bindings
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


def _filter_by_profile(
    capabilities: list[Any], profile_risk: int
) -> list[Any]:
    """Filter capabilities by their risk level relative to the active profile.

    Capabilities with a ``risk`` attribute are filtered: only those
    whose risk index <= profile_risk are returned.  Capabilities without
    a ``risk`` attribute are always included (backward compat).
    """
    risk_order = ["low", "medium", "high", "critical"]
    result: list[Any] = []
    for cap in capabilities:
        risk = None
        if hasattr(cap, "risk"):
            risk = cap.risk
        elif isinstance(cap, dict):
            risk = cap.get("risk")
        if risk is None:
            result.append(cap)
        else:
            risk_str = str(risk).lower()
            cap_risk_idx = risk_order.index(risk_str) if risk_str in risk_order else 1
            if cap_risk_idx <= profile_risk:
                result.append(cap)
    return result
