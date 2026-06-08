"""Unit tests for StateGraph nodes — pause, resume, parallel sub-agents,
AgentState serialization, structured reasoning, and PAUSED phase routing."""

import json
import re
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, ".")

from core.graph.state import THINK_RE, AgentPhase, AgentState, RoundState
from core.tools._constants import TOOL_TAGS, ToolBlock


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def base_state():
    s = AgentState(
        endpoint_url="http://test",
        model="test-model",
        messages=[{"role": "user", "content": "hello"}],
    )
    s.round_state = RoundState(
        round_num=1,
        response="I will run ls",
        tool_blocks=[ToolBlock("bash", "ls -la")],
    )
    return s


@pytest.fixture
def non_effectful_state():
    s = AgentState(
        endpoint_url="http://test",
        model="test-model",
        messages=[{"role": "user", "content": "search"}],
    )
    s.round_state = RoundState(
        round_num=1,
        response="I will search",
        tool_blocks=[ToolBlock("web_search", "latest news")],
    )
    return s


@pytest.fixture
def multi_tool_state():
    s = AgentState(
        endpoint_url="http://test",
        model="test-model",
        messages=[{"role": "user", "content": "do multiple things"}],
    )
    s.round_state = RoundState(
        round_num=1,
        response="Running multiple tools",
        tool_blocks=[
            ToolBlock("bash", "rm -rf /"),
            ToolBlock("web_search", "safe query"),
            ToolBlock("create_document", "README\nmarkdown\n# Hello"),
        ],
    )
    return s


# ── AgentState serialization ──────────────────────────────────────

class TestAgentStateSerialization:
    def test_to_dict_roundtrip(self, base_state):
        d = base_state.to_dict()
        restored = AgentState.from_dict(d)
        assert restored.run_id == base_state.run_id
        assert restored.phase == base_state.phase
        assert restored.round_state.round_num == base_state.round_state.round_num
        assert restored.round_state.response == base_state.round_state.response
        assert restored.endpoint_url == base_state.endpoint_url
        assert restored.model == base_state.model

    def test_to_dict_new_fields_preserved(self):
        s = AgentState(
            endpoint_url="http://test",
            model="test",
            messages=[{"role": "user", "content": "hi"}],
            pause_before_effectful=True,
        )
        s.structured_reasoning.append({"type": "test", "content": "trace"})
        s.parallel_sub_agents.append({"task": "sub1"})
        d = s.to_dict()
        restored = AgentState.from_dict(d)
        assert restored.pause_before_effectful is True
        assert len(restored.structured_reasoning) == 1
        assert restored.structured_reasoning[0]["type"] == "test"
        assert len(restored.parallel_sub_agents) == 1
        assert restored.parallel_sub_agents[0]["task"] == "sub1"

    def test_to_dict_clears_volatile_fields(self, base_state):
        base_state.events.append("test event")
        base_state.mcp_mgr = MagicMock()
        d = base_state.to_dict()
        assert d["events"] == []
        assert d["mcp_mgr"] is None
        assert d["headers"] is None

    def test_phase_name_roundtrip(self):
        for phase in AgentPhase:
            s = AgentState(endpoint_url="", model="", messages=[])
            s.phase = phase
            d = s.to_dict()
            restored = AgentState.from_dict(d)
            assert restored.phase == phase, f"Failed for {phase}"


# ── Pause node ────────────────────────────────────────────────────

