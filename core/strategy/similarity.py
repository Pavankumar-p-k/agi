"""Goal/activity similarity scoring (Phase 12.6)."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from core.strategy.generator import classify_goal

MAX_RESULTS = 10
DEFAULT_THRESHOLD = 0.35

_KNOWN_DOMAINS = ["android", "ios", "web", "ml", "research", "backend",
                  "frontend", "data", "general"]

_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "with", "in", "on", "that",
    "my", "our", "your", "is", "are", "be",
}


def _tokens(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS}


def text_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    intersection = len(ta & tb)
    union = len(ta | tb)
    return intersection / union if union else 0.0


def infer_domain(text: str) -> str:
    lowered = (text or "").lower()
    for domain in _KNOWN_DOMAINS:
        if domain in lowered:
            return domain
    return ""


def _tag_value(tag) -> str:
    return getattr(tag, "value", tag)


class SimilarityScorer:
    """Score how similar a past activity is to a current goal."""

    def score_experience(
        self,
        goal: str,
        goal_type: str,
        tags: Optional[List[str]],
        experience,
    ) -> float:
        exp_goal = getattr(experience, "goal", "") or getattr(
            experience, "label", ""
        )
        exp_domain = getattr(experience, "domain", "") or infer_domain(exp_goal)
        exp_type = classify_goal(exp_goal)

        text = text_similarity(goal, exp_goal)
        type_match = 1.0 if exp_type == goal_type else 0.0

        candidate_domain = infer_domain(goal)
        domain_match = 1.0 if (
            candidate_domain and exp_domain == candidate_domain
        ) else 0.0

        tags = tags or []
        raw_tools = getattr(experience, "tools_used", None)
        if not isinstance(raw_tools, (list, tuple, set)):
            raw_tools = []
        exp_tools = [_tag_value(t) for t in raw_tools]
        if tags:
            overlap = len({_tag_value(t) for t in tags} & set(exp_tools))
            tag_overlap = overlap / len(tags)
        else:
            tag_overlap = 0.0

        core = 0.65 * text + 0.35 * type_match
        domain_factor = 1.0 if domain_match else 0.5
        score = 0.85 * core * domain_factor + 0.15 * tag_overlap
        return max(0.0, min(1.0, score))

    def filter_and_score(
        self,
        experiences: List,
        goal: str,
        goal_type: str,
        tags: Optional[List[str]],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> List[Tuple[float, object]]:
        scored: List[Tuple[float, object]] = []
        for experience in experiences or []:
            score = self.score_experience(goal, goal_type, tags, experience)
            if score >= threshold:
                scored.append((score, experience))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[:MAX_RESULTS]
