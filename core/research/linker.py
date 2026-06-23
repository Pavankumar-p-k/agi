"""Linker — entity extraction and fact-to-fact relationship classification."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

from core.research.graph_models import EDGE_CONTRADICTS, EDGE_SUPPORTS, EDGE_RELATED_TO
from core.research.models import Fact

logger = logging.getLogger(__name__)

# — Entity extraction patterns —

_CAPITALIZED_PATTERN = re.compile(r'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\b')
_VERSION_PATTERN = re.compile(r'\b\d+\.\d+(?:\.\d+)?\b')
_TECH_TERMS = {
    "api", "sdk", "rest", "graphql", "websocket", "json", "xml", "http",
    "docker", "kubernetes", "linux", "android", "ios", "python", "java",
    "javascript", "typescript", "node", "react", "angular", "vue",
    "sql", "nosql", "postgresql", "mysql", "mongodb", "redis",
    "aws", "azure", "gcp", "cloud", "serverless", "microservice",
    "oauth", "jwt", "tls", "ssl", "https",
}

_STOP_ENTITIES = {
    "The", "This", "That", "These", "Those", "It",
    "We", "They", "He", "She", "I", "You",
    "However", "Therefore", "Additionally", "Also",
    "First", "Second", "Third", "Finally", "Next",
    "Our", "My", "Your", "His", "Her", "Its",
    "API", "SDK", "Version", "Release", "Please",
    "Click", "Select", "Enter", "Press", "Navigate",
    "Sign", "Log", "Subscribe", "Share", "Follow",
    "What", "Who", "Where", "When", "Why", "How",
    "Which", "Whose", "Whom",
    "Is", "Are", "Was", "Were", "Do", "Does", "Did",
    "Has", "Have", "Had", "Can", "Could", "Will", "Would",
    "May", "Might", "Shall", "Should",
    "Yes", "No", "Not", "None", "All", "Every",
    "More", "Less", "Most", "Least", "Many", "Much",
    "Here", "There", "Now", "Then", "Today", "Yesterday",
    "Let", "Get", "Make", "Take", "Give",
}

_NEGATION_WORDS = {"not", "no", "never", "without", "lacks", "missing", "doesn't", "don't", "won't"}


class Linker:
    """Extracts entities from facts and classifies fact-to-fact relationships.

    Usage:
        linker = Linker()
        entities = linker.extract_entities(fact)
        rel = linker.classify_relationship(fact_a, fact_b)
    """

    def extract_entities(self, fact: Fact) -> list[str]:
        """Extract entity names from a fact claim.

        Returns a deduplicated list of entity names, keeping the first
        occurrence order.
        """
        claim = fact.claim
        lower = claim.lower()
        entities: list[str] = []
        seen: set[str] = set()

        # 1. Capitalized multi-word phrases (Company X, Product Y)
        for match in _CAPITALIZED_PATTERN.finditer(claim):
            name = match.group(1).strip()
            if name in _STOP_ENTITIES:
                continue
            if len(name) < 3:
                continue
            key = name.lower()
            if key not in seen:
                seen.add(key)
                entities.append(name)

        # 2. Tech terms (lowercase, single-word)
        for word in _TECH_TERMS:
            pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
            if pattern.search(lower):
                if word not in seen:
                    seen.add(word)
                    entities.append(word.title())

        # 3. Version numbers as entities
        for match in _VERSION_PATTERN.finditer(claim):
            ver = match.group()
            if ver not in seen:
                seen.add(ver)
                entities.append(f"v{ver}")

        return entities

    def classify_relationship(self, fact_a: Fact,
                              fact_b: Fact,
                              ) -> str | None:
        """Classify the relationship between two facts.

        Returns one of: SUPPORTS, CONTRADICTS, RELATED_TO, or None.

        Uses entity overlap, attribute comparison, and value conflict detection.
        """
        # Must share at least one entity to be related
        entities_a = set(e.lower() for e in self.extract_entities(fact_a))
        entities_b = set(e.lower() for e in self.extract_entities(fact_b))
        common_entities = entities_a & entities_b

        if not common_entities:
            return None

        # Check for contradiction: same subject, opposite claims
        if self._is_contradiction(fact_a, fact_b, common_entities):
            return EDGE_CONTRADICTS

        # Check for support: same subject, corroborating claims
        if self._is_support(fact_a, fact_b, common_entities):
            return EDGE_SUPPORTS

        # Different attributes about same entity
        return EDGE_RELATED_TO

    def _is_contradiction(self, fact_a: Fact, fact_b: Fact,
                          common_entities: set[str]) -> bool:
        """Detect if two facts contradict each other."""
        # Same entity, opposite pricing
        prices_a = self._extract_prices(fact_a.claim)
        prices_b = self._extract_prices(fact_b.claim)
        if prices_a and prices_b and prices_a != prices_b:
            return True

        # Same entity, different numbers for same attribute
        nums_a = self._extract_numbers(fact_a.claim)
        nums_b = self._extract_numbers(fact_b.claim)
        if nums_a and nums_b:
            # Check if claims are about the same topic using verb overlap
            verbs_a = self._extract_verbs(fact_a.claim)
            verbs_b = self._extract_verbs(fact_b.claim)
            common_verbs = verbs_a & verbs_b
            if common_verbs and nums_a != nums_b:
                return True

        # Negation contradiction: one says X has Y, other says X doesn't have Y
        a_lower = fact_a.claim.lower()
        b_lower = fact_b.claim.lower()
        for entity in common_entities:
            # Check if one claim negates what the other asserts
            a_has_negation = any(n in a_lower for n in _NEGATION_WORDS)
            b_has_negation = any(n in b_lower for n in _NEGATION_WORDS)
            if a_has_negation != b_has_negation:
                return True

        return False

    def _is_support(self, fact_a: Fact, fact_b: Fact,
                    common_entities: set[str]) -> bool:
        """Detect if two facts support/corroborate each other."""
        # Same entity, same attribute, same direction
        prices_a = self._extract_prices(fact_a.claim)
        prices_b = self._extract_prices(fact_b.claim)
        if prices_a and prices_b and prices_a == prices_b:
            return True

        # Same source = likely support
        if fact_a.source_url == fact_b.source_url:
            return True

        # Same entity, similar verbs, similar numbers
        nums_a = self._extract_numbers(fact_a.claim)
        nums_b = self._extract_numbers(fact_b.claim)
        if nums_a and nums_b:
            # Same order of magnitude
            if abs(nums_a[0] - nums_b[0]) / max(nums_a[0], nums_b[0], 1) < 0.3:
                verbs_a = self._extract_verbs(fact_a.claim)
                verbs_b = self._extract_verbs(fact_b.claim)
                if verbs_a & verbs_b:
                    return True

        return False

    def _extract_prices(self, claim: str) -> list[str]:
        """Extract price strings like $10, $12.99."""
        return re.findall(r'\$\d+(?:\.\d{2})?', claim)

    def _extract_numbers(self, claim: str) -> list[float]:
        """Extract numeric values from a claim."""
        nums = re.findall(r'\b\d+(?:,\d{3})*(?:\.\d+)?', claim)
        return [float(n.replace(",", "")) for n in nums]

    def _extract_verbs(self, claim: str) -> set[str]:
        """Extract canonical verb forms from a claim."""
        verbs = {
            "costs", "prices", "charges", "offers", "provides", "supports",
            "includes", "requires", "uses", "enables", "features",
            "launched", "released", "announced", "acquired",
            "handles", "processes", "supports", "delivers",
            "is", "was", "are", "were", "has", "have",
        }
        lower = claim.lower()
        return {v for v in verbs if v in lower}
