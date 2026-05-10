"""
reply/auto_reply.py — Auto Reply Engine
========================================
- Checks laptop status before replying
- Prevents double-text
- Sends offline fallback when laptop is OFF
- Respects cooldowns
- Logs all replies
"""
from __future__ import annotations
import asyncio, logging, time, sqlite3
from dataclasses import dataclass
from typing import Optional, Callable

from db.schema import connect, get_setting, DB_PATH
from friends.registry import FriendRegistry
from brain.router import BrainRouter, BrainResponse

logger = logging.getLogger(__name__)

OFFLINE_FALLBACK = "Jarvis here. Pavan is currently unavailable — I'll let him know you messaged."
DOUBLE_TEXT_WINDOW_S = 30   # won't send two messages within this window


@dataclass
class ReplyResult:
    sent:       bool
    text:       str
    reason:     str   # sent|offline|cooldown|double_text|system_paused|awaiting_reply
    friend_id:  str
    latency_ms: float = 0.0
    source:     str = ""


class AutoReplyEngine:

    def __init__(self, db_path: str = DB_PATH,
                 send_fn: Optional[Callable] = None):
        """
        send_fn: async callable(friend_id, text) → bool
        Pass your actual WhatsApp/Instagram send function here.
        """
        self._db       = db_path
        self._registry = FriendRegistry(db_path)
        self._router   = BrainRouter()
        self._send_fn  = send_fn or self._default_send
        self._last_sent: dict[str, float] = {}

    # ── Main entry point ──────────────────────────────────────────

    async def handle_incoming(self, friend_id: str, message: str,
                               platform: str = "whatsapp") -> ReplyResult:
        """
        Called when a new message arrives from a friend.
        Returns ReplyResult describing what happened.
        """
        start = time.time()

        # 1. System paused?
        if get_setting("system_paused", self._db) == "true":
            return ReplyResult(False, "", "system_paused", friend_id)

        # 2. Auto reply enabled?
        if get_setting("auto_reply_enabled", self._db) != "true":
            return ReplyResult(False, "", "auto_reply_disabled", friend_id)

        # 3. Load friend profile
        profile = self._registry.get_profile(friend_id)
        if not profile:
            profile = self._registry.get_or_create(friend_id, platform)

        # 4. Mark reply received (clears awaiting_reply)
        self._registry.mark_reply_received(friend_id)

        # 5. Store incoming message
        self._store_message(friend_id, "user", message, platform)

        # 6. Update metadata
        self._log_metadata(friend_id, message)

        # 7. Laptop OFF → offline fallback
        if get_setting("laptop_status", self._db) == "offline":
            await self._send_fn(friend_id, OFFLINE_FALLBACK)
            self._store_message(friend_id, "jarvis", OFFLINE_FALLBACK, platform)
            return ReplyResult(True, OFFLINE_FALLBACK, "offline", friend_id,
                                (time.time()-start)*1000)

        # 8. Double-text check
        last_sent = self._last_sent.get(friend_id, 0)
        if (time.time() - last_sent) < DOUBLE_TEXT_WINDOW_S:
            logger.debug("[AutoReply] Double-text blocked for %s", friend_id)
            return ReplyResult(False, "", "double_text", friend_id)

        # 9. Get conversation history
        history = self._get_history(friend_id, n=8)

        # 10. Get memory tokens
        memory = self._get_memory_tokens(friend_id)

        # 11. Generate response
        response: BrainResponse = await self._router.route(
            profile, history, message, memory
        )

        # 12. Safety check — never escalate conflicts
        reply_text = self._safety_filter(response.text, message)

        # 13. Send
        sent = await self._send_fn(friend_id, reply_text)

        if sent:
            self._last_sent[friend_id] = time.time()
            self._store_message(friend_id, "jarvis", reply_text, platform)
            self._registry.set_awaiting_reply(friend_id, True)
            self._update_engagement(friend_id, message, reply_text)
            logger.info("[AutoReply] Sent to %s via %s [%s]",
                         friend_id, response.source, platform)

        elapsed = (time.time() - start) * 1000
        return ReplyResult(sent, reply_text, "sent" if sent else "send_failed",
                            friend_id, elapsed, response.source)

    # ── Conflict safety filter ─────────────────────────────────────

    def _safety_filter(self, reply: str, original_msg: str) -> str:
        """
        Ensure reply doesn't escalate emotional tension.
        If conflict detected, soften the response.
        """
        conflict_words = ["angry","fight","hate","annoyed","whatever","forget it",
                           "leave me alone","stop","shut up"]
        msg_lower = original_msg.lower()
        has_conflict = any(w in msg_lower for w in conflict_words)

        if has_conflict:
            SOFTEN_PREFIX = ["hey, ",  "alright, "]
            import random
            # Don't add anything aggressive
            aggressive = ["fight","argue","wrong","stupid","idiot"]
            reply_lower = reply.lower()
            if any(w in reply_lower for w in aggressive):
                reply = "let's talk when you're ready"
        return reply

    # ── DB helpers ─────────────────────────────────────────────────

    def _store_message(self, friend_id: str, role: str,
                        content: str, platform: str) -> None:
        try:
            con = connect(self._db)
            expire = time.time() + 30 * 86400
            con.execute(
                "INSERT INTO short_term_messages (friend_id,role,content,platform,timestamp,expires_at) "
                "VALUES (?,?,?,?,?,?)",
                (friend_id, role, content, platform, time.time(), expire)
            )
            con.execute(
                "UPDATE friends SET last_interaction=? WHERE friend_id=?",
                (time.time(), friend_id)
            )
            con.commit()
            con.close()
        except Exception as e:
            logger.warning("[AutoReply] Store error: %s", e)

    def _get_history(self, friend_id: str, n: int = 8) -> list[dict]:
        try:
            con = connect(self._db)
            rows = con.execute(
                "SELECT role, content FROM short_term_messages "
                "WHERE friend_id=? ORDER BY timestamp DESC LIMIT ?",
                (friend_id, n)
            ).fetchall()
            con.close()
            history = [{"role": "user" if r["role"]=="user" else "assistant",
                         "content": r["content"]} for r in reversed(rows)]
            return history
        except Exception:
            return []

    def _get_memory_tokens(self, friend_id: str) -> list[dict]:
        try:
            con = connect(self._db)
            rows = con.execute(
                "SELECT token_type, token_value FROM memory_tokens "
                "WHERE friend_id=? ORDER BY times_used DESC LIMIT 10",
                (friend_id,)
            ).fetchall()
            con.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _log_metadata(self, friend_id: str, message: str) -> None:
        try:
            emoji_count = sum(1 for c in message if ord(c) > 127)
            emoji_density = min(1.0, emoji_count / max(len(message), 1) * 10)
            # Simple sentiment: positive words vs negative
            pos_words = ["good","great","love","happy","nice","awesome","yes","cool","haha"]
            neg_words = ["bad","hate","sad","angry","no","ugh","awful","terrible"]
            msg_lower = message.lower()
            sentiment = 0.5
            pos = sum(1 for w in pos_words if w in msg_lower)
            neg = sum(1 for w in neg_words if w in msg_lower)
            if pos + neg > 0:
                sentiment = pos / (pos + neg)
            conflict = int(any(w in msg_lower for w in ["fight","hate","angry","stop","leave"]))

            con = connect(self._db)
            con.execute(
                "INSERT INTO metadata_logs (friend_id,tone_score,emoji_density,"
                "message_length,sentiment,conflict_flag,timestamp) VALUES (?,?,?,?,?,?,?)",
                (friend_id, sentiment, emoji_density, len(message),
                 sentiment, conflict, time.time())
            )
            con.commit()
            con.close()
        except Exception as e:
            logger.warning("[Metadata] Log error: %s", e)

    def _update_engagement(self, friend_id: str,
                            user_msg: str, reply: str) -> None:
        """Update engagement score based on message characteristics."""
        try:
            con = connect(self._db)
            # Recent sentiment average
            rows = con.execute(
                "SELECT AVG(sentiment) as avg_s, AVG(conflict_flag) as avg_c "
                "FROM metadata_logs WHERE friend_id=? AND timestamp > ?",
                (friend_id, time.time() - 7*86400)
            ).fetchone()
            con.close()
            if rows and rows["avg_s"] is not None:
                raw_eng = rows["avg_s"] * (1 - rows["avg_c"])
                # Smooth update
                profile = self._registry.get_profile(friend_id)
                if profile:
                    old = profile.engagement_score
                    new_eng = old * 0.8 + raw_eng * 0.2
                    self._registry.update_engagement(friend_id, new_eng)
        except Exception as e:
            logger.warning("[Engagement] Update error: %s", e)

    @staticmethod
    async def _default_send(friend_id: str, text: str) -> bool:
        """Default send function — prints to console. Replace with real implementation."""
        print(f"[JARVIS → {friend_id}] {text}")
        return True
