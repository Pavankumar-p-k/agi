"""SQLite-backed storage for browser-extracted facts."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.fact_extraction.models import ExtractedFact


class BrowserFactStore:
    def __init__(self, db_path: str = ":memory:"):
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("CREATE TABLE IF NOT EXISTS facts (fact_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def _row_to_fact(self, row: tuple[str, str]) -> ExtractedFact:
        fact_id, payload = row
        data = json.loads(payload)
        data["fact_id"] = fact_id
        return ExtractedFact(**data)

    def store_facts(self, facts: list[ExtractedFact]) -> None:
        for fact in facts:
            key = (fact.claim.strip().lower(), fact.source_url.strip().lower())
            for existing_id, payload in self._conn.execute("SELECT fact_id, payload FROM facts").fetchall():
                data = json.loads(payload)
                if (str(data.get("claim", "")).strip().lower(), str(data.get("source_url", "")).strip().lower()) == key:
                    self._conn.execute("DELETE FROM facts WHERE fact_id = ?", (existing_id,))
                    break
            payload = json.dumps(fact.to_dict(), ensure_ascii=False)
            self._conn.execute(
                "INSERT OR REPLACE INTO facts (fact_id, payload) VALUES (?, ?)",
                (fact.fact_id, payload),
            )
        self._conn.commit()

    def fact_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()
        return int(row[0]) if row else 0

    def get_all_facts(self) -> list[ExtractedFact]:
        rows = self._conn.execute("SELECT fact_id, payload FROM facts ORDER BY fact_id").fetchall()
        return [self._row_to_fact(row) for row in rows]

    def get_facts_by_entity(self, entity: str) -> list[ExtractedFact]:
        rows = self._conn.execute("SELECT fact_id, payload FROM facts").fetchall()
        return [self._row_to_fact(r) for r in rows if json.loads(r[1]).get("entity") == entity]

    def get_facts_by_category(self, category: str) -> list[ExtractedFact]:
        rows = self._conn.execute("SELECT fact_id, payload FROM facts").fetchall()
        return [self._row_to_fact(r) for r in rows if json.loads(r[1]).get("category") == category]

    def search_facts(self, query: str) -> list[ExtractedFact]:
        query = query.lower()
        rows = self._conn.execute("SELECT fact_id, payload FROM facts").fetchall()
        return [self._row_to_fact(r) for r in rows if query in json.loads(r[1]).get("claim", "").lower()]

    def delete_fact(self, fact_id: str) -> None:
        self._conn.execute("DELETE FROM facts WHERE fact_id = ?", (fact_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
