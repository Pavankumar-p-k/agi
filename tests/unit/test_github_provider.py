from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def provider():
    from core.providers.adapters.github_provider import GitHubProvider
    return GitHubProvider()


@pytest.mark.asyncio
async def test_capabilities(provider):
    caps = provider.capabilities()
    assert "github" in caps.capability_names
    assert "git" in caps.capability_names


@pytest.mark.asyncio
async def test_health(provider):
    health = await provider.health()
    assert health.status.name in ("HEALTHY", "DEGRADED")


@pytest.mark.asyncio
async def test_execute_status(provider):
    result = await provider.execute({"action": "status"})
    assert result.exit_code in (0, 1)


@pytest.mark.asyncio
async def test_execute_unknown_action(provider):
    result = await provider.execute({"action": "nonexistent"})
    assert not result.success


@pytest.mark.asyncio
async def test_handle_tool(provider):
    result = await provider.handle_tool("github_status", "")
    if result is not None:
        assert hasattr(result, "success")
        assert hasattr(result, "output")

    result = await provider.handle_tool("some_other_tool", "")
    assert result is None


@pytest.mark.asyncio
async def test_handle_tool_with_content(provider):
    result = await provider.handle_tool("github_commit", "test message")
    if result is not None:
        assert hasattr(result, "success")


@pytest.mark.asyncio
async def test_estimate_cost(provider):
    cost = await provider.estimate_cost({})
    assert cost == 0.0


@pytest.mark.asyncio
async def test_estimate_latency(provider):
    lat = await provider.estimate_latency({})
    assert lat == 500.0
