"""
channels/base.py
Base classes and security for JARVIS messaging channels.
Supports DM pairing protocols and Access Control Lists (ACLs).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("jarvis.channels.base")


@dataclass
class ChannelConfig:
    enabled: bool = False
    token: str = ""
    webhook_secret: str = ""
    allowlist: Set[str] = field(default_factory=set)
    blocklist: Set[str] = field(default_factory=set)
    extra: dict[str, Any] = field(default_factory=dict)


class ChannelACL:
    """Access Control List for channels."""
    def __init__(self, allowlist: Optional[Set[str]] = None, blocklist: Optional[Set[str]] = None):
        self.allowlist = allowlist or set()
        self.blocklist = blocklist or set()

    def is_allowed(self, user_id: str) -> bool:
        if user_id in self.blocklist:
            return False
        if not self.allowlist:
            return True # Open by default if no allowlist
        return user_id in self.allowlist


class PairingProtocol:
    """Challenge-response protocol for pairing a new user/device."""
    def __init__(self):
        self._pending_challenges: Dict[str, str] = {}

    def create_challenge(self, user_id: str) -> str:
        challenge = str(uuid.uuid4().hex[:6]).upper()
        self._pending_challenges[user_id] = challenge
        return challenge

    def verify_response(self, user_id: str, response: str) -> bool:
        expected = self._pending_challenges.get(user_id)
        if expected and response.strip().upper() == expected:
            del self._pending_challenges[user_id]
            return True
        return False


class ChannelPlugin:
    """Base class for all messaging channels."""
    id: str = ""
    name: str = ""
    description: str = ""

    def __init__(self, config: ChannelConfig | None = None):
        self.config = config or ChannelConfig()
        self.acl = ChannelACL(self.config.allowlist, self.config.blocklist)
        self.pairing = PairingProtocol()
        self._running = False
        self._brain = None

    async def start(self, brain: Any) -> None:
        self._brain = brain
        self._running = True
        logger.info("[Channels] %s started", self.name)

    async def stop(self) -> None:
        self._running = False
        logger.info("[Channels] %s stopped", self.name)

    async def send(self, target: str, message: str) -> bool:
        raise NotImplementedError

    def check_access(self, user_id: str) -> bool:
        """Verify if a user has access to this channel."""
        allowed = self.acl.is_allowed(user_id)
        if not allowed:
            logger.warning(f"[Channels] Blocked access attempt from {user_id} on {self.id}")
        return allowed

    @property
    def is_running(self) -> bool:
        return self._running


__all__ = ["ChannelPlugin", "ChannelConfig", "ChannelACL", "PairingProtocol"]
