"""Orchestration planner: goal → ordered multi-provider plan.

Completed from the committed contract in tests/unit/test_orchestration.py
(_detect_pattern / _SUB_TASK_PATTERNS / OrchestrationPlanner) and the
feedback-integration contract in tests/unit/test_provider_feedback.py
(decision ids recorded into step tasks via the existing ProviderRouter).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.providers.orchestration.models import (
    ChainType,
    OrchestrationPlan,
    ProviderStep,
    StepDependency,
)

logger = logging.getLogger(__name__)

# Ordered pattern table: first matching substring wins.
_SUB_TASK_PATTERNS: list[tuple[str, list[str]]] = [
    ("research", ["research", "investigate", "analyze", "explore"]),
    ("secure", ["secure", "security", "audit", "vulnerability"]),
    ("refactor", ["refactor", "restructure", "clean up"]),
    ("debug", ["debug", "fix", "bug", "error", "broken"]),
    ("document", ["document", "docs", "readme", "documentation"]),
    ("test", ["test", "unit tests", "coverage"]),
    ("review", ["review", "critique", "inspect"]),
    ("full", ["full stack", "full-stack", "end to end", "complete app", "whole app"]),
    ("build", ["build", "compile", "construct"]),
]

# Chain templates per pattern.  Each entry: (chain_type, label, capability).
_CHAIN_TEMPLATES: dict[str, list[tuple[ChainType, str, str]]] = {
    "generate": [(ChainType.SEQUENTIAL, "generate", "coding")],
    "review": [
        (ChainType.SEQUENTIAL, "generate", "coding"),
        (ChainType.VERIFY, "review", "review"),
    ],
    "secure": [
        (ChainType.SEQUENTIAL, "generate", "coding"),
        (ChainType.VERIFY, "security review", "security"),
    ],
    "refactor": [
        (ChainType.SEQUENTIAL, "refactor", "coding"),
        (ChainType.VERIFY, "test", "testing"),
    ],
    "debug": [
        (ChainType.SEQUENTIAL, "diagnose", "coding"),
        (ChainType.VERIFY, "test", "testing"),
    ],
    "full": [
        (ChainType.SEQUENTIAL, "implement", "coding"),
        (ChainType.VERIFY, "security review", "security"),
        (ChainType.PARALLEL, "test", "testing"),
        (ChainType.PARALLEL, "document", "documentation"),
        (ChainType.VERIFY, "review", "review"),
    ],
    "research": [
        (ChainType.SEQUENTIAL, "research", "research"),
        (ChainType.PIPELINE, "implement", "coding"),
    ],
    "build": [
        (ChainType.SEQUENTIAL, "generate", "coding"),
        (ChainType.VERIFY, "build", "testing"),
    ],
    "document": [
        (ChainType.SEQUENTIAL, "generate", "coding"),
        (ChainType.SEQUENTIAL, "document", "documentation"),
    ],
    "test": [
        (ChainType.SEQUENTIAL, "generate", "coding"),
        (ChainType.VERIFY, "test", "testing"),
    ],
}

_STEP_LABEL_PREFIX: dict[str, str] = {
    "generate": "sequential",
    "review": "verify",
    "implement": "sequential",
    "refactor": "sequential",
    "diagnose": "sequential",
    "test": "verify",
    "security review": "verify",
    "build": "verify",
    "document": "parallel",
    "research": "sequential",
}


def _detect_pattern(goal: str) -> str:
    """Detect the workflow pattern from a free-form goal (default 'generate')."""
    text = str(goal or "").lower()
    for pattern, keywords in _SUB_TASK_PATTERNS:
        for keyword in keywords:
            if keyword in text:
                return pattern
    return "generate"


class OrchestrationPlanner:
    """Builds an OrchestrationPlan for a goal using the existing router."""

    def __init__(self, router: Any = None) -> None:
        self._router = router

    def _get_router(self) -> Any:
        if self._router is not None:
            return self._router
        try:
            from core.providers.router import ProviderRouter
            self._router = ProviderRouter()
        except Exception as exc:
            logger.debug("[orchestration_planner] router unavailable: %s", exc)
            self._router = False  # sentinel: known-unavailable
        return self._router or None

    def _select_provider(
        self,
        capability: str,
        task: dict[str, Any],
        step: ProviderStep,
        used: dict[str, int],
    ) -> str:
        """Pick a provider for the step (router-backed, count-balanced fallback)."""
        router = self._get_router()
        if router is not None:
            try:
                provider = router.select(capability, dict(task), record_decision=True)
            except Exception as exc:
                logger.debug("[orchestration_planner] router select failed: %s", exc)
                provider = None
            if provider is not None:
                task["_decision_id"] = getattr(router, "last_decision_id", "") or ""
                return str(provider.provider_id)

        # Deterministic fallback spread over the known internal providers.
        registry = None
        try:
            from core.providers.registry import provider_registry
            registry = provider_registry
        except Exception:
            pass
        candidates: list[str] = []
        if registry is not None:
            try:
                candidates = [
                    p.provider_id
                    for p in registry.get_providers_for_capability(capability)
                    if p.enabled
                ] or [p.provider_id for p in registry.list_enabled()]
            except Exception:
                candidates = []
        if not candidates:
            return "forge"
        candidates.sort()
        chosen = min(candidates, key=lambda pid: (used.get(pid, 0), pid))
        used[chosen] = used.get(chosen, 0) + 1
        return chosen

    def plan(
        self,
        goal: str,
        context: Optional[dict[str, Any]] = None,
    ) -> OrchestrationPlan:
        plan = OrchestrationPlan(goal=str(goal or ""), context=dict(context or {}))
        pattern = _detect_pattern(goal)
        template = _CHAIN_TEMPLATES.get(pattern, _CHAIN_TEMPLATES["generate"])

        used_provider_counts: dict[str, int] = {}
        produced_step_ids: list[str] = []
        for index, (chain_type, label, capability) in enumerate(template):
            task: dict[str, Any] = {
                "goal": str(goal or ""),
                "capability": capability,
                "pattern": pattern,
            }
            if context:
                task.update(context)
            step = ProviderStep(
                step_id=f"step{index + 1}",
                task=task,
                chain_type=chain_type,
                label=f"{chain_type.value}:{label}",
            )
            # Verification/parallel stages depend on everything produced so far
            # (generation → verify/test/document/review ordering).
            if chain_type in (ChainType.VERIFY, ChainType.PARALLEL, ChainType.CONSENSUS):
                step.dependencies = [
                    StepDependency(step_id=dep_id) for dep_id in produced_step_ids
                ]
            step.provider_id = self._select_provider(
                capability, step.task, step, used_provider_counts
            )
            plan.add_step(step)
            produced_step_ids.append(step.step_id)
        return plan

    def plan_and_summarize(self, goal: str, context: Optional[dict[str, Any]] = None) -> str:
        plan = self.plan(goal, context=context)
        return plan.summary()
