"""MemoryAdapter — bridges the Strategic Reasoning Layer to existing memory and activity systems.

Phase 12.5: Wired to ActivityStore, KnowledgeStore, and FactStore.

Pipeline:
  ActivityGraph + KnowledgeStore + ResearchFacts
      ↓
  MemoryAdapter.get_evidence()
      ↓
  EvidenceBundle
      ↓
  OutcomePredictor._blend()

All queries are read-only. Errors in any store are caught and logged
so the strategy layer degrades gracefully when stores are empty.
"""

from __future__ import annotations

import logging
from statistics import mean, StatisticsError
from typing import Any

from core.belief.integration import BeliefIntegrator
from core.strategy.models import EvidenceBundle

logger = logging.getLogger(__name__)

# Keyword-based domain classification (shared with predictor)
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "android": ["android", "apk", "mobile", "kotlin", "java"],
    "web": ["web", "frontend", "react", "api", "backend", "server"],
    "data": ["data", "analytics", "pipeline", "etl", "database"],
    "ml": ["ml", "model", "training", "inference", "neural"],
    "infra": ["infra", "deploy", "kubernetes", "docker", "cloud"],
}


def _detect_domains(goal: str) -> list[str]:
    """Detect domain keywords in the goal."""
    goal_lower = goal.lower()
    found: list[str] = []
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in goal_lower for kw in keywords):
            found.append(domain)
    return found or ["general"]


class PastActivity:
    """Summary of a past activity relevant to strategy prediction."""
    def __init__(self, goal: str, status: str, duration_days: float,
                 agent_count: int, error_count: int, domain: str):
        self.goal = goal
        self.status = status
        self.duration_days = duration_days
        self.agent_count = agent_count
        self.error_count = error_count
        self.domain = domain


class DomainEvidence:
    """Aggregated evidence for a domain from long-term memory."""
    def __init__(self, domain: str, success_rate: float,
                 avg_duration_days: float, pattern_count: int):
        self.domain = domain
        self.success_rate = success_rate
        self.avg_duration_days = avg_duration_days
        self.pattern_count = pattern_count


