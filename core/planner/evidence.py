"""PlanEvidenceEngine — evidence, confidence, risks, and alternatives for plans.

Each plan node is scored against the system's accumulated knowledge:
  - Past experiences (KnowledgeStore) via SimilarityScorer
  - Knowledge patterns (KnowledgeStore)
  - Failure patterns (PatternFailureMemory)
  - Research facts  (FactStore/FactRetriever)
  - ActivityGraph historical stats

The engine produces structured evidence that makes every plan explainable.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.planner.store import PlanStore

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

_GOAL_TYPE_PREFIXES: dict[str, list[str]] = {
    "build": ["build ", "create ", "develop ", "implement ", "make "],
    "research": ["research ", "investigate ", "study ", "learn ", "analyze "],
    "refactor": ["refactor ", "rewrite ", "restructure ", "migrate ", "redesign "],
    "explore": ["explore ", "find ", "discover ", "survey ", "audit "],
}


def _classify_goal(goal: str) -> str:
    gl = goal.lower().strip()
    for gt, prefixes in _GOAL_TYPE_PREFIXES.items():
        if any(gl.startswith(p) for p in prefixes):
            return gt
    return "build"


def _extract_domain_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from a description."""
    stopwords = {"the", "a", "an", "this", "that", "with", "for", "and", "or", "but",
                 "in", "on", "at", "to", "of", "is", "was", "be", "has", "have"}
    words = set(re.findall(r'[a-z]{3,}', text.lower()))
    return words - stopwords


def _flatten_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    """BFS over plan tree returning all nodes."""
    nodes = [node]
    queue = [node]
    while queue:
        current = queue.pop(0)
        for child in current.get("children", []):
            nodes.append(child)
            queue.append(child)
    return nodes


# ── PlanEvidenceEngine ───────────────────────────────────────────────────────


