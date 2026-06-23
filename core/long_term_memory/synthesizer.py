"""KnowledgeSynthesizer — cross-activity pattern detection and knowledge consolidation.

Takes multiple ExperienceSummary objects and produces KnowledgeItems:
  - Pattern: repeated tool sequences / domains that succeed or fail
  - Heuristic: rules of thumb ("research before build reduces failures")
  - Warning: common failure modes
  - Principle: high-confidence generalizations
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from core.belief.integration import BeliefIntegrator
from core.long_term_memory.models import ExperienceSummary, KnowledgeItem
from core.long_term_memory.store import KnowledgeStore
from core.pattern_failure_memory import PatternFailureMemory

logger = logging.getLogger(__name__)

_MIN_EVIDENCE_FOR_PATTERN = 2
_MIN_EVIDENCE_FOR_PRINCIPLE = 3
_HIGH_CONFIDENCE = 0.8
_MEDIUM_CONFIDENCE = 0.5


class KnowledgeSynthesizer:
    """Cross-activity knowledge synthesis.

    Usage:
        syn = KnowledgeSynthesizer(store)
        items = syn.synthesize_from_experiences(experiences)

    Phase 16.1: Accepts optional BeliefIntegrator. When present, all
    confidence values are computed through the Belief Quality Engine
    instead of simple heuristic formulas.
    """

    def __init__(self, store: KnowledgeStore | None = None,
                 pattern_memory: PatternFailureMemory | None = None,
                 belief_integrator: BeliefIntegrator | None = None):
        self._store = store or KnowledgeStore()
        self._pattern_memory = pattern_memory or PatternFailureMemory()
        self._belief = belief_integrator

    # ── Main synthesis pipeline ────────────────────────────────────────

    def synthesize_from_experiences(
        self, experiences: list[ExperienceSummary],
    ) -> list[KnowledgeItem]:
        """Run the full synthesis pipeline over a batch of experiences.

        Returns newly created KnowledgeItems (also persisted).
        """
        new_items: list[KnowledgeItem] = []
        new_items.extend(self._synthesize_domain_patterns(experiences))
        new_items.extend(self._synthesize_tool_patterns(experiences))
        new_items.extend(self._synthesize_failure_patterns(experiences))
        new_items.extend(self._synthesize_principles(experiences))

        for item in new_items:
            self._store.insert_knowledge(item)

        if new_items:
            logger.info("KnowledgeSynthesizer: created %d new knowledge items",
                        len(new_items))
        return new_items

    def synthesize_all(self, limit: int = 100) -> list[KnowledgeItem]:
        """Load all stored experiences and synthesize."""
        experiences = self._store.get_all_experiences(limit)
        return self.synthesize_from_experiences(experiences)

    # ── Pattern detection ──────────────────────────────────────────────

    def _compute_confidence(self, category: str, evidence_count: int,
                             domain: str = "general",
                             current_confidence: float | None = None,
                             created_at=None) -> float:
        """Compute confidence via BeliefIntegrator if available, else heuristic."""
        if self._belief is not None:
            dc = self._belief.adjust_knowledge_confidence(
                category=category,
                evidence_count=evidence_count,
                domain=domain,
                current_confidence=current_confidence,
                created_at=created_at or datetime.utcnow(),
            )
            return dc.overall
        return current_confidence or 0.5

    def _synthesize_domain_patterns(
        self, experiences: list[ExperienceSummary],
    ) -> list[KnowledgeItem]:
        """Find domains where success rate is notably high or low."""
        items: list[KnowledgeItem] = []
        domain_groups: dict[str, list[bool]] = {}

        for exp in experiences:
            domain_groups.setdefault(exp.domain, []).append(exp.success)

        for domain, outcomes in domain_groups.items():
            if len(outcomes) < _MIN_EVIDENCE_FOR_PATTERN:
                continue
            success_rate = sum(1 for s in outcomes if s) / len(outcomes)
            now = datetime.utcnow()
            if success_rate >= _HIGH_CONFIDENCE:
                items.append(KnowledgeItem(
                    knowledge_id=f"kn_{uuid.uuid4().hex[:12]}",
                    category="pattern",
                    claim=f"Projects in domain '{domain}' succeed at {success_rate:.0%} rate",
                    confidence=self._compute_confidence(
                        category="pattern", evidence_count=len(outcomes),
                        domain=domain, current_confidence=success_rate,
                        created_at=now,
                    ),
                    evidence_count=len(outcomes),
                    tags=[domain, "domain_success"],
                    created_at=now,
                    last_validated=now,
                ))
            elif success_rate <= 0.3 and len(outcomes) >= _MIN_EVIDENCE_FOR_PATTERN:
                items.append(KnowledgeItem(
                    knowledge_id=f"kn_{uuid.uuid4().hex[:12]}",
                    category="warning",
                    claim=f"Projects in domain '{domain}' fail frequently ({success_rate:.0%} success)",
                    confidence=self._compute_confidence(
                        category="warning", evidence_count=len(outcomes),
                        domain=domain, current_confidence=1.0 - success_rate,
                        created_at=now,
                    ),
                    evidence_count=len(outcomes),
                    tags=[domain, "domain_failure"],
                    created_at=now,
                    last_validated=now,
                ))
        return items

    def _synthesize_tool_patterns(
        self, experiences: list[ExperienceSummary],
    ) -> list[KnowledgeItem]:
        """Find tools that correlate with success or failure."""
        items: list[KnowledgeItem] = []
        tool_outcomes: dict[str, list[bool]] = {}

        for exp in experiences:
            for tool in exp.tools_used:
                tool_outcomes.setdefault(tool, []).append(exp.success)

        for tool, outcomes in tool_outcomes.items():
            if len(outcomes) < _MIN_EVIDENCE_FOR_PATTERN:
                continue
            success_rate = sum(1 for s in outcomes if s) / len(outcomes)
            now = datetime.utcnow()
            if success_rate >= _HIGH_CONFIDENCE:
                items.append(KnowledgeItem(
                    knowledge_id=f"kn_{uuid.uuid4().hex[:12]}",
                    category="heuristic",
                    claim=f"Tool '{tool}' correlates with high success ({success_rate:.0%})",
                    confidence=self._compute_confidence(
                        category="heuristic", evidence_count=len(outcomes),
                        domain="general", current_confidence=success_rate,
                        created_at=now,
                    ),
                    evidence_count=len(outcomes),
                    tags=[tool, "tool_success"],
                    created_at=now,
                    last_validated=now,
                ))
        return items

    def _synthesize_failure_patterns(
        self, experiences: list[ExperienceSummary],
    ) -> list[KnowledgeItem]:
        """Find common failure modes across experiences.

        Merges activity-level errors with PatternFailureMemory entries.
        """
        items: list[KnowledgeItem] = []
        error_counter: Counter[str] = Counter()
        error_domains: dict[str, set[str]] = {}

        for exp in experiences:
            if not exp.success and exp.error_summary:
                # Use first 60 chars as the error key
                key = exp.error_summary[:60]
                error_counter[key] += 1
                error_domains.setdefault(key, set()).add(exp.domain)

        for error_key, count in error_counter.items():
            if count < _MIN_EVIDENCE_FOR_PATTERN:
                continue
            domain_list = sorted(error_domains[error_key])
            domains = ", ".join(domain_list)
            now = datetime.utcnow()
            items.append(KnowledgeItem(
                knowledge_id=f"kn_{uuid.uuid4().hex[:12]}",
                category="warning",
                claim=f"Common failure: '{error_key[:80]}' (seen {count}x in {domains})",
                confidence=self._compute_confidence(
                    category="warning", evidence_count=count,
                    domain=domain_list[0] if domain_list else "general",
                    current_confidence=min(0.9, 0.3 + count * 0.15),
                    created_at=now,
                ),
                evidence_count=count,
                tags=domain_list + ["failure_pattern"],
                created_at=now,
                last_validated=now,
            ))

        # Merge in PatternFailureMemory entries
        pattern_stats = self._pattern_memory.get_stats()
        top_patterns = sorted(
            pattern_stats.get("patterns", {}).items(),
            key=lambda x: x[1].get("count", 0),
            reverse=True,
        )[:5]
        for pattern_key, stats in top_patterns:
            if stats.get("count", 0) < _MIN_EVIDENCE_FOR_PATTERN:
                continue
            success_rate = stats.get("success_rate", 0.5)
            now = datetime.utcnow()
            if success_rate < 0.5:
                items.append(KnowledgeItem(
                    knowledge_id=f"kn_{uuid.uuid4().hex[:12]}",
                    category="warning",
                    claim=f"Error pattern persists: '{pattern_key[:80]}' has {success_rate:.0%} fix rate",
                    confidence=self._compute_confidence(
                        category="warning", evidence_count=stats.get("count", 1),
                        domain="general", current_confidence=1.0 - success_rate,
                        created_at=now,
                    ),
                    evidence_count=stats.get("count", 1),
                    source_pattern_keys=[pattern_key],
                    tags=["error_pattern", "failure_memory"],
                    created_at=now,
                    last_validated=now,
                ))

        return items

    def _synthesize_principles(
        self, experiences: list[ExperienceSummary],
    ) -> list[KnowledgeItem]:
        """Find high-confidence, high-evidence generalizations.

        Principles require the strongest evidence.
        """
        items: list[KnowledgeItem] = []
        domain_count = len(experiences)

        if domain_count < _MIN_EVIDENCE_FOR_PRINCIPLE:
            return items

        # Principle: "most activities succeed"
        successes = sum(1 for e in experiences if e.success)
        overall_rate = successes / domain_count
        now = datetime.utcnow()
        if domain_count >= _MIN_EVIDENCE_FOR_PRINCIPLE:
            items.append(KnowledgeItem(
                knowledge_id=f"kn_{uuid.uuid4().hex[:12]}",
                category="principle",
                claim=f"Overall activity success rate: {overall_rate:.0%} across {domain_count} activities",
                confidence=self._compute_confidence(
                    category="principle", evidence_count=domain_count,
                    domain="general", current_confidence=overall_rate,
                    created_at=now,
                ),
                evidence_count=domain_count,
                tags=["overall", "meta"],
                created_at=now,
                last_validated=now,
            ))

        # Principle: "activities with error summaries fail more often"
        with_errors = [e for e in experiences if e.error_summary]
        if with_errors:
            error_fail_rate = sum(1 for e in with_errors if not e.success) / len(with_errors)
            if len(with_errors) >= _MIN_EVIDENCE_FOR_PRINCIPLE and error_fail_rate > 0.3:
                items.append(KnowledgeItem(
                    knowledge_id=f"kn_{uuid.uuid4().hex[:12]}",
                    category="principle",
                    claim=f"Activities with errors fail at {error_fail_rate:.0%} rate ({len(with_errors)} examples)",
                    confidence=self._compute_confidence(
                        category="principle", evidence_count=len(with_errors),
                        domain="general",
                        current_confidence=min(0.85, error_fail_rate + 0.2),
                        created_at=now,
                    ),
                    evidence_count=len(with_errors),
                    tags=["errors", "failure"],
                    created_at=now,
                    last_validated=now,
                ))

        return items
