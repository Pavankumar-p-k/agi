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
"""Channel message processor — routes through the canonical pipeline."""
from __future__ import annotations

import logging

from core.pipeline.adapters import channel_adapter

logger = logging.getLogger(__name__)


async def process_message(
    text: str,
    source: str,
    channel_id: str,
    user_id: str,
    user_name: str,
) -> str:
    """Process a channel message through the canonical pipeline."""
    response_text = await channel_adapter(text, source, channel_id, user_id, user_name)
    _emit_hooks(text, source, channel_id, user_id, user_name, response_text)
    return response_text


def _emit_hooks(
    text: str,
    source: str,
    channel_id: str,
    user_id: str,
    user_name: str,
    response_text: str,
) -> None:
    """Emit plugin hooks and MCP bridge notifications."""
    logger.info("[Channel] %s|%s|%s -> %.80s", source, channel_id, user_name, response_text)

    try:
        import asyncio

        from brain.events import PluginEventBus
        asyncio.create_task(PluginEventBus.instance().emit(
            "on_channel_message",
            text=text,
            source=source,
            channel_id=channel_id,
            user_id=user_id,
            user_name=user_name,
            response=response_text,
        ))
    except Exception as hook_exc:
        logger.debug("on_channel_message hook failed: %s", hook_exc)

    try:
        from mcp.server import mcp_server
        if mcp_server.is_running:
            mcp_server.enqueue_event("message", {
                "session_key": channel_id,
                "role": "user",
                "text": text,
                "source": source,
                "user_id": user_id,
                "user_name": user_name,
            })
            mcp_server.enqueue_event("message", {
                "session_key": channel_id,
                "role": "assistant",
                "text": response_text,
                "source": "jarvis",
            })
    except Exception as bridge_exc:
        logger.debug("MCP Server event enqueuing failed: %s", bridge_exc)
