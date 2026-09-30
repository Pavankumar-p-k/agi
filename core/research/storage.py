# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.models import ResearchResult, ResearchConfidence, Fact, Claim, Source, Hypothesis

logger = logging.getLogger("jarvis.research.storage")


class ResearchStorage:
    """Research data storage connecting to JARVIS memory architecture."""

    def __init__(self, use_existing_memory: bool = True):
        self.use_existing_memory = use_existing_memory
        self.research_results: Dict[str, ResearchResult] = {}
        self.claims_by_task: Dict[str, List[Claim]] = {}
        self.facts_by_source: Dict[str, List[Fact]] = {}

    def save_result(self, result: ResearchResult, task_id: str = "") -> str:
        """Save a research result."""
        result_id = result.id or task_id or str(uuid4())
        self.research_results[result_id] = result

        # Also store claims and facts to existing memory if available
        if self.use_existing_memory:
            try:
                self._store_to_existing_memory(result, result_id)
            except Exception as e:
                logger.debug(f"Existing memory storage unavailable: {e}")

        return result_id

    def _store_to_existing_memory(self, result: ResearchResult, result_id: str) -> None:
        """Store research data to JARVIS existing memory systems."""
        try:
            # Store important facts through the Memory stage gateway (Rule 3).
            from core.pipeline.stages.memory import store_facts

            for fact in result.claims or []:
                # Extract key facts from claims
                if fact.text and len(fact.text) > 10:
                    # Store as a fact with the claim as subject
                    store_facts([
                        type('Fact', (), {
                            'subject': claim_text[:50] if claim_text else "research finding",
                            'predicate': "research_findings",
                            'object': fact.text[:200],
                            'confidence': fact.confidence,
                            'category': "research",
                            'user_id': "jarvis",
                            'tenant_id': "default",
                        })()
                    ], user_id="jarvis", tenant_id="default", force=True)

            # Store claims as facts
            for claim in (result.claims or []):
                if claim.text and len(claim.text) > 10:
                    store_facts([
                        type('Fact', (), {
                            'subject': claim.text[:50],
                            'predicate': "research_claim",
                            'object': claim.evidence_ids.__len__() if claim.evidence_ids else 0,
                            'confidence': claim.confidence,
                            'category': 'research',
                            'user_id': 'jarvis',
                            "tenant_id": "default",
                        })()
                    ], user_id="jarvis", tenant_id="default", force=True)

            # Store evidence relationships to DecisionStore
            from memory.decision_store import DecisionStore
            decision_store = DecisionStore()

            for claim in (result.claims or []):
                if claim.evidence_ids:
                    for eid in claim.evidence_ids[:5]:  # Top 5 evidence items
                        decision_store.store(
                            context=f"research_claim_{result_id}",
                            decision=claim.text[:100] if claim.text else "",
                            alternatives=[],
                            outcome=claim.status,
                            lesson=f"Confidence: {claim.confidence}",
                            success=claim.status in ["supported", "partially_supported"],
                            tags=["research", result_id],
                        )

        except ImportError:
            logger.debug("JARVIS memory modules not available for storage")
        except Exception as e:
            logger.debug(f"Error storing to existing memory: {e}")

    def get_result(self, result_id: str) -> Optional[ResearchResult]:
        """Get a research result by ID."""
        return self.research_results.get(result_id)

    def list_results(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent research results."""
        results = list(self.research_results.values())[-limit:]
        return [
            {
                "id": r.id,
                "query": r.query if hasattr(r, 'query') else "unknown",
                "status": r.status,
                "confidence": r.overall_confidence,
                "fact_count": len(r.claims) if r.claims else 0,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in results
        ]

    def search_results(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search research results by query match."""
        results = []
        for result_id, result in self.research_results.items():
            # Simple match against sub_questions or summary
            text_to_search = " ".join([
                str(result.sub_questions) if hasattr(result, 'sub_questions') else "",
                result.overall_confidence if hasattr(result, 'overall_confidence') else "0",
            ]).lower()

            if query.lower() in text_to_search:
                results.append({
                    "id": result.id,
                    "query": getattr(result, 'query', 'unknown'),
                    "status": result.status,
                    "confidence": result.overall_confidence,
                })

        # Sort by confidence
        results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return results[:limit]

    def clear(self) -> None:
        """Clear all stored research data."""
        self.research_results.clear()
        self.claims_by_task.clear()
        self.facts_by_source.clear()


def uuid4():
    import uuid
    return uuid.uuid4()


class FactStore:
    """SQLite-backed persistence for research facts."""

    def __init__(self, db_path: str = ":memory:") -> None:
        import sqlite3

        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS facts "
            "(fact_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self._conn.commit()

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _key(fact: Fact) -> str:
        return str(fact.fact_id or fact.id)

    def _row_to_fact(self, row) -> Fact:
        fact_id, payload = row
        data = json.loads(payload)
        data["fact_id"] = fact_id
        return Fact.from_dict(data)

    def _all_rows(self):
        return self._conn.execute(
            "SELECT fact_id, payload FROM facts").fetchall()

    # ── CRUD ─────────────────────────────────────────────────────────
    def insert_fact(self, fact: Fact) -> str:
        key = self._key(fact)
        payload = json.dumps(fact.to_dict(), default=str)
        self._conn.execute(
            "INSERT OR REPLACE INTO facts (fact_id, payload) VALUES (?, ?)",
            (key, payload))
        self._conn.commit()
        return key

    def get_fact(self, fact_id: str) -> Optional[Fact]:
        row = self._conn.execute(
            "SELECT fact_id, payload FROM facts WHERE fact_id = ?",
            (str(fact_id),)).fetchone()
        return self._row_to_fact(row) if row else None

    def get_all_facts(self) -> List[Fact]:
        return [self._row_to_fact(row) for row in self._all_rows()]

    def search_facts(self, query: str) -> List[Fact]:
        needle = str(query).lower()
        return [fact for fact in self.get_all_facts()
                if needle in (fact.claim or "").lower()]

    def get_facts_by_activity(self, activity_id: str) -> List[Fact]:
        return [fact for fact in self.get_all_facts()
                if fact.activity_id == activity_id]

    def get_facts_by_source(self, source_url: str) -> List[Fact]:
        return [fact for fact in self.get_all_facts()
                if fact.source_url == source_url]

    def get_facts_by_category(self, category: str) -> List[Fact]:
        return [fact for fact in self.get_all_facts()
                if fact.category == category]

    def delete_fact(self, fact_id: str) -> None:
        self._conn.execute("DELETE FROM facts WHERE fact_id = ?",
                           (str(fact_id),))
        self._conn.commit()

    def delete_facts_by_activity(self, activity_id: str) -> int:
        keys = [self._key(fact) for fact in self.get_all_facts()
                if fact.activity_id == activity_id]
        for key in keys:
            self.delete_fact(key)
        return len(keys)

    def count_facts(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()
        return int(row[0]) if row else 0

    def count_by_source(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for fact in self.get_all_facts():
            counts[fact.source_url] = counts.get(fact.source_url, 0) + 1
        return counts

    def count_by_category(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for fact in self.get_all_facts():
            counts[fact.category] = counts.get(fact.category, 0) + 1
        return counts

    def close(self) -> None:
        self._conn.close()


# Singleton
research_storage = ResearchStorage()