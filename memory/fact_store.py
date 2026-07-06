from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Generator, List

from memory.extraction import ExtractedFact

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/jarvis_memory.db")


class FactStore:
    """SQLite-backed store for extracted facts with optional embedding support.

    The store is thread-safe via a reentrant lock.  Fact embeddings are
    generated lazily using the existing ``EmbeddingMemory.embed()``
    infrastructure.
    """

    def __init__(self, db_path: str | Path = _DB_PATH, disable_embedding: bool = False) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._embedding_available: bool = not disable_embedding
        self._init_db()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id          TEXT PRIMARY KEY,
                    subject     TEXT NOT NULL,
                    predicate   TEXT NOT NULL,
                    object      TEXT NOT NULL,
                    confidence  REAL NOT NULL DEFAULT 0.5,
                    category    TEXT NOT NULL DEFAULT 'fact',
                    user_id     TEXT NOT NULL DEFAULT '',
                    source_text TEXT NOT NULL DEFAULT '',
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    is_active   INTEGER NOT NULL DEFAULT 1,
                    embedding   BLOB,
                    activity_id TEXT,
                    conversation_id TEXT,
                    source_message TEXT,
                    last_verified REAL,
                    verification_level TEXT DEFAULT 'extracted',
                    derived_from TEXT
                )
            """)
            # Migrate existing databases — add missing columns
            existing_cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(facts)").fetchall()
            }
            _PROVENANCE_COLUMNS: dict[str, str] = {
                "activity_id": "TEXT",
                "conversation_id": "TEXT",
                "source_message": "TEXT",
                "last_verified": "REAL",
                "verification_level": "TEXT DEFAULT 'extracted'",
                "derived_from": "TEXT",
            }
            for col_name, col_type in _PROVENANCE_COLUMNS.items():
                if col_name not in existing_cols:
                    conn.execute(f"ALTER TABLE facts ADD COLUMN {col_name} {col_type}")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_facts_user
                ON facts(user_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_facts_category
                ON facts(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_facts_subject
                ON facts(subject)
            """)

    @contextlib.contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def store_facts(
        self,
        facts: list[ExtractedFact],
        user_id: str = "",
        force: bool = False,
    ) -> list[str]:
        """Insert extracted facts, deduplicating by (subject, predicate, object, user_id).

        When *force* is True, dedup is skipped and every fact is inserted
        (useful for storing contradictory facts).

        Returns the list of fact IDs that were inserted.
        """
        inserted: list[str] = []
        now = time.time()

        with self._lock, self._connect() as conn:
            for fact in facts:
                fact_user = fact.user_id or user_id

                if not force:
                    # Check for existing fact (case-insensitive)
                    existing = conn.execute(
                        """SELECT id, confidence FROM facts
                           WHERE LOWER(subject)=LOWER(?) AND LOWER(predicate)=LOWER(?)
                             AND LOWER(object)=LOWER(?) AND user_id=?""",
                        (fact.subject, fact.predicate, fact.object, fact_user),
                    ).fetchone()

                    if existing:
                        # Update confidence if new fact is more confident
                        if fact.confidence > existing["confidence"]:
                            conn.execute(
                                """UPDATE facts SET confidence=?, updated_at=?, is_active=1 WHERE id=?""",
                                (fact.confidence, now, existing["id"]),
                            )
                        continue

                fact_id = uuid.uuid4().hex
                embedding = self._compute_embedding(f"{fact.subject} {fact.predicate} {fact.object}")
                embedding_blob = self._serialize_embedding(embedding)

                conn.execute(
                    """INSERT INTO facts
                       (id, subject, predicate, object, confidence, category, user_id,
                        source_text, created_at, updated_at, embedding, is_active,
                        activity_id, conversation_id, source_message,
                        last_verified, verification_level, derived_from)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
                               ?, ?, ?, ?, ?, ?)""",
                    (
                        fact_id, fact.subject, fact.predicate, fact.object,
                        fact.confidence, fact.category, fact_user,
                        fact.source_text, now, now, embedding_blob,
                        fact.activity_id, fact.conversation_id, fact.source_message,
                        fact.last_verified, fact.verification_level, fact.derived_from,
                    ),
                )
                inserted.append(fact_id)

        if inserted:
            logger.debug("Stored %d new facts for user '%s'", len(inserted), user_id)
        return inserted

    def search_facts(
        self,
        query: str,
        user_id: str = "",
        limit: int = 10,
        min_confidence: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Search facts by semantic similarity to the query.

        Falls back to keyword matching when embeddings are unavailable.
        """
        query_embedding = self._compute_embedding(query)
        if query_embedding is not None:
            return self._search_by_embedding(query_embedding, user_id, limit, min_confidence)
        return self._search_by_keyword(query, user_id, limit, min_confidence)

    def get_user_facts(
        self,
        user_id: str,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve all active facts for a user, optionally filtered by category."""
        with self._lock, self._connect() as conn:
            if category:
                rows = conn.execute(
                    """SELECT * FROM facts
                       WHERE user_id=? AND is_active=1 AND category=?
                       ORDER BY confidence DESC, updated_at DESC
                       LIMIT ?""",
                    (user_id, category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM facts
                       WHERE user_id=? AND is_active=1
                       ORDER BY confidence DESC, updated_at DESC
                       LIMIT ?""",
                    (user_id, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_fact_by_id(self, fact_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM facts WHERE id=?",
                (fact_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_fact(self, fact_id: str, **updates: Any) -> bool:
        """Update fields on an existing fact.  Returns True if any row changed."""
        allowed = {"confidence", "object", "predicate", "subject", "is_active", "access_count"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return False
        fields["updated_at"] = time.time()
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [fact_id]
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                f"UPDATE facts SET {set_clause} WHERE id=?",
                values,
            )
            return cur.rowcount > 0

    def mark_inactive(self, fact_id: str) -> bool:
        return self.update_fact(fact_id, is_active=0)

    def delete_facts_for_user(self, user_id: str) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM facts WHERE user_id=?",
                (user_id,),
            )
            return cur.rowcount

    # ── Contradiction detection ──────────────────────────────────────────────

    def find_contradictions(
        self,
        new_facts: list[ExtractedFact],
        user_id: str = "",
        threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Check new facts against stored facts for contradictions.

        A contradiction is flagged when the same subject+predicate pair has
        a different object value with confidence above *threshold*.

        Returns a list of dicts with ``existing_fact`` and ``new_fact`` keys.
        """
        contradictions: list[dict[str, Any]] = []
        with self._lock, self._connect() as conn:
            for nf in new_facts:
                rows = conn.execute(
                    """SELECT * FROM facts
                       WHERE LOWER(subject)=LOWER(?) AND LOWER(predicate)=LOWER(?)
                         AND user_id=? AND is_active=1 AND confidence>=?
                         AND LOWER(object)!=LOWER(?)""",
                    (nf.subject, nf.predicate, nf.user_id or user_id, threshold, nf.object),
                ).fetchall()
                for row in rows:
                    contradictions.append({
                        "existing_fact": dict(row),
                        "new_fact": {
                            "subject": nf.subject,
                            "predicate": nf.predicate,
                            "object": nf.object,
                            "confidence": nf.confidence,
                            "category": nf.category,
                            "source_text": nf.source_text,
                        },
                    })
        return contradictions

    # ── Consolidation ─────────────────────────────────────────────────────────

    def consolidate(self, user_id: str = "", min_similarity: float = 0.5) -> int:
        """Merge duplicate or near-duplicate facts for a user.

        Facts with the same (subject, predicate) whose objects share at least
        *min_similarity* fraction of words are consolidated — the higher-
        confidence fact survives, the lower-confidence fact is marked inactive.

        Returns the number of facts deactivated.
        """
        deactivated = 0
        now = time.time()

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM facts
                   WHERE user_id=? AND is_active=1
                   ORDER BY LOWER(subject), LOWER(predicate), confidence DESC""",
                (user_id,),
            ).fetchall()

            groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for row in rows:
                key = (row["subject"].lower(), row["predicate"].lower())
                groups.setdefault(key, []).append(dict(row))

            for key, group in groups.items():
                if len(group) < 2:
                    continue
                # Keep the highest-confidence fact as reference
                reference = group[0]
                for candidate in group[1:]:
                    sim = self._word_overlap(reference["object"], candidate["object"])
                    if sim >= min_similarity:
                        conn.execute(
                            "UPDATE facts SET is_active=0, updated_at=? WHERE id=?",
                            (now, candidate["id"]),
                        )
                        deactivated += 1
                        logger.debug(
                            "Consolidated fact %s into %s (overlap=%.2f)",
                            candidate["id"], reference["id"], sim,
                        )

        return deactivated

    @staticmethod
    def _word_overlap(a: str, b: str) -> float:
        """Fraction of shared words between two strings (order-independent)."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        return len(intersection) / max(len(words_a), len(words_b))

    # ── Embedding helpers ────────────────────────────────────────────────────

    def _compute_embedding(self, text: str) -> list[float] | None:
        if self._embedding_available is False:
            return None
        try:
            from memory.embedding_memory import get_embedding_memory

            result = get_embedding_memory().embed(text)
            if result.is_ok():
                arr = result.unwrap()
                return arr.tolist() if hasattr(arr, "tolist") else list(arr)
            self._embedding_available = False
        except Exception:
            logger.debug("Embedding unavailable for fact: %s", text[:60])
            self._embedding_available = False
        return None

    @staticmethod
    def _serialize_embedding(embedding: list[float] | None) -> bytes | None:
        if embedding is None:
            return None
        import struct
        return struct.pack(f"{len(embedding)}f", *embedding)

    def _search_by_embedding(
        self,
        query_emb: list[float],
        user_id: str,
        limit: int,
        min_confidence: float,
    ) -> list[dict[str, Any]]:
        """Full scan with cosine similarity.  Acceptable for moderate fact counts."""
        import numpy as np
        import struct

        q = np.array(query_emb, dtype=np.float32)
        scored: list[tuple[float, dict[str, Any]]] = []

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM facts
                   WHERE user_id=? AND is_active=1 AND confidence>=?
                   AND embedding IS NOT NULL
                   ORDER BY confidence DESC LIMIT 200""",
                (user_id, min_confidence),
            ).fetchall()

            for row in rows:
                blob = row["embedding"]
                if not blob:
                    continue
                vec = np.frombuffer(blob, dtype=np.float32)
                if len(vec) != len(q):
                    continue
                sim = float(np.dot(q, vec) / (np.linalg.norm(q) * np.linalg.norm(vec) + 1e-10))
                scored.append((sim, dict(row)))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def _search_by_keyword(
        self,
        query: str,
        user_id: str,
        limit: int,
        min_confidence: float,
    ) -> list[dict[str, Any]]:
        """Simple LIKE search across subject/predicate/object fields."""
        terms = query.lower().split()
        if not terms:
            return []

        conditions = " AND ".join(
            f"(LOWER(subject) LIKE ? OR LOWER(predicate) LIKE ? OR LOWER(object) LIKE ?)"
            for _ in terms
        )
        params: list[str] = []
        for t in terms:
            pattern = f"%{t}%"
            params.extend([pattern, pattern, pattern])
        params.extend([user_id, min_confidence, limit])

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""SELECT * FROM facts
                   WHERE ({conditions}) AND user_id=? AND is_active=1 AND confidence>=?
                   ORDER BY confidence DESC, updated_at DESC
                   LIMIT ?""",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Stats ────────────────────────────────────────────────────────────────

    def count_facts(self, user_id: str = "") -> int:
        with self._lock, self._connect() as conn:
            if user_id:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM facts WHERE user_id=? AND is_active=1",
                    (user_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM facts WHERE is_active=1",
                ).fetchone()
            return row["cnt"] if row else 0

    def get_categories(self, user_id: str = "") -> dict[str, int]:
        with self._lock, self._connect() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT category, COUNT(*) as cnt FROM facts WHERE user_id=? AND is_active=1 GROUP BY category",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT category, COUNT(*) as cnt FROM facts WHERE is_active=1 GROUP BY category",
                ).fetchall()
            return {r["category"]: r["cnt"] for r in rows}


# ── Singleton accessor ───────────────────────────────────────────────────────


_fact_store: FactStore | None = None


def get_fact_store() -> FactStore:
    global _fact_store
    if _fact_store is None:
        _fact_store = FactStore()
    return _fact_store
