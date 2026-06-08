from core.graph.edges import route_decision
from core.graph.graph import StateGraph
from core.graph.nodes import (
    finish_node,
    force_answer_node,
    parallel_sub_agents_node,
    pause_node,
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
    g.add_node("tool_call", tool_call_node)
    g.add_node("verify", verify_node)
    g.add_node("route", route_node)
    g.add_node("force_answer", force_answer_node)
    g.add_node("pause", pause_node)
    g.add_node("resume", resume_node)
    g.add_node("parallel_sub_agents", parallel_sub_agents_node)
    g.add_node("finish", finish_node)
    g.set_entry_point("setup")
    g.add_edge("setup", "think")
    g.add_conditional_edges("think", route_decision, {
        "tool_call": "tool_call",
        "pause": "pause",
        "parallel_sub_agents": "parallel_sub_agents",
        "force_answer": "force_answer",
        "finish": "finish",
        "think": "think",
    })
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
    g.add_edge("route", "think")
    g.add_edge("finish", "__end__")
    return g