class TestPauseNode:
    @pytest.mark.asyncio
    async def test_pauses_effectful_tool(self, base_state):
        from core.graph.nodes import pause_node

        base_state.pause_before_effectful = True
        result = await pause_node(base_state)

        assert result.phase == AgentPhase.PAUSED
        assert result.paused_tool_data is not None
        assert len(result.paused_tool_data) == 1
        assert result.paused_tool_data[0]["tool"] == "bash"

    @pytest.mark.asyncio
    async def test_skips_non_effectful_tool(self, non_effectful_state):
        from core.graph.nodes import pause_node

        non_effectful_state.pause_before_effectful = True
        result = await pause_node(non_effectful_state)

        assert result.phase == AgentPhase.TOOL_CALLING
        assert result.paused_tool_data is None

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self, base_state):
        from core.graph.nodes import pause_node

        base_state.pause_before_effectful = False
        result = await pause_node(base_state)

        assert result.phase == AgentPhase.TOOL_CALLING
        assert result.paused_tool_data is None

    @pytest.mark.asyncio
    async def test_emits_human_review_event(self, base_state):
        from core.graph.nodes import pause_node

        base_state.pause_before_effectful = True
        result = await pause_node(base_state)

        events = result.events
        assert len(events) == 1
        payload = json.loads(events[0][6:])  # strip "data: "
        assert payload["type"] == "human_review"
        assert "run_id" in payload
        assert payload["round"] == 0  # state.round_num, not round_state.round_num
        assert len(payload["tools"]) == 1
        assert payload["tools"][0]["tool"] == "bash"

    @pytest.mark.asyncio
    async def test_pauses_only_effectful_in_mixed(self, multi_tool_state):
        from core.graph.nodes import pause_node

        multi_tool_state.pause_before_effectful = True
        result = await pause_node(multi_tool_state)

        assert result.phase == AgentPhase.PAUSED
        tools = result.paused_tool_data
        tool_types = {t["tool"] for t in tools}
        assert "bash" in tool_types
        assert "create_document" in tool_types
        assert "web_search" not in tool_types

    @pytest.mark.asyncio
    async def test_saves_checkpoint(self, base_state):
        from core.graph.nodes import pause_node
        import core.persistence.store as _pstore

        base_state.pause_before_effectful = True
        original = _pstore.checkpoint_store
        mock_store = MagicMock()
        mock_store.save_agent_state = MagicMock(return_value="test-run-id")
        _pstore.checkpoint_store = mock_store
        try:
            await pause_node(base_state)
            mock_store.save_agent_state.assert_called_once()
        finally:
            _pstore.checkpoint_store = original

    @pytest.mark.asyncio
    async def test_handles_no_tool_blocks(self):
        from core.graph.nodes import pause_node

        s = AgentState(
            endpoint_url="http://test",
            model="test",
            messages=[{"role": "user", "content": "hi"}],
            pause_before_effectful=True,
        )
        s.round_state = RoundState(round_num=1, response="no tools")
        result = await pause_node(s)

        assert result.phase == AgentPhase.TOOL_CALLING
        assert result.paused_tool_data is None


# ── Resume node ───────────────────────────────────────────────────

class TestResumeNode:
    @pytest.mark.asyncio
    async def test_approve_goes_to_tool_calling(self):
        from core.graph.nodes import resume_node

        s = AgentState(
            endpoint_url="http://test",
            model="test",
            messages=[{"role": "user", "content": "hi"}],
        )
        s.resume_action = "approve"
        result = await resume_node(s)

        assert result.phase == AgentPhase.TOOL_CALLING
        assert result.resume_action == ""
        assert result.paused_tool_data is None

    @pytest.mark.asyncio
    async def test_reject_goes_to_thinking_with_feedback(self):
        from core.graph.nodes import resume_node

        s = AgentState(
            endpoint_url="http://test",
            model="test",
            messages=[{"role": "user", "content": "hi"}],
        )
        s.resume_action = "reject"
        s.resume_feedback = "Don't run that"
        result = await resume_node(s)

        assert result.phase == AgentPhase.THINKING
        assert result.resume_action == ""
        assert result.resume_feedback == ""
        assert result.paused_tool_data is None
        assert any("Don't run that" in m.get("content", "") for m in result.messages)

    @pytest.mark.asyncio
    async def test_reject_default_feedback(self):
        from core.graph.nodes import resume_node

        s = AgentState(
            endpoint_url="http://test",
            model="test",
            messages=[{"role": "user", "content": "hi"}],
        )
        s.resume_action = "reject"
        s.resume_feedback = ""
        result = await resume_node(s)

        assert result.phase == AgentPhase.THINKING
        assert any("rejected by the user" in m.get("content", "") for m in result.messages)

    @pytest.mark.asyncio
    async def test_no_action_stays_paused(self):
        from core.graph.nodes import resume_node

        s = AgentState(
            endpoint_url="http://test",
            model="test",
            messages=[{"role": "user", "content": "hi"}],
        )
        s.resume_action = ""
        result = await resume_node(s)

        assert result.phase == AgentPhase.PAUSED

    @pytest.mark.asyncio
    async def test_approve_emits_event(self):
        from core.graph.nodes import resume_node

        s = AgentState(
            endpoint_url="http://test",
            model="test",
            messages=[{"role": "user", "content": "hi"}],
        )
        s.resume_action = "approve"
        result = await resume_node(s)

        events = result.events
        assert len(events) == 1
        payload = json.loads(events[0][6:])
        assert payload["type"] == "resume_approved"

    @pytest.mark.asyncio
    async def test_reject_emits_event(self):
        from core.graph.nodes import resume_node

        s = AgentState(
            endpoint_url="http://test",
            model="test",
            messages=[{"role": "user", "content": "hi"}],
        )
        s.resume_action = "reject"
        s.resume_feedback = "nope"
        result = await resume_node(s)

        events = result.events
        assert len(events) == 1
        payload = json.loads(events[0][6:])
        assert payload["type"] == "resume_rejected"
        assert payload["feedback"] == "nope"


