import re
from datetime import datetime
from uuid import uuid4

from .models import ExtractedFact


_ENTITY_PATTERNS = [
    (re.compile(r"\b(version|v)\s*(\d[\d.]*)", re.I), "technical"),
    (re.compile(r"\$\s*[\d,]+\.?\d*"), "pricing"),
    (re.compile(r"\b(price|cost|fee|charge|rate)\s*(:.*|is.*)", re.I), "pricing"),
    (re.compile(r"\b(released|launched|announced|updated)\s", re.I), "news"),
    (re.compile(r"\b(tutorial|guide|how to|example|walkthrough)\b", re.I), "tutorial"),
    (re.compile(r"\b(versus|vs\.|compared|alternative|instead of)\b", re.I), "comparison"),
    (re.compile(r"\d{4}\b"), "news"),
    (re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b"), "technical"),
]

_CONFIDENCE_BOOST = re.compile(
    r"\b(confirmed|according to|officially|announced|documented|reported|"
    r"latest|current|verified|as of)\b", re.I
)
_CONFIDENCE_PENALTY = re.compile(
    r"\b(maybe|perhaps|possibly|might|could|seems|appears|i think|"
    r"i believe|probably|allegedly)\b", re.I
)


class BrowserFactExtractor:
    def extract_from_snapshot(
        self,
        snapshot: dict,
        source_url: str,
        max_facts: int = 30,
    ) -> list[ExtractedFact]:
        facts: list[ExtractedFact] = []
        seen_claims: set[str] = set()

        now = datetime.utcnow().isoformat(timespec="seconds")

        title = snapshot.get("title", "") or ""
        url = source_url or snapshot.get("url", "") or ""

        # 1. Headings + paragraph text
        headings = snapshot.get("headings", [])
        paragraphs = snapshot.get("paragraphs", [])
        if headings and paragraphs:
            for item in _collect_headings_with_content(headings, paragraphs):
                fact = self._make_fact(item["claim"], item["entity"], url,
                                       item["source_type"], now, seen_claims)
                if fact:
                    facts.append(fact)

        if not headings and paragraphs:
            for p in paragraphs:
                txt = (p.get("text", "") or "").strip()
                if len(txt) < 20:
                    continue
                entity = _guess_entity(txt)
                fact = self._make_fact(txt, entity, url, "paragraph", now, seen_claims)
                if fact:
                    facts.append(fact)

        # 2. Tables
        tables = snapshot.get("tables", [])
        for table in tables:
            rows = table.get("rows", [])
            caption = table.get("caption", "")
            for row in rows:
                cells = row.get("cells", [])
                if len(cells) >= 2:
                    key = cells[0].strip()
                    val = cells[1].strip()
                    claim = f"{key}: {val}"
                    if caption:
                        claim = f"[{caption}] {key}: {val}"
                    if len(claim) > 15:
                        entity = _guess_entity(key) or _guess_entity(val)
                        fact = self._make_fact(claim, entity, url, "table", now, seen_claims)
                        if fact:
                            fact.attributes = {key: val}
                            facts.append(fact)

        # 3. Definition lists
        def_lists = snapshot.get("definition_lists", [])
        for dl in def_lists:
            terms = dl.get("terms", [])
            for td in terms:
                term = td.get("term", "").strip()
                defn = td.get("definition", "").strip()
                if term and defn:
                    claim = f"{term}: {defn}"
                    if len(claim) > 15:
                        entity = _guess_entity(term)
                        fact = self._make_fact(claim, entity, url, "definition", now, seen_claims)
                        if fact:
                            fact.attributes = {term: defn}
                            facts.append(fact)

        # 4. List items with context
        list_items = snapshot.get("list_items", [])
        list_parents = snapshot.get("list_parents", [])
        for i, item in enumerate(list_items):
            txt = (item.get("text", "") or "").strip()
            if len(txt) < 20:
                continue
            prefix = list_parents[i] if i < len(list_parents) else ""
            claim = f"{prefix}: {txt}" if prefix else txt
            entity = _guess_entity(txt) or _guess_entity(prefix)
            fact = self._make_fact(claim, entity, url, "list_item", now, seen_claims)
            if fact:
                facts.append(fact)

        # 5. Title as fallback
        if not facts and title:
            entity = _guess_entity(title)
            fact = self._make_fact(title, entity, url, "title", now, seen_claims)
            if fact:
                facts.append(fact)

        # Sort by confidence descending, limit
        facts.sort(key=lambda f: f.confidence, reverse=True)
        return facts[:max_facts]

    def _make_fact(
        self,
        claim: str,
        entity: str | None,
        source_url: str,
        source_type: str,
        now: str,
        seen: set[str],
    ) -> ExtractedFact | None:
        norm = _normalize(claim)
        if not norm or norm in seen:
            return None
        seen.add(norm)
        category = _classify(claim, source_type)
        confidence = _score_confidence(claim)
        tags = _extract_tags(claim)
        return ExtractedFact(
            fact_id=f"fact_{uuid4().hex[:12]}",
            entity=entity,
            claim=claim[:500],
            source_url=source_url,
            source_type=source_type,
            category=category,
            confidence=confidence,
            tags=tags,
            extracted_at=now,
        )

    @staticmethod
    def to_json_serializable(facts: list[ExtractedFact]) -> list[dict]:
        return [
            {
                "fact_id": f.fact_id,
                "entity": f.entity,
                "claim": f.claim,
                "source_url": f.source_url,
                "source_type": f.source_type,
                "category": f.category,
                "confidence": f.confidence,
                "tags": f.tags,
                "attributes": f.attributes,
                "extracted_at": f.extracted_at,
            }
            for f in facts
        ]


def _normalize(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip().lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return t


def _guess_entity(text: str) -> str | None:
    m = re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
    if m:
        return m.group(0)
    m = re.search(r"\b[a-z]+\b", text)
    if m:
        return m.group(0)
    return None


def _classify(claim: str, source_type: str) -> str:
    if source_type == "table" or source_type == "definition":
        return "property"
    lower = claim.lower()
    if any(w in lower for w in ("price", "cost", "$", "fee", "charge", "rate")):
        return "pricing"
    if any(w in lower for w in ("version", "v ", "release", "update")):
        return "technical"
    if any(w in lower for w in ("tutorial", "guide", "how to", "steps")):
        return "tutorial"
    if any(w in lower for w in ("vs", "versus", "compared", "alternative")):
        return "comparison"
    return "general"


def _score_confidence(claim: str) -> float:
    score = 0.5
    if re.search(r"\b\d+\b", claim):
        score += 0.15
    if re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", claim):
        score += 0.1
    if re.search(r"\d{4}", claim):
        score += 0.1
    if _CONFIDENCE_BOOST.search(claim):
        score += 0.1
    if _CONFIDENCE_PENALTY.search(claim):
        score -= 0.2
    if len(claim) > 100:
        score += 0.05
    if len(claim) > 200:
        score += 0.05
    return max(0.0, min(1.0, round(score, 2)))


def _extract_tags(claim: str) -> list[str]:
    tags = []
    for m in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", claim):
        tags.append(m.group(0))
    for m in re.finditer(r"\bv?\d+[\d.]*\b", claim, re.I):
        tags.append(m.group(0))
    return tags[:6]


def _collect_headings_with_content(
    headings: list[dict],
    paragraphs: list[dict],
) -> list[dict]:
    results = []
    p_idx = 0
    for h in headings:
        h_tag = h.get("tag", "h2").upper()
        h_text = (h.get("text", "") or "").strip()
        if not h_text:
            continue
        entity = _guess_entity(h_text)
        following: list[str] = []
        while p_idx < len(paragraphs):
            p_text = (paragraphs[p_idx].get("text", "") or "").strip()
            if not p_text:
                p_idx += 1
                continue
            following.append(p_text)
            p_idx += 1
            break
        if following:
            claim = f"[{h_tag}] {h_text}: {' '.join(following)}"
            results.append({"claim": claim[:500], "entity": entity, "source_type": f"heading_{h_tag.lower()}"})
        else:
            results.append({"claim": h_text, "entity": entity, "source_type": f"heading_{h_tag.lower()}"})
    for p in paragraphs[p_idx:]:
        txt = (p.get("text", "") or "").strip()
        if txt:
            results.append({"claim": txt, "entity": _guess_entity(txt), "source_type": "paragraph"})
    return results
