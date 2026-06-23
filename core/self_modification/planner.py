"""Self-Modification Engine (Phase 18.0) — Patch Planner.

Maps an ImprovementProposal (from Phase 14.1 or Phase 17) to a concrete
ModificationPlan with a predefined recipe and target.

The planner is a pure function — no side effects, no I/O.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.self_modification.models import (
    ModificationPlan,
    ModificationRecipe,
    ModificationTarget,
)
from core.self_modification.recipes import get_recipe, get_registered_recipes

logger = logging.getLogger(__name__)

# ── Proposal-to-Recipe Mapping ────────────────────────────────────────
# Heuristic rules that map proposal types/targets to recipes.
# These are deterministic — no LLM dependency.

_PROPOSAL_TYPE_TO_RECIPE: dict[str, ModificationRecipe] = {
    "add_retry": ModificationRecipe.ADD_RETRY_LOOP,
    "retry_capable": ModificationRecipe.ADD_RETRY_LOOP,
    "improve_reliability": ModificationRecipe.ADD_RETRY_LOOP,
    "make_retryable": ModificationRecipe.ADD_RETRY_LOOP,
    "add_retry_loop": ModificationRecipe.ADD_RETRY_LOOP,
    "add_verification": ModificationRecipe.ADD_VERIFICATION_STEP,
    "verify_output": ModificationRecipe.ADD_VERIFICATION_STEP,
    "verification_builtin": ModificationRecipe.ADD_VERIFICATION_STEP,
    "increase_timeout": ModificationRecipe.INCREASE_TIMEOUT,
    "longer_timeout": ModificationRecipe.INCREASE_TIMEOUT,
    "timeout": ModificationRecipe.INCREASE_TIMEOUT,
    "enable_failure_memory": ModificationRecipe.ENABLE_FAILURE_MEMORY,
    "failure_memory": ModificationRecipe.ENABLE_FAILURE_MEMORY,
    "has_failure_memory": ModificationRecipe.ENABLE_FAILURE_MEMORY,
    "add_calibration": ModificationRecipe.ADD_CALIBRATION_HOOK,
    "calibration_hook": ModificationRecipe.ADD_CALIBRATION_HOOK,
    "calibrate": ModificationRecipe.ADD_CALIBRATION_HOOK,
    "promote_property": ModificationRecipe.PROMOTE_PROPERTY,
    "set_property": ModificationRecipe.PROMOTE_PROPERTY,
}

# Recipe → supported target systems (canonical name or tool name prefix)
_RECIPE_TARGET_MAP: dict[ModificationRecipe, list[str]] = {
    ModificationRecipe.ADD_RETRY_LOOP: [
        "browser_automation", "browser_navigate", "browser_click",
        "browser_fill", "build_project",
    ],
    ModificationRecipe.ADD_VERIFICATION_STEP: [
        "browser_automation", "browser_snapshot", "browser_screenshot",
        "research_url", "extract_facts",
    ],
    ModificationRecipe.INCREASE_TIMEOUT: [
        "browser_automation", "build_project", "research_infrastructure",
    ],
    ModificationRecipe.ENABLE_FAILURE_MEMORY: [
        "browser_automation", "automated_build", "execution_infrastructure",
    ],
    ModificationRecipe.ADD_CALIBRATION_HOOK: [
        "strateg", "strategy_predictor", "strategy_evaluator",
        "outcome_predictor", "principle_extractor",
    ],
    ModificationRecipe.PROMOTE_PROPERTY: [
        "automated_build", "browser_automation", "build_benchmark",
        "opportunity_discovery", "self_modification",
    ],
}

# Known file paths for target systems (for planner resolution)
_SYSTEM_FILE_MAP: dict[str, dict[str, Any]] = {
    "browser_automation": {
        "file": "core/tools/browser_tools.py",
        "functions": [
            "_hdl_browser_navigate", "_hdl_browser_click", "_hdl_browser_fill",
            "_hdl_browser_snapshot", "_hdl_browser_screenshot",
        ],
    },
    "automated_build": {
        "file": "core/tools/automated_build.py",
        "functions": ["do_automated_build", "_build_project"],
    },
    "build_project": {
        "file": "core/tools/execution.py",
        "functions": ["_hdl_build_project"],
    },
    "strategic_reasoning": {
        "file": "core/strategy/predictor.py",
        "functions": ["predict_outcome"],
    },
    "strategy_predictor": {
        "file": "core/strategy/predictor.py",
        "functions": ["predict_outcome"],
    },
    "strategy_evaluator": {
        "file": "core/strategy/evaluator.py",
        "functions": ["evaluate"],
    },
    "outcome_predictor": {
        "file": "core/strategy/predictor.py",
        "functions": ["predict_outcome"],
    },
}


class SelfModificationPlanner:
    """Maps proposals to concrete modification plans.

    Stateless — all state lives in the plan objects it creates.
    """

    def plan_from_proposal(
        self,
        proposal_id: str,
        target_system: str,
        proposal_type: str,
        rationale: str,
        expected_improvement: float = 0.0,
        confidence: float = 0.0,
        extra_params: dict[str, Any] | None = None,
    ) -> ModificationPlan | None:
        """Create a ModificationPlan from an improvement proposal.

        Returns None if no recipe matches the proposal type or target.
        """
        # 1. Resolve proposal type → recipe
        recipe = _PROPOSAL_TYPE_TO_RECIPE.get(proposal_type)
        if recipe is None:
            logger.info(f"No recipe for proposal type '{proposal_type}'")
            return None

        # 2. Check if recipe supports this target
        supported = _RECIPE_TARGET_MAP.get(recipe, [])
        if supported and not any(target_system.startswith(s) for s in supported):
            logger.info(f"Recipe {recipe.value} does not support target '{target_system}'")
            return None

        # 3. Resolve target details (file, function)
        target = self._resolve_target(recipe, target_system, extra_params)
        if target is None:
            logger.info(f"Cannot resolve target for '{target_system}' with recipe {recipe.value}")
            return None

        # 4. Build plan
        plan_id = f"mod_{uuid.uuid4().hex[:12]}"
        return ModificationPlan(
            plan_id=plan_id,
            proposal_id=proposal_id,
            recipe=recipe,
            target=target,
            rationale=rationale,
            expected_improvement=expected_improvement,
            confidence=confidence,
        )

    def plan_for_opportunity(
        self,
        opportunity: Any,
        extra_params: dict[str, Any] | None = None,
    ) -> ModificationPlan | None:
        """Create a plan from an Opportunity object (Phase 17)."""
        # Map opportunity target + source to a proposal type
        target_system = getattr(opportunity, "target_system", "")
        source = getattr(opportunity, "source", None)
        source_str = source.value if hasattr(source, "value") else str(source or "")

        # Derive proposal type from opportunity source + system
        proposal_type = self._infer_type_from_opportunity(target_system, source_str)
        if not proposal_type:
            return None

        rationale = getattr(opportunity, "rationale", "") or (
            f"Self-modification for {target_system} ({source_str})"
        )
        score = getattr(opportunity, "opportunity_score", 0.0)
        opp_id = getattr(opportunity, "id", "unknown")

        return self.plan_from_proposal(
            proposal_id=opp_id,
            target_system=target_system,
            proposal_type=proposal_type,
            rationale=rationale,
            expected_improvement=score,
            confidence=getattr(opportunity, "confidence", 0.5),
            extra_params=extra_params,
        )

    def list_available_recipes(self) -> list[dict[str, Any]]:
        """Return all registered recipes with metadata."""
        results = []
        for name, entry in get_registered_recipes().items():
            results.append({
                "recipe": name,
                "description": entry.get("description", ""),
                "supported_targets": _RECIPE_TARGET_MAP.get(entry["recipe"], []),
                "config_schema": entry.get("config_schema", {}),
            })
        return results

    # ── Internal ───────────────────────────────────────────────────────

    def _resolve_target(
        self,
        recipe: ModificationRecipe,
        system_name: str,
        extra_params: dict[str, Any] | None = None,
    ) -> ModificationTarget | None:
        """Resolve a system name to a concrete target file and function."""
        if recipe == ModificationRecipe.PROMOTE_PROPERTY:
            # Property promotion doesn't need a file target
            return ModificationTarget(
                system_name=system_name,
                target_file="",
                target_function="",
                extra_params=extra_params or {},
            )

        # Check known system map
        system_info = _SYSTEM_FILE_MAP.get(system_name)
        if system_info:
            functions = system_info["functions"]
            return ModificationTarget(
                system_name=system_name,
                target_file=system_info["file"],
                target_function=functions[0] if functions else "",
                extra_params=extra_params or {},
            )

        # Fuzzy match: find the closest system by prefix
        for key, info in _SYSTEM_FILE_MAP.items():
            if system_name.startswith(key) or key.startswith(system_name):
                functions = info["functions"]
                return ModificationTarget(
                    system_name=system_name,
                    target_file=info["file"],
                    target_function=functions[0] if functions else "",
                    extra_params=extra_params or {},
                )

        return None

    @staticmethod
    def _infer_type_from_opportunity(
        target_system: str,
        source: str,
    ) -> str | None:
        """Map an opportunity source + target to a proposal type string."""
        # Bottleneck tools → add retry
        if source == "bottleneck" and any(
            t in target_system for t in ["browser", "build", "tool"]
        ):
            return "add_retry"
        # Ceiling gaps in strategy → add calibration
        if source == "ceiling" and "strateg" in target_system:
            return "add_calibration"
        # Principle-driven → promote property
        if source == "principle":
            return "promote_property"
        # Experiment → vary timeout
        if source == "experiment" and "timeout" in target_system:
            return "increase_timeout"

        return None
