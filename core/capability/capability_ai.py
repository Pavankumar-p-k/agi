"""Capability AI Coordinator for JARVIS.

Manages the questions:
- "What can JARVIS do?" (Live Registry & Discovery)
- "What can it use?" (Selection & Recommendation)
- "What is missing?" (Gap Detection & Composition)
- "How can that capability be safely obtained?" (Quarantine Pipeline)
- "What has been learned from experience?" (Epistemic Learning)

Boundary Guarantee:
Capability AI DOES NOT replace Super-Brain (does not decide user goals or global planning).
Capability AI DOES NOT replace Specialist AIs (does not execute domain work directly).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from core.capability.acquisition import (
    AcquisitionCandidate,
    CapabilityAcquisitionPipeline,
    QuarantineAudit,
)
from core.capability.discovery import CapabilityDiscoveryService
from core.capability.experience import CapabilityExperienceEntry, CapabilityExperienceStore
from core.capability.selection import CapabilityGap, CapabilityRecommendation, CapabilitySelector
from core.specialist import SpecialistModule
from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    RiskTier,
)
from tools.registry import CapabilityRegistry, _ensure_registry

logger = logging.getLogger(__name__)


class CapabilityAI:
    """Authoritative Capability Intelligence layer for JARVIS."""

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        experience_store: Optional[CapabilityExperienceStore] = None,
    ) -> None:
        self.registry = registry if registry is not None else _ensure_registry()
        self.discovery = CapabilityDiscoveryService(self.registry)
        self.selector = CapabilitySelector(self.registry)
        self.acquisition = CapabilityAcquisitionPipeline(self.registry)
        self.experience = experience_store or CapabilityExperienceStore()

    def sync(self, specialists: Optional[list[SpecialistModule]] = None) -> dict[str, Any]:
        """Perform a full discovery sync across all specialists and host CLI tools."""
        return self.discovery.discover_all(specialists=specialists)

    def what_can_jarvis_do(self, only_healthy: bool = True) -> list[CapabilityDefinition]:
        """Return the live answer to 'What can JARVIS do right now?'."""
        caps = self.registry.list_capabilities(status=CapabilityStatus.AVAILABLE)
        if only_healthy:
            return [c for c in caps if c.health in (CapabilityHealth.HEALTHY, CapabilityHealth.DEGRADED)]
        return caps

    def recommend(
        self,
        goal: str,
        *,
        max_risk: Optional[RiskTier | str] = None,
        min_reliability: float = 0.0,
        required_types: Optional[list[CapabilityType | str]] = None,
    ) -> list[CapabilityRecommendation]:
        """Recommend capabilities to Super-Brain for solving a sub-goal."""
        # 1. First check if a previously learned operational recipe exists
        learned = self.experience.find_experience(goal)
        recs = self.selector.recommend_capabilities(
            goal,
            max_risk=max_risk,
            min_reliability=min_reliability,
            required_types=required_types,
        )
        # If we have a learned recipe, boost matching capabilities
        if learned:
            learned_caps = set(learned.capabilities_used)
            for r in recs:
                if r.capability.name in learned_caps:
                    r.score += 0.2
                    r.match_reason += f" [Learned recipe '{learned.pattern_key}' bonus]"
            recs.sort(key=lambda r: r.score, reverse=True)

        return recs

    def check_gaps(self, required_capabilities: list[str]) -> tuple[list[CapabilityDefinition], list[CapabilityGap]]:
        """Identify available capabilities vs missing capability gaps for Super-Brain."""
        return self.selector.detect_gaps(required_capabilities)

    def validate_workflow(self, workflow_chain: list[str]) -> tuple[bool, list[CapabilityDefinition], list[CapabilityGap]]:
        """Validate an end-to-end capability chain before execution."""
        return self.selector.validate_composition(workflow_chain)

    def acquire_safely(
        self,
        candidate: AcquisitionCandidate,
        *,
        host_environment: Optional[list[str]] = None,
        sandbox_tester: Optional[Callable[[], bool]] = None,
        user_approval_granted: bool = False,
        handler: Optional[Callable] = None,
        live_verifier: Optional[Callable[[], bool]] = None,
    ) -> QuarantineAudit:
        """Run a candidate through the complete 10-stage quarantine acquisition pipeline."""
        audit = self.acquisition.create_quarantine_audit(candidate)

        if not self.acquisition.inspect_static(audit):
            return audit

        if not self.acquisition.check_dependencies(audit, host_environment=host_environment):
            return audit

        if not self.acquisition.sandbox_test(audit, test_runner=sandbox_tester):
            return audit

        if not self.acquisition.security_check(audit):
            return audit

        if not self.acquisition.grant_user_approval(audit, approved=user_approval_granted):
            return audit

        cap = self.acquisition.install_and_register(audit, handler=handler)
        if not cap:
            return audit

        self.acquisition.verify_live(audit, cap.name, live_verifier=live_verifier)
        return audit

    def record_experience(
        self,
        pattern_key: str,
        goal_intent: str,
        capabilities_used: list[str],
        success: bool = True,
        note: Optional[str] = None,
    ) -> CapabilityExperienceEntry:
        """Reinforce learning from successful or failed multi-capability operations."""
        # Update registry reliability metrics for each capability used
        for cap_name in capabilities_used:
            self.registry.record_execution(cap_name, success=success, failure_reason=note)

        return self.experience.record_experience(
            pattern_key=pattern_key,
            goal_intent=goal_intent,
            capabilities_used=capabilities_used,
            success=success,
            note=note,
        )
