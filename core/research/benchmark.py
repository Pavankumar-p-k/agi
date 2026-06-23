"""Phase 7.2 Research Benchmark — R1 through R5.

Tests the complete research pipeline:
  R1 — Single-page extraction
  R2 — Multi-page aggregation
  R3 — Contradiction detection
  R4 — Fact synthesis
  R5 — Research report generation

Each benchmark returns a dict with pass/fail + metrics.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from typing import Any

from core.research.extractor import FactExtractor
from core.research.reasoner import FactReasoner
from core.research.retriever import FactRetriever
from core.research.synthesizer import FactSynthesizer
from core.research.storage import FactStore

logger = logging.getLogger(__name__)

# ── Sample data ──────────────────────────────────────────────────────────

_PAGE_A = (
    "TechCrunch announced that Company X launched Product Y in January 2025. "
    "The product costs $10 per month. "
    "It supports REST APIs and WebSocket connections. "
    "Company X claims it handles 10,000 requests per second. "
    "Please sign in to your account to see pricing details."
)

_PAGE_B = (
    "Ars Technica reports that Company X released Product Y last quarter. "
    "The device costs $12 per month according to their website. "
    "It offers a free tier with limited features. "
    "Reviewers note it handles 5,000 requests per second in testing. "
    "Click here to subscribe for more details."
)

_PAGE_C = (
    "According to Company X's official documentation, "
    "Product Y is their latest cloud service. "
    "The enterprise plan is priced at $10 per month. "
    "It provides REST API support and a new GraphQL endpoint. "
    "The service launched in December 2024. "
    "This is not financial advice."
)


def _make_store() -> tuple[FactStore, str]:
    """Create a temporary FactStore and return (store, tmpdir)."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "bench.db")
    store = FactStore(db_path=db_path)
    return store, tmpdir


def _extract_all(extractor: FactExtractor) -> tuple[list, list, list]:
    """Extract facts from all three sample pages."""
    fa = extractor.extract(_PAGE_A, "https://techcrunch.com/product-y")
    fb = extractor.extract(_PAGE_B, "https://arstechnica.com/product-y")
    fc = extractor.extract(_PAGE_C, "https://companyx.com/product-y")
    return fa, fb, fc


# ── Benchmarks ──────────────────────────────────────────────────────────


def fact_extractor_benchmark() -> dict[str, Any]:
    """R1 — Single-page extraction quality."""
    extractor = FactExtractor()
    facts = extractor.extract(_PAGE_A, "https://techcrunch.com/product-y",
                              max_facts=20)

    sufficient_count = len(facts) >= 3
    has_no_nav = not any("sign in" in f.claim.lower() for f in facts)
    categories = [f.category for f in facts]
    has_pricing = "pricing" in categories
    has_technical = "technical" in categories
    has_high_conf = any(f.confidence > 0.6 for f in facts)

    return {
        "benchmark": "R1 — Single-page extraction",
        "pass": sufficient_count and has_no_nav and has_pricing and has_high_conf,
        "metrics": {
            "fact_count": len(facts),
            "categories_found": categories,
            "max_confidence": round(max(f.confidence for f in facts), 2) if facts else 0,
            "nav_filtered": has_no_nav,
        },
        "details": {
            "sufficient_count": sufficient_count,
            "no_nav_text": has_no_nav,
            "has_pricing": has_pricing,
            "has_technical": has_technical,
            "has_high_confidence": has_high_conf,
        },
    }


def multi_page_aggregation_benchmark() -> dict[str, Any]:
    """R2 — Multi-page aggregation via FactRetriever."""
    store, tmpdir = _make_store()
    extractor = FactExtractor()
    retriever = FactRetriever(store)

    fa, fb, fc = _extract_all(extractor)
    for f in fa + fb + fc:
        store.insert_fact(f)

    retrieved = retriever.retrieve("Product Y pricing", limit=50)
    sources = set(f.source_url for f in retrieved)
    multi_source = len(sources) >= 2
    grouped = retriever.group_by_source(retrieved)

    shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "benchmark": "R2 — Multi-page aggregation",
        "pass": multi_source and len(grouped) >= 2,
        "metrics": {
            "total_retrieved": len(retrieved),
            "sources_found": list(sources),
            "groups_count": len(grouped),
            "multi_source": multi_source,
        },
        "details": {
            "facts_per_source": {k: len(v) for k, v in grouped.items()},
        },
    }


