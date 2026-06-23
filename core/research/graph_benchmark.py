"""Phase 7.3 Graph Benchmarks — K1 through K5.

Tests the knowledge graph pipeline:
  K1 — Entity extraction
  K2 — Fact linking
  K3 — Contradiction graph
  K4 — Cross-source graph
  K5 — End-to-end knowledge graph

Each benchmark returns a dict with pass/fail + metrics.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any

from core.research.extractor import FactExtractor
from core.research.graph_store import GraphStore
from core.research.knowledge_graph import KnowledgeGraph
from core.research.linker import Linker
from core.research.models import Fact

# ── Sample data ──────────────────────────────────────────────────────────

_PAGE_A = (
    "TechCrunch announced that Company X launched Product Y in January 2025. "
    "The product costs $10 per month. "
    "It supports REST APIs and WebSocket connections. "
    "Company X claims it handles 10,000 requests per second."
)

_PAGE_B = (
    "Ars Technica reports that Company X released Product Y last quarter. "
    "The device costs $12 per month according to their website. "
    "It offers a free tier with limited features. "
    "Reviewers note it handles 5,000 requests per second in testing."
)

_PAGE_C = (
    "According to Company X's official documentation, "
    "Product Y is their latest cloud service. "
    "The enterprise plan is priced at $10 per month. "
    "It provides REST API support and a new GraphQL endpoint. "
    "The service launched in December 2024."
)


def _make_store() -> tuple[GraphStore, str]:
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "graph_bench.db")
    store = GraphStore(db_path=db_path)
    return store, tmpdir


def _make_kg() -> tuple[KnowledgeGraph, str, list[Fact]]:
    """Create a populated knowledge graph for benchmarks."""
    store, tmpdir = _make_store()
    kg = KnowledgeGraph(store)
    extractor = FactExtractor()

    fa = extractor.extract(_PAGE_A, "https://techcrunch.com/product-y")
    fb = extractor.extract(_PAGE_B, "https://arstechnica.com/product-y")
    fc = extractor.extract(_PAGE_C, "https://companyx.com/product-y")
    all_facts = fa + fb + fc
    kg.add_facts(all_facts)
    return kg, tmpdir, all_facts


# ── Benchmarks ──────────────────────────────────────────────────────────


def entity_extraction_benchmark() -> dict[str, Any]:
    """K1 — Entity extraction from fact claims."""
    linker = Linker()
    extractor = FactExtractor()

    facts = extractor.extract(_PAGE_A, "https://techcrunch.com/product-y")
    all_entities: list[str] = []
    for f in facts:
        all_entities.extend(linker.extract_entities(f))

    unique = list(set(e.lower() for e in all_entities))

    # Should extract: Company X, Product Y, TechCrunch, REST APIs, WebSocket
    has_company_x = "company x" in unique
    has_product_y = "product y" in unique
    has_techcrunch = "techcrunch" in unique
    has_technical = "rest" in unique or "api" in unique
    has_count = len(unique) >= 3

    return {
        "benchmark": "K1 — Entity extraction",
        "pass": has_company_x and has_product_y and has_count,
        "metrics": {
            "entities_found": len(unique),
            "entities_list": unique[:10],
        },
        "details": {
            "has_company_x": has_company_x,
            "has_product_y": has_product_y,
            "has_techcrunch": has_techcrunch,
            "has_technical": has_technical,
        },
    }


def fact_linking_benchmark() -> dict[str, Any]:
    """K2 — Fact-to-entity and fact-to-fact linking."""
    kg, tmpdir, facts = _make_kg()

    stats = kg.get_statistics()
    has_nodes = stats["total_nodes"] > 0
    has_edges = stats["total_edges"] > 0
    has_entities = stats["nodes_by_type"].get("entity", 0) > 0
    has_fact_nodes = stats["nodes_by_type"].get("fact", 0) > 0

    # Check that entities are linked to facts
    entities = kg.get_all_entities()
    entity_linked = False
    if entities:
        linked_facts = kg.get_entity_facts(entities[0].label)
        entity_linked = len(linked_facts) > 0

    shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "benchmark": "K2 — Fact linking",
        "pass": has_nodes and has_edges and has_entities and entity_linked,
        "metrics": {
            "total_nodes": stats["total_nodes"],
            "nodes_by_type": stats["nodes_by_type"],
            "total_edges": stats["total_edges"],
            "edges_by_type": stats["edges_by_type"],
        },
        "details": {
            "has_fact_nodes": has_fact_nodes,
            "has_entity_nodes": has_entities,
            "has_edges": has_edges,
            "entities_linked_to_facts": entity_linked,
        },
    }


def contradiction_graph_benchmark() -> dict[str, Any]:
    """K3 — Contradiction detection in the graph."""
    kg, tmpdir, facts = _make_kg()

    stats = kg.get_statistics()
    contradictions = stats["edges_by_type"].get("CONTRADICTS", 0)
    supports = stats["edges_by_type"].get("SUPPORTS", 0)

    has_contradictions = contradictions > 0

    # Query contradictions for Company X
    contradictions_found = kg.get_contradictions("Company X")
    query_works = len(contradictions_found) > 0

    shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "benchmark": "K3 — Contradiction graph",
        "pass": has_contradictions and query_works,
        "metrics": {
            "contradiction_edges": contradictions,
            "support_edges": supports,
            "total_nodes": stats["total_nodes"],
            "total_edges": stats["total_edges"],
        },
        "details": {
            "has_contradictions": has_contradictions,
            "query_contradictions": query_works,
            "contradiction_count": contradictions,
            "support_count": supports,
        },
    }


def cross_source_graph_benchmark() -> dict[str, Any]:
    """K4 — Cross-source entity and relationship tracking."""
    kg, tmpdir, facts = _make_kg()

    # Query for Company X — should connect facts from all 3 sources
    result = kg.query_entity("Company X")
    nodes_found = len(result.nodes)
    edges_found = len(result.edges)

    # Should have nodes from multiple sources
    source_urls: set[str] = set()
    for node in result.nodes:
        src = node.data.get("source_url", "")
        if src:
            source_urls.add(src)
    multi_source = len(source_urls) >= 2

    shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "benchmark": "K4 — Cross-source graph",
        "pass": multi_source and nodes_found >= 3,
        "metrics": {
            "nodes_found": nodes_found,
            "edges_found": edges_found,
            "sources_in_graph": list(source_urls),
        },
        "details": {
            "multi_source": multi_source,
            "source_count": len(source_urls),
        },
    }


def end_to_end_benchmark() -> dict[str, Any]:
    """K5 — End-to-end knowledge graph construction and query."""
    kg, tmpdir, facts = _make_kg()

    # 1. Stats verify
    stats = kg.get_statistics()
    has_structure = (
        stats["total_nodes"] >= 5
        and stats["total_edges"] >= 3
        and stats["nodes_by_type"].get("fact", 0) >= 3
        and stats["nodes_by_type"].get("entity", 0) >= 2
    )

    # 2. Entity query
    company_x = kg.query_entity("Company X")
    entity_query_works = len(company_x.nodes) >= 2

    # 3. Fact query
    fact_id = next((f.fact_id for f in facts), None)
    fact_query_works = False
    if fact_id:
        fact_result = kg.query_fact(fact_id)
        fact_query_works = len(fact_result.nodes) >= 1 and len(fact_result.edges) >= 1

    # 4. Entity facts
    entity_facts = kg.get_entity_facts("Company X")
    entity_facts_work = len(entity_facts) >= 2

    # 5. Traversal
    traverse_result = kg.traverse("Company X")
    traverse_works = len(traverse_result.nodes) >= 2

    # 6. Statistics
    stats_works = "fact" in stats["nodes_by_type"] and "entity" in stats["nodes_by_type"]

    shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "benchmark": "K5 — End-to-end knowledge graph",
        "pass": (has_structure and entity_query_works and fact_query_works
                 and entity_facts_work and traverse_works and stats_works),
        "metrics": {
            "total_nodes": stats["total_nodes"],
            "total_edges": stats["total_edges"],
            "facts": stats["nodes_by_type"].get("fact", 0),
            "entities": stats["nodes_by_type"].get("entity", 0),
            "contradictions": stats["edges_by_type"].get("CONTRADICTS", 0),
            "supports": stats["edges_by_type"].get("SUPPORTS", 0),
            "references": stats["edges_by_type"].get("REFERENCES", 0),
        },
        "details": {
            "has_structure": has_structure,
            "entity_query_works": entity_query_works,
            "fact_query_works": fact_query_works,
            "entity_facts_work": entity_facts_work,
            "traverse_works": traverse_works,
            "stats_works": stats_works,
        },
    }


def run_all() -> dict[str, Any]:
    """Run all K1-K5 benchmarks and return aggregated results."""
    results: dict[str, Any] = {
        "phase": "7.3",
        "benchmarks": {},
        "summary": {},
    }

    for name, fn in [
        ("K1", entity_extraction_benchmark),
        ("K2", fact_linking_benchmark),
        ("K3", contradiction_graph_benchmark),
        ("K4", cross_source_graph_benchmark),
        ("K5", end_to_end_benchmark),
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
