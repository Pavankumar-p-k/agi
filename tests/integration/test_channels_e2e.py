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

"""Integration tests for the channel message pipeline.

Tests the full flow: ChannelPlugin -> ChannelController -> processor.process_message()
with mocked external dependencies.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.asyncio


class TestChannelProcessor:
    """Tests the channel message processing pipeline."""

    async def test_process_message_with_mocked_routes(self):
        from channels.processor import process_message
        with patch("core.model_router.route_request") as mock_route, \
             patch("core.llm_router.get_router") as mock_get_router, \
             patch("brain.epistemic_tagger.epistemic_tagger") as mock_tagger, \
             patch("core.intent_router.extract_intent", new_callable=AsyncMock) as mock_intent, \
             patch("core.main.execute_action", new_callable=AsyncMock) as mock_action:
            mock_route.return_value = ("ollama/llama3", "local", "hello")
            mock_intent.return_value = {"intent": "chat"}
            mock_action.return_value = {"executed": False}
            mock_router = AsyncMock()
            mock_router.acompletion.return_value.choices = [
                MagicMock(message=MagicMock(content="Hello from JARVIS"))
            ]
            mock_get_router.return_value = mock_router
            mock_tagger.tag_response.return_value = "Hello from JARVIS"
            result = await process_message(
                text="hello", source="test", channel_id="chan1",
                user_id="user1", user_name="Alice"
            )
            assert result == "Hello from JARVIS"

    async def test_process_message_fallback_on_llm_failure(self):
        from channels.processor import process_message
        with patch("core.model_router.route_request") as mock_route, \
             patch("core.llm_router.get_router") as mock_get_router, \
             patch("core.model_router.get_ollama_url") as mock_url, \
             patch("core.model_router.model_for_role") as mock_model, \
             patch("core.intent_router.extract_intent", new_callable=AsyncMock) as mock_intent, \
             patch("core.main.execute_action", new_callable=AsyncMock) as mock_action, \
             patch("httpx.AsyncClient") as mock_httpx, \
             patch("brain.epistemic_tagger.epistemic_tagger") as mock_tagger:
            mock_route.return_value = ("llama3", "local", "hello")
            mock_intent.return_value = {"intent": "chat"}
            mock_action.return_value = {"executed": False}
            mock_get_router.return_value.acompletion.side_effect = Exception("LLM down")
            mock_url.return_value = "http://localhost:11434"
            mock_model.return_value = "llama3"
            mock_response = MagicMock()
            mock_response.json.return_value = {"message": {"content": "Fallback response"}}
            mock_httpx.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_tagger.tag_response.return_value = "Fallback response"
            result = await process_message(
                text="hello", source="test", channel_id="chan1",
                user_id="user1", user_name="Alice"
            )
            assert result == "Fallback response"


class TestChannelControllerIntegration:
    """Tests ChannelController with real channel instances (mocked deps)."""

    async def test_register_and_send_to_all(self):
        from channels.controller import ChannelController
        from channels.base import ChannelPlugin

        controller = ChannelController()
        p1 = ChannelPlugin()
        p1.id = "chan1"
        p1.send = AsyncMock(return_value=True)
        controller.register(p1)

        p2 = ChannelPlugin()
        p2.id = "chan2"
        p2.send = AsyncMock(return_value=True)
        controller.register(p2)

        assert "chan1" in controller.channels
        assert "chan2" in controller.channels
        assert len(controller.channels) == 2

    async def test_start_all_with_mocked_channels(self):
        from channels.controller import ChannelController
        from channels.base import ChannelPlugin, ChannelConfig

        controller = ChannelController()
        p = ChannelPlugin(ChannelConfig(enabled=True, token="fake"))
        p.id = "test"
        p.start = AsyncMock()
        p.stop = AsyncMock()
        controller.register(p)

        await controller.start_all(None)
        p.start.assert_awaited_once()

        await controller.stop_all()
        p.stop.assert_awaited_once()


class TestWhatsappWebhook:
    """Tests for the WhatsApp webhook router and sender."""

    async def test_whatsapp_router_prefix(self):
        with patch.dict("os.environ", {"META_VERIFY_TOKEN": "test-token"}, clear=True):
            from routers.whatsapp import router
            assert router.prefix == "/api/whatsapp"

    async def test_whatsapp_sender_init(self):
        with patch.dict("os.environ", {}, clear=True):
            from tools.whatsapp_sender import WhatsAppSender
            sender = WhatsAppSender()
            assert sender.ready is False

    async def test_whatsapp_sender_with_env(self):
        with patch.dict("os.environ", {"META_WHATSAPP_TOKEN": "tok", "META_WHATSAPP_PHONE_ID": "123"}):
            from tools.whatsapp_sender import WhatsAppSender
            sender = WhatsAppSender()
            assert sender.ready is True

    async def test_whatsapp_sender_send(self):
        with patch.dict("os.environ", {"META_WHATSAPP_TOKEN": "tok", "META_WHATSAPP_PHONE_ID": "123"}):
            from tools.whatsapp_sender import WhatsAppSender
            sender = WhatsAppSender()
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock()
                mock_client.return_value.__aenter__.return_value.post.return_value.status_code = 200
                result = await sender.send("+1234567890", "test message")
                assert result is True

    async def test_whatsapp_sender_send_fails(self):
        with patch.dict("os.environ", {"META_WHATSAPP_TOKEN": "tok", "META_WHATSAPP_PHONE_ID": "123"}):
            from tools.whatsapp_sender import WhatsAppSender
            sender = WhatsAppSender()
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock()
                mock_client.return_value.__aenter__.return_value.post.return_value.status_code = 401
                result = await sender.send("+1234567890", "test")
                assert result is False

    async def test_whatsapp_sender_send_empty_token(self):
        with patch.dict("os.environ", {}, clear=True):
            from tools.whatsapp_sender import WhatsAppSender
            sender = WhatsAppSender()
            result = await sender.send("+1234567890", "test")
            assert result is False