def contradiction_detection_benchmark() -> dict[str, Any]:
    """R3 — Contradiction detection across sources."""
    store, tmpdir = _make_store()
    extractor = FactExtractor()
    reasoner = FactReasoner()

    fa, fb, fc = _extract_all(extractor)
    all_facts = fa + fb + fc

    comparison = reasoner.analyze(all_facts)

    has_contradictions = len(comparison.contradictions) > 0
    has_agreements = len(comparison.agreements) > 0
    has_unique = len(comparison.unique_claims) > 0
    has_gaps = len(comparison.gaps) > 0

    shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "benchmark": "R3 — Contradiction detection",
        "pass": has_contradictions and has_unique and has_gaps,
        "metrics": {
            "contradictions": len(comparison.contradictions),
            "agreements": len(comparison.agreements),
            "unique_claims": len(comparison.unique_claims),
            "gaps": len(comparison.gaps),
            "total_facts": comparison.total_facts,
        },
        "details": {
            "contradiction_summaries": [c.summary() for c in comparison.contradictions],
            "agreement_summaries": [a.summary() for a in comparison.agreements],
            "has_contradictions": has_contradictions,
            "has_agreements": has_agreements,
            "has_unique": has_unique,
            "has_gaps": has_gaps,
        },
    }


def fact_synthesis_benchmark() -> dict[str, Any]:
    """R4 — Fact synthesis from multiple sources."""
    store, tmpdir = _make_store()
    extractor = FactExtractor()
    reasoner = FactReasoner()
    synthesizer = FactSynthesizer()

    fa, fb, fc = _extract_all(extractor)
    all_facts = fa + fb + fc
    comparison = reasoner.analyze(all_facts)

    report = synthesizer.synthesize(
        topic="Product Y — Competitive Analysis",
        facts=all_facts,
        comparison=comparison,
    )

    has_summary = len(report.summary) > 50
    has_evidence = len(report.evidence_by_source) >= 2
    has_conflicts = len(report.conflicts) > 0
    has_recommendations = len(report.recommendations) > 0
    has_sources = len(report.sources_consulted) >= 2
    has_confidence = 0.0 <= report.overall_confidence <= 1.0

    shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "benchmark": "R4 — Fact synthesis",
        "pass": (has_summary and has_evidence and has_conflicts
                 and has_recommendations and has_sources and has_confidence),
        "metrics": {
            "summary_length": len(report.summary),
            "evidence_sources": len(report.evidence_by_source),
            "conflict_count": len(report.conflicts),
            "recommendation_count": len(report.recommendations),
            "overall_confidence": report.overall_confidence,
        },
        "details": {
            "has_summary": has_summary,
            "has_evidence": has_evidence,
            "has_conflicts": has_conflicts,
            "has_recommendations": has_recommendations,
            "has_sources": has_sources,
            "has_confidence": has_confidence,
        },
    }


def report_generation_benchmark() -> dict[str, Any]:
    """R5 — End-to-end research report generation."""
    store, tmpdir = _make_store()
    extractor = FactExtractor()
    reasoner = FactReasoner()
    synthesizer = FactSynthesizer()
    retriever = FactRetriever(store)

    fa, fb, fc = _extract_all(extractor)
    for f in fa + fb + fc:
        store.insert_fact(f)

    retrieved = retriever.retrieve("Product Y pricing features")
    comparison = reasoner.analyze(retrieved)
    has_reasoning = comparison.total_facts > 0

    report = synthesizer.synthesize(
        topic="Product Y — Full Analysis",
        facts=retrieved,
        comparison=comparison,
    )

    has_all_fields = all([
        report.topic,
        report.sources_consulted,
        report.total_facts > 0,
        len(report.summary) > 50,
        report.evidence_by_source,
        len(report.generated_at) > 0,
    ])

    shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "benchmark": "R5 — End-to-end research report",
        "pass": has_reasoning and has_all_fields,
        "metrics": {
            "facts_extracted": len(fa) + len(fb) + len(fc),
            "facts_retrieved": len(retrieved),
            "sources_consulted": len(report.sources_consulted),
            "agreements": len(comparison.agreements),
            "contradictions": len(comparison.contradictions),
            "recommendations": len(report.recommendations),
        },
        "details": {
            "has_reasoning": has_reasoning,
            "has_all_fields": has_all_fields,
            "summary_preview": report.summary[:200],
        },
    }


def run_all() -> dict[str, Any]:
    """Run all R1-R5 benchmarks and return aggregated results."""
    results: dict[str, Any] = {
        "phase": "7.2",
        "benchmarks": {},
        "summary": {},
    }

    for name, fn in [
        ("R1", fact_extractor_benchmark),
        ("R2", multi_page_aggregation_benchmark),
        ("R3", contradiction_detection_benchmark),
        ("R4", fact_synthesis_benchmark),
        ("R5", report_generation_benchmark),
    ]:
        try:
            result = fn()
            results["benchmarks"][name] = result
        except Exception as e:
            results["benchmarks"][name] = {
                "benchmark": name,
                "pass": False,
                "error": str(e),
            }

    passed = sum(1 for b in results["benchmarks"].values() if b.get("pass"))
    total = len(results["benchmarks"])
    results["summary"] = {
        "passed": passed,
        "total": total,
        "pass_rate": f"{passed}/{total}",
        "status": "PASS" if passed == total else f"{passed}/{total}",
    }

    return results
