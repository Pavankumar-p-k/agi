"""FactExtractor — converts raw text and DOM content into structured facts.

Deterministic extraction with confidence scoring. Designed to be
upgradable to LLM-based extraction without changing the interface.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any

from core.research.models import Fact

logger = logging.getLogger(__name__)

# Category keywords — simple pattern matching to classify claims
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "technical": ["api", "sdk", "library", "framework", "version", "release",
                   "deprecated", "migration", "breaking change", "endpoint",
                   "function", "method", "class", "module", "protocol",
                   "authentication", "encryption", "performance", "latency",
                   "throughput", "memory", "cpu", "gpu"],
    "pricing": ["price", "cost", "pricing", "free", "premium", "enterprise",
                 "subscription", "monthly", "annual", "credit", "tier",
                 "paid", "billing", "plan"],
    "comparison": ["better than", "worse than", "faster than", "cheaper than",
                    "compared to", "alternative", "competitor", "vs",
                    "versus", "unlike", "advantage", "disadvantage"],
    "news": ["announced", "launched", "released", "acquired", "merged",
              "raised", "funding", "partnership", "new feature",
              "update", "roadmap"],
    "tutorial": ["how to", "step", "guide", "tutorial", "example",
                  "following", "install", "configure", "setup", "deploy"],
    "reference": ["documentation", "specification", "standard", "definition",
                   "format", "schema", "structure", "field", "property",
                   "attribute", "parameter"],
}

_CONFIDENCE_BOOST_WORDS: list[str] = [
    "confirmed", "announced", "reportedly", "according to",
    "official", "documented", "published", "released",
    "version", "v2", "v3", "v4",
]

_CONFIDENCE_PENALTY_WORDS: list[str] = [
    "maybe", "perhaps", "possibly", "might", "could",
    "seems like", "apparently", "rumored", "unconfirmed",
    "i think", "i believe", "i assume",
]

_STRIPPED_PREFIXES: list[str] = [
    "i think", "i believe", "i assume", "i guess",
    "it seems", "it appears", "i found that",
    "the article says", "the page states", "according to the",
]


class FactExtractor:
    """Transforms text/DOM content into structured facts.

    Usage:
        extractor = FactExtractor()
        facts = extractor.extract(text, "https://example.com")
        facts = extractor.extract_from_dom(dom_data, "https://example.com")
    """

    def extract(self, text: str, source_url: str,
                activity_id: str | None = None,
                node_id: str | None = None,
                max_facts: int = 50) -> list[Fact]:
        """Extract facts from plain text.

        Splits on sentences, filters noise, scores confidence,
        assigns categories by keyword matching.
        """
        if not text or not text.strip():
            return []

        raw_sentences = self._split_sentences(text)
        facts: list[Fact] = []
        now = datetime.utcnow()

        for sentence in raw_sentences:
            if len(facts) >= max_facts:
                break

            cleaned = self._clean_sentence(sentence)
            if not self._is_extractable(cleaned):
                continue

            confidence = self._score_confidence(cleaned)
            category = self._classify(cleaned)
            tags = self._extract_tags(cleaned)

            fact = Fact(
                fact_id=f"fact_{uuid.uuid4().hex[:12]}",
                source_url=source_url,
                claim=cleaned[:500],
                confidence=round(confidence, 2),
                category=category,
                tags=tags,
                timestamp=now,
                activity_id=activity_id,
                node_id=node_id,
            )
            facts.append(fact)

        logger.debug("FactExtractor: %d facts from %d sentences (src=%s)",
                     len(facts), len(raw_sentences), source_url[:60])
        return facts

    def extract_from_dom(self, dom: dict[str, Any] | str | None,
                          source_url: str,
                          activity_id: str | None = None,
                          node_id: str | None = None,
                          max_facts: int = 50) -> list[Fact]:
        """Extract facts from a browser DOM snapshot.

        Accepts either a dict (parsed JSON snapshot) or a raw HTML string.
        Extracts text content from common content elements.
        """
        if dom is None:
            return []
        if isinstance(dom, str):
            text = self._html_to_text(dom)
        elif isinstance(dom, dict):
            text = self._dict_to_text(dom)
        else:
            return []
        return self.extract(text, source_url, activity_id, node_id, max_facts)

    # ── Sentence processing ─────────────────────────────────────────────

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences on common boundaries."""
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        # Split on sentence-ending punctuation
        raw = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        return [s.strip() for s in raw if len(s.strip()) > 15]

    def _clean_sentence(self, sentence: str) -> str:
        """Normalize a sentence for extraction."""
        s = sentence.strip()
        # Remove leading garbage
        s = re.sub(r'^[#*\-\d\.\s]+', '', s)
        # Remove trailing garbage
        s = re.sub(r'[\s#*]+$', '', s)
        # Strip common hedging prefixes
        for prefix in _STRIPPED_PREFIXES:
            if s.lower().startswith(prefix):
                s = s[len(prefix):].strip().lstrip(",;:-").strip()
        return s

    def _is_extractable(self, sentence: str) -> bool:
        """Determine if a sentence is a factual claim worth extracting."""
        if len(sentence) < 20:
            return False
        if len(sentence) > 1000:
            return False
        lower = sentence.lower()
        # Skip questions
        if sentence.strip().endswith("?"):
            return False
        # Skip commands / instructions
        command_starts = ["click", "select", "choose", "enter", "type",
                          "press", "navigate", "go to", "open", "run",
                          "execute", "install", "download"]
        first_word = lower.split()[0] if lower.split() else ""
        if first_word in command_starts:
            return False
        # Skip navigation / UI text
        nav_patterns = ["sign in", "sign up", "log in", "log out",
                        "subscribe", "follow us", "share this",
                        "cookie", "privacy policy", "terms of service",
                        "all rights reserved"]
        if any(p in lower for p in nav_patterns):
            return False
        # Must have a verb (rough heuristic: contains common verb patterns)
        verb_indicators = [" is ", " are ", " was ", " were ", " has ",
                           " have ", " had ", " does ", " did ", " will ",
                           " can ", " may ", " should ", " would ", " could ",
                           " provides ", " supports ", " includes ", " offers ",
                           " requires ", " uses ", " enables ",
                           " costs ", " starts ", " begins ", " ends ",
                           " contains ", " features ", " allows ",
                           " helps ", " makes ", " runs ", " works ",
                           " delivers ", " gives ", " adds ", " creates ",
                           " builds ", " generates ", " produces ",
                           " sends ", " receives ", " returns ",
                           " shows ", " displays ", " handles ",
                           " manages ", " controls ", " monitors ",
                           " launches ", " releases ", " publishes ",
                           " introduces ", " announces ",
                           " explained ", " described ", " defined ",
                           " specified ", " outlined ", " summarized ",
                           " announced ", " launched ", " released ",
                           " introduced ", " published ", " acquired ",
                           " merged ", " raised ", " partnered ",
                           " provided ", " supported ", " included ",
                           " offered ", " required ", " enabled ",
                           " delivered ", " added ", " created ",
                           " built ", " generated ", " produced ",
                           " sent ", " received ",
                           " showed ", " handled ",
                           " managed ", " controlled ", " monitored ",
                           " focused on ", " dealt with ",
                           " consisted of ",
                           " was used for ", " was known as ",
                           " aimed to ", " attempted to ",
                           " tends to ",
        ]
        if not any(v in lower for v in verb_indicators):
            return False
        return True

    # ── Scoring ─────────────────────────────────────────────────────────

    def _score_confidence(self, sentence: str) -> float:
        """Score a sentence's likely factuality from 0.0 to 1.0."""
        lower = sentence.lower()
        score = 0.5

        # Boost for specific entities
        if re.search(r'\b\d+\b', sentence):  # has numbers
            score += 0.15
        if re.search(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', sentence):  # proper nouns
            score += 0.1
        if re.search(r'\d{4}', sentence):  # has a year
            score += 0.1

        # Boost for confident language
        for word in _CONFIDENCE_BOOST_WORDS:
            if word in lower:
                score += 0.1

        # Penalty for uncertain language
        for word in _CONFIDENCE_PENALTY_WORDS:
            if word in lower:
                score -= 0.2

        # Longer, specific sentences are more likely factual
        if len(sentence) > 100:
            score += 0.05
        if len(sentence) > 200:
            score += 0.05

        return max(0.0, min(1.0, score))

    def _classify(self, sentence: str) -> str:
        """Assign a category to a sentence based on keyword matching."""
        lower = sentence.lower()
        best_category = "general"
        best_score = 0

        for category, keywords in _CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in lower)
            if score > best_score:
                best_score = score
                best_category = category

        return best_category

    def _extract_tags(self, sentence: str) -> list[str]:
        """Extract notable terms as tags."""
        tags: list[str] = []
        lower = sentence.lower()

        # Extract capitalized multi-word phrases (likely proper nouns)
        proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', sentence)
        for pn in proper_nouns[:3]:
            tags.append(pn.lower().replace(" ", "_"))

        # Extract version numbers
        versions = re.findall(r'(?:v|version\s+)?\d+\.\d+(?:\.\d+)?', lower)
        for v in versions[:2]:
            tags.append(v.replace(" ", "_"))

        return tags

    # ── HTML / DOM helpers ──────────────────────────────────────────────

    def _html_to_text(self, html: str) -> str:
        """Crude HTML-to-text extraction."""
        # Remove scripts and styles
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        # Replace block tags with newlines
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</(p|div|h[1-6]|li|tr|blockquote|section)>', '\n', text, flags=re.IGNORECASE)
        # Strip remaining tags
        text = re.sub(r'<[^>]+>', '', text)
        # Decode common entities
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&nbsp;', ' ').replace('&#39;', "'").replace('&quot;', '"')
        return text.strip()

    def _dict_to_text(self, data: dict[str, Any]) -> str:
        """Extract text content from a browser DOM snapshot dict.

        Handles the format returned by browser_snapshot:
        {"url": "...", "title": "...", "content": "..."}
        """
        # Try common keys for text content
        for key in ("content", "text", "body", "markdown", "textContent", "innerText"):
            if key in data and isinstance(data[key], str):
                return data[key]
        # Try nested
        if "data" in data and isinstance(data["data"], dict):
            return self._dict_to_text(data["data"])
        # Fall back to stringifying the value keys
        parts: list[str] = []
        for v in data.values():
            if isinstance(v, str) and len(v) > 50:
                parts.append(v)
        return "\n".join(parts)
