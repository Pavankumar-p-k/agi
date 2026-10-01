"""IRC channel — python-irc reactor over a socket connection."""
from __future__ import annotations

import inspect
import logging
import os
from typing import Any, Optional

import irc.client
import irc.connection

from channels.base import ChannelConfig, ChannelPlugin

logger = logging.getLogger(__name__)


class IRCChannel(ChannelPlugin):
    """IRC channel (server/nick/port from config ``extra`` or env vars)."""

    id = "irc"
    name = "IRC"

    def __init__(self, config: Optional[ChannelConfig] = None,
                 handler: Any = None) -> None:
        super().__init__(config, handler)
        self._connection: Any = None
        self._reactor: Any = None

    def _settings(self) -> tuple[str, str, int, list[str]]:
        extra = self.config.extra or {}
        server = str(extra.get("server") or os.getenv("IRC_SERVER", ""))
        nick = str(extra.get("nick") or os.getenv("IRC_NICK", ""))
        port = int(extra.get("port") or os.getenv("IRC_PORT", 6697))
        channels = extra.get("channels") or []
        if isinstance(channels, str):
            channels = [c.strip() for c in channels.split(",") if c.strip()]
        return server, nick, port, list(channels)

    async def start(self, app: Any = None) -> None:
        self._app = app
        server, nick, port, channels = self._settings()
        if not server or not nick:
            self.is_running = False
            return
        try:
            self._reactor = irc.client.Reactor()
            factory = irc.connection.Factory()
            self._connection = factory.server()
            connect = getattr(self._connection, "connect", None)
            if connect is not None:
                result = connect(server, port, nick)
                if inspect.isawaitable(result):
                    await result
            for channel in channels:
                join = getattr(self._connection, "join", None)
                if join is not None:
                    join(channel)
            self.is_running = True
        except Exception as exc:  # noqa: BLE001 — honest failure
            logger.warning("[irc] start failed: %s", exc)
            self.is_running = False

    async def stop(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                quit_fn = getattr(connection, "quit", None)
                if quit_fn is not None:
                    quit_fn("shutting down")
            except Exception:  # noqa: BLE001
                pass
            close = getattr(connection, "close", None)
            if close is not None:
                try:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
                except Exception:  # noqa: BLE001
                    pass
        self._reactor = None
        self.is_running = False

    async def send(self, target: str, message: str) -> bool:
        if self._connection is None:
            return False
        try:
            privmsg = getattr(self._connection, "privmsg", None)
            if privmsg is None:
                return False
            privmsg(target, str(message))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("[irc] send failed: %s", exc)
            return False


__all__ = ["IRCChannel"]
