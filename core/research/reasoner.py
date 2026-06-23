"""FactReasoner — cross-source contradiction detection, agreement finding, gap analysis."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from core.research.models import Fact

logger = logging.getLogger(__name__)


@dataclass
class Contradiction:
    """Two or more facts making opposing claims about the same entity+attribute."""
    entity: str
    attribute: str
    values: list[str]
    facts: list[Fact]
    confidence: float = 1.0

    def summary(self, max_values: int = 3) -> str:
        vals = self.values[:max_values]
        rest = f" and {len(self.values) - max_values} more" if len(self.values) > max_values else ""
        return (f"Contradiction about '{self.entity}' ({self.attribute}): "
                f"{', '.join(vals)}{rest} "
                f"from {len(self.facts)} sources")


@dataclass
class Agreement:
    """Multiple facts supporting the same claim about an entity."""
    entity: str
    attribute: str
    value: str
    facts: list[Fact]
    confidence: float = 1.0

    def summary(self) -> str:
        return (f"Agreement: '{self.entity}' {self.attribute} = '{self.value}' "
                f"(supported by {len(self.facts)} sources)")


@dataclass
class UniqueClaim:
    """A claim found in only one source — potentially valuable or unreliable."""
    entity: str
    attribute: str
    value: str
    fact: Fact

    def summary(self) -> str:
        return (f"Unique claim: '{self.entity}' {self.attribute} = '{self.value}' "
                f"(only from {self.fact.source_url[:60]})")


@dataclass
class Gap:
    """A question or topic area with insufficient fact coverage."""
    question: str
    entity: str | None = None
    suggested_sources: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return f"Gap: {self.question}" + (f" (suggested: {', '.join(self.suggested_sources)})" if self.suggested_sources else "")


@dataclass
class FactComparison:
    """Full comparison result across multiple sources."""
    contradictions: list[Contradiction] = field(default_factory=list)
    agreements: list[Agreement] = field(default_factory=list)
    unique_claims: list[UniqueClaim] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    total_facts: int = 0
    sources_analyzed: list[str] = field(default_factory=list)

    def has_conflicts(self) -> bool:
        return len(self.contradictions) > 0

    def summary(self) -> str:
        parts = [
            f"Compared {self.total_facts} facts from {len(self.sources_analyzed)} sources",
            f"{len(self.agreements)} agreements",
            f"{len(self.contradictions)} contradictions",
            f"{len(self.unique_claims)} unique claims",
            f"{len(self.gaps)} gaps",
        ]
        return " | ".join(parts)


# — Entity and attribute extraction patterns —

_ENTITY_PATTERN = re.compile(r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)')
_NUMBER_PATTERN = re.compile(r'\d+(?:\.\d+)?')
_PRICE_PATTERN = re.compile(r'\$\d+(?:\.\d{2})?')
_VERSION_PATTERN = re.compile(r'(?:v|version\s+)?\d+\.\d+(?:\.\d+)?')

# Verb-based attribute patterns: "X supports Y" → attribute="supports", value="Y"
_ATTRIBUTE_VERBS: list[str] = [
    "costs", "prices", "charges", "offers", "provides", "supports",
    "includes", "requires", "uses", "enables", "features",
    "launched", "released", "announced", "acquired",
    "has", "contains", "delivers", "gives",
    "is", "was", "are", "were",
]


def _extract_entity(claim: str) -> str | None:
    """Extract the primary entity (capitalized noun phrase) from a claim."""
    matches = _ENTITY_PATTERN.findall(claim)
    # Filter out stop words and common non-entities
    stop_entities = {"The", "This", "That", "These", "Those", "It",
                     "We", "They", "He", "She", "I", "You",
                     "However", "Therefore", "Additionally", "Also",
                     "First", "Second", "Third", "Finally", "Next",
                     "Our", "My", "Your", "His", "Her", "Its",
                     "API", "SDK", "Version", "Release"}
    for m in matches:
        cleaned = m.strip()
        if cleaned in stop_entities:
            continue
        if len(cleaned) < 2:
            continue
        return cleaned
    return None


def _extract_attribute(claim: str) -> str | None:
    """Extract the attribute/predicate from a claim."""
    lower = claim.lower()
    for verb in _ATTRIBUTE_VERBS:
        pattern = re.compile(r'\b' + re.escape(verb) + r'\b', re.IGNORECASE)
        match = pattern.search(lower)
        if match:
            return verb
    return None


def _extract_value(claim: str) -> str | None:
    """Extract the value (price, number, version) from a claim."""
    # Try price first
    price = _PRICE_PATTERN.search(claim)
    if price:
        return price.group()
    # Try version
    version = _VERSION_PATTERN.search(claim)
    if version:
        return version.group()
    # Try generic number
    number = _NUMBER_PATTERN.search(claim)
    if number:
        return number.group()
    return None


def _entity_attribute_key(entity: str | None, attribute: str | None) -> str:
    """Create a merge key for grouping claims about the same entity+attribute."""
    return f"{entity or 'unknown'}::{attribute or 'unknown'}"


class FactReasoner:
    """Analyzes facts across sources for contradictions, agreements, and gaps.

    Usage:
        reasoner = FactReasoner()
        comparison = reasoner.analyze(facts)
        if comparison.has_conflicts():
            print(comparison.summary())
    """

    def analyze(self, facts: list[Fact]) -> FactComparison:
        """Analyze a list of facts and produce a structured comparison."""
        if not facts:
            return FactComparison()

        # Extract sources
        sources = sorted(set(f.source_url for f in facts))

        # Group facts by entity+attribute key
        groups: dict[str, list[Fact]] = defaultdict(list)
        for f in facts:
            entity = _extract_entity(f.claim)
            attribute = _extract_attribute(f.claim)
            key = _entity_attribute_key(entity, attribute)
            groups[key].append(f)

        contradictions: list[Contradiction] = []
        agreements: list[Agreement] = []
        unique_claims: list[UniqueClaim] = []

        for key, group_facts in groups.items():
            entity = _extract_entity(group_facts[0].claim)
            attribute = _extract_attribute(group_facts[0].claim)

            # Collect distinct values
            values: dict[str, list[Fact]] = defaultdict(list)
            for f in group_facts:
                val = _extract_value(f.claim)
                if val:
                    values[val].append(f)

            if not values:
                # Non-numeric claims — treat as agreements if multiple sources
                if len(group_facts) >= 2:
                    source_set = set(f.source_url for f in group_facts)
                    if len(source_set) >= 2:
                        agreements.append(Agreement(
                            entity=entity or "unknown",
                            attribute=attribute or "unknown",
                            value=group_facts[0].claim[:80],
                            facts=group_facts,
                        ))
                else:
                    # Single source, no numeric value — unique claim
                    unique_claims.append(UniqueClaim(
                        entity=entity or "unknown",
                        attribute=attribute or "unknown",
                        value=group_facts[0].claim[:80],
                        fact=group_facts[0],
                    ))
                continue

            # Multiple different values for same entity+attribute → contradiction
            if len(values) > 1:
                all_values = list(values.keys())
                all_facts: list[Fact] = []
                for vf in values.values():
                    all_facts.extend(vf)

                # Determine confidence based on source diversity
                source_set = set(f.source_url for f in all_facts)
                confidence = min(1.0, 0.5 + len(source_set) * 0.15)

                contradictions.append(Contradiction(
                    entity=entity or "unknown",
                    attribute=attribute or "unknown",
                    values=all_values,
                    facts=all_facts,
                    confidence=round(confidence, 2),
                ))
            else:
                # Single value — check if cross-source
                val = list(values.keys())[0]
                source_set = set(f.source_url for f in values[val])
                if len(source_set) >= 2:
                    agreements.append(Agreement(
                        entity=entity or "unknown",
                        attribute=attribute or "unknown",
                        value=val,
                        facts=values[val],
                    ))
                elif len(values[val]) == 1:
                    unique_claims.append(UniqueClaim(
                        entity=entity or "unknown",
                        attribute=attribute or "unknown",
                        value=val,
                        fact=values[val][0],
                    ))

        # Gap detection — identify entities mentioned by only one source
        # or entities with contradictory claims that lack resolution
        gaps: list[Gap] = []
        for c in contradictions:
            if len(c.values) >= 2:
                gaps.append(Gap(
                    question=f"What is the correct {c.attribute} for {c.entity}?",
                    entity=c.entity,
                ))

        return FactComparison(
            contradictions=contradictions,
            agreements=agreements,
            unique_claims=unique_claims,
            gaps=gaps,
            total_facts=len(facts),
            sources_analyzed=sources,
        )
