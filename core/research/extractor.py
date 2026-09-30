"""Fact extraction from research text.

Extractor.extract_from_text returns a list of Fact records:
- sentences shorter than MIN_FACT_LENGTH are skipped (guard clause);
- "X is Y" sentences extract as semantic facts;
- other informative sentences are kept as plain text facts.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from core.research.models import Fact as ResearchFact


MIN_FACT_LENGTH = 20

# Sentence splitter: punctuation followed by space+capital or end.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
# "X is Y" pattern for semantic facts.
_IS_PATTERN = re.compile(r"^(?P<subject>[A-Z][\w\s'-]{1,60}?)\s+is\s+(?P<object>.{5,200})$")


@dataclass
class Fact:
    text: str
    source_url: str = ""
    source_title: str = ""
    query: str = ""
    kind: str = "text"           # "text" | "semantic"
    subject: str = ""
    object: str = ""
    confidence: float = 0.6
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "query": self.query,
            "kind": self.kind,
            "subject": self.subject,
            "object": self.object,
            "confidence": self.confidence,
        }


class Extractor:
    """Extracts candidate facts from untrusted research text."""

    def extract_from_text(self, text: str,
                          source_url: str = "",
                          source_title: str = "",
                          query: str = "") -> List[Fact]:
        text = str(text or "").strip()
        if len(text) < MIN_FACT_LENGTH:
            return []

        facts: List[Fact] = []
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
        for sentence in sentences:
            sentence_lower = sentence.lower()  # fix (SPCL-9): define before use
            if len(sentence) < MIN_FACT_LENGTH:
                continue
            match = _IS_PATTERN.match(sentence)
            if match:
                facts.append(Fact(
                    text=sentence,
                    source_url=source_url,
                    source_title=source_title,
                    query=query,
                    kind="semantic",
                    subject=match.group("subject").strip(),
                    object=match.group("object").strip().rstrip("."),
                    confidence=0.75,
                ))
            elif any(ch.isalpha() for ch in sentence_lower):
                facts.append(Fact(
                    text=sentence,
                    source_url=source_url,
                    source_title=source_title,
                    query=query,
                    kind="text",
                ))
        return facts


_QUESTION_WORDS = ("what", "why", "how", "who", "whom", "whose", "when",
                   "where", "which", "is", "are", "do", "does", "did",
                   "can", "could", "should", "would", "will")

_COMMAND_PREFIXES = ("click", "tap", "press", "sign in", "sign up", "log in",
                     "login", "log out", "subscribe", "download", "install",
                     "buy", "shop", "add to cart", "register", "enable",
                     "accept", "cookie", "menu", "search", "home", "next",
                     "previous", "continue reading", "learn more", "read more")

_HEDGES = ("maybe", "possibly", "perhaps", "probably", "might", "unclear",
           "rumor", "allegedly")
_TECH_TERMS = ("python", "javascript", "rust", "java", "api", "aws", "google",
               "microsoft", "docker", "linux", "windows", "server", "framework",
               "library", "sdk", "rest", "vertex", "cloud", "ai")
_CATEGORY_TERMS = {
    "pricing": ("$", "cost", "price", "pricing", "per month", "per year",
                "subscription", "plan"),
    "tutorial": ("how to", "install", "tutorial", "getting started", "step by step"),
    "comparison": (" vs ", "versus", "compared to", "comparison", "better than"),
    "technical": ("version", "release", "api", "framework", "library", "sdk",
                  "server", "python", "javascript", "rust", "docker", "aws",
                  "rest", "database", "algorithm"),
}


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _looks_like_question(sentence: str) -> bool:
    stripped = sentence.strip()
    if stripped.endswith("?"):
        return True
    first = re.split(r"\W+", stripped.lower())[0] if stripped else ""
    return first in _QUESTION_WORDS


def _looks_like_command(sentence: str) -> bool:
    lowered = sentence.strip().lower()
    return any(lowered.startswith(prefix) for prefix in _COMMAND_PREFIXES)


def _is_fact_candidate(sentence: str) -> bool:
    if len(sentence.strip()) < MIN_FACT_LENGTH:
        return False
    if _looks_like_question(sentence) or _looks_like_command(sentence):
        return False
    return any(ch.isalpha() for ch in sentence)


def _score(sentence: str) -> float:
    text = sentence.lower()
    score = 0.5
    if re.search(r"\d", text):
        score += 0.2
    if any(term in text for term in _TECH_TERMS):
        score += 0.15
    if re.search(r"\b(?:19|20)\d{2}\b", text):
        score += 0.1
    if any(word in text for word in ("released", "confirmed", "officially",
                                     "announced", "published", "documented")):
        score += 0.1
    if any(hedge in text for hedge in _HEDGES):
        score -= 0.2
    return max(0.0, min(1.0, round(score, 3)))


def _category(sentence: str) -> str:
    lowered = sentence.lower()
    for category, terms in _CATEGORY_TERMS.items():
        if any(term in lowered for term in terms):
            return category
    return "general"


def _tags(sentence: str) -> List[str]:
    tags: List[str] = []
    for token in re.findall(r"[A-Z][A-Za-z0-9+.-]{1,}", sentence):
        lowered = token.lower()
        if len(lowered) > 1 and lowered not in tags:
            tags.append(lowered)
    for term in _TECH_TERMS:
        if term in sentence.lower() and term not in tags:
            tags.append(term)
    return tags[:8]


class FactExtractor:
    """Extracts research facts as models.Fact records from text and DOM."""

    MIN_LENGTH = MIN_FACT_LENGTH

    def extract(self, text: str, source_url: str = "",
                max_facts: int = 50) -> List["ResearchFact"]:
        text = str(text or "").strip()
        if len(text) < self.MIN_LENGTH:
            return []
        facts: List["ResearchFact"] = []
        for sentence in _split_sentences(text):
            if not _is_fact_candidate(sentence):
                continue
            facts.append(ResearchFact(
                fact_id=uuid.uuid4().hex,
                claim=sentence,
                source_url=source_url,
                confidence=_score(sentence),
                category=_category(sentence),
                tags=_tags(sentence),
            ))
            if max_facts is not None and len(facts) >= max_facts:
                break
        return facts

    def extract_from_dom(self, dom, source_url: str = "",
                         max_facts: int = 50) -> List["ResearchFact"]:
        """Extract facts from a DOM snapshot dict, HTML string or None."""
        if dom is None:
            return []
        if isinstance(dom, dict):
            content = str(dom.get("content") or dom.get("text") or "")
        else:
            content = str(dom)
            if "<" in content and ">" in content:
                content = re.sub(r"<script[^>]*>.*?</script>", " ", content,
                                 flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r"<[^>]+>", " ", content)
            import html as _html
            content = _html.unescape(content)
        content = " ".join(content.split())
        return self.extract(content, source_url, max_facts=max_facts)


__all__ = ["Extractor", "FactExtractor", "Fact", "MIN_FACT_LENGTH"]
