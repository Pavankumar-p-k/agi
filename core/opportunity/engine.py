"""OpportunityDiscoveryEngine — scans four sources to answer "what should JARVIS improve next?".

The engine is stateless — all state lives in injected stores. It generates
Opportunity candidates from four independent discovery methods:

  1. Bottleneck Discovery — find systems/tools with low success rates
  2. Ceiling Analysis — compare current vs theoretical capability ceiling
  3. Experiment History — find successful experiment patterns to extend
  4. Principle-Driven Discovery — apply accepted principles to systems lacking them

Each candidate is scored with the same formula:

    opportunity_score = bottleneck_impact × improvement_headroom
                      × success_probability × confidence × calibration_accuracy

A low score in any single dimension drives the product down, preventing
overconfidence in speculative opportunities.

When a calibrator is available, the 5th dimension (calibration_accuracy)
adjusts scores based on historical prediction accuracy per source.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from core.opportunity.calibration import OpportunityCalibrator
from core.opportunity.models import (
    Opportunity,
    OpportunitySource,
    OpportunityStatus,
)

logger = logging.getLogger(__name__)

# ── Default system capability scores (from Phase 16.2 assessment) ────────
# These serve as priors when no data-driven scores are available.
# Each is a 0.0–1.0 estimate of current capability maturity.

DEFAULT_SYSTEM_SCORES: dict[str, float] = {
    "execution_infrastructure": 0.96,
    "research_infrastructure": 0.92,
    "coding_intelligence": 0.93,
    "memory_learning": 0.88,
    "collaboration": 0.85,
    "generalization": 0.86,
    "belief_quality": 0.91,
    "strategic_reasoning": 0.82,
    "autonomous_improvement": 0.78,
    "activity_scheduler": 0.85,
    "automated_build": 0.80,
    "build_benchmark": 0.70,
    "self_modification": 0.45,
    "opportunity_discovery": 0.35,
    "browser_automation": 0.65,
    "voice_assistant": 0.70,
}

# Thresholds
MIN_BOTTLENECK_USAGE = 3  # minimum tool uses to consider bottleneck signal
BOTTLENECK_IMPACT_FLOOR = 0.10  # minimum impact for any bottleneck candidate
PRINCIPLE_SUCCESS_THRESHOLD = 0.60  # experiment success rate to trigger extension
MAX_OPPORTUNITIES_PER_SOURCE = 15  # cap per discovery source


class OpportunityDiscoveryEngine:
    """Scans stores for improvement opportunities and returns ranked candidates.

    The engine accepts optional store references — each defaults to None.
    Discovery methods gracefully degrade when their data source is absent.
    """

    def __init__(
        self,
        system_scores: dict[str, float] | None = None,
        calibrator: OpportunityCalibrator | None = None,
    ):
        self.system_scores = {**DEFAULT_SYSTEM_SCORES, **(system_scores or {})}
        self.calibrator = calibrator

    # ── Public API ─────────────────────────────────────────────────────

    def discover_all(
        self,
        activity_store: Any | None = None,
        principle_store: Any | None = None,
        registry: Any | None = None,
        experiment_runner: Any | None = None,
    ) -> list[Opportunity]:
        """Run all four discovery methods and return ranked opportunities.

        Results are deduplicated by target_system + source, keeping the
        highest-scoring opportunity when multiple sources flag the same
        system.
        """
        now = datetime.now(timezone.utc)

        bottlenecks = self.discover_bottlenecks(activity_store)
        ceilings = self.discover_ceilings()
        from_experiments = self.discover_from_experiments(experiment_runner)
        from_principles = self.discover_from_principles(principle_store, registry)

        all_opportunities: list[Opportunity] = []
        seen: set[tuple[str, str]] = set()

        for batch in [bottlenecks, ceilings, from_experiments, from_principles]:
            for opp in batch:
                key = (opp.target_system, opp.source.value)
                if key not in seen:
                    opp.created_at = now
                    all_opportunities.append(opp)
                    seen.add(key)
                else:
                    # Update existing if this score is higher
                    for existing in all_opportunities:
                        if (existing.target_system, existing.source.value) == key:
                            if opp.opportunity_score > existing.opportunity_score:
                                existing.opportunity_score = opp.opportunity_score
                                existing.bottleneck_impact = opp.bottleneck_impact
                                existing.improvement_headroom = opp.improvement_headroom
                                existing.success_probability = opp.success_probability
                                existing.confidence = opp.confidence
                                existing.calibration_accuracy = opp.calibration_accuracy
                                existing.rationale = opp.rationale
                                existing.evidence = opp.evidence
                            break

        all_opportunities.sort(key=lambda o: o.opportunity_score, reverse=True)
        return all_opportunities

    def discover_bottlenecks(
        self, activity_store: Any | None = None
    ) -> list[Opportunity]:
        """Find systems with low success rates despite high usage.

        Scans activity history for tool_call nodes and computes per-tool
        success rates. Tools with high usage but low success become
        bottleneck opportunities.
        """
        if activity_store is None:
            logger.info("Bottleneck discovery skipped: no activity_store")
            return []

        try:
            # Query tool_call nodes from activity graph
            tool_nodes = activity_store.get_nodes_by_type("tool_call")
            if not tool_nodes:
                return []

            # Aggregate per-tool stats
            tool_stats: dict[str, dict[str, float | int]] = defaultdict(
                lambda: {"successes": 0, "failures": 0, "total": 0}
            )

            for node in tool_nodes:
                label = getattr(node, "label", "") or ""
                status = getattr(node, "status", "") or ""
                tool_name = label.lower().strip()
                if not tool_name:
                    continue

                stats = tool_stats[tool_name]
                stats["total"] += 1
                if status and "fail" not in status.lower() and "error" not in status.lower():
                    stats["successes"] += 1
                else:
                    stats["failures"] += 1

            if not tool_stats:
                return []

            max_total = max(s["total"] for s in tool_stats.values())
            opportunities: list[Opportunity] = []

            for tool_name, stats in tool_stats.items():
                total = stats["total"]
                if total < MIN_BOTTLENECK_USAGE:
                    continue

                success_rate = stats["successes"] / total if total > 0 else 0.0
                failure_rate = 1.0 - success_rate

                # Impact: high when tool often fails AND is widely used
                usage_fraction = total / max_total if max_total > 0 else 0.0
                impact = failure_rate * (0.3 + 0.7 * usage_fraction)
                if impact < BOTTLENECK_IMPACT_FLOOR:
                    continue

                headroom = 1.0 - success_rate

                # Success probability: inversely related to how much we've
                # already tried and failed. More total uses with low success
                # → harder problem → lower probability.
                success_prob = max(0.20, 1.0 - failure_rate * 1.5)
                success_prob = min(0.90, success_prob)

                # Confidence: scales with evidence count
                confidence = min(1.0, 0.3 + total * 0.05)

                # 5-dimensional scoring with calibration
                raw_score = impact * headroom * success_prob * confidence
                adj_score, cal_accuracy = self._apply_calibration(
                    raw_score, OpportunitySource.BOTTLENECK, _tool_to_system(tool_name)
                )

                opportunities.append(Opportunity(
                    id=_make_id("bottleneck"),
                    target_system=_tool_to_system(tool_name),
                    improvement_description=(
                        f"{tool_name} has {stats['failures']}/{total} failures "
                        f"({failure_rate:.0%} failure rate). "
                        f"Improving reliability would unblock {total} workflows."
                    ),
                    source=OpportunitySource.BOTTLENECK,
                    bottleneck_impact=round(impact, 3),
                    improvement_headroom=round(headroom, 3),
                    success_probability=round(success_prob, 3),
                    confidence=round(confidence, 3),
                    opportunity_score=round(adj_score, 3),
                    rationale=(
                        f"Bottleneck: {tool_name} fails {failure_rate:.0%} of the time "
                        f"({stats['failures']}/{total}). Usage rank: "
                        f"{'high' if usage_fraction > 0.5 else 'moderate' if usage_fraction > 0.2 else 'low'}."
                    ),
                    evidence=[f"{tool_name}: {stats['successes']} successes, {stats['failures']} failures"],
                ))

            return opportunities

        except Exception as e:
            logger.warning(f"Bottleneck discovery error: {e}")
            return []

    def discover_ceilings(self) -> list[Opportunity]:
        """Compare each subsystem's current score to its theoretical ceiling.

        Systems with large headroom (gap between current and 1.0) are
        high-opportunity targets — but only if they are sufficiently
        impactful.
        """
        opportunities: list[Opportunity] = []

        for system_name, current_score in self.system_scores.items():
            headroom = 1.0 - current_score
            if headroom < 0.02:
                continue  # negligible headroom (>=0.98 already perfect)

            # Impact: how much improvement matters. Systems that are
            # currently weak AND critical score highest.
            # Use (1.0 - current_score) as a rough proxy for criticality:
            # the systems farthest from maturity offer the most marginal gain.
            impact = 0.3 + 0.7 * headroom

            # Success probability: history-dependent, but for ceiling analysis
            # we use a conservative estimate that improves with headroom
            # (more room = easier initial gains).
            success_prob = min(0.85, 0.40 + headroom * 0.6)

            # Confidence: moderate — ceiling analysis is heuristic
            confidence = 0.50 + 0.30 * headroom

            # 5-dimensional scoring with calibration
            raw_score = impact * headroom * success_prob * confidence
            adj_score, cal_accuracy = self._apply_calibration(
                raw_score, OpportunitySource.CEILING, system_name
            )

            desc = _ceiling_description(system_name, current_score, headroom)

            opportunities.append(Opportunity(
                id=_make_id("ceiling"),
                target_system=system_name,
                improvement_description=desc,
                source=OpportunitySource.CEILING,
                bottleneck_impact=round(impact, 3),
                improvement_headroom=round(headroom, 3),
                success_probability=round(success_prob, 3),
                confidence=round(confidence, 3),
                calibration_accuracy=round(cal_accuracy, 3),
                opportunity_score=round(adj_score, 3),
                rationale=(
                    f"Ceiling gap: {system_name} at {current_score:.0%} capacity "
                    f"({headroom:.0%} headroom). "
                    f"{'High' if headroom > 0.3 else 'Moderate' if headroom > 0.15 else 'Low'} improvement potential."
                ),
                evidence=[f"Current score: {current_score:.2f}, Ceiling: 1.00, Headroom: {headroom:.2f}"],
            ))

        return opportunities

    def discover_from_experiments(
        self, experiment_runner: Any | None = None
    ) -> list[Opportunity]:
        """Scan past experiments for patterns that could generalize.

        Finds experiment knob changes with high success rates and proposes
        applying them to similar systems or domains.
        """
        if experiment_runner is None:
            logger.info("Experiment discovery skipped: no experiment_runner")
            return []

        try:
            experiments = experiment_runner.get_experiments(limit=50)
            if not experiments:
                return []

            # Group experiments by knob change (pattern)
            pattern_stats: dict[str, dict] = defaultdict(
                lambda: {"successes": 0, "failures": 0, "total": 0, "domains": set(), "systems": set()}
            )

            for exp in experiments:
                status = getattr(exp, "status", "") or ""
                knob_changes = getattr(exp, "knob_changes", []) or []
                control_metrics = getattr(exp, "control_metrics", {}) or {}
                candidate_metrics = getattr(exp, "candidate_metrics", {}) or {}
                domain = getattr(exp, "domain", "") or "general"

                # Determine success: improvement seen in candidate vs control
                was_success = False
                if control_metrics and candidate_metrics:
                    improved_count = 0
                    total_metrics = 0
                    for metric_key in control_metrics:
                        if metric_key in candidate_metrics:
                            total_metrics += 1
                            if candidate_metrics[metric_key] > control_metrics[metric_key]:
                                improved_count += 1
                    if total_metrics > 0 and improved_count / total_metrics > 0.5:
                        was_success = True
                elif "complete" in status.lower():
                    was_success = "fail" not in status.lower() and "revert" not in status.lower()

                for change in knob_changes:
                    change_name = change.knob_name if hasattr(change, "knob_name") else str(change)
                    pattern = f"improve_{change_name}"
                    ps = pattern_stats[pattern]
                    ps["total"] += 1
                    if was_success:
                        ps["successes"] += 1
                    else:
                        ps["failures"] += 1
                    ps["domains"].add(domain)
                    ps["systems"].add(change_name)

            opportunities: list[Opportunity] = []

            for pattern_name, stats in pattern_stats.items():
                total = stats["total"]
                success_rate = stats["successes"] / total if total > 0 else 0.0
                if success_rate < PRINCIPLE_SUCCESS_THRESHOLD or total < 1:
                    continue

                knobs_in_scope = _pattern_to_scope(pattern_name)

                impact = 0.5 + 0.5 * success_rate
                headroom = 0.5  # moderate — depends on target system
                success_prob = success_rate * 0.85  # regress to mean
                confidence = min(1.0, 0.3 + total * 0.10)

                # 5-dimensional scoring with calibration
                raw_score = impact * headroom * success_prob * confidence
                adj_score, cal_accuracy = self._apply_calibration(
                    raw_score, OpportunitySource.EXPERIMENT, knobs_in_scope
                )

                sys_list = ", ".join(sorted(stats["systems"]))
                opportunities.append(Opportunity(
                    id=_make_id("experiment"),
                    target_system=knobs_in_scope,
                    improvement_description=(
                        f"Extend successful pattern '{pattern_name}' "
                        f"({stats['successes']}/{total} successful experiments) "
                        f"to new systems or domains."
                    ),
                    source=OpportunitySource.EXPERIMENT,
                    bottleneck_impact=round(impact, 3),
                    improvement_headroom=round(headroom, 3),
                    success_probability=round(success_prob, 3),
                    confidence=round(confidence, 3),
                    calibration_accuracy=round(cal_accuracy, 3),
                    opportunity_score=round(adj_score, 3),
                    rationale=(
                        f"Experiment history: '{pattern_name}' succeeded "
                        f"{stats['successes']}/{total} times ({success_rate:.0%}) "
                        f"across {len(stats['domains'])} domains. "
                        f"Proven pattern ready for wider application."
                    ),
                    evidence=[
                        f"Pattern: {pattern_name}",
                        f"Success rate: {stats['successes']}/{total}",
                        f"Domains: {', '.join(sorted(stats['domains']))}",
                        f"Systems: {sys_list}" if sys_list else "",
                    ],
                ))

            return opportunities

        except Exception as e:
            logger.warning(f"Experiment discovery error: {e}")
            return []

    def discover_from_principles(
        self,
        principle_store: Any | None = None,
        registry: Any | None = None,
    ) -> list[Opportunity]:
        """Use accepted principles to find systems missing recommended properties.

        For each accepted principle, scan all registered system profiles.
        Systems that lack the property recommended by the principle
        become targets for improvement.
        """
        if principle_store is None or registry is None:
            logger.info("Principle-driven discovery skipped: missing store or registry")
            return []

        try:
            principles = principle_store.list_principles(status="accepted")
            if not principles:
                return []

            profiles = registry.list_profiles()
            if not profiles:
                return []

            # Build reverse-index: system_id → profile
            profile_map: dict[str, Any] = {}
            for p in profiles:
                sid = getattr(p, "system_id", None) or getattr(p, "id", None) or ""
                profile_map[sid] = p

            opportunities: list[Opportunity] = []

            for principle in principles:
                property_name = getattr(principle, "property_name", "") or ""
                discrimination = getattr(principle, "discrimination", 0.0) or 0.0
                principle_confidence = getattr(principle, "confidence", 0.0) or 0.0
                domains = getattr(principle, "domains", []) or []

                if not property_name:
                    continue

                for profile_sid, profile in profile_map.items():
                    properties: dict = getattr(profile, "properties", {}) or {}
                    current_val = properties.get(property_name)

                    # Skip if property already True (or not applicable)
                    if current_val is True or current_val == 1.0:
                        continue

                    # Skip numeric properties above a threshold
                    if isinstance(current_val, (int, float)) and current_val >= 0.8:
                        continue

                    impact = min(1.0, abs(discrimination) * 2.0)
                    headroom = 0.6 if current_val is False or current_val == 0.0 else 0.8
                    success_prob = principle_confidence
                    confidence = principle_confidence

                    # 5-dimensional scoring with calibration
                    raw_score = impact * headroom * success_prob * confidence
                    adj_score, cal_accuracy = self._apply_calibration(
                        raw_score, OpportunitySource.PRINCIPLE, profile_sid
                    )

                    if adj_score < 0.05:
                        continue

                    domain_desc = f" (domains: {', '.join(domains[:3])})" if domains else ""

                    opportunities.append(Opportunity(
                        id=_make_id("principle"),
                        target_system=profile_sid,
                        improvement_description=(
                            f"Add '{property_name}' property to {profile_sid} "
                            f"(principle suggests +{discrimination:.0%} discrimination{domain_desc})"
                        ),
                        source=OpportunitySource.PRINCIPLE,
                        bottleneck_impact=round(impact, 3),
                        improvement_headroom=round(headroom, 3),
                        success_probability=round(success_prob, 3),
                        confidence=round(confidence, 3),
                        calibration_accuracy=round(cal_accuracy, 3),
                        opportunity_score=round(adj_score, 3),
                        rationale=(
                            f"Principle-driven: accepted principle for '{property_name}' "
                            f"(confidence: {principle_confidence:.2f}, "
                            f"discrimination: {discrimination:+.0%}). "
                            f"System '{profile_sid}' currently lacks this property "
                            f"(current value: {current_val})."
                        ),
                        evidence=[
                            f"Principle: {getattr(principle, 'principle_id', 'unknown')}",
                            f"Property: {property_name} ({getattr(principle, 'category', 'unknown')})",
                            f"Target system: {profile_sid} (current: {current_val})",
                            f"Discrimination: {discrimination:+.0%}",
                            f"Confidence: {principle_confidence:.2f}",
                        ],
                    ))

            return opportunities

        except Exception as e:
            logger.warning(f"Principle-driven discovery error: {e}")
            return []

    def _apply_calibration(
        self,
        score: float,
        source: OpportunitySource,
        target_system: str,
    ) -> tuple[float, float]:
        """Multiply score by calibration accuracy factor.

        Returns:
            (adjusted_score, calibration_accuracy_factor)
        """
        if self.calibrator is None:
            return score, 1.0
        factor = self.calibrator.get_adjustment_factor(
            source=source.value,
            target_system=target_system,
        )
        return score * factor, factor

    def get_scored_systems(self) -> dict[str, float]:
        """Return current system scores (for external use)."""
        return dict(self.system_scores)


# ── Helpers ─────────────────────────────────────────────────────────────

def _make_id(prefix: str) -> str:
    return f"opp_{prefix}_{uuid.uuid4().hex[:12]}"


def _tool_to_system(tool_name: str) -> str:
    """Map raw tool name to a canonical system name."""
    mapping = {
        "browser_navigate": "browser_automation",
        "browser_click": "browser_automation",
        "browser_fill": "browser_automation",
        "browser_snapshot": "browser_automation",
        "browser_screenshot": "browser_automation",
        "build_project": "automated_build",
        "run_tests": "automated_build",
        "send_email": "execution_infrastructure",
        "research_url": "research_infrastructure",
        "extract_facts": "research_infrastructure",
        "edit_file": "coding_intelligence",
        "create_file": "coding_intelligence",
    }
    return mapping.get(tool_name, tool_name)


def _ceiling_description(system_name: str, score: float, headroom: float) -> str:
    if headroom > 0.3:
        return (
            f"{system_name} is at {score:.0%} capacity with {headroom:.0%} headroom. "
            f"Significant improvement potential — expected to be the most impactful area."
        )
    if headroom > 0.15:
        return (
            f"{system_name} is at {score:.0%} capacity with {headroom:.0%} headroom. "
            f"Moderate improvement potential."
        )
    return (
        f"{system_name} is at {score:.0%} capacity with {headroom:.0%} headroom. "
        f"Near ceiling — marginal gains only."
    )


def _pattern_to_scope(pattern_name: str) -> str:
    """Map a knob-change pattern to target system scope."""
    mapping = {
        "improve_research.min_sources": "research_infrastructure",
        "improve_coding.simulation_required": "coding_intelligence",
        "improve_coding.safety_threshold": "coding_intelligence",
        "improve_planner.inject_domain_patterns": "strategic_reasoning",
        "improve_planner.inject_failure_warnings": "strategic_reasoning",
        "improve_scheduler.urgency_bonus": "activity_scheduler",
        "improve_scheduler.retry_bonus": "activity_scheduler",
        "improve_scheduler.waiting_bonus_per_minute": "activity_scheduler",
    }
    return mapping.get(pattern_name, "general")
