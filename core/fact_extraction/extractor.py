"""Browser fact extraction utilities."""
from __future__ import annotations

import re
import uuid
from typing import Any

from core.fact_extraction.models import ExtractedFact


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower()
    text = text.replace(".", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _guess_entity(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    matches = re.findall(r"[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)*|[A-Z]{2,}", cleaned)
    if matches:
        return matches[0]
    words = cleaned.split()
    if len(words) >= 2:
        return words[0].lower()
    return cleaned.lower()


def _classify(claim: str, source_type: str | None = None) -> str:
    text = (claim or "").lower()
    if source_type == "table":
        return "property"
    if "$" in claim or "price" in text or "cost" in text:
        return "pricing"
    if "how to" in text or "install" in text or "tutorial" in text:
        return "tutorial"
    if "vs" in text or "versus" in text or "compare" in text:
        return "comparison"
    if any(token in text for token in ("version", "release", "api", "framework", "python", "javascript", "rust", "aws", "docker", "server")):
        return "technical"
    return "general"


def _score_confidence(text: str) -> float:
    score = 0.5
    if not text:
        return 0.0
    normalized = text.lower()
    if re.search(r"\d", normalized):
        score += 0.2
    if re.search(r"\b(?:python|javascript|rust|aws|google|microsoft|docker|api|server|linux|windows)\b", normalized):
        score += 0.15
    if re.search(r"\b(?:202[0-9]|19[0-9]{2})\b", normalized):
        score += 0.1
    if any(word in normalized for word in ("maybe", "possibly", "perhaps", "probably", "unclear")):
        score -= 0.2
    if "officially confirmed" in normalized or "released" in normalized:
        score += 0.1
    return max(0.0, min(1.0, score))


class BrowserFactExtractor:
    def extract_from_snapshot(self, snapshot: dict[str, Any], page_url: str, max_facts: int = 50) -> list[ExtractedFact]:
        facts: list[ExtractedFact] = []
        seen: set[str] = set()

        def add_fact(claim: str, source_type: str, entity: str | None = None, category: str | None = None, source_url: str | None = None, confidence: float | None = None, attributes: dict[str, Any] | None = None):
            if not claim or not claim.strip():
                return
            key = (claim.strip().lower(), str(source_url or page_url).lower())
            if key in seen:
                return
            seen.add(key)
            fact = ExtractedFact(
                fact_id=str(uuid.uuid4()),
                entity=entity or _guess_entity(claim) or "Unknown",
                claim=claim.strip(),
                source_url=source_url or page_url,
                source_type=source_type,
                category=category or _classify(claim, source_type),
                confidence=float(confidence if confidence is not None else _score_confidence(claim)),
                tags=[entity] if entity else [],
                attributes=attributes or {},
            )
            facts.append(fact)

        title = (snapshot or {}).get("title")
        if title:
            add_fact(title, "heading", entity=_guess_entity(title), category="general", source_url=page_url)

        for heading in (snapshot or {}).get("headings", []) or []:
            text = (heading.get("text") if isinstance(heading, dict) else str(heading)).strip()
            if text:
                add_fact(text, f"heading_{(heading.get('tag') if isinstance(heading, dict) else 'heading').lower()}", entity=_guess_entity(text), source_url=page_url)

        for paragraph in (snapshot or {}).get("paragraphs", []) or []:
            text = (paragraph.get("text") if isinstance(paragraph, dict) else str(paragraph)).strip()
            if text:
                add_fact(text, "paragraph", entity=_guess_entity(text), source_url=page_url)

        for table in (snapshot or {}).get("tables", []) or []:
            caption = table.get("caption", "") if isinstance(table, dict) else str(table)
            rows = table.get("rows", []) if isinstance(table, dict) else []
            for row in rows:
                cells = row.get("cells", []) if isinstance(row, dict) else []
                if cells:
                    left, right = str(cells[0]), str(cells[1]) if len(cells) > 1 else ""
                    claim = f"{left}: {right}" if right else left
                    add_fact(claim, "table", entity=_guess_entity(left), source_url=page_url, category="property", attributes={"caption": caption})

        for item in (snapshot or {}).get("definition_lists", []) or []:
            if isinstance(item, dict):
                for term in item.get("terms", []) or []:
                    if isinstance(term, dict):
                        text = term.get("term") or term.get("definition")
                        if text:
                            add_fact(str(text), "definition", entity=_guess_entity(str(text)), source_url=page_url)

        for item in (snapshot or {}).get("list_items", []) or []:
            text = (item.get("text") if isinstance(item, dict) else str(item)).strip()
            if text:
                add_fact(text, "list_item", entity=_guess_entity(text), source_url=page_url)

        facts.sort(key=lambda fact: fact.confidence, reverse=True)
        if max_facts is not None:
            facts = facts[: max_facts]
        return facts

    def to_json_serializable(self, facts: list[ExtractedFact]) -> list[dict[str, Any]]:
        return [fact.to_dict() for fact in facts]


__all__ = ["BrowserFactExtractor", "_normalize", "_guess_entity", "_classify", "_score_confidence"]
