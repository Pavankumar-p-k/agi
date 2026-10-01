"""Evidence query layer for strategic reasoning (Phase 12.4-12.6)."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, List, Optional

from core.strategy.models import EvidenceBundle
from core.strategy.similarity import SimilarityScorer, infer_domain


@dataclass
class PastActivity:
    """A previously observed activity, normalised for strategy reasoning."""

    activity_id: str = ""
    goal: str = ""
    domain: str = ""
    status: str = ""
    duration_days: float = 0.0
    success: bool = True


@dataclass
class DomainEvidence:
    """Aggregate evidence for a single domain."""

    domain: str = ""
    sample_size: int = 0
    success_rate: float = 0.0
    avg_duration_days: float = 0.0


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def _experience_duration_days(experience) -> float:
    seconds = _get(experience, "duration_seconds")
    if seconds:
        return float(seconds) / 86400.0
    days = _get(experience, "duration_days")
    if days is not None:
        return float(days)
    return 0.0


def _node_duration_days(node) -> float:
    started = _get(node, "started_at")
    completed = _get(node, "completed_at")
    if started and completed:
        return max(0.0, (completed - started).total_seconds() / 86400.0)
    return 0.0


def _node_success(node) -> bool:
    status = _get(node, "status")
    value = getattr(status, "value", status)
    return str(value).upper() == "COMPLETED"


class MemoryAdapter:
    """Build evidence bundles from activity, knowledge and fact stores."""

    def __init__(
        self,
        activity_store=None,
        knowledge_store=None,
        fact_store=None,
        belief_integrator=None,
    ) -> None:
        self._activity_store = activity_store
        self._knowledge_store = knowledge_store
        self._fact_store = fact_store
        self.belief_integrator = belief_integrator
        self.similarity = SimilarityScorer()

    # ── helpers ──────────────────────────────────────────────────────

    def _safe(self, fn, default):
        try:
            return fn()
        except Exception:
            return default

    def _experiences(self, domain: str) -> List:
        if self._knowledge_store is None:
            return []
        return self._safe(
            lambda: list(
                self._knowledge_store.get_experiences_by_domain(domain, limit=20)
            ),
            [],
        ) or []

    def _nodes(self, goal: str) -> List:
        if self._activity_store is None:
            return []
        return self._safe(
            lambda: list(self._activity_store.search_nodes(goal, limit=10)), []
        ) or []

    def _failure_patterns(self, goal: str, domain: str) -> List[str]:
        if self._knowledge_store is None:
            return []
        items: List = []
        if hasattr(self._knowledge_store, "search_knowledge"):
            items = self._safe(
                lambda: list(self._knowledge_store.search_knowledge(domain, limit=10)),
                [],
            ) or []
        failures = []
        for item in items:
            category = _get(item, "category", "")
            if str(category) == "warning":
                claim = _get(item, "claim", "")
                if claim:
                    failures.append(claim)
        return failures

    # ── bundle construction ──────────────────────────────────────────

    def _build_bundle(
        self,
        durations: List[float],
        successes: List[bool],
        goal_labels: List[str],
        failures: List[str],
        avg_similarity: float,
        domain: str = "",
    ) -> EvidenceBundle:
        sample_size = len(durations)
        avg_duration = statistics.mean(durations) if durations else 0.0
        std = statistics.pstdev(durations) if len(durations) > 1 else 0.0
        success_rate = (
            sum(1 for s in successes if s) / sample_size if sample_size else 0.0
        )

        if self.belief_integrator is not None:
            confidence = self.belief_integrator.adjust_evidence_bundle_confidence(
                sample_size=sample_size, domain=domain
            )
        else:
            confidence = min(1.0, sample_size / 20.0) if sample_size else 0.0

        return EvidenceBundle(
            sample_size=sample_size,
            avg_duration_days=avg_duration,
            duration_std=std,
            success_rate=success_rate,
            avg_similarity=avg_similarity,
            common_failures=list(failures),
            similar_activities=list(goal_labels),
            confidence=confidence,
        )

    # ── public API ───────────────────────────────────────────────────

    def get_evidence(
        self, goal: str, goal_type: str = "build", tags: Optional[List[str]] = None
    ) -> EvidenceBundle:
        tags = tags or []
        domain = infer_domain(goal)

        durations: List[float] = []
        successes: List[bool] = []
        labels: List[str] = []
        similarities: List[float] = []

        experiences = self._experiences(domain)
        for score, exp in self.similarity.filter_and_score(
            experiences, goal, goal_type, tags
        ):
            durations.append(_experience_duration_days(exp))
            successes.append(bool(_get(exp, "success", False)))
            labels.append(_get(exp, "goal", "") or "")
            similarities.append(score)

        for node in self._nodes(goal):
            node_domain = infer_domain(_get(node, "label", ""))
            if domain and node_domain and node_domain != domain:
                continue
            durations.append(_node_duration_days(node))
            successes.append(_node_success(node))
            labels.append(_get(node, "label", "") or "")

        failures = self._failure_patterns(goal, domain)
        avg_similarity = statistics.mean(similarities) if similarities else 0.0

        return self._build_bundle(
            durations=durations,
            successes=successes,
            goal_labels=labels,
            failures=failures,
            avg_similarity=avg_similarity,
            domain=domain,
        )

    def query_similar_activities(self, goal: str) -> List[PastActivity]:
        results = []
        for node in self._nodes(goal):
            results.append(
                PastActivity(
                    activity_id=_get(node, "activity_id", "") or "",
                    goal=_get(node, "label", "") or "",
                    domain=infer_domain(_get(node, "label", "")),
                    status=str(getattr(_get(node, "status", ""), "value",
                                      _get(node, "status", ""))),
                    duration_days=_node_duration_days(node),
                    success=_node_success(node),
                )
            )
        return results

    def query_domain_evidence(self, domains: List[str]) -> List[DomainEvidence]:
        results = []
        for domain in domains or []:
            experiences = self._experiences(domain)
            if not experiences:
                continue
            durations = [_experience_duration_days(e) for e in experiences]
            success_rate = (
                sum(1 for e in experiences if _get(e, "success", False))
                / len(experiences)
            )
            results.append(
                DomainEvidence(
                    domain=domain,
                    sample_size=len(experiences),
                    success_rate=success_rate,
                    avg_duration_days=(
                        statistics.mean(durations) if durations else 0.0
                    ),
                )
            )
        return results

    def query_research_facts(self, goal: str) -> List[str]:
        if self._fact_store is None:
            return []
        facts = self._safe(
            lambda: list(self._fact_store.search_facts(goal, limit=5)), []
        ) or []
        return [
            _get(f, "claim", "") for f in facts if _get(f, "claim", "")
        ]

    def query_experiment_results(self, tags: List[str]) -> List:
        return []
