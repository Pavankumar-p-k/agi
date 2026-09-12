"""Capability Selection, Composition, and Gap Detection Engine.

Enables Super-Brain to:
1. Query recommended capabilities for a specific goal or constraint
2. Compose multi-capability workflows and validate prerequisite chains
3. Detect capability gaps before execution to prevent LLM hallucinations
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    RiskTier,
)
from tools.registry import CapabilityRegistry, _ensure_registry

logger = logging.getLogger(__name__)


@dataclass
class CapabilityRecommendation:
    capability: CapabilityDefinition
    score: float
    match_reason: str
    prerequisites_met: bool = True
    missing_prerequisites: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.capability.name,
            "owner_module": self.capability.owner_module,
            "type": self.capability.type.value,
            "score": round(self.score, 3),
            "health": self.capability.health.value,
            "reliability_score": self.capability.reliability.score,
            "risk": self.capability.risk.value,
            "match_reason": self.match_reason,
            "prerequisites_met": self.prerequisites_met,
            "missing_prerequisites": self.missing_prerequisites,
        }


@dataclass
class CapabilityGap:
    """Explicit indicator that JARVIS lacks a required capability."""
    requested_need: str
    reason: str
    missing_dependencies: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    suggested_acquisition_sources: list[str] = field(default_factory=lambda: ["local_cli", "pypi", "github"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap": True,
            "requested_need": self.requested_need,
            "reason": self.reason,
            "missing_dependencies": self.missing_dependencies,
            "missing_requirements": self.missing_requirements,
            "suggested_acquisition_sources": self.suggested_acquisition_sources,
        }


class CapabilitySelector:
    """Brokers capabilities between Super-Brain goals and Specialist execution."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None) -> None:
        self.registry = registry if registry is not None else _ensure_registry()

    def recommend_capabilities(
        self,
        goal: str,
        *,
        max_risk: Optional[RiskTier | str] = None,
        min_reliability: float = 0.0,
        required_types: Optional[list[CapabilityType | str]] = None,
        available_requirements: Optional[list[str]] = None,
        include_capabilities: Optional[list[str]] = None,
    ) -> list[CapabilityRecommendation]:
        """Rank and recommend available capabilities for a goal without dictating the plan."""
        goal_tokens = set(goal.lower().replace("-", " ").replace(".", " ").split())
        recommendations: list[CapabilityRecommendation] = []
        all_caps = self.registry.list_capabilities(status=CapabilityStatus.AVAILABLE)

        risk_order = {RiskTier.LOW: 1, RiskTier.MEDIUM: 2, RiskTier.HIGH: 3, RiskTier.CRITICAL: 4}
        max_risk_level = risk_order.get(
            max_risk if isinstance(max_risk, RiskTier) else RiskTier(max_risk), 4
        ) if max_risk else 4

        types_set = {
            t.value if isinstance(t, CapabilityType) else t
            for t in (required_types or [])
        } if required_types else None

        avail_reqs = set(available_requirements or ["filesystem", "terminal", "display", "network", "mouse", "keyboard", "python"])

        for cap in all_caps:
            # 1. Filter out unhealthy capabilities
            if cap.health == CapabilityHealth.UNHEALTHY:
                continue

            # 2. Filter by risk ceiling
            cap_risk_level = risk_order.get(cap.risk, 1)
            if cap_risk_level > max_risk_level:
                continue

            # 3. Filter by type
            if types_set and cap.type.value not in types_set:
                continue

            # 4. Filter by minimum reliability
            if cap.reliability.score < min_reliability:
                continue

            # 5. Check prerequisites
            missing_reqs = [r for r in cap.requirements if r.lower() not in avail_reqs]
            prereqs_met = len(missing_reqs) == 0

            # 6. Score relevance
            cap_text = f"{cap.name} {cap.description} {cap.owner_module} {' '.join(cap.risk_tags)}".lower()
            overlap = sum(1 for token in goal_tokens if token in cap_text)
            is_explicitly_included = bool(include_capabilities and cap.name in include_capabilities)

            if overlap == 0 and len(goal_tokens) > 0 and not is_explicitly_included:
                continue

            if is_explicitly_included:
                overlap = max(1, overlap)

            # Base score from overlap
            base_score = overlap / max(1, len(goal_tokens))
            # Weight with historical reliability (70% semantic match, 30% reliability)
            weighted_score = (base_score * 0.7) + (cap.reliability.score * 0.3)
            # Bonus for healthy over degraded
            if cap.health == CapabilityHealth.HEALTHY:
                weighted_score += 0.05
            if not prereqs_met:
                weighted_score *= 0.5  # Penalize missing prerequisites

            recommendations.append(
                CapabilityRecommendation(
                    capability=cap,
                    score=weighted_score,
                    match_reason=f"Matched {overlap} keywords with reliability {int(cap.reliability.score*100)}%",
                    prerequisites_met=prereqs_met,
                    missing_prerequisites=missing_reqs,
                )
            )

        recommendations.sort(key=lambda r: r.score, reverse=True)
        return recommendations

    def detect_gaps(
        self,
        required_needs: list[str],
        *,
        available_requirements: Optional[list[str]] = None,
    ) -> tuple[list[CapabilityDefinition], list[CapabilityGap]]:
        """Identify available capabilities vs missing capability gaps for required steps."""
        found: list[CapabilityDefinition] = []
        gaps: list[CapabilityGap] = []
        avail_reqs = set(available_requirements or ["filesystem", "terminal", "display", "network", "mouse", "keyboard", "python"])

        for need in required_needs:
            # 1. Exact or prefix match in registry
            cap = self.registry.get_capability(need)
            if not cap:
                # Search partial
                matches = [c for c in self.registry.list_capabilities() if need.lower() in c.name.lower()]
                if matches:
                    cap = matches[0]

            if not cap:
                gaps.append(
                    CapabilityGap(
                        requested_need=need,
                        reason=f"No capability matching '{need}' is registered in JARVIS",
                        suggested_acquisition_sources=["local_cli", "pypi", "github"],
                    )
                )
            elif cap.health == CapabilityHealth.UNHEALTHY:
                gaps.append(
                    CapabilityGap(
                        requested_need=need,
                        reason=f"Capability '{cap.name}' exists but is UNHEALTHY or missing from host environment",
                        missing_dependencies=list(cap.dependencies),
                        missing_requirements=list(cap.requirements),
                    )
                )
            else:
                missing_reqs = [r for r in cap.requirements if r.lower() not in avail_reqs]
                if missing_reqs:
                    gaps.append(
                        CapabilityGap(
                            requested_need=need,
                            reason=f"Capability '{cap.name}' is available but missing system prerequisites: {missing_reqs}",
                            missing_requirements=missing_reqs,
                        )
                    )
                else:
                    found.append(cap)

        return found, gaps

    def validate_composition(
        self,
        chain: list[str],
    ) -> tuple[bool, list[CapabilityDefinition], list[CapabilityGap]]:
        """Verify that a composite chain of capabilities can execute cleanly end-to-end."""
        resolved, gaps = self.detect_gaps(chain)
        is_valid = len(gaps) == 0 and len(resolved) == len(chain)
        return is_valid, resolved, gaps
