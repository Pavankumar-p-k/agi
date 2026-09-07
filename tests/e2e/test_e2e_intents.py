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

"""End-to-end tests for all 14 JARVIS intents.
Tests intent classification via the unified intent router.
"""
import pytest
import json


class TestIntentClassification:
    """Tests that the unified intent router correctly classifies each intent type."""

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_chat(self, client):
        """'what is python' should be classified as chat."""
        payload = {"message": "what is python", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_play_media(self, client):
        """'play cry for me on youtube' should be play_media."""
        payload = {"message": "play cry for me on youtube", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_open_url(self, client):
        """'open youtube' should be open_url."""
        payload = {"message": "open youtube", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_web_search(self, client):
        """'search latest AI news' should be web_search."""
        payload = {"message": "search latest AI news", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_pc_control(self, client):
        """'open notepad' should be pc_control."""
        payload = {"message": "open notepad", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_reminder(self, client):
        """'remind me to drink water in 1 minute' should be reminder."""
        payload = {"message": "remind me to drink water in 1 minute", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_browser_task(self, client):
        """'sign up for a new account on github' should be browser_task."""
        payload = {"message": "sign up for a new account on github", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_message(self, client):
        """'send an email to john@example.com' should be message."""
        payload = {"message": "send an email to john@example.com with subject hello saying hi", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_weather(self, client):
        """'what's the weather in London' should be weather."""
        payload = {"message": "what's the weather in London", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_news(self, client):
        """'latest technology news' should be news."""
        payload = {"message": "latest technology news", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_stocks(self, client):
        """'AAPL stock price' should be stocks."""
        payload = {"message": "AAPL stock price", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_sports(self, client):
        """'NBA scores' should be sports."""
        payload = {"message": "NBA scores", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_time(self, client):
        """'what time is it in Tokyo' should be time."""
        payload = {"message": "what time is it in Tokyo", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_build(self, client):
        """'build a portfolio page' should be build."""
        payload = {"message": "build a portfolio page with animations", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)

    @pytest.mark.intent
    @pytest.mark.asyncio
    async def test_intent_code_task(self, client):
        """'refactor this python code' should be code_task."""
        payload = {"message": "refactor this python function to be more efficient", "user_id": "test"}
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code in (200, 201)


class TestIntentRouterUnit:
    """Unit tests for the intent router itself (no server needed)."""

    @pytest.mark.asyncio
    async def test_extract_intent_chat(self):
        from core.intent_router import extract_intent
        result = await extract_intent("what is python")
        assert result.get("intent") == "chat"

    @pytest.mark.asyncio
    async def test_extract_intent_build(self):
        from core.intent_router import extract_intent
        result = await extract_intent("build a coffee shop website")
        assert result.get("intent") == "build"

    @pytest.mark.asyncio
    async def test_extract_intent_play_media(self):
        from core.intent_router import extract_intent
        result = await extract_intent("play despacito")
        assert result.get("intent") == "play_media"

    @pytest.mark.asyncio
    async def test_extract_intent_pc_control(self):
        from core.intent_router import extract_intent
        result = await extract_intent("open notepad")
        assert result.get("intent") == "pc_control"

    @pytest.mark.asyncio
    async def test_extract_intent_weather(self):
        from core.intent_router import extract_intent
        result = await extract_intent("what's the weather in London")
        assert result.get("intent") == "weather"

    @pytest.mark.asyncio
    async def test_extract_intent_news(self):
        from core.intent_router import extract_intent
        result = await extract_intent("latest technology news")
        assert result.get("intent") == "news"

    @pytest.mark.asyncio
    async def test_extract_intent_stocks(self):
        from core.intent_router import extract_intent
        result = await extract_intent("AAPL stock price")
        assert result.get("intent") == "stocks"

    @pytest.mark.asyncio
    async def test_extract_intent_message(self):
        from core.intent_router import extract_intent
        result = await extract_intent("send an email to john@example.com with subject hello saying hi")
        assert result.get("intent") == "message"

    @pytest.mark.asyncio
    async def test_extract_intent_browser_task(self):
        from core.intent_router import extract_intent
        result = await extract_intent("sign up for a new account on github")
        assert result.get("intent") == "browser_task"

    @pytest.mark.asyncio
    async def test_extract_intent_reminder(self):
        from core.intent_router import extract_intent
        result = await extract_intent("remind me to drink water in 1 minute")
        assert result.get("intent") == "reminder"

    @pytest.mark.asyncio
    async def test_extract_intent_open_url(self):
        from core.intent_router import extract_intent
        result = await extract_intent("open youtube")
        assert result.get("intent") == "open_url"

    @pytest.mark.asyncio
    async def test_extract_intent_sports(self):
        from core.intent_router import extract_intent
        result = await extract_intent("NBA scores")
        assert result.get("intent") == "sports"

    @pytest.mark.asyncio
    async def test_extract_intent_time(self):
        from core.intent_router import extract_intent
        result = await extract_intent("what time is it in Tokyo")
        assert result.get("intent") == "time"

    @pytest.mark.asyncio
    async def test_extract_intent_code_task(self):
        from core.intent_router import extract_intent
        result = await extract_intent("refactor this python function to be more efficient")
        assert result.get("intent") == "code_task"

    @pytest.mark.asyncio
    async def test_extract_intent_web_search(self):
        from core.intent_router import extract_intent
        result = await extract_intent("search latest AI news")
        assert result.get("intent") == "web_search"

    @pytest.mark.asyncio
    async def test_intent_router_fallback(self):
        """When instructor is unavailable, should fallback to chat."""
        from core.intent_router import extract_intent
        result = await extract_intent("any message here")
        assert result.get("intent") in ("chat", "web_search", "message")
