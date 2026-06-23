"""Intent classifier — maps user goal text to a deterministic workflow template."""

import re
from typing import Any

from core.planner.templates import list_templates, get_template

# Keyword → template_id mappings (ordered by priority)
_KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["android", "apk", "coffee shop", "mobile app"], "android_app_build"),
    (["bookstore", "website", "web app", "web project"], "research_build_validate_email"),
    (["research", "email", "report"], "research_build_email"),
    (["build", "test", "validate", "notify"], "build_validate_notify"),
]


def classify(goal: str) -> str | None:
    """Classify a user goal into a template ID using keyword matching.

    Returns the best-matching template_id, or None if no match.
    """
    goal_lower = goal.lower()

    for keywords, template_id in _KEYWORD_RULES:
        if any(kw in goal_lower for kw in keywords):
            t = get_template(template_id)
            if t:
                return template_id

    return None


def extract_parameters(goal: str, template_id: str) -> dict[str, Any]:
    """Extract parameters from a goal string for a given template."""
    goal_lower = goal.lower()
    params: dict[str, Any] = {"original_goal": goal}

    # Extract recipient email if present
    email_patterns = [
        r"email\s+(?:it|the\s+results?|the\s+report|the\s+apk)\s+to\s+([\w.@+-]+)",
        r"send\s+to\s+([\w.@+-]+)",
        r"to\s+([\w.@+-]+)",
    ]
    for pat in email_patterns:
        m = re.search(pat, goal_lower)
        if m:
            params["recipient"] = m.group(1)
            break

    # Extract topic/project type
    topic_patterns = [
        r"(?:build|create|make|develop)\s+(?:a|an|the)?\s*(.+?)(?:\s+(?:app|website|project|site))",
        r"(?:build|create|make)\s+(?:a|an|the)?\s*(.+?)(?:\s+and)",
        r"(?:about|for)\s+(.+?)(?:\s*(?:website|app|project))",
    ]
    for pat in topic_patterns:
        m = re.search(pat, goal_lower)
        if m:
            params["topic"] = m.group(1).strip()
            break

    if "topic" not in params:
        params["topic"] = goal_lower[:60]

    return params
