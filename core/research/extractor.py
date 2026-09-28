"""Fact extraction from research text.

Extractor.extract_from_text returns a list of Fact records:
- sentences shorter than MIN_FACT_LENGTH are skipped (guard clause);
- "X is Y" sentences extract as semantic facts;
- other informative sentences are kept as plain text facts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


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


class FactExtractor(Extractor):
    """Alias kept for backward compatibility."""


__all__ = ["Extractor", "FactExtractor", "Fact", "MIN_FACT_LENGTH"]
