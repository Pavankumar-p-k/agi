from __future__ import annotations

import asyncio
import logging
import os
import threading

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from .base import ChannelPlugin, ChannelConfig
from .processor import process_message

logger = logging.getLogger(__name__)


class SlackChannel(ChannelPlugin):
    id = "slack"
    name = "Slack"
    description = "Slack bot integration via socket mode"

    def __init__(self, config: ChannelConfig | None = None):
        super().__init__(config)
        self._client: WebClient | None = None
        self._socket_client: SocketModeClient | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self, brain) -> None:
        await super().start(brain)
        token = self.config.token or os.getenv("SLACK_BOT_TOKEN", "")
        app_token = os.getenv("SLACK_APP_TOKEN", "")
        if not token or not app_token:
            logger.warning("[Slack] SLACK_BOT_TOKEN or SLACK_APP_TOKEN not set — channel disabled")
            self._running = False
            return

        self._client = WebClient(token=token)
        self._loop = asyncio.get_running_loop()

        def handle_socket_message(client: SocketModeClient, req: SocketModeRequest):
            if req.type != "events_api":
                return
            payload = req.payload
            event = payload.get("event", {})
            if event.get("type") != "app_mention":
                return
            text = event.get("text", "")
            user = event.get("user", "unknown")
            channel = event.get("channel", "")
            if not text:
                return
            bot_user_id = payload.get("authorizations", [{}])[0].get("user_id", "")
            if bot_user_id:
                text = text.replace(f"<@{bot_user_id}>", "").strip()
            if not text:
                return

            async def respond():
                reply = await process_message(
                    text=text,
                    source="slack",
                    channel_id=channel,
                    user_id=user,
                    user_name=f"<@{user}>",
                )
                if self._client:
                    self._client.chat_postMessage(channel=channel, text=reply[:3000])

            asyncio.run_coroutine_threadsafe(respond(), self._loop)
            client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        self._socket_client = SocketModeClient(
            app_token=app_token,
            client=self._client,
        )
        self._socket_client.socket_mode_request_listeners.append(handle_socket_message)

        def run():
            self._socket_client.connect()
            self._socket_client.listen()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        self._running = True
        logger.info("[Slack] Connected")

    async def stop(self) -> None:
        if self._socket_client:
            self._socket_client.disconnect()
            self._socket_client = None
        self._client = None
        if self._thread:
            self._thread = None
        await super().stop()

    async def send(self, target: str, message: str) -> bool:
        try:
            token = self.config.token or os.getenv("SLACK_BOT_TOKEN", "")
            client = WebClient(token=token)
            client.chat_postMessage(channel=target, text=message[:3000])
            return True
        except Exception as e:
            logger.warning("[Slack] Send failed: %s", e)
            return False
