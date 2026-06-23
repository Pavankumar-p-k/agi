"""Phase 12.6 — Similarity Scoring for goal-activity matching.

SimilarityScorer computes a multi-dimensional similarity score between
a current goal and a past activity (ExperienceSummary). Used by MemoryAdapter
to rank and filter evidence by relevance before aggregation.

Dimensions and weights:
  goal_type_match  (0.40) — same build/research/refactor/explore category
  tag_overlap      (0.25) — Jaccard similarity with tools_used (proxy for approach)
  domain_match     (0.20) — overlapping domain keywords
  text_similarity  (0.15) — word overlap between goal descriptions

MIN_SIMILARITY = 0.10 filters out completely unrelated activities.
MAX_RESULTS    = 20 caps the number returned for efficiency.
"""

from __future__ import annotations

from typing import Any


_GOAL_TYPE_PREFIXES: dict[str, list[str]] = {
    "build": ["build ", "create ", "develop ", "implement ", "make "],
    "research": ["research ", "investigate ", "study ", "learn ", "analyze "],
    "refactor": ["refactor ", "rewrite ", "restructure ", "migrate ", "redesign "],
    "explore": ["explore ", "find ", "discover ", "survey ", "audit "],
}

MIN_SIMILARITY = 0.10
MAX_RESULTS = 20


def classify_goal(goal: str) -> str:
    """Classify a goal string into a goal type (build/research/refactor/explore)."""
    goal_lower = goal.lower().strip()
    for gtype, prefixes in _GOAL_TYPE_PREFIXES.items():
        if any(goal_lower.startswith(p) for p in prefixes):
            return gtype
    return "build"


def _jaccard(a: set, b: set) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class SimilarityScorer:
    """Computes multi-dimensional similarity between a current goal and past activities.

    Stateless — safe to create fresh per query or reuse across queries.
    """

    WEIGHTS: dict[str, float] = {
        "goal_type": 0.40,
        "tag_overlap": 0.25,
        "domain": 0.20,
        "text": 0.15,
    }

    def score_experience(self, goal: str, goal_type: str,
                         tags: list[str], experience: Any) -> float:
        """Score similarity between a current goal and one past experience.

        The experience must have: goal, domain, tools_used (list).
        node_count is optional (for future complexity weighting).
        """
        past_goal = getattr(experience, "goal", None) or ""
        past_domain = getattr(experience, "domain", None) or "general"
        past_tools = getattr(experience, "tools_used", None) or []

        # Goal type match (0.40)
        past_type = classify_goal(past_goal)
        type_score = 1.0 if past_type == goal_type else 0.0

        # Tag/tool overlap (0.25) — tags ↔ tools_used
        tool_score = 0.0
        if tags and past_tools:
            tool_score = _jaccard(set(tags), set(past_tools))

        # Domain match (0.20)
        domain_score = 1.0 if past_domain == "general" else 0.0
        current_domains = self._detect_domains(goal)
        if current_domains:
            domain_score = 1.0 if any(
                d in past_domain or past_domain in d
                for d in current_domains
            ) else 0.0

        # Text similarity (0.15) — word overlap in goal descriptions
        current_words = set(goal.lower().split())
        past_words = set(past_goal.lower().split())
        text_score = _jaccard(current_words, past_words)

        score = (
            type_score * self.WEIGHTS["goal_type"]
            + tool_score * self.WEIGHTS["tag_overlap"]
            + domain_score * self.WEIGHTS["domain"]
            + text_score * self.WEIGHTS["text"]
        )
        return round(min(score, 1.0), 4)

    def filter_and_score(self, experiences: list, goal: str,
                         goal_type: str = "build",
                         tags: list[str] | None = None
                         ) -> list[tuple[float, Any]]:
        """Score and filter experiences by similarity to the current goal.

        Returns list of (score, experience) tuples sorted descending,
        filtered to those above MIN_SIMILARITY, capped at MAX_RESULTS.
        """
        tags = tags or []
        scored = [
            (self.score_experience(goal, goal_type, tags, e), e)
            for e in experiences
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(s, e) for s, e in scored if s >= MIN_SIMILARITY][:MAX_RESULTS]

    @staticmethod
    def _detect_domains(goal: str) -> list[str]:
        """Reuse domain detection from memory_adapter without direct import."""
        goal_lower = goal.lower()
        domains = []
        kw_map = {
            "android": ["android", "apk", "mobile", "kotlin", "java"],
            "web": ["web", "frontend", "react", "api", "backend", "server"],
            "data": ["data", "analytics", "pipeline", "etl", "database"],
            "ml": ["ml", "model", "training", "inference", "neural"],
            "infra": ["infra", "deploy", "kubernetes", "docker", "cloud"],
        }
        for domain, keywords in kw_map.items():
            if any(kw in goal_lower for kw in keywords):
                domains.append(domain)
        return domains
