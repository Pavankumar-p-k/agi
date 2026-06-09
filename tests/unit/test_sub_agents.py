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

from core.result import Ok

@pytest.fixture(autouse=True)
def mock_complete_global():
    with patch("core.llm_router.complete") as mock:
        mock.return_value = Ok("Test output from agent.")
        yield mock

@pytest.fixture(autouse=True)
def mock_smolagents():
    # Mock ForgeAgent's internal smolagents usage
    with patch("core.sub_agents.agents.forge.CodeAgent") as mock_agent, \
         patch("core.sub_agents.agents.forge.LiteLLMModel") as mock_model:
        
        agent_instance = MagicMock()
        mock_agent.return_value = agent_instance
        agent_instance.run.return_value = "Mocked smolagents code output"
        
        yield {
            "agent": mock_agent,
            "model": mock_model,
            "instance": agent_instance
        }

@pytest.fixture(autouse=True)
def mock_mem0():
    # Mock NexusAgent's memory usage
    with patch("memory.mem0_adapter.mem0_memory") as mock:
        mock.search.return_value = []
        mock.format_context.return_value = ""
        yield mock

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
async def test_nexus_run():
    from core.sub_agents.agents.nexus import NexusAgent
    a = NexusAgent()
    result = await a.run("What is quantum computing?", mode="research")
    assert result.success
    assert result.agent_name == "NEXUS"
    assert result.mode == "research"
    assert len(result.output) > 0

@pytest.mark.asyncio
async def test_forge_run():
    from core.sub_agents.agents.forge import ForgeAgent
    a = ForgeAgent()
    result = await a.run("Write a fibonacci function", mode="generate", lang="Python")
    assert result.success
    assert result.agent_name == "FORGE"
    assert "smolagents" in result.output.lower() or "Mocked" in result.output

@pytest.mark.asyncio
async def test_invalid_mode_falls_back():
    from core.sub_agents.agents.nexus import NexusAgent
    a = NexusAgent()
    result = await a.run("test", mode="nonexistent_mode")
    assert result.success  # should use default mode, not crash

@pytest.mark.asyncio
async def test_registry_run():
    from core.sub_agents.registry import agent_registry
    result = await agent_registry.run("ORACLE", "Plan a website build", mode="plan")
    assert result.success
    assert result.agent_name == "ORACLE"

@pytest.mark.asyncio
async def test_parallel_run():
    from core.sub_agents.registry import agent_registry
    tasks = [
        {"agent": "NEXUS", "task": "research AI", "mode": "brief"},
        {"agent": "SCRIBE", "task": "write docs for AI module", "mode": "docs"},
    ]
    results = await agent_registry.run_parallel(tasks)
    assert len(results) == 2
    assert all(r.success for r in results)

@pytest.mark.asyncio
async def test_result_to_dict():
    from core.sub_agents.agents.herald import HeraldAgent
    a = HeraldAgent()
    result = await a.run("Draft an update email")
    d = result.to_dict()
    assert "agent_name" in d
    assert "output" in d
    assert "duration_s" in d