# ── Parallel sub-agents node ──────────────────────────────────────

class TestParallelSubAgentsNode:
    @pytest.mark.asyncio
    async def test_skips_when_no_configs(self):
        from core.graph.nodes import parallel_sub_agents_node

        s = AgentState(
            endpoint_url="http://test",
            model="test",
            messages=[{"role": "user", "content": "hi"}],
        )
        result = await parallel_sub_agents_node(s)

        assert result.phase == AgentPhase.THINKING
        assert result.parallel_results == []

    @pytest.mark.asyncio
    async def test_emits_start_and_complete_events(self):
        from core.graph.nodes import parallel_sub_agents_node

        s = AgentState(
            endpoint_url="http://test",
            model="test",
            messages=[{"role": "user", "content": "hi"}],
            parallel_sub_agents=[{"task": "sub task", "tools": ["web_search"]}],
        )

        with patch(
            "core.graph.nodes._run_sub_agent",
            new=AsyncMock(return_value={
                "index": 0, "task": "sub task",
                "response": "result", "results": [],
                "error": None,
            }),
        ):
            result = await parallel_sub_agents_node(s)

        events = result.events
        types = []
        for e in events:
            if e.startswith("data: ") and not e.startswith("data: [DONE]"):
                types.append(json.loads(e[6:]).get("type"))

        assert "parallel_start" in types
        assert "parallel_complete" in types
        assert result.phase == AgentPhase.THINKING


# ── Route decision (PAUSED) ───────────────────────────────────────

class TestRouteDecision:
    def test_route_decision_paused_no_action(self):
        from core.graph.edges import route_decision

        s = AgentState(endpoint_url="", model="", messages=[])
        s.phase = AgentPhase.PAUSED
        assert route_decision(s) == "__pause__"

    def test_route_decision_paused_with_resume(self):
        from core.graph.edges import route_decision

        s = AgentState(endpoint_url="", model="", messages=[])
        s.phase = AgentPhase.PAUSED
        s.resume_action = "approve"
        assert route_decision(s) == "resume"

    def test_route_decision_thinking_with_parallel(self):
        from core.graph.edges import route_decision

        s = AgentState(endpoint_url="", model="", messages=[])
        s.phase = AgentPhase.THINKING
        s.parallel_sub_agents.append({"task": "sub"})
        s.round_state = RoundState(round_num=1, response="ok")
        assert route_decision(s) == "parallel_sub_agents"

    def test_route_decision_thinking_with_pause(self):
        from core.graph.edges import route_decision

        s = AgentState(endpoint_url="", model="", messages=[])
        s.phase = AgentPhase.THINKING
        s.pause_before_effectful = True
        s.round_state = RoundState(
            round_num=1, response="ok",
            tool_blocks=[ToolBlock("bash", "cmd")],
        )
        assert route_decision(s) == "pause"


# ── Structured reasoning extraction ────────────────────────────────

class TestStructuredReasoning:
    def test_extracts_think_blocks(self):
        resp = "<think>I need to search for info</think> Let me search."
        traces = []
        for t in THINK_RE.findall(resp):
            traces.append({"type": "reasoning_block", "content": t.strip()[:500]})
        assert len(traces) == 1
        assert "think" in traces[0]["content"]

    def test_extracts_confidence_scores(self):
        resp = "I am confident (confidence: 85%) in this answer."
        conf_re = re.compile(
            r"(?:confidence|confident|certainty|sure)\s*[:=]\s*(\d+(?:\.\d+)?)%?",
            re.IGNORECASE,
        )
        scores = []
        for cm in conf_re.finditer(resp):
            scores.append(float(cm.group(1)))
        assert len(scores) == 1
        assert scores[0] == 85.0

    def test_detects_alternatives(self):
        resp = "We could also try a different approach as an alternative."
        has_alt = bool(re.search(
            r"(?:alternative|instead|another option|could also)",
            resp, re.IGNORECASE,
        ))
        assert has_alt is True

    def test_no_false_positive_alternatives(self):
        resp = "The answer is 42."
        has_alt = bool(re.search(
            r"(?:alternative|instead|another option|could also)",
            resp, re.IGNORECASE,
        ))
        assert has_alt is False
