# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""core/ambiguity_resolver.py
Detects vague or underspecified goals and generates targeted clarification questions.
Called after interpret_goal() and before proceeding to build.
Saves time, tokens, and failed builds by resolving ambiguity upfront.
"""
import logging
from dataclasses import asdict, dataclass, field

logger = logging.getLogger("ambiguity_resolver")


@dataclass
class AmbiguityResult:
    ambiguous: bool = False
    questions: list[str] = field(default_factory=list)
    field_map: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# Default values that signal "LLM guessed, user didn't specify"
_AMBIGUOUS_DEFAULTS = {
    "business_type": {"general", ""},
    "brand_name": {"Website", ""},
    "tone": {"professional"},
    "style": {"modern_minimal"},
}

_AMBIGUOUS_PAGE_SET = {"index", "about", "contact"}

# Mapping from field → question template
_FIELD_QUESTIONS: dict[str, str] = {
    "business_type": "What type of business is this? (e.g., coffee_shop, restaurant, portfolio, ecommerce, tech_startup, bakery)",
    "brand_name": "What's the brand or company name?",
    "pages": "What pages do you need? (e.g., home, about, menu, blog, gallery, contact, services, pricing, faq)",
    "tone": "What tone should the site have? (professional, casual, luxury, fun, warm, minimal, bold)",
    "style": "What style? (modern_minimal, business, creative, ecommerce, blog, portfolio, saas)",
}

_QUESTION_PRIORITY = ["business_type", "brand_name", "pages", "tone", "style"]


def check_ambiguity(interpreted: dict) -> AmbiguityResult:
    """Check if the interpreted goal has ambiguous/unspecified fields.

    Returns AmbiguityResult with:
    - ambiguous: True if any field needs clarification
    - questions: 1-2 targeted questions to ask
    - field_map: {question_text: field_name} for mapping answers back
    """
    result = AmbiguityResult()
    goal = interpreted.get("original_goal", "")
    questions_needed: list[tuple[str, str]] = []

    for field in _QUESTION_PRIORITY:
        if len(questions_needed) >= 2:
            break

        value = interpreted.get(field)
        if field == "pages":
            if _is_pages_ambiguous(value, goal):
                questions_needed.append((field, _FIELD_QUESTIONS[field]))
        elif _is_field_ambiguous(field, value, goal):
            questions_needed.append((field, _FIELD_QUESTIONS[field]))

    # Only mark ambiguous if the goal itself was vague
    if questions_needed and _is_goal_vague(goal):
        result.ambiguous = True
        for field, question in questions_needed:
            result.questions.append(question)
            result.field_map[question] = field

    return result


def resolve_ambiguity(interpreted: dict, question: str, answer: str) -> dict:
    """Apply a user's answer to the interpreted goal and return updated dict.

    Mutates and returns the interpreted dict so it can be chained.
    """
    field = _infer_field_from_question(question)
    if not field:
        logger.warning(f"[AMBIGUITY] Unknown question, cannot resolve: {question[:60]}")
        return interpreted

    answer = answer.strip()

    if field == "pages":
        parsed = [p.strip().lower().replace("home", "index") for p in answer.replace(",", " ").split()]
        if parsed:
            interpreted["pages"] = sorted(set(parsed))
    elif field == "business_type":
        bt = answer.lower().replace(" ", "_")
        interpreted["business_type"] = bt
    elif field == "brand_name":
        interpreted["brand_name"] = answer
    elif field == "tone":
        interpreted["tone"] = answer.lower()
    elif field == "style":
        interpreted["style"] = answer.lower()

    interpreted["reasoning"] = interpreted.get("reasoning", []) + [f"ambiguity_resolved:{field}={answer[:40]}"]
    return interpreted


def _is_field_ambiguous(field: str, value, goal: str) -> bool:
    """Check if a field value is the default/ambiguous."""
    if value is None:
        return True
    defaults = _AMBIGUOUS_DEFAULTS.get(field, set())
    if isinstance(value, str) and value.strip().lower() in {d.lower() for d in defaults}:
        return True
    return False


def _is_pages_ambiguous(pages: list[str] | None, goal: str) -> bool:
    """Check if pages are just the defaults with no user input."""
    if not pages:
        return True
    goal_lower = goal.lower()
    # If goal mentions specific pages, trust the LLM
    for kw in (" page", " pages", "landing", "blog", "menu", "gallery", "portfolio", "services", "pricing", "faq"):
        if kw in goal_lower:
            return False
    return set(pages) == _AMBIGUOUS_PAGE_SET


def _is_goal_vague(goal: str) -> bool:
    """Check if the original goal is vague/short."""
    goal_lower = goal.lower().strip()
    vague_patterns = [
        "build a website", "create a website", "make a website",
        "build a site", "create a site", "make a site",
        "build a page", "create a page", "make a page",
        "generate a website", "generate a site",
        "build me a", "create me a", "make me a",
        "i need a website", "i want a website",
    ]
    if any(goal_lower.startswith(p) or goal_lower == p for p in vague_patterns):
        return True
    if len(goal.split()) <= 4:
        return True
    return False


def _infer_field_from_question(question: str) -> str | None:
    """Map a question text back to the field it targets."""
    for field, template in _FIELD_QUESTIONS.items():
        if question.strip() == template.strip():
            return field
    # Fallback: keyword match
    q = question.lower()
    if "business" in q or "type" in q:
        return "business_type"
    if "brand" in q or "name" in q:
        return "brand_name"
    if "page" in q:
        return "pages"
    if "tone" in q:
        return "tone"
    if "style" in q:
        return "style"
    return None
