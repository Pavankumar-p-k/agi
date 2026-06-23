"""BehaviorAdapter — injects learned knowledge into the agent decision pipeline.

Provides query points for:
  - Planner: what patterns apply to this goal?
  - Research: what do we already know about this topic?
  - Coding: what risks does this change carry?

Each adapter method returns structured context that can be injected
into prompts, risk calculations, or planning decisions.
"""

from __future__ import annotations

import logging
from typing import Any

from core.long_term_memory.models import KnowledgeItem, KnowledgeQuery
from core.long_term_memory.store import KnowledgeStore
from core.coding.change_planner import ChangePlanner
from core.coding.repository_indexer import RepositoryIndexer

logger = logging.getLogger(__name__)


class BehaviorAdapter:
    """Bridges stored knowledge into agent decision-making.

    Usage:
        adapter = BehaviorAdapter(knowledge_store)
        context = adapter.for_planner("Build Android payment feature")
        # inject context into planner prompt
    """

    def __init__(self, store: KnowledgeStore | None = None):
        self._store = store or KnowledgeStore()

    # ── Planner influence ─────────────────────────────────────────────

    def for_planner(self, goal: str, domain: str | None = None) -> dict[str, Any]:
        """Return knowledge context relevant to a planner goal.

        Returns:
          - matching domain patterns
          - failure warnings
          - relevant heuristics
        """
        result: dict[str, Any] = {
            "domain_patterns": [],
            "warnings": [],
            "heuristics": [],
            "principles": [],
        }

        # Domain-aware patterns
        if domain:
            domain_items = self._store.query_knowledge(KnowledgeQuery(
                tag=domain, min_confidence=0.5, limit=5,
            ))
            for item in domain_items:
                if item.category == "pattern":
                    result["domain_patterns"].append(item.to_dict())
                elif item.category == "warning":
                    result["warnings"].append(item.to_dict())
                elif item.category == "heuristic":
                    result["heuristics"].append(item.to_dict())

        # Text search for goal-relevant knowledge
        text_matches = self._store.search_knowledge(goal, limit=5)
        for item in text_matches:
            entry = item.to_dict()
            if entry not in result["domain_patterns"] + result["warnings"] + result["heuristics"]:
                if item.category == "principle":
                    result["principles"].append(entry)
                elif item.category == "warning":
                    if entry not in result["warnings"]:
                        result["warnings"].append(entry)

        logger.debug("BehaviorAdapter: planner context has %d items",
                     sum(len(v) for v in result.values()))
        return result

    # ── Research influence ────────────────────────────────────────────

    def for_research(self, question: str) -> dict[str, Any]:
        """Return what JARVIS already knows about a research question.

        This allows research to skip well-known topics and focus on gaps.
        """
        result: dict[str, Any] = {
            "known_claims": [],
            "confidence_gaps": [],
        }

        matches = self._store.search_knowledge(question, limit=10)
        for item in matches:
            entry = item.to_dict()
            if item.category in ("factoid", "pattern"):
                result["known_claims"].append(entry)
            elif item.confidence < 0.6:
                result["confidence_gaps"].append(entry)

        # High-confidence knowledge can short-circuit research
        high_conf = [m for m in matches if m.confidence >= 0.8]
        result["sufficient_confidence"] = len(high_conf) >= 2

        return result

    # ── Coding influence ──────────────────────────────────────────────

    def for_coding(self, file_path: str | None = None,
                   change_type: str | None = None,
                   indexer: RepositoryIndexer | None = None) -> dict[str, Any]:
        """Return risk-relevant knowledge for a coding change.

        Can augment ImpactAnalyzer risk scores with learned patterns.
        """
        result: dict[str, Any] = {
            "risk_factors": [],
            "known_issues": [],
            "risk_modifier": 0.0,
        }

        # File-specific warnings
        if file_path:
            matches = self._store.search_knowledge(file_path, limit=5)
            for item in matches:
                if item.category == "warning":
                    result["known_issues"].append(item.to_dict())
                    result["risk_modifier"] += 0.1

        # Change-type warnings
        if change_type:
            matches = self._store.query_knowledge(KnowledgeQuery(
                tag=change_type, min_confidence=0.3, limit=5,
            ))
            for item in matches:
                if item.category == "warning":
                    result["risk_factors"].append(item.to_dict())
                    result["risk_modifier"] += 0.05

        logger.debug("BehaviorAdapter: coding context risk_modifier=%.2f",
                     result["risk_modifier"])
        return result

    # ── Utility ───────────────────────────────────────────────────────

    def format_for_prompt(self, context: dict[str, Any]) -> str:
        """Format knowledge context as a compact prompt injection string."""
        parts: list[str] = []

        if context.get("domain_patterns"):
            parts.append("Known patterns:")
            for p in context["domain_patterns"][:3]:
                parts.append(f"  - {p['claim']} ({p['confidence']:.0%} confidence)")

        if context.get("warnings"):
            parts.append("Known warnings:")
            for w in context["warnings"][:3]:
                parts.append(f"  - {w['claim']}")

        if context.get("heuristics"):
            parts.append("Heuristics:")
            for h in context["heuristics"][:2]:
                parts.append(f"  - {h['claim']}")

        if context.get("principles"):
            parts.append("General principles:")
            for p in context["principles"][:2]:
                parts.append(f"  - {p['claim']}")

        return "\n".join(parts)