class MemoryAdapter:
    """Read-only query adapter for strategic evidence.

    Phase 12.5: wired to ActivityStore, KnowledgeStore, and FactStore.
    Default constructor creates lazy store instances. For testing, inject
    pre-configured stores.
    """

    def __init__(self, activity_store=None, knowledge_store=None,
                 fact_store=None, belief_integrator: BeliefIntegrator | None = None):
        self._activity_store = activity_store
        self._knowledge_store = knowledge_store
        self._fact_store = fact_store
        self._belief = belief_integrator

    # -- Lazy store accessors --

    def _get_knowledge_store(self):
        if self._knowledge_store is None:
            from core.long_term_memory.store import KnowledgeStore
            self._knowledge_store = KnowledgeStore()
        return self._knowledge_store

    def _get_activity_store(self):
        if self._activity_store is None:
            from core.activity.storage import ActivityStore
            self._activity_store = ActivityStore()
        return self._activity_store

    def _get_fact_store(self):
        if self._fact_store is None:
            from core.research.storage import FactStore
            self._fact_store = FactStore()
        return self._fact_store

    # -- Primary evidence API --

    def get_evidence(self, goal: str, goal_type: str = "build",
                     tags: list[str] | None = None) -> EvidenceBundle:
        """Get aggregated evidence bundle for a goal.

        Phase 12.6: ExperienceSummaries are scored by similarity against
        the current goal so only the most relevant past activities contribute.
        """
        domains = _detect_domains(goal)

        durations: list[float] = []
        successes: list[bool] = []
        goal_labels: list[str] = []
        similarity_scores: list[float] = []
        failures: list[str] = []

        # 1. Query ExperienceSummaries — similarity-scored and filtered
        self._collect_experience_evidence(domains, goal, goal_type,
                                          tags or [], durations,
                                          successes, goal_labels,
                                          similarity_scores)

        # 2. Query ActivityStore nodes (supplemental, no similarity filter)
        self._collect_activity_evidence(goal, domains, durations, successes, goal_labels)

        # 3. Query KnowledgeStore for failure patterns
        self._collect_failure_patterns(domains, failures)

        # 4. Compute avg_similarity from scored experiences
        avg_sim = 0.0
        if similarity_scores:
            avg_sim = sum(similarity_scores) / len(similarity_scores)

        # 5. Build bundle
        return self._build_bundle(durations, successes, goal_labels,
                                  failures, avg_sim, domains[0] if domains else "general")

    # -- Internal collectors --

    def _collect_experience_evidence(self, domains: list[str],
                                     goal: str, goal_type: str,
                                     tags: list[str],
                                     durations: list[float],
                                     successes: list[bool],
                                     goal_labels: list[str],
                                     similarity_scores: list[float]) -> None:
        """Collect evidence from KnowledgeStore, ranked by similarity.

        Phase 12.6: uses SimilarityScorer to score and filter experiences.
        Only those above the similarity threshold contribute to evidence.
        """
        from core.strategy.similarity import SimilarityScorer
        scorer = SimilarityScorer()

        all_experiences: list = []
        ks = self._get_knowledge_store()
        for domain in domains:
            try:
                domain_exps = ks.get_experiences_by_domain(domain, limit=20)
                all_experiences.extend(domain_exps)
            except Exception as exc:
                logger.debug("MemoryAdapter: experience query error for %s: %s",
                             domain, exc)

        # Score, filter, and sort by similarity
        scored = scorer.filter_and_score(all_experiences, goal, goal_type, tags)

        for score, exp in scored:
            if exp.duration_seconds is not None:
                durations.append(exp.duration_seconds / 86400.0)
            successes.append(exp.success)
            similarity_scores.append(score)
            if exp.goal and len(goal_labels) < 10:
                goal_labels.append(exp.goal[:80])

    def _collect_activity_evidence(self, goal: str, domains: list[str],
                                   durations: list[float],
                                   successes: list[bool],
                                   goal_labels: list[str]) -> None:
        """Collect evidence from ActivityStore by searching for matching labels."""
        store = self._get_activity_store()
        seen: set[str] = set()
        tokens = [t.lower() for t in goal.split() if len(t) > 3]
        for token in tokens[:5]:
            try:
                nodes = store.search_nodes(token, limit=10)
                for node in nodes:
                    if node.node_id in seen:
                        continue
                    seen.add(node.node_id)
                    if node.started_at and node.completed_at:
                        delta = node.completed_at - node.started_at
                        durations.append(delta.total_seconds() / 86400.0)
                    successes.append(node.status.value == "COMPLETED")
                    if len(goal_labels) < 10:
                        goal_labels.append(node.label[:80])
            except Exception as exc:
                logger.debug("MemoryAdapter: activity query error for %s: %s",
                             token, exc)

    def _collect_failure_patterns(self, domains: list[str],
                                  failures: list[str]) -> None:
        """Collect failure warnings from KnowledgeStore."""
        ks = self._get_knowledge_store()
        try:
            from core.long_term_memory.models import KnowledgeQuery
            warnings = ks.query_knowledge(
                KnowledgeQuery(category="warning", min_confidence=0.3, limit=20)
            )
            for w in warnings:
                if any(d in " ".join(w.tags).lower() for d in domains):
                    failures.append(w.claim)
        except Exception as exc:
            logger.debug("MemoryAdapter: failure pattern query error: %s", exc)

    # -- Bundle builder --

    def _build_bundle(self, durations: list[float],
                      successes: list[bool],
                      goal_labels: list[str],
                      failures: list[str],
                      avg_similarity: float = 0.0,
                      domain: str = "general") -> EvidenceBundle:
        """Aggregate collected evidence into an EvidenceBundle.

        Phase 12.6: avg_similarity is forwarded from the similarity scorer
        so the bundle reflects relevance quality, not just quantity.
        """
        sample_size = len(successes)
        if sample_size == 0:
            # Preserve failure patterns even without quantitative evidence
            return EvidenceBundle(
                common_failures=failures[:5],
                similar_activities=goal_labels[:5],
            )

        avg_dur = mean(durations) if durations else 0.0

        dur_std = 0.0
        if len(durations) >= 2:
            try:
                dur_std = mean((d - avg_dur) ** 2 for d in durations) ** 0.5
            except (StatisticsError, ZeroDivisionError):
                pass

        success_rate = sum(1 for s in successes if s) / len(successes)

        if self._belief is not None:
            bundle_conf = self._belief.adjust_evidence_bundle_confidence(
                sample_size=sample_size,
                domain=domain,
            )
        else:
            bundle_conf = min(sample_size / 20.0, 1.0) * 0.85 + 0.05

        return EvidenceBundle(
            sample_size=sample_size,
            avg_duration_days=round(avg_dur, 1),
            duration_std=round(dur_std, 2),
            success_rate=round(success_rate, 3),
            avg_similarity=round(avg_similarity, 3),
            common_failures=failures[:5],
            similar_activities=goal_labels[:5],
            confidence=round(bundle_conf, 3),
        )

    # -- Query methods (kept for backward compatibility) --

    def query_similar_activities(self, goal: str, limit: int = 10) -> list[PastActivity]:
        """Find past activities with similar goals.
        
        Now wired to ActivityStore + KnowledgeStore.
        """
        domains = _detect_domains(goal)
        results: list[PastActivity] = []
        seen: set[str] = set()

        # From ActivityStore
        store = self._get_activity_store()
        tokens = [t.lower() for t in goal.split() if len(t) > 3]
        for token in tokens[:5]:
            try:
                nodes = store.search_nodes(token, limit=5)
                for node in nodes:
                    if node.node_id in seen:
                        continue
                    seen.add(node.node_id)
                    dur = 0.0
                    if node.started_at and node.completed_at:
                        dur = (node.completed_at - node.started_at).total_seconds() / 86400.0
                    results.append(PastActivity(
                        goal=node.label, status=node.status.value,
                        duration_days=round(dur, 1),
                        agent_count=1 if node.agent_id else 0,
                        error_count=1 if node.status.value == "FAILED" else 0,
                        domain=domains[0] if domains else "general",
                    ))
            except Exception:
                pass

        return results[:limit]

    def query_domain_evidence(self, domains: list[str]) -> list[DomainEvidence]:
        """Get aggregated evidence for specific domains.
        
        Now wired to KnowledgeStore.
        """
        ks = self._get_knowledge_store()
        results: list[DomainEvidence] = []
        for d in domains:
            try:
                experiences = ks.get_experiences_by_domain(d, limit=20)
                if not experiences:
                    continue
                successes = sum(1 for e in experiences if e.success)
                total = len(experiences)
                durations = [e.duration_seconds / 86400.0 for e in experiences
                             if e.duration_seconds]
                avg_dur = mean(durations) if durations else 0.0
                results.append(DomainEvidence(
                    domain=d,
                    success_rate=round(successes / total, 3),
                    avg_duration_days=round(avg_dur, 1),
                    pattern_count=total,
                ))
            except Exception:
                pass
        return results

    def query_research_facts(self, goal: str) -> list[str]:
        """Get relevant facts from research memory.
        
        Now wired to FactStore.
        """
        store = self._get_fact_store()
        facts: list[str] = []
        tokens = [t.lower() for t in goal.split() if len(t) > 3]
        for token in tokens[:3]:
            try:
                results = store.search_facts(token, limit=5)
                for f in results:
                    facts.append(f.claim[:200])
            except Exception:
                pass
        return facts

    def query_experiment_results(self, tags: list[str]) -> list[dict]:
        """Get outcomes from self-improvement experiments.
        
        Stub — ExperimentStore not yet wired to workflow.db.
        """
        return []
