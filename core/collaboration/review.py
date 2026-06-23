"""ArtifactReviewer — structured review workflow for multi-agent collaboration.

Provides deterministic issue detection patterns and quality scoring
that reviewers can use to produce consistent ArtifactReview objects.
"""

from __future__ import annotations

import re
import logging
from typing import Any

from core.collaboration.models import ArtifactReview, ReviewDecision

logger = logging.getLogger(__name__)


class ArtifactReviewer:
    """Deterministic review helpers for collaboration sessions.

    These are pattern-based checks that any reviewer agent can apply.
    Actual decisions remain with the reviewer agents themselves;
    this provides the infrastructure to produce structured reviews.
    """

    IMPLEMENTATION_PATTERNS = {
        r"(?i)(TODO|FIXME|HACK|XXX)": "Contains unresolved placeholder",
        r"print\(|console\.log\(|println\(": "Contains debug print statements",
        r"(?i)(not implemented|unimplemented|stub)": "Contains stub/unimplemented code",
        r"pass\s*\n|raise\s+NotImplementedError": "Contains pass-through or not-implemented",
    }

    SECURITY_PATTERNS = {
        r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]+['\"]": "Hardcoded credential detected",
        r"(?i)(eval|exec)\s*\(": "Use of dynamic code execution",
        r"shell\s*=\s*True": "Shell=True in subprocess (security risk)",
        r"(?i)SELECT\s+.*\s+FROM\s+.*\s+WHERE\s+.*['\"]\s*\+\s*": "SQL injection risk (string concatenation)",
    }

    QUALITY_PATTERNS = {
        r"(\w+)\s*=\s*\1\s*\+\s*1": "C-style increment detected",
        r"(?i)except\s*:": "Bare except clause",
        r"(?i)except\s+\w+\s*,\s*\w+": "Python 2 style exception syntax",
    }

    def __init__(self, reviewer_id: str):
        self.reviewer_id = reviewer_id

    def review_artifact(self, content: str, goal: str) -> ArtifactReview:
        """Produce a structured review by running all pattern checks.

        This is a deterministic baseline. Agents can extend or override
        this with LLM-based analysis.
        """
        issues: list[str] = []
        suggestions: list[str] = []

        # Check implementation patterns
        for pattern, msg in self.IMPLEMENTATION_PATTERNS.items():
            matches = re.findall(pattern, content)
            if matches:
                issues.append(f"{msg} ({len(matches)} found)")

        # Check security patterns
        for pattern, msg in self.SECURITY_PATTERNS.items():
            matches = re.findall(pattern, content)
            if matches:
                issues.append(f"[SECURITY] {msg} ({len(matches)} found)")

        # Check quality patterns
        for pattern, msg in self.QUALITY_PATTERNS.items():
            matches = re.findall(pattern, content)
            if matches:
                issues.append(f"{msg} ({len(matches)} found)")

        # Goal alignment check (substring matching for compound identifiers)
        goal_lower = goal.lower()
        content_lower = content.lower()
        goal_keywords = set(goal_lower.split())
        overlap = {kw for kw in goal_keywords if kw in content_lower}
        if len(overlap) < max(1, len(goal_keywords) * 0.2):
            issues.append("Low goal alignment: few goal keywords appear in artifact")
            suggestions.append("Ensure the artifact directly addresses requirements")

        # Length check
        word_count = len(content.split())
        if word_count < 10:
            issues.append("Artifact is too short to be meaningful")
        elif word_count > 10000:
            suggestions.append("Consider splitting artifact into smaller modules")

        # Decision based on issues
        if not issues:
            decision = ReviewDecision.APPROVED
            score = 1.0
            comments = "All automatic checks passed."
        elif len(issues) <= 2:
            decision = ReviewDecision.CHANGES_REQUESTED
            score = max(0.3, 1.0 - len(issues) * 0.2)
            comments = f"{len(issues)} issue(s) found. Please address and resubmit."
        else:
            decision = ReviewDecision.REJECTED
            score = 0.2
            comments = f"{len(issues)} issue(s) found. Major revision required."

        return ArtifactReview(
            review_id=f"rev_{self.reviewer_id}_{hash(content) % 10000:04x}",
            reviewer_id=self.reviewer_id,
            artifact_version_id="",
            decision=decision,
            comments=comments,
            issues=issues,
            suggestions=suggestions,
            score=score,
        )
