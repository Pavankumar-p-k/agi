from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class ExtractedFact:
    subject: str
    predicate: str
    object: str
    confidence: float
    category: str
    source_text: str
    user_id: str = ""
    id: str | None = None
    activity_id: str | None = None
    conversation_id: str | None = None
    source_message: str | None = None
    created_at: float | None = None
    last_verified: float | None = None
    verification_level: str = "extracted"
    derived_from: str | None = None


_KNOWN_CATEGORIES = frozenset({
    "preference", "attribute", "capability", "relation", "fact",
})


# ── Pattern registry ─────────────────────────────────────────────────────────


class _Pattern:
    __slots__ = ("regex", "category", "base_confidence", "subject_group", "object_group")

    def __init__(
        self,
        regex: str,
        category: str,
        base_confidence: float = 0.6,
        subject_group: str = "subject",
        object_group: str = "object",
    ) -> None:
        self.regex = re.compile(regex, re.IGNORECASE)
        self.category = category
        self.base_confidence = base_confidence
        self.subject_group = subject_group
        self.object_group = object_group


_PATTERNS: list[_Pattern] = [
    # "X is Y" / "X are Y" / "X was Y" / "X were Y"
    _Pattern(
        r"(?P<subject>\w[\w\s]*?)\s+(?:is|are|was|were)\s+(?P<object>.+)",
        category="attribute",
        base_confidence=0.55,
    ),
    # "X can Y" / "X cannot Y"
    _Pattern(
        r"(?P<subject>\w[\w\s]*?)\s+can(?:not)?\s+(?P<object>.+)",
        category="capability",
        base_confidence=0.6,
    ),
    # "X has Y" / "X have Y"
    _Pattern(
        r"(?P<subject>\w[\w\s]*?)\s+(?:has|have)\s+(?P<object>.+)",
        category="attribute",
        base_confidence=0.5,
    ),
    # "X likes Y" / "X loves Y" / "X hates Y"
    _Pattern(
        r"(?P<subject>\w[\w\s]*?)\s+(?:likes|loves|hates|enjoys|prefers)\s+(?P<object>.+)",
        category="preference",
        base_confidence=0.7,
    ),
    # "I like Y" / "I love Y" / "I prefer Y"
    _Pattern(
        r"I\s+(?:like|love|prefer|enjoy|hate|dislike)\s+(?P<object>.+)",
        category="preference",
        base_confidence=0.75,
        subject_group="subject",
    ),
    # "My favorite Y is X" / "My preferred Y is X"
    _Pattern(
        r"my\s+favorite\s+(?P<subject>\w[\w\s]*?)\s+is\s+(?P<object>.+)",
        category="preference",
        base_confidence=0.8,
    ),
    # "I use Y" / "I work with Y" / "I work on Y"
    _Pattern(
        r"I\s+(?:use|work\s+with|work\s+on|program\s+in|code\s+in)\s+(?P<object>.+)",
        category="preference",
        base_confidence=0.65,
        subject_group="subject",
    ),
    # "I am a Y" / "I am an Y"
    _Pattern(
        r"I\s+am\s+(?:a|an)\s+(?P<object>.+)",
        category="attribute",
        base_confidence=0.7,
        subject_group="subject",
    ),
    # "I have Y" / "I've Y"
    _Pattern(
        r"I\s+(?:have|'ve)\s+(?P<object>.+)",
        category="attribute",
        base_confidence=0.5,
        subject_group="subject",
    ),
    # "Remember that X" / "Know that X" / "Learn that X"
    _Pattern(
        r"(?:remember|know|learn)\s+that\s+(?P<subject>\w[\w\s]*?)\s+(?:is|was|has|can)\s+(?P<object>.+)",
        category="fact",
        base_confidence=0.85,
    ),
    # "The answer is X"
    _Pattern(
        r"the\s+answer\s+is\s+(?P<object>.+)",
        category="fact",
        base_confidence=0.7,
        subject_group="subject",
    ),
    # "Set my Y to X" / "Set my Y as X"
    _Pattern(
        r"set\s+my\s+(?P<subject>\w[\w\s]*?)\s+(?:to|as)\s+(?P<object>.+)",
        category="preference",
        base_confidence=0.8,
    ),
]


