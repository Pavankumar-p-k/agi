from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from core.providers.base import ExecutionProvider
from core.providers.orchestration.models import (
    ChainType, ProviderStep, StepDependency, OrchestrationPlan,
)
from core.providers.registry import provider_registry
from core.providers.router import provider_router

logger = logging.getLogger(__name__)

# ── Pattern definitions: goal text → required sub-tasks ────────────────────
_SUB_TASK_PATTERNS: dict[str, list[tuple[str, str, ChainType, list[str]]]] = {
    "generate": [
        ("coding", "Generate code", ChainType.SEQUENTIAL, []),
    ],
    "review": [
        ("coding", "Generate code", ChainType.SEQUENTIAL, []),
        ("review", "Security review", ChainType.VERIFY, ["generate"]),
    ],
    "refactor": [
        ("coding", "Refactor code", ChainType.SEQUENTIAL, []),
        ("testing", "Run tests", ChainType.VERIFY, ["refactor"]),
    ],
    "debug": [
        ("debugging", "Debug issue", ChainType.SEQUENTIAL, []),
        ("testing", "Verify fix", ChainType.VERIFY, ["debug"]),
    ],
    "document": [
        ("documentation", "Write documentation", ChainType.SEQUENTIAL, []),
    ],
    "test": [
        ("coding", "Write code", ChainType.SEQUENTIAL, []),
        ("testing", "Write tests", ChainType.PARALLEL, []),
    ],
    "secure": [
        ("coding", "Write code", ChainType.SEQUENTIAL, []),
        ("security", "Security audit", ChainType.VERIFY, ["coding"]),
    ],
    "full": [
        ("coding", "Write code", ChainType.SEQUENTIAL, []),
        ("security", "Security review", ChainType.VERIFY, ["coding"]),
        ("testing", "Write tests", ChainType.PARALLEL, ["coding"]),
        ("documentation", "Document code", ChainType.PARALLEL, ["coding"]),
        ("review", "Final review", ChainType.VERIFY, ["testing", "security"]),
    ],
    "research": [
        ("research", "Research topic", ChainType.SEQUENTIAL, []),
        ("coding", "Implement findings", ChainType.PIPELINE, ["research"]),
    ],
    "build": [
        ("coding", "Generate code", ChainType.SEQUENTIAL, []),
        ("review", "Review code", ChainType.VERIFY, ["coding"]),
        ("testing", "Test build", ChainType.VERIFY, ["review"]),
    ],
}

_GOAL_KEYWORDS: list[tuple[list[str], str]] = [
    (["full stack", "fullstack", "complete", "full workflow"], "full"),
    (["security", "secure", "vulnerability"], "secure"),
    (["review", "audit", "inspect"], "review"),
    (["refactor", "clean", "improve code"], "refactor"),
    (["debug", "fix", "bug", "error", "crash"], "debug"),
    (["document", "docstring", "readme"], "document"),
    (["test", "unit test", "pytest"], "test"),
    (["research", "investigate", "find"], "research"),
    (["build", "compile", "package"], "build"),
]


def _detect_pattern(goal: str) -> str:
    goal_lower = goal.lower()
    best_pattern = "generate"
    best_priority = -1

    for keywords, pattern in _GOAL_KEYWORDS:
        for kw in keywords:
            if kw in goal_lower:
                priority = len(keywords) + goal_lower.count(kw)
                if priority > best_priority:
                    best_priority = priority
                    best_pattern = pattern

    return best_pattern


def _make_step_id(prefix: str, seen: set[str]) -> str:
    base = prefix.lower().replace(" ", "_")
    sid = base
    n = 1
    while sid in seen:
        n += 1
        sid = f"{base}_{n}"
    seen.add(sid)
    return sid


