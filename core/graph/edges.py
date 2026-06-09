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
