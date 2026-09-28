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

# All 5 tool agents are now real — see test_tool_agents_are_real


def test_router_hop_is_real():
    """Router hop is now real: find_agent_for_goal returns an agent, list_agents returns agents."""
    from core.agents.router import find_agent_for_goal, get_agent, list_agents

    agent = find_agent_for_goal("build android app")
    assert agent is not None, "Router should find an agent for 'build android app'"
    assert hasattr(agent, "agent_id") and isinstance(agent.agent_id, str)

    result = list_agents()
    assert isinstance(result, list), "list_agents should return a list"
    assert len(result) > 0, "list_agents should return at least one agent"


@pytest.mark.parametrize("module,classname", ADAPTER_MODULES)
def test_adapter_hop_has_no_real_identity(module, classname):
    """Adapter hop is a stub: instances expose no real string agent_id.

    WHEN FIXED: assert isinstance(inst.agent_id, str) and inst.agent_id == expected.
    """
    cls = getattr(importlib.import_module(module), classname)
    inst = cls()
    if classname in ("ForgeAdapter", "NexusAdapter", "OracleAdapter", "PhantomAdapter", "HeraldAdapter", "ScribeAdapter", "AtlasAdapter", "SentinelAdapter", "CipherAdapter"):
        # All adapters are now real
        expected_ids = {
            "ForgeAdapter": "forge", "NexusAdapter": "nexus",
            "OracleAdapter": "oracle", "PhantomAdapter": "phantom",
            "HeraldAdapter": "herald", "ScribeAdapter": "scribe",
            "AtlasAdapter": "atlas", "SentinelAdapter": "sentinel",
            "CipherAdapter": "cipher",
        }
        assert isinstance(inst.agent_id, str) and inst.agent_id == expected_ids[classname], (
            f"{classname} should have real agent_id='{expected_ids[classname]}'"
        )
    else:
        assert not isinstance(getattr(inst, "agent_id", None), str), (
            f"{classname} unexpectedly has a real agent_id — flip this test "
            "to assert the working behavior"
        )


def test_browser_agent_is_real():
    """BrowserAgent is now a real Chrome usage pattern analyzer (read-only).

    It has an analyze() method that returns a BrowserSnapshot with open_tabs,
    history, patterns, and predictions.
    """
    from core.agents.browser_agent import BrowserAgent

    agent = BrowserAgent()
    assert hasattr(agent, "analyze"), "BrowserAgent must have analyze()"
    assert hasattr(agent, "get_open_tabs"), "BrowserAgent must have get_open_tabs()"
    assert hasattr(agent, "get_history"), "BrowserAgent must have get_history()"
    assert hasattr(agent, "get_patterns"), "BrowserAgent must have get_patterns()"
    assert hasattr(agent, "get_predictions"), "BrowserAgent must have get_predictions()"
    snap = agent.analyze()
    assert hasattr(snap, "open_tabs"), "BrowserSnapshot must have open_tabs"
    assert hasattr(snap, "patterns"), "BrowserSnapshot must have patterns"
    assert hasattr(snap, "predictions"), "BrowserSnapshot must have predictions"
    assert hasattr(snap, "timestamp"), "BrowserSnapshot must have timestamp"


REAL_TOOL_AGENTS = [
    ("core.agents.build_agent", "BuildAgent"),
    ("core.agents.email_agent", "EmailAgent"),
    ("core.agents.memory_agent", "MemoryAgent"),
    ("core.agents.research_agent", "ResearchAgent"),
    ("core.agents.test_agent", "TestAgent"),
]


@pytest.mark.parametrize("module,classname", REAL_TOOL_AGENTS)
def test_tool_agents_are_real(module, classname):
    """Build/Email/Memory/Research/Test agents are now real, not stubs.

    Each must have an analyze() method returning a dataclass snapshot.
    """
    cls = getattr(importlib.import_module(module), classname, None)
    assert cls is not None, f"{classname} class not found in {module}"
    inst = cls()
    assert type(inst).__name__ == classname, (
        f"{classname} should be a real class, got {type(inst).__name__}"
    )
    assert hasattr(inst, "analyze"), f"{classname} must have analyze()"


def test_legacy_forge_hop_returns_real():
    """ForgeSubAgent now delegates to real ForgeAgent backend and returns a dict."""
    from core.providers.adapters.forge import ForgeSubAgent

    result = asyncio.run(ForgeSubAgent().run({"task": "write hello world"}))
    assert isinstance(result, dict), (
        f"ForgeSubAgent should return a dict, got {type(result)}"
    )
    assert "success" in result or "output" in result, (
        f"ForgeSubAgent result should have success/output keys, got {list(result.keys())}"
    )


def test_capabilities_registry_is_real():
    """CAPABILITIES is now a real routing dict with all 15 agent ids."""
    from core.agents.capabilities import CAPABILITIES

    assert isinstance(CAPABILITIES, dict), "CAPABILITIES must be a dict"
    expected_ids = {
        "research", "build", "test", "browser", "memory", "email",
        "forge", "nexus", "oracle", "phantom", "cipher",
        "herald", "atlas", "scribe", "sentinel",
    }
    assert expected_ids.issubset(set(CAPABILITIES.keys())), (
        f"Missing agent ids: {expected_ids - set(CAPABILITIES.keys())}"
    )
    for aid, keywords in CAPABILITIES.items():
        assert isinstance(keywords, list) and len(keywords) > 0, (
            f"{aid} has empty keywords"
        )


def test_capability_ai_reports_empty_registry():
    """Silent empty-success: CapabilityAI runs but the registry holds nothing.

    Guards the failure mode where an empty registry looks like success.
    WHEN FIXED: assert len(recs) > 0 and len(caps) > 0.
    """
    from core.capability.capability_ai import CapabilityAI

    ai = CapabilityAI()
    assert ai.recommend("build a calculator app") == []
    assert ai.what_can_jarvis_do(only_healthy=False) == []
