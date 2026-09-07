from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def provider():
    from core.providers.adapters.email_provider import EmailProvider
    return EmailProvider()


@pytest.mark.asyncio
async def test_capabilities(provider):
    caps = provider.capabilities()
    assert "email" in caps.capability_names
    assert "send_email" in caps.capability_names


@pytest.mark.asyncio
async def test_health(provider):
    health = await provider.health()
    assert health.status.name in ("HEALTHY", "DEGRADED", "DOWN")


@pytest.mark.asyncio
async def test_execute_compose(provider):
    result = await provider.execute({
        "action": "compose",
        "to": "test@example.com",
        "subject": "Test",
        "body": "Hello",
    })
    assert result.success
    assert "test@example.com" in result.output
    assert "Test" in result.output


@pytest.mark.asyncio
async def test_execute_send_no_recipients(provider):
    result = await provider.execute({"action": "send"})
    assert not result.success
    assert "recipients" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_unknown_action(provider):
    result = await provider.execute({"action": "nonexistent"})
    assert not result.success


@pytest.mark.asyncio
async def test_handle_tool_email_send(provider):
    result = await provider.handle_tool("email_send", "body content",
                                         to="test@example.com", subject="Test")
    assert result is not None
    assert hasattr(result, "success")

    result = await provider.handle_tool("send_email", "body",
                                         to="test@example.com", subject="Test")
    assert result is not None


@pytest.mark.asyncio
async def test_handle_tool_non_email(provider):
    result = await provider.handle_tool("other_tool", "")
    assert result is None


@pytest.mark.asyncio
async def test_estimate_cost(provider):
    cost = await provider.estimate_cost({})
    assert cost == 0.0


@pytest.mark.asyncio
async def test_estimate_latency(provider):
    lat = await provider.estimate_latency({})
    assert lat == 100.0
