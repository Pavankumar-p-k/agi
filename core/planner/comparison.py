"""ComparativeScorer — evaluates multiple candidate plans side-by-side.

Wraps the PlanEvidenceEngine to score each candidate across 5 dimensions:
  - Confidence (35%): average per-node confidence from evidence engine
  - Historical Success (25%): matched experience success rate
  - Duration (15%): shorter is better (normalized)
  - Risk (15%): fewer + lower-severity risks is better
  - Evidence Strength (10%): count and quality of supporting evidence

Produces a ranked comparison with a clear recommendation.
"""

from __future__ import annotations

import logging
from typing import Any

from core.planner.evidence import PlanEvidenceEngine

logger = logging.getLogger(__name__)

# Scoring weights
W_CONFIDENCE = 0.35
W_HISTORICAL = 0.25
W_DURATION = 0.15
W_RISK = 0.15
W_EVIDENCE = 0.10


class ComparativeScorer:
    """Scores and compares multiple candidate plans.

    Each candidate is a dict with keys:
      strategy_key, strategy_label, root_node, estimated_duration_days, etc.

    Returns a comparison dict with ranked candidates and a recommendation.
    """

    def __init__(self) -> None:
        self._evidence_engine = PlanEvidenceEngine()

    def compare(
        self, goal: str, candidates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Score all candidates and return a ranked comparison."""
        scored: list[dict[str, Any]] = []

        for cand in candidates:
            score = self._score_candidate(goal, cand)
            scored.append(score)

        # Sort by overall score descending
        scored.sort(key=lambda c: c["overall_score"], reverse=True)

        best = scored[0] if scored else None

        return {
            "goal": goal[:120],
            "total_candidates": len(scored),
            "candidates": scored,
            "recommended": {
                "strategy_key": best["strategy_key"] if best else None,
                "strategy_label": best["strategy_label"] if best else None,
                "overall_score": best["overall_score"] if best else 0.0,
                "reasoning": self._build_reasoning(best, scored) if best else "",
            } if best else None,
        }

    def _score_candidate(
        self, goal: str, cand: dict[str, Any],
    ) -> dict[str, Any]:
        """Score one candidate across all dimensions."""
        strat_key = cand["strategy_key"]
        strat_label = cand["strategy_label"]
        root_node = cand["root_node"]
        est_days = cand.get("estimated_duration_days", 10)
        est_cost = cand.get("estimated_cost", "medium")
        risk_mod = cand.get("risk_modifier", 0.0)
        conf_mod = cand.get("confidence_modifier", 0.0)
        pros = cand.get("pros", [])
        cons = cand.get("cons", [])

        # Flatten nodes for evidence scoring
        all_nodes = self._flatten_nodes(root_node)

        # Evidence scoring (per-node)
        experiences = self._evidence_engine._safe_call(
            lambda: self._evidence_engine._get_knowledge_store().get_all_experiences()
        ) or []
        knowledge_items = self._evidence_engine._safe_call(
            lambda: self._evidence_engine._get_knowledge_store().get_all_knowledge()
        ) or []
        patterns = self._evidence_engine._safe_call(
            lambda: self._evidence_engine._get_failure_memory().get_all_patterns()
        ) or {}
        facts = []
        act_graph_stats = {}

        node_scores: list[dict] = []
        total_evidence = 0
        total_risks = 0
        matched_experiences = 0
        matched_failures = 0

        for node in all_nodes:
            ev = self._evidence_engine._compute_node_evidence(
                node, experiences, knowledge_items, patterns, facts, act_graph_stats,
            )
            node_scores.append(ev)
            total_evidence += ev["evidence_count"]
            total_risks += ev["risk_count"]
            for e in ev["evidence"]:
                if e["type"] == "experience":
                    matched_experiences += 1
                    if not e.get("success", True):
                        matched_failures += 1

        # Dimension scores (all normalized 0.0–1.0)

        # 1. Confidence (35%) — average node confidence
        if node_scores:
            avg_conf = sum(n["confidence"] for n in node_scores) / len(node_scores)
        else:
            avg_conf = 0.5
        conf_score = min(1.0, max(0.0, avg_conf + conf_mod))

        # 2. Historical Success (25%) — success rate of matched experiences
        if matched_experiences > 0:
            success_rate = (matched_experiences - matched_failures) / matched_experiences
        else:
            success_rate = 0.5  # neutral prior
        hist_score = min(1.0, max(0.0, success_rate))

        # 3. Duration (15%) — shorter is better, normalized
        # Scale: 5 days → 1.0, 30 days → 0.0
        dur_score = max(0.0, 1.0 - (est_days - 5) / 25) if est_days >= 5 else 1.0

        # 4. Risk (15%) — fewer + lower-severity risks
        critical = sum(1 for n in node_scores for r in n["risks"] if r.get("severity") == "critical")
        warnings = sum(1 for n in node_scores for r in n["risks"] if r.get("severity") == "warning")
        risk_penalty = critical * 0.25 + warnings * 0.10
        risk_score = max(0.0, min(1.0, 1.0 - risk_penalty + (risk_mod * 5)))
        risk_score = max(0.0, min(1.0, risk_score))

        # 5. Evidence Strength (10%) — count × quality
        ev_quality = min(1.0, total_evidence / max(len(all_nodes) * 3, 1))
        ev_score = min(1.0, ev_quality)

        # Overall score
        overall = (
            W_CONFIDENCE * conf_score
            + W_HISTORICAL * hist_score
            + W_DURATION * dur_score
            + W_RISK * risk_score
            + W_EVIDENCE * ev_score
        )

        return {
            "strategy_key": strat_key,
            "strategy_label": strat_label,
            "strategy_description": cand.get("strategy_description", ""),
            "overall_score": round(overall, 4),
            "dimensions": {
                "confidence": round(conf_score, 3),
                "historical_success": round(hist_score, 3),
                "duration": round(dur_score, 3),
                "risk": round(risk_score, 3),
                "evidence_strength": round(ev_score, 3),
            },
            "estimated_duration_days": est_days,
            "estimated_cost": est_cost,
            "total_nodes": len(all_nodes),
            "total_evidence": total_evidence,
            "total_risks": total_risks,
            "critical_risks": critical,
            "warning_risks": warnings,
            "pros": pros,
            "cons": cons,
            # Include the plan tree for the UI to render
            "root_node": root_node,
        }

    @staticmethod
    def _flatten_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
        nodes = [node]
        queue = [node]
        while queue:
            current = queue.pop(0)
            for child in current.get("children", []):
                nodes.append(child)
                queue.append(child)
        return nodes

    @staticmethod
    def _build_reasoning(
        best: dict[str, Any], all_scored: list[dict[str, Any]],
    ) -> str:
        parts = [f"{best['strategy_label']} scores highest at {best['overall_score']:.0%} overall."]

        dims = best["dimensions"]
        parts.append(f"Confidence: {dims['confidence']:.0%}, Risk: {dims['risk']:.0%}, Duration: {best['estimated_duration_days']}d.")

        # Compare to runner-up
        if len(all_scored) > 1:
            second = all_scored[1]
            margin = best["overall_score"] - second["overall_score"]
            if margin > 0.1:
                parts.append(f"Leads {second['strategy_label']} by {margin:.0%} — clear recommendation.")
            else:
                diff = second["overall_score"] - best["overall_score"]
                parts.append(f"Close race with {second['strategy_label']} ({second['overall_score']:.0%}).")

        return " ".join(parts)
