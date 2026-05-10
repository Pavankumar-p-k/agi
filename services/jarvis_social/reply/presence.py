"""
reply/presence.py — Social Presence Engine
============================================
Runs every 30-60 minutes.
Initiates conversations only when:
- No pending reply (no awaiting_reply flag)
- Cooldown has passed
- Engagement above threshold
- Presence feature is enabled
"""
from __future__ import annotations
import asyncio, logging, random, time
from db.schema import get_setting, DB_PATH
from friends.registry import FriendRegistry
from brain.router import BrainRouter

logger = logging.getLogger(__name__)

PRESENCE_INTERVAL_MIN = 30 * 60   # 30 minutes
PRESENCE_INTERVAL_MAX = 60 * 60   # 60 minutes

INITIATION_TYPES = ["check_in", "continuation", "casual"]


class SocialPresenceEngine:

    def __init__(self, db_path: str = DB_PATH, send_fn=None):
        self._db     = db_path
        self._reg    = FriendRegistry(db_path)
        self._router = BrainRouter()
        self._send   = send_fn or self._default_send
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("[Presence] Engine started.")
        while self._running:
            interval = random.randint(PRESENCE_INTERVAL_MIN, PRESENCE_INTERVAL_MAX)
            await asyncio.sleep(interval)
            await self.run_cycle()

    def stop(self) -> None:
        self._running = False

    async def run_cycle(self) -> list[dict]:
        """Check all friends and initiate where appropriate."""
        if get_setting("presence_enabled", self._db) != "true":
            return []
        if get_setting("system_paused", self._db) == "true":
            return []

        initiated = []
        friends = self._reg.all_friends()

        for friend in friends:
            if not friend.can_initiate:
                continue
            result = await self._initiate(friend)
            if result:
                initiated.append(result)

        logger.info("[Presence] Cycle complete. Initiated: %d", len(initiated))
        return initiated

    async def _initiate(self, friend) -> dict | None:
        init_type = random.choice(INITIATION_TYPES)
        from jarvis_os.memory.memory_manager import MemoryManager
        tokens = MemoryCleanup(self._db).get_tokens(friend.friend_id)

        response = await self._router.generate_initiation(friend, tokens, init_type)
        sent = await self._send(friend.friend_id, response.text)

        if sent:
            self._reg.set_awaiting_reply(friend.friend_id, True)
            self._reg.set_cooldown(friend.friend_id, friend.special_mode)
            logger.info("[Presence] Initiated with %s (%s)", friend.display_name, init_type)
            return {"friend_id": friend.friend_id, "type": init_type, "text": response.text}
        return None

    @staticmethod
    async def _default_send(friend_id: str, text: str) -> bool:
        print(f"[JARVIS PRESENCE → {friend_id}] {text}")
        return True
