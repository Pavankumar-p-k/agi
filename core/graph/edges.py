from core.graph.state import AgentPhase, AgentState


def route_decision(state: AgentState) -> str:
    if state.error:
        return "finish"
    if state.phase == AgentPhase.SETUP:
        return "think"
    if state.phase == AgentPhase.PAUSED:
        if state.resume_action:
            return "resume"
        return "__pause__"
    if state.phase == AgentPhase.THINKING:
        if state.force_answer:
            return "force_answer"
        if state.parallel_sub_agents:
            return "parallel_sub_agents"
        if not state.round_state or not state.round_state.tool_blocks:
            return "finish"
        if state.pause_before_effectful:
            return "pause"
        return "tool_call"
    if state.phase == AgentPhase.TOOL_CALLING:
        if state.effectful_used and state.verifier_rounds < 2:
            return "verify"
        return "think"
    if state.phase == AgentPhase.VERIFYING:
        if state.verifier_rounds < 2 and state.round_state and state.round_state.tool_blocks:
            return "think"
        return "think"
    if state.phase == AgentPhase.FORCE_ANSWER:
        return "finish"
    if state.phase == AgentPhase.FINISHED:
        return "__end__"
    return "finish"