class PlanEvidenceEngine:
    """Computes evidence, risks, alternatives, and confidence for a plan.

    Stateless — all data sourced from external stores on each call.
    Safe to create fresh per request.
    """

    def __init__(self) -> None:
        self._plan_store = PlanStore()

    def get_evidence(self, plan_id: str) -> dict[str, Any] | None:
        """Per-node evidence for every node in the plan tree."""
        plan = self._plan_store.get(plan_id)
        if not plan:
            return None
        root = plan.get("root_node", {})
        nodes = _flatten_nodes(root)

        knowledge = self._get_knowledge_store()
        experiences = self._safe_call(lambda: knowledge.get_all_experiences()) or []
        knowledge_items = self._safe_call(lambda: knowledge.get_all_knowledge()) or []
        failure_memory = self._get_failure_memory()
        patterns = self._safe_call(lambda: failure_memory.get_all_patterns()) or {}
        facts = self._get_all_facts()
        act_graph = self._get_activity_graph_stats()

        node_evidence: list[dict[str, Any]] = []
        for node in nodes:
            ev = self._compute_node_evidence(
                node, experiences, knowledge_items, patterns, facts, act_graph,
            )
            node_evidence.append(ev)

        return {
            "plan_id": plan_id,
            "overall": self._compute_overall(node_evidence),
            "nodes": node_evidence,
        }

    def get_risks(self, plan_id: str) -> dict[str, Any] | None:
        """Aggregated risks for the entire plan."""
        evidence = self.get_evidence(plan_id)
        if not evidence:
            return None
        all_risks: list[dict] = []
        for node_ev in evidence["nodes"]:
            for risk in node_ev.get("risks", []):
                all_risks.append({**risk, "node_id": node_ev["node_id"]})
        return {
            "plan_id": plan_id,
            "total_risks": len(all_risks),
            "risks": all_risks,
            "critical_count": sum(1 for r in all_risks if r.get("severity") == "critical"),
            "warning_count": sum(1 for r in all_risks if r.get("severity") == "warning"),
            "info_count": sum(1 for r in all_risks if r.get("severity") == "info"),
        }

    def get_alternatives(self, plan_id: str) -> dict[str, Any] | None:
        """Alternative approaches for the plan."""
        plan = self._plan_store.get(plan_id)
        if not plan:
            return None
        root = plan.get("root_node", {})
        nodes = _flatten_nodes(root)

        knowledge = self._get_knowledge_store()
        knowledge_items = self._safe_call(lambda: knowledge.get_all_knowledge()) or []

        alternatives: list[dict] = []
        for node in nodes:
            alts = self._compute_alternatives(node, knowledge_items)
            if alts:
                alternatives.append({
                    "node_id": node.get("id"),
                    "node_title": node.get("title"),
                    "alternatives": alts,
                })

        return {
            "plan_id": plan_id,
            "total_alternatives": sum(len(a["alternatives"]) for a in alternatives),
            "nodes": alternatives,
        }

    def get_confidence(self, plan_id: str) -> dict[str, Any] | None:
        """Overall and per-node confidence scores."""
        evidence = self.get_evidence(plan_id)
        if not evidence:
            return None
        return {
            "plan_id": plan_id,
            "overall": evidence["overall"],
            "nodes": [
                {"node_id": n["node_id"], "confidence": n["confidence"],
                 "evidence_count": n["evidence_count"], "risk_count": n["risk_count"]}
                for n in evidence["nodes"]
            ],
        }

    # ── Internal ─────────────────────────────────────────────────────────────

    def _compute_node_evidence(
        self,
        node: dict[str, Any],
        experiences: list[Any],
        knowledge_items: list[Any],
        patterns: dict,
        facts: list[Any],
        act_graph_stats: dict[str, Any],
    ) -> dict[str, Any]:
        node_id = node.get("id", "")
        title = node.get("title", "")
        description = node.get("description", "")
        text = f"{title} {description}".strip() or node.get("title", "")
        goal_type = _classify_goal(text)
        keywords = _extract_domain_keywords(text)

        evidence_items: list[dict] = []
        risk_items: list[dict] = []

        # ── 1. Match against past experiences (via SimilarityScorer) ──────
        scorer = self._get_similarity_scorer()
        matched = scorer.filter_and_score(
            experiences, goal=text, goal_type=goal_type,
            tags=list(keywords),
        )
        matched_experiences = len(matched)
        failed_experiences = 0
        for score, exp in matched:
            exp_success = getattr(exp, "success", True)
            exp_id = getattr(exp, "activity_id", None) or ""
            if not exp_success:
                failed_experiences += 1
            evidence_items.append({
                "type": "experience",
                "id": exp_id[:16],
                "summary": (getattr(exp, "goal", None) or "")[:80],
                "relevance": round(score, 2),
                "success": exp_success,
                "duration": getattr(exp, "duration_seconds", None),
            })

        # ── 2. Match against knowledge items ──────────────────────────────
        for ki in (knowledge_items or []):
            ki_claim = getattr(ki, "claim", None) or ""
            ki_category = getattr(ki, "category", None) or ""
            ki_confidence = getattr(ki, "confidence", 0.5)
            ki_id = getattr(ki, "knowledge_id", None) or ""
            ki_evidence = getattr(ki, "evidence_count", 1)

            claim_keywords = _extract_domain_keywords(ki_claim)
            overlap = keywords & claim_keywords

            if overlap:
                evidence_items.append({
                    "type": ki_category if ki_category else "principle",
                    "id": ki_id[:16],
                    "summary": ki_claim[:80],
                    "confidence": ki_confidence,
                    "evidence_count": ki_evidence,
                })

        # ── 3. Match against research facts (FactStore) ───────────────────
        fact_keywords = " ".join(keywords)
        matched_facts = []
        for fact in (facts or []):
            fact_claim = getattr(fact, "claim", None) or ""
            fact_cat = getattr(fact, "category", None) or ""
            fact_source = getattr(fact, "source_url", None) or ""
            fact_id = getattr(fact, "fact_id", None) or ""
            fact_confidence = getattr(fact, "confidence", 0.5)
            fact_keywords_set = _extract_domain_keywords(fact_claim)
            overlap = keywords & fact_keywords_set
            if overlap:
                matched_facts.append(fact)
                evidence_items.append({
                    "type": "research_fact",
                    "id": fact_id[:16],
                    "summary": fact_claim[:80],
                    "confidence": fact_confidence,
                    "relevance": round(len(overlap) / max(len(keywords), 1), 2),
                    "category": fact_cat,
                    "source": fact_source[:40] if fact_source else None,
                })

        # ── 4. Match against failure patterns ─────────────────────────────
        for pat_key, pat_entry in (patterns or {}).items():
            pat_text = pat_key.lower()
            if any(kw in pat_text for kw in keywords):
                strategies = getattr(pat_entry, "strategies", {})
                best = getattr(pat_entry, "best_strategy", lambda: None)()
                if not best and strategies:
                    best = list(strategies.keys())[0]
                stats = strategies.get(best) if best else None
                success_rate = getattr(stats, "success_rate", 0.5) if stats else 0.5
                risk_items.append({
                    "severity": "warning" if success_rate < 0.5 else "info",
                    "type": "known_failure",
                    "pattern": pat_key[:60],
                    "success_rate": success_rate,
                    "strategy": best,
                })

        # ── 5. ActivityGraph historical stats ─────────────────────────────
        tool_stats = act_graph_stats.get(goal_type, {})
        if tool_stats.get("total", 0) >= 3:
            sr = tool_stats.get("success_rate", 1.0)
            evidence_items.append({
                "type": "activity_graph",
                "id": "ag_history",
                "summary": f"Historical {goal_type} success rate: {sr:.0%} ({tool_stats['success']}/{tool_stats['total']})",
                "confidence": sr,
                "relevance": 1.0,
            })
            if sr < 0.5:
                risk_items.append({
                    "severity": "warning",
                    "type": "low_historical_success",
                    "detail": f"Historical {goal_type} success rate is {sr:.0%}",
                })

        # ── 6. Deduce risks ──────────────────────────────────────────────
        if matched_experiences == 0:
            risk_items.append({
                "severity": "critical",
                "type": "no_prior_examples",
                "detail": "No prior experiences match this task",
            })
        elif failed_experiences / max(matched_experiences, 1) > 0.3:
            risk_items.append({
                "severity": "warning",
                "type": "high_failure_rate",
                "detail": f"{failed_experiences}/{matched_experiences} prior attempts failed",
            })

        if len(keywords) <= 2:
            risk_items.append({
                "severity": "warning",
                "type": "vague_description",
                "detail": "Task description has very few distinguishing keywords",
            })

        if goal_type == "build":
            risk_items.append({
                "severity": "info",
                "type": "build_task",
                "detail": "Build tasks may have hidden dependencies (API, SDK, credentials)",
            })

        # ── Compute per-node confidence ──────────────────────────────────
        confidence = self._compute_confidence(
            matched_experiences=matched_experiences,
            failed_experiences=failed_experiences,
            evidence_items=evidence_items,
            risk_items=risk_items,
        )

        return {
            "node_id": node_id,
            "title": title,
            "confidence": round(confidence, 2),
            "evidence": evidence_items[:20],
            "evidence_count": len(evidence_items),
            "risks": risk_items,
            "risk_count": len(risk_items),
        }

    def _compute_alternatives(
        self, node: dict[str, Any], knowledge_items: list[Any],
    ) -> list[dict]:
        title = node.get("title", "")
        description = node.get("description", "")
        text = f"{title} {description}".strip()
        goal_type = _classify_goal(text)
        keywords = _extract_domain_keywords(text)

        alts: list[dict] = []

        # ── 1. Technology alternatives (hardcoded patterns) ───────────────
        if goal_type == "build":
            if any(kw in keywords for kw in {"android", "mobile", "app"}):
                alts.append({
                    "approach": "Web-first",
                    "description": "Build a responsive web app instead of native",
                    "pros": ["Cross-platform", "Faster iteration"],
                    "cons": ["Less native feel", "Limited hardware access"],
                })
                alts.append({
                    "approach": "Flutter / Cross-platform",
                    "description": "Use Flutter, React Native, or Kotlin Multiplatform",
                    "pros": ["Shared codebase", "Native performance"],
                    "cons": ["Larger binary", "Platform-specific bugs"],
                })
            if any(kw in kw2 for kw2 in {"backend", "api", "server", "service"} for kw in keywords):
                alts.append({
                    "approach": "Serverless",
                    "description": "Use Lambda/Cloud Functions instead of dedicated server",
                    "pros": ["Auto-scaling", "No ops"],
                    "cons": ["Cold starts", "Vendor lock-in"],
                })

        # ── 2. Research vs Build alternatives ─────────────────────────────
        if goal_type == "build":
            alts.append({
                "approach": "Research-first",
                "description": "Research existing solutions before building from scratch",
                "pros": ["Avoid reinvention", "Known pitfalls"],
                "cons": ["Slower start", "May limit creativity"],
            })
        elif goal_type == "research":
            alts.append({
                "approach": "Prototype-first",
                "description": "Build a minimal prototype to validate assumptions",
                "pros": ["Concrete results", "Early feedback"],
                "cons": ["May miss depth", "Scope creep risk"],
            })

        # ── 3. Knowledge-driven alternatives ──────────────────────────────
        for ki in (knowledge_items or []):
            ki_claim = getattr(ki, "claim", None) or ""
            ki_category = getattr(ki, "category", None) or ""
            ki_confidence = getattr(ki, "confidence", 0.5)

            if ki_category not in ("pattern", "heuristic"):
                continue
            claim_lower = ki_claim.lower()
            if any(kw in claim_lower for kw in keywords):
                alts.append({
                    "approach": ki_claim[:60],
                    "description": f"Suggested by knowledge ({ki_category}, confidence={ki_confidence:.2f})",
                    "pros": [f"Confidence: {ki_confidence:.0%}"],
                    "cons": [],
                })

        return alts[:5]

    def _compute_overall(self, node_evidence: list[dict]) -> dict[str, Any]:
        if not node_evidence:
            return {"confidence": 0.0, "total_evidence": 0, "total_risks": 0}

        avg_conf = sum(n.get("confidence", 0) for n in node_evidence) / len(node_evidence)
        total_evidence = sum(n.get("evidence_count", 0) for n in node_evidence)
        total_risks = sum(n.get("risk_count", 0) for n in node_evidence)

        return {
            "confidence": round(avg_conf, 2),
            "total_nodes": len(node_evidence),
            "total_evidence": total_evidence,
            "total_risks": total_risks,
            "nodes_with_risks": sum(1 for n in node_evidence if n.get("risk_count", 0) > 0),
            "critical_risks": sum(1 for n in node_evidence for r in n.get("risks", []) if r.get("severity") == "critical"),
            "warning_risks": sum(1 for n in node_evidence for r in n.get("risks", []) if r.get("severity") == "warning"),
        }

    @staticmethod
    def _compute_confidence(
        matched_experiences: int,
        failed_experiences: int,
        evidence_items: list[dict],
        risk_items: list[dict],
    ) -> float:
        """Blended confidence score.

        Formula:
          base = 0.5 (neutral prior)
          +0.02 per matched_experience (capped at +0.30)
          -0.15 per failed_experience (capped at -0.40)
          +0.04 per evidence item beyond experiences (capped at +0.20)
          -0.10 per critical risk
          -0.05 per warning risk
          clamped to [0.05, 0.98]
        """
        score = 0.5
        score += min(matched_experiences * 0.02, 0.30)
        score -= min(failed_experiences * 0.15, 0.40)
        non_exp_evidence = max(0, len(evidence_items) - matched_experiences)
        score += min(non_exp_evidence * 0.04, 0.20)

        for risk in risk_items:
            if risk.get("severity") == "critical":
                score -= 0.10
            elif risk.get("severity") == "warning":
                score -= 0.05

        return max(0.05, min(0.98, score))

    # ── Store accessors ──────────────────────────────────────────────────────

    @staticmethod
    def _get_knowledge_store():
        from core.long_term_memory.store import KnowledgeStore
        return KnowledgeStore()

    @staticmethod
    def _get_failure_memory():
        from core.pattern_failure_memory import PatternFailureMemory
        return PatternFailureMemory()

    @staticmethod
    def _get_similarity_scorer():
        from core.strategy.similarity import SimilarityScorer
        return SimilarityScorer()

    @staticmethod
    def _get_all_facts() -> list[Any]:
        try:
            from core.research.storage import FactStore
            store = FactStore()
            return store.get_all_facts(limit=200) or []
        except Exception as e:
            logger.debug("Evidence engine: FactStore unavailable: %s", e)
            return []

    @staticmethod
    def _get_activity_graph_stats() -> dict[str, dict]:
        """Build success-rate stats by goal type from the activity graph."""
        try:
            from core.activity.storage import ActivityStore
            store = ActivityStore()
            nodes = store.get_all_nodes() or []
            stats: dict[str, dict] = {}
            for n in nodes:
                ntype = getattr(n, "node_type", None) or ""
                status = getattr(n, "status", None) or ""
                if ntype not in stats:
                    stats[ntype] = {"total": 0, "success": 0}
                stats[ntype]["total"] += 1
                if status in ("completed", "COMPLETED"):
                    stats[ntype]["success"] += 1
            for s in stats.values():
                s["success_rate"] = s["success"] / max(s["total"], 1)
            return stats
        except Exception as e:
            logger.debug("Evidence engine: ActivityStore unavailable: %s", e)
            return {}

    @staticmethod
    def _safe_call(fn, default=None):
        try:
            return fn()
        except Exception as e:
            logger.debug("Evidence engine query failed: %s", e)
            return default