class OrchestrationPlanner:
    """Analyzes a goal and produces an OrchestrationPlan.

    The planner detects what sub-tasks are needed based on goal keywords,
    assigns providers using the router, and determines the appropriate
    chain type (sequential, parallel, pipeline, verify) for each step.
    """

    def __init__(
        self,
        router=provider_router,
        registry=provider_registry,
    ):
        self._router = router
        self._registry = registry

    def plan(self, goal: str, context: dict[str, Any] | None = None) -> OrchestrationPlan:
        """Produce an orchestration plan for the given goal."""

        pattern = _detect_pattern(goal)
        sub_tasks = _SUB_TASK_PATTERNS.get(pattern, _SUB_TASK_PATTERNS["generate"])

        steps: list[ProviderStep] = []
        seen_ids: set[str] = set()
        assigned: dict[str, str] = {}  # step_id → provider_id
        capability_to_step: dict[str, str] = {}  # capability → first step_id with that capability
        label_to_step: dict[str, str] = {}  # label (lowercase, no spaces) → step_id

        for capability, label, chain_type, depends_on in sub_tasks:
            step_id = _make_step_id(label, seen_ids)
            task = self._build_task(goal, capability, label, context)

            # Resolve providers for this capability
            provider = self._select_provider(capability, task)
            provider_id = provider.provider_id if provider else "forge"
            assigned[step_id] = provider_id

            # Build a mapping: capability → step_id (first step wins)
            if capability not in capability_to_step:
                capability_to_step[capability] = step_id
            label_key = label.lower().replace(" ", "_")
            if label_key not in label_to_step:
                label_to_step[label_key] = step_id

            # Resolve dependency references: depends_on entries can be capability names,
            # label keys, or step aliases from the pattern definitions
            def _resolve_dep(dep: str) -> str | None:
                # Direct step_id match
                if dep in seen_ids:
                    return dep
                # Capability name → step_id
                if dep in capability_to_step:
                    return capability_to_step[dep]
                # Label key → step_id
                dep_key = dep.lower().replace(" ", "_")
                if dep_key in label_to_step:
                    return label_to_step[dep_key]
                # Alias: map common aliases to their capability
                _ALIAS_MAP = {
                    "generate": "coding",
                    "refactor": "coding",
                    "debug": "debugging",
                    "coding": "coding",
                }
                resolved_cap = _ALIAS_MAP.get(dep, dep)
                if resolved_cap in capability_to_step:
                    return capability_to_step[resolved_cap]
                return None

            dependencies = []
            for dep in depends_on:
                resolved = _resolve_dep(dep)
                if resolved:
                    dependencies.append(StepDependency(step_id=resolved))

            step = ProviderStep(
                step_id=step_id,
                chain_type=chain_type,
                label=label,
                task=task,
                provider_id=provider_id,
                dependencies=dependencies,
                expected_artifact_keys=task.get("expected_artifacts", []),
            )
            steps.append(step)

        return OrchestrationPlan(
            goal=goal,
            steps=steps,
            context=context or {},
        )

    def _build_task(
        self, goal: str, capability: str, label: str, context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        task: dict[str, Any] = {
            "goal": goal,
            "capability": capability,
            "label": label,
            "mode": "generate",
        }
        if context:
            task["context"] = context

        # Copy language/framework from context
        if context:
            for key in ("language", "framework", "project_dir"):
                if key in context:
                    task[key] = context[key]

        # Expected artifacts per step type
        if capability == "coding":
            task["expected_artifacts"] = ["source_code"]
        elif capability == "testing":
            task["expected_artifacts"] = ["test_code", "test_report"]
            task["mode"] = "test"
        elif capability == "documentation":
            task["expected_artifacts"] = ["documentation"]
            task["mode"] = "document"
        elif capability == "security":
            task["expected_artifacts"] = ["security_report"]
            task["mode"] = "audit"
        elif capability == "review":
            task["expected_artifacts"] = ["review_report"]
            task["mode"] = "review"
        elif capability == "debugging":
            task["expected_artifacts"] = ["fixed_code"]
            task["mode"] = "debug"

        return task

    def _select_provider(self, capability: str, task: dict[str, Any]) -> ExecutionProvider | None:
        return self._router.select(capability, task)

    def plan_and_summarize(self, goal: str) -> str:
        plan = self.plan(goal)
        return plan.summary()
