"""
memory/cleanup.py — Hybrid Memory Model + Daily Cleanup
=========================================================
Short-term: message content, 30 day retention.
Long-term: metadata and extracted tokens (permanent).
Daily cleanup: extracts important tokens before deleting content.
"""
from __future__ import annotations
import logging, re, time, sqlite3
from db.schema import connect, DB_PATH

logger = logging.getLogger(__name__)

# Token patterns to extract before deleting messages
TOKEN_PATTERNS = {
    "nickname": [
        r"call me (\w+)", r"my name is (\w+)", r"they call me (\w+)"
    ],
    "inside_joke": [
        r"remember when (.{10,60})", r"that time (.{10,60})", r"lol that (.{10,40})"
    ],
    "preference": [
        r"i love (\w[\w\s]{0,30})", r"i hate (\w[\w\s]{0,30})",
        r"my favorite (.{5,40})", r"i prefer (.{5,40})"
    ],
    "fact": [
        r"i work at (.{5,40})", r"i'm from (.{5,30})",
        r"i study (.{5,40})", r"i live in (.{5,30})"
    ],
}


class MemoryCleanup:

    def __init__(self, db_path: str = DB_PATH):
        self._db = db_path

    def run_daily_cleanup(self) -> dict:
        """
        1. Extract important tokens from messages about to expire
        2. Delete expired messages
        Returns stats dict.
        """
        stats = {"tokens_extracted": 0, "messages_deleted": 0, "friends_processed": 0}

        # Get messages expiring in next 48h
        expiry_threshold = time.time() + 48 * 3600
        con = connect(self._db)
        rows = con.execute(
            "SELECT id, friend_id, content FROM short_term_messages "
            "WHERE expires_at < ?",
            (expiry_threshold,)
        ).fetchall()
        con.close()

        # Extract tokens from expiring messages
        for row in rows:
            extracted = self._extract_tokens(row["content"])
            for token_type, value in extracted:
                self._store_token(row["friend_id"], token_type, value, row["content"])
                stats["tokens_extracted"] += 1

        # Delete expired messages
        now = time.time()
        con = connect(self._db)
        result = con.execute(
            "DELETE FROM short_term_messages WHERE expires_at < ?", (now,)
        )
        stats["messages_deleted"] = result.rowcount
        con.commit()
        con.close()

        # Also prune excess reasoning_traces (keep 7 days)
        con = connect(self._db)
        con.execute(
            "DELETE FROM metadata_logs WHERE timestamp < ?",
            (now - 90 * 86400,)
        )
        con.commit()
        con.close()

        logger.info("[Cleanup] Done: %s", stats)
        return stats

    def _extract_tokens(self, text: str) -> list[tuple[str, str]]:
        found = []
        text_lower = text.lower()
        for token_type, patterns in TOKEN_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text_lower)
                for m in matches:
                    clean = m.strip()
                    if 2 < len(clean) < 60:
                        found.append((token_type, clean))
        return found

    def _store_token(self, friend_id: str, token_type: str,
                      value: str, context: str) -> None:
        try:
            con = connect(self._db)
            con.execute("""
                INSERT INTO memory_tokens (friend_id, token_type, token_value, context)
                VALUES (?,?,?,?)
                ON CONFLICT(friend_id, token_type, token_value) DO UPDATE SET
                    times_used = times_used + 1
            """, (friend_id, token_type, value, context[:100]))
            con.commit()
            con.close()
        except Exception as e:
            logger.warning("[Memory] Token store error: %s", e)

    def get_tokens(self, friend_id: str) -> list[dict]:
        con = connect(self._db)
        rows = con.execute(
            "SELECT * FROM memory_tokens WHERE friend_id=? ORDER BY times_used DESC",
            (friend_id,)
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        con = connect(self._db)
        msg_count = con.execute("SELECT COUNT(*) FROM short_term_messages").fetchone()[0]
        token_count = con.execute("SELECT COUNT(*) FROM memory_tokens").fetchone()[0]
        con.close()
        return {"short_term_messages": msg_count, "memory_tokens": token_count}
