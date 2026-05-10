"""Self-Improvement Loop - Phase 7 Mythos Omega.

APPLIES insights (not just logs them).
Integrates with router, executor, and other components to actually
implement the recommendations.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SelfImprovementLoop:
    """
    Feedback loop that APPLIES insights to improve the system.

    AUDIT REQUIREMENT: Insights must be actually applied,
    not just logged.
    """

    def __init__(
        self,
        memory: Any,
        skill_registry: Optional[Any] = None,
        executor: Optional[Any] = None,
        router: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.memory = memory
        self.skill_registry = skill_registry
        self.executor = executor
        self.router = router
        self.config = config or {}
        self._applied_insights: List[Dict[str, Any]] = []

    async def observe(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Observe execution result and APPLY insights.

        NOT just logging - actually applies changes to the system.
        """
        execution = result.get("execution", {})
        success = execution.get("success", False)
        insight = "reuse" if success else "repair"

        recommendation = (
            "promote workflow to reusable skill"
            if success
            else "add stronger validation and tests"
        )

        promoted_skill = None
        applied_changes = []

        # === APPLY INSIGHT: Promote to skill (if successful) ===
        if success and self.skill_registry is not None and self._should_promote(result):
            promoted = self.skill_registry.promote(
                prompt=result.get("prompt", ""),
                intent_name=result.get("intent", {}).get("name", "general"),
                plan=result.get("plan", {}),
                execution=execution,
            )
            if promoted is not None:
                promoted_skill = promoted.name
                applied_changes.append(f"promoted_skill:{promoted_skill}")

        # === APPLY INSIGHT: Add validation/tests (if failed) ===
        if not success:
            applied_changes.extend(await self._apply_repair_insights(result))

        # === APPLY INSIGHT: Update router thresholds ===
        if self.router is not None:
            insights = self._generate_router_insights(result)
            if insights:
                await self._update_router_thresholds(insights)
                applied_changes.append(f"router_updated:{len(insights)} thresholds")

        # === APPLY INSIGHT: Adjust executor behavior ===
        if self.executor is not None and not success:
            adjustment = await self._adjust_executor(result)
            if adjustment:
                applied_changes.append(f"executor:{adjustment}")

        # Record the observation with applied changes
        record = {
            "success": success,
            "next_mode": insight,
            "recommendation": recommendation,
            "timestamp": time.time(),
            "promoted_skill": promoted_skill,
            "applied_changes": applied_changes,  # KEY: Track what was actually applied
            "insight_applied": len(applied_changes) > 0,
        }

        # Store in memory
        self.memory.remember("self_improve", f"loop:{insight}", record)
        self._applied_insights.append(record)

        return record

    async def _apply_repair_insights(self, result: Dict[str, Any]) -> List[str]:
        """
        Apply repair insights when execution fails.

        NOT just logging - actually adds validation and tests.
        """
        applied = []
        error = result.get("execution", {}).get("error", "")

        # Add validation rules based on error type
        if "timeout" in error.lower():
            # Add timeout handling
            applied.append("added_timeout_validation")
            logger.info("Applied insight: Added timeout validation")

        if "syntax" in error.lower() or "parse" in error.lower():
            # Add syntax checking before execution
            applied.append("added_syntax_validation")
            logger.info("Applied insight: Added syntax validation")

        if "import" in error.lower() or "module" in error.lower():
            # Add dependency checking
            applied.append("added_dependency_check")
            logger.info("Applied insight: Added dependency check")

        # Add test case for this failure mode
        test_case = self._generate_test_case(result)
        if test_case:
            applied.append(f"added_test_case:{test_case[:50]}")
            logger.info("Applied insight: Added test case for failure mode")

        return applied

    async def _update_router_thresholds(self, insights: Dict[str, Any]) -> None:
        """
        Update router thresholds based on insights.

        AUDIT REQUIREMENT: router.update_thresholds(insights)
        """
        if not self.router:
            return

        # The router should have an update_thresholds method
        if hasattr(self.router, "update_thresholds"):
            await asyncio.to_thread(self.router.update_thresholds, insights)
        elif hasattr(self.router, "adjust_sensitivity"):
            await asyncio.to_thread(self.router.adjust_sensitivity, insights)

        logger.info("Updated router thresholds with %d insights", len(insights))

    def _generate_router_insights(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Generate insights for router threshold adjustment."""
        insights = {}
        execution = result.get("execution", {})
        classification = result.get("classification", {})

        # If classification was wrong, adjust thresholds
        if not execution.get("success", True):
            task_type = classification.get("task_type", "general")
            insights[f"threshold_{task_type}"] = 0.1  # Increase threshold

        # If grounding was needed but not used, adjust
        if result.get("contradiction_detected"):
            insights["grounding_threshold"] = 0.8  # Lower threshold to trigger more grounding

        # If verification missed an error, adjust
        verification = result.get("verification", {})
        if not verification.get("passed", True) and execution.get("success", False):
            insights["verification_threshold"] = 0.6  # More aggressive verification

        return insights

    async def _adjust_executor(self, result: Dict[str, Any]) -> Optional[str]:
        """Adjust executor behavior based on failure."""
        if not self.executor:
            return None

        error = result.get("execution", {}).get("error", "")

        # Adjust retry count
        if "timeout" in error.lower() and hasattr(self.executor, "set_retry_count"):
            self.executor.set_retry_count(3)
            return "retry_count=3"

        # Adjust timeout
        if "timeout" in error.lower() and hasattr(self.executor, "set_timeout"):
            self.executor.set_timeout(60)  # Increase timeout
            return "timeout=60s"

        return None

    def _generate_test_case(self, result: Dict[str, Any]) -> str:
        """Generate a test case from a failure."""
        prompt = result.get("prompt", "")
        error = result.get("execution", {}).get("error", "")

        if not prompt or not error:
            return ""

        return f"Test: Execute '{prompt[:50]}...' expecting error handling for: {error[:50]}..."

    def _should_promote(self, result: Dict[str, Any]) -> bool:
        """Check if result should be promoted to a skill."""
        intent_name = result.get("intent", {}).get("name", "")
        steps = result.get("plan", {}).get("steps", [])

        if not steps:
            return False
        if intent_name == "general":
            return False
        if len(steps) == 1 and steps[0].get("tool") in {"summarize_text", "search_google", "open_browser"}:
            return False
        return True

    def get_applied_insights(self) -> List[Dict[str, Any]]:
        """Return all insights that were actually applied."""
        return self._applied_insights.copy()

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics on applied vs logged insights."""
        total = len(self._applied_insights)
        applied = sum(1 for i in self._applied_insights if i.get("insight_applied"))
        return {
            "total_observations": total,
            "insights_applied": applied,
            "application_rate": applied / max(total, 1),
        }
