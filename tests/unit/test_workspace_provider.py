from __future__ import annotations

import pytest


@pytest.fixture
def provider():
    from core.providers.adapters.workspace_provider import WorkspaceProvider
    return WorkspaceProvider()


@pytest.mark.asyncio
async def test_capabilities(provider):
    caps = provider.capabilities()
    assert "workspace" in caps.capability_names
    assert "desktop_state" in caps.capability_names


@pytest.mark.asyncio
async def test_health(provider):
    health = await provider.health()
    assert health.status.name in ("HEALTHY", "DEGRADED")


@pytest.mark.asyncio
async def test_execute_snapshot(provider):
    result = await provider.execute({"action": "snapshot"})
    assert result.success
    assert "Desktop Snapshot" in result.output


@pytest.mark.asyncio
async def test_execute_active_window(provider):
    result = await provider.execute({"action": "active_window"})
    assert result.exit_code in (0, 1)


@pytest.mark.asyncio
async def test_execute_clipboard(provider):
    result = await provider.execute({"action": "clipboard"})
    assert result.success


@pytest.mark.asyncio
async def test_execute_processes(provider):
    result = await provider.execute({"action": "processes"})
    assert result.success
    assert "Processes" in result.output


@pytest.mark.asyncio
async def test_execute_system_stats(provider):
    result = await provider.execute({"action": "system_stats"})
    assert result.success
    assert "CPU" in result.output or "System Stats" in result.output


@pytest.mark.asyncio
async def test_execute_unknown_action(provider):
    result = await provider.execute({"action": "nonexistent"})
    assert not result.success


@pytest.mark.asyncio
async def test_handle_tool(provider):
    result = await provider.handle_tool("workspace_snapshot", "")
    assert result is not None
    assert result.success

    result = await provider.handle_tool("some_other_tool", "")
    assert result is None


@pytest.mark.asyncio
async def test_estimate_cost(provider):
    cost = await provider.estimate_cost({})
    assert cost == 0.0


@pytest.mark.asyncio
async def test_estimate_latency(provider):
    lat = await provider.estimate_latency({})
    assert lat == 10.0


@pytest.mark.asyncio
async def test_handle_tool_unknown(provider):
    result = await provider.handle_tool("not_workspace_tool", "")
    assert result is None
