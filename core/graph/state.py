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
from __future__ import annotations

import re
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class AgentPhase(Enum):
    SETUP = auto()
    THINKING = auto()
    TOOL_CALLING = auto()
    VERIFYING = auto()
    FORCE_ANSWER = auto()
    DOC_STREAMING = auto()
    PAUSED = auto()
    FINISHED = auto()
    ERROR = auto()


THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL | re.IGNORECASE)


@dataclass
class RoundState:
    round_num: int
    response: str = ""
    reasoning: str = ""
    native_tool_calls: list[dict] = field(default_factory=list)
    tool_blocks: list[Any] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)
    tool_result_texts: list[str] = field(default_factory=list)

    @property
    def cleaned_response(self) -> str:
        from core.agent_tools import strip_tool_blocks
        return strip_tool_blocks(self.response).strip()


@dataclass
class AgentState:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    error: str | None = None
    checkpoint_id: int | None = None

    endpoint_url: str = ""
    model: str = ""
    messages: list[dict] = field(default_factory=list)
    headers: dict | None = None
    temperature: float = 0.3
    max_tokens: int = 4096
    prompt_type: str | None = None
    max_rounds: int = 20
    max_tool_calls: int = 0
    context_length: int = 0
    active_document: Any = None
    disabled_tools: set | None = None
    owner: str | None = None
    relevant_tools: set | None = None
    fallbacks: list[tuple] | None = None
    _is_teacher_run: bool = False

    pause_before_effectful: bool = False
    paused_tool_data: list[dict] | None = None
    resume_action: str = ""
    resume_feedback: str = ""

    structured_reasoning: list[dict] = field(default_factory=list)

    parallel_sub_agents: list[dict] = field(default_factory=list)
    parallel_results: list[dict] = field(default_factory=list)

    round_num: int = 0
    phase: AgentPhase = AgentPhase.SETUP
    total_tool_calls: int = 0
    total_start: float = 0.0

    full_response: str = ""
    tool_events: list[dict] = field(default_factory=list)
    round_texts: list[str] = field(default_factory=list)
    round_state: RoundState | None = None

    recent_call_sigs: deque[str] = field(default_factory=lambda: deque(maxlen=6))
    stuck_rounds: int = 0
    tool_type_counts: Counter = field(default_factory=Counter)
    force_answer: bool = False
    effectful_used: bool = False

    verifier_rounds: int = 0
    verifier_instruction: str = ""

    real_input_tokens: int = 0
    real_output_tokens: int = 0
    last_round_input_tokens: int = 0
    has_real_usage: bool = False
    time_to_first_token: float | None = None
    first_token_received: bool = False
    backend_gen_tps: float = 0
    backend_prefill_tps: float = 0

    doc_acc: str = ""
    doc_opened: bool = False
    doc_last_len: int = 0
    doc_fence_offset: int = 0
    doc_scan_from: int = 0

    prep_timings: dict[str, float] = field(default_factory=dict)

    events: list[str] = field(default_factory=list)

    mcp_mgr: Any = None
    mcp_schemas: list[dict] = field(default_factory=list)
    mcp_disabled_map: dict | None = None
    is_api_model: bool = False
    needs_admin: bool = False
    last_user: str = ""
    retrieval_query: str = ""
    relevant_tools_set: set | None = None
    all_tool_schemas: list[dict] = field(default_factory=list)
    candidates: list[tuple] = field(default_factory=list)
    disabled_tools_set: set = field(default_factory=set)

    def advance_round(self) -> int:
        self.round_num += 1
        self.phase = AgentPhase.THINKING
        return self.round_num

    def is_stuck(self, max_stuck: int = 4) -> tuple[bool, str]:
        runaway = next(
            (t for t, n in self.tool_type_counts.items() if n >= 15),
            None,
        )
        if runaway:
            return True, f"calling {runaway} over and over"
        if self.stuck_rounds >= max_stuck:
            return True, "repeating the same tool calls without new progress"
        return False, ""

    def record_tool_call(self, tool_type: str, content: str):
        sig = f"{tool_type}:{(content or '').strip()[:120]}"
        is_repeat = sig in self.recent_call_sigs
        self.recent_call_sigs.append(sig)
        self.tool_type_counts[tool_type] += 1
        real_text = THINK_RE.sub("", self.round_texts[-1] if self.round_texts else "").strip()
        if is_repeat and not real_text:
            self.stuck_rounds += 1
        else:
            self.stuck_rounds = 0

    def reset_for_verifier(self):
        self.effectful_used = False

    def to_dict(self) -> dict:
        import dataclasses
        d = dataclasses.asdict(self)
        d["phase"] = self.phase.name
        d["round_state"] = dataclasses.asdict(self.round_state) if self.round_state else None
        d["recent_call_sigs"] = list(self.recent_call_sigs)
        d["tool_type_counts"] = dict(self.tool_type_counts)
        d["headers"] = None
        d["mcp_mgr"] = None
        d["mcp_schemas"] = []
        d["mcp_disabled_map"] = None
        d["all_tool_schemas"] = []
        d["candidates"] = []
        d["active_document"] = None
        d["events"] = []
        return d

    @classmethod
    def from_dict(cls, d: dict) -> AgentState:
        phase_name = d.pop("phase", "SETUP")
        rs_data = d.pop("round_state", None)
        rs = RoundState(**rs_data) if rs_data else None
        d["recent_call_sigs"] = deque(d.pop("recent_call_sigs", []), maxlen=6)
        d["tool_type_counts"] = Counter(d.pop("tool_type_counts", {}))
        state = cls(**d)
        state.phase = AgentPhase[phase_name]
        state.round_state = rs
        return state
