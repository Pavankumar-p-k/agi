"""Tests for JARVIS sub-agent system."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

def make_mock_response(text: str):
    block = MagicMock()
    block.text = text
    usage = MagicMock()
    usage.output_tokens = len(text) // 4
    resp = MagicMock()
    resp.content = [block]
    resp.usage = usage
    return resp

@pytest.fixture
def mock_anthropic():
    with patch("core.sub_agents.base_agent.anthropic.Anthropic") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.messages.create.return_value = make_mock_response("Test output from agent.")
        yield client

def test_registry_has_all_agents():
    from core.sub_agents.registry import agent_registry
    names = agent_registry.names()
    for expected in ["NEXUS","FORGE","ORACLE","PHANTOM","CIPHER","HERALD","SCRIBE","ATLAS","SENTINEL","MAESTRO"]:
        assert expected in names, f"{expected} missing from registry"

def test_agent_info():
    from core.sub_agents.agents.nexus import NexusAgent
    a = NexusAgent()
    info = a.info()
    assert info["name"] == "NEXUS"
    assert "research" in info["modes"]

@pytest.mark.asyncio
async def test_nexus_run(mock_anthropic):
    from core.sub_agents.agents.nexus import NexusAgent
    a = NexusAgent()
    result = await a.run("What is quantum computing?", mode="research")
    assert result.success
    assert result.agent_name == "NEXUS"
    assert result.mode == "research"
    assert len(result.output) > 0

@pytest.mark.asyncio
async def test_forge_run(mock_anthropic):
    from core.sub_agents.agents.forge import ForgeAgent
    a = ForgeAgent()
    result = await a.run("Write a fibonacci function", mode="generate", lang="Python")
    assert result.success
    assert result.agent_name == "FORGE"

@pytest.mark.asyncio
async def test_invalid_mode_falls_back(mock_anthropic):
    from core.sub_agents.agents.nexus import NexusAgent
    a = NexusAgent()
    result = await a.run("test", mode="nonexistent_mode")
    assert result.success  # should use default mode, not crash

@pytest.mark.asyncio
async def test_registry_run(mock_anthropic):
    from core.sub_agents.registry import agent_registry
    result = await agent_registry.run("ORACLE", "Plan a website build", mode="plan")
    assert result.success
    assert result.agent_name == "ORACLE"

@pytest.mark.asyncio
async def test_parallel_run(mock_anthropic):
    from core.sub_agents.registry import agent_registry
    tasks = [
        {"agent": "NEXUS", "task": "research AI", "mode": "brief"},
        {"agent": "SCRIBE", "task": "write docs for AI module", "mode": "docs"},
    ]
    results = await agent_registry.run_parallel(tasks)
    assert len(results) == 2
    assert all(r.success for r in results)

@pytest.mark.asyncio
async def test_result_to_dict(mock_anthropic):
    from core.sub_agents.agents.herald import HeraldAgent
    a = HeraldAgent()
    result = await a.run("Draft an update email")
    d = result.to_dict()
    assert "agent_name" in d
    assert "output" in d
    assert "duration_s" in d