# ── False positive filters ────────────────────────────────────────────────────

_QUESTION_WORDS = frozenset({"how", "what", "when", "where", "why", "who", "whose", "which"})
_GREETINGS = frozenset({
    "hello", "hi", "hey", "howdy", "good morning", "good afternoon",
    "good evening", "how are you", "how's it going", "what's up",
})


def _is_false_positive(subject: str, full_match: str) -> bool:
    """Check if a match is a likely false positive (greeting, question, etc.)."""
    lower_match = full_match.lower().strip()
    lower_subject = subject.lower().strip()

    if lower_match in _GREETINGS or any(lower_match.startswith(g) for g in _GREETINGS):
        return True
    if lower_subject in _QUESTION_WORDS:
        return True
    if lower_subject in ("how", "what") and len(full_match.split()) <= 5:
        return True
    return False


def extract_facts(
    text: str,
    user_id: str = "",
    activity_id: str | None = None,
    conversation_id: str | None = None,
    source_message: str | None = None,
) -> List[ExtractedFact]:
    """Extract structured facts from a text string using pattern matching.

    Args:
        text: The raw text to extract facts from.
        user_id: Optional user identifier to attach to extracted facts.
        activity_id: Optional ActivityGraph node id for provenance.
        conversation_id: Optional conversation id for provenance.
        source_message: Optional message role (``"user"`` / ``"assistant"``).

    Returns:
        A list of :class:`ExtractedFact` instances, ordered by match position.
    """
    import time

    facts: list[ExtractedFact] = []
    seen: set[tuple[str, str, str]] = set()
    now = time.time()

    for pattern in _PATTERNS:
        for match in pattern.regex.finditer(text):
            subject_raw = match.group(pattern.subject_group) if pattern.subject_group in match.groupdict() else "user"
            obj = match.group(pattern.object_group).strip().rstrip(".!")

            # Normalise first-person references
            subject = _normalise_subject(subject_raw.strip())

            full_match = match.group(0).strip()
            if _is_false_positive(subject, full_match):
                continue

            # Deduplicate identical triples
            key = (subject.lower(), pattern.category, obj.lower())
            if key in seen:
                continue
            seen.add(key)

            fact = ExtractedFact(
                subject=subject,
                predicate=pattern.category,
                object=obj,
                confidence=pattern.base_confidence,
                category=pattern.category,
                source_text=full_match,
                user_id=user_id,
                activity_id=activity_id,
                conversation_id=conversation_id,
                source_message=source_message,
                created_at=now,
            )
            facts.append(fact)

    return facts


def extract_facts_from_messages(
    messages: list[dict[str, str]],
    user_id: str = "",
    activity_id: str | None = None,
    conversation_id: str | None = None,
) -> List[ExtractedFact]:
    """Extract facts from a list of message dicts (``{"role": ..., "content": ...}``).

    Only extracts from ``"user"`` and ``"assistant"`` messages.
    """
    facts: list[ExtractedFact] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role not in ("user", "assistant"):
            continue
        facts.extend(
            extract_facts(
                content,
                user_id=user_id,
                activity_id=activity_id,
                conversation_id=conversation_id,
                source_message=role,
            ),
        )
    return facts


def _normalise_subject(subject: str) -> str:
    """Normalise first-person and possessive references."""
    lower = subject.strip().lower()
    if lower in ("i", "me", "my", "myself"):
        return "user"
    if lower in ("you", "your", "yourself", "the assistant"):
        return "assistant"
    if lower in ("it", "its", "this", "that"):
        return subject  # keep the original reference
    return subject
