"""SPCL-9 Step 1: proof artifacts for the stub hand-off layer.

Straight read of the smoke test: 7/26 sub-AIs execute real work when called
directly; the 19 that must pass through ``core/agents/*`` (router, registry,
base class, 9 adapters, 6 tool agents, ``_legacy/`` backends) are all
``Auto-reconstructed`` placeholder stubs.

These tests assert the CURRENT broken reality, one per hand-off point (not
one per sub-AI). They pass today by correctly documenting brokenness. When a
hop is genuinely implemented, its test must be flipped to assert the working
behavior — the "WHEN FIXED" note on each test says what to change.

Pre-existing breakage, not SPCL-9 damage: ``tests/unit/test_agent_adapters.py``
already fails on ``'forge' not found in 'CAPABILITIES'`` on the untouched
tree, because ``CAPABILITIES`` is the string ``"CAPABILITIES"``, not a dict.
"""
import asyncio
import importlib

import pytest

ADAPTER_MODULES = [
    ("core.agents.adapters.atlas_adapter", "AtlasAdapter"),
    ("core.agents.adapters.cipher_adapter", "CipherAdapter"),
    ("core.agents.adapters.forge_adapter", "ForgeAdapter"),
    ("core.agents.adapters.herald_adapter", "HeraldAdapter"),
    ("core.agents.adapters.nexus_adapter", "NexusAdapter"),
    ("core.agents.adapters.oracle_adapter", "OracleAdapter"),
    ("core.agents.adapters.phantom_adapter", "PhantomAdapter"),
    ("core.agents.adapters.scribe_adapter", "ScribeAdapter"),
    ("core.agents.adapters.sentinel_adapter", "SentinelAdapter"),
]

TOOL_AGENTS = [
    ("core.agents.browser_agent", "BrowserAgent"),
    ("core.agents.build_agent", "BuildAgent"),
    ("core.agents.email_agent", "EmailAgent"),
    ("core.agents.memory_agent", "MemoryAgent"),
    ("core.agents.research_agent", "ResearchAgent"),
    ("core.agents.test_agent", "TestAgent"),
]


def test_router_hop_is_stub():
    """Router hop does not exist: every lookup returns None.

    WHEN FIXED: assert find_agent_for_goal("build android app").agent_id == "build"
    and list_agents() returns the 15 registered agents.
    """
    from core.agents.router import find_agent_for_goal, get_agent, list_agents

    assert find_agent_for_goal("build android app") is None
    assert get_agent("forge") is None
    assert list_agents() is None


@pytest.mark.parametrize("module,classname", ADAPTER_MODULES)
def test_adapter_hop_has_no_real_identity(module, classname):
    """Adapter hop is a stub: instances expose no real string agent_id.

    WHEN FIXED: assert isinstance(inst.agent_id, str) and inst.agent_id == expected.
    """
    cls = getattr(importlib.import_module(module), classname)
    inst = cls()
    assert not isinstance(getattr(inst, "agent_id", None), str), (
        f"{classname} unexpectedly has a real agent_id — flip this test "
        "to assert the working behavior"
    )


@pytest.mark.parametrize("module,classname", TOOL_AGENTS)
def test_tool_agent_module_is_stub(module, classname):
    """Tool-agent hop is a stub: classes resolve to DynamicStub, not real agents.

    WHEN FIXED: assert the class is a BaseAgent subclass with real capabilities.
    """
    cls = getattr(importlib.import_module(module), classname, None)
    assert cls is not None
    assert type(cls()).__name__ == "DynamicStub", (
        f"{classname} unexpectedly has real logic — flip this test"
    )


def test_legacy_forge_hop_returns_stub():
    """ForgeSubAgent delegates to the stub _legacy backend, not a real result.

    WHEN FIXED: assert isinstance(result, dict) with real output content.
    """
    from core.providers.adapters.forge import ForgeSubAgent

    result = asyncio.run(ForgeSubAgent().run({"task": "write hello world"}))
    assert not isinstance(result, dict), (
        "ForgeSubAgent unexpectedly returned a real dict — flip this test "
        "to assert the working behavior"
    )


def test_capabilities_registry_is_unusable():
    """Registry hop is absent: CAPABILITIES is a stub string, not a routing table.

    This is the pre-existing root cause of test_agent_adapters.py failing on
    the untouched tree. WHEN FIXED: assert all 15 agent ids with non-empty,
    non-overlapping keyword lists.
    """
    from core.agents.capabilities import CAPABILITIES

    assert not isinstance(CAPABILITIES, dict)


def test_capability_ai_reports_empty_registry():
    """Silent empty-success: CapabilityAI runs but the registry holds nothing.

    Guards the failure mode where an empty registry looks like success.
    WHEN FIXED: assert len(recs) > 0 and len(caps) > 0.
    """
    from core.capability.capability_ai import CapabilityAI

    ai = CapabilityAI()
    assert ai.recommend("build a calculator app") == []
    assert ai.what_can_jarvis_do(only_healthy=False) == []
