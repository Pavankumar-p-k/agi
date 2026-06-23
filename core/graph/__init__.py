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
from core.graph.edges import route_decision
from core.graph.graph import StateGraph
from core.graph.nodes import (
    finish_node,
    force_answer_node,
    parallel_sub_agents_node,
    pause_node,
    plan_node,
    resume_node,
    route_node,
    setup_node,
    think_node,
    tool_call_node,
    verify_node,
)
from core.graph.state import AgentPhase as AgentPhase
from core.graph.state import AgentState as AgentState
from core.graph.state import RoundState as RoundState


def build_default_graph() -> StateGraph:
    g = StateGraph()
    g.add_node("setup", setup_node)
    g.add_node("think", think_node)
    g.add_node("plan", plan_node)
    g.add_node("tool_call", tool_call_node)
    g.add_node("verify", verify_node)
    g.add_node("route", route_node)
    g.add_node("force_answer", force_answer_node)
    g.add_node("pause", pause_node)
    g.add_node("resume", resume_node)
    g.add_node("parallel_sub_agents", parallel_sub_agents_node)
    g.add_node("finish", finish_node)
    def _route_after_parse(state: AgentState) -> str:
        """Decide what to do after route_node parses tool blocks from the LLM response."""
        if state.error:
            return "finish"
        if state.phase == AgentPhase.PAUSED:
            return "__pause__"
        if state.phase in (AgentPhase.FINISHED, AgentPhase.FORCE_ANSWER):
            return "finish"
        if state.round_state and state.round_state.tool_blocks:
            return "plan"  # plan_node runs pre_plan before tool_call
        return "finish"

    g.set_entry_point("setup")
    g.add_edge("setup", "think")
    g.add_edge("think", "route")
    # route → decision based on parsed tool blocks
    g.add_conditional_edges("route", _route_after_parse, {
        "plan": "plan",
        "finish": "finish",
        "__pause__": "__pause__",
    })
    g.add_edge("plan", "tool_call")
    g.add_conditional_edges("tool_call", route_decision, {
        "verify": "verify",
        "think": "think",
        "finish": "finish",
    })
    g.add_conditional_edges("verify", route_decision, {
        "think": "think",
        "finish": "finish",
    })
    g.add_conditional_edges("pause", route_decision, {
        "tool_call": "tool_call",
        "resume": "resume",
        "__pause__": "__pause__",
    })
    g.add_conditional_edges("resume", route_decision, {
        "tool_call": "tool_call",
        "think": "think",
        "__pause__": "__pause__",
    })
    g.add_conditional_edges("parallel_sub_agents", route_decision, {
        "think": "think",
        "finish": "finish",
    })
    g.add_edge("force_answer", "finish")
    g.add_edge("finish", "__end__")
    return g
