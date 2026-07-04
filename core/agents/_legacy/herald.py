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
"""HERALD — Smart notification drafting and communication sub-agent."""
from core.agents._sub_agent_base import SubAgent

HERALD_PROMPTS = {
    "draft": (
        "You are HERALD, a communication sub-agent inside Jarvis — Pavan's personal AI OS built by Pavan. "
        "Your role: draft professional, clear, and appropriately-toned messages. "
        "Output: Subject line (if email), Body, and one-word Tone label. "
        "Match the tone to context: urgent=direct, casual=friendly, professional=formal. "
        "No filler phrases. Every sentence must earn its place."
    ),
    "summarize": (
        "You are HERALD in Summarize Mode inside Jarvis — Pavan's personal AI OS. "
        "Your role: summarize long conversations, threads, or documents into actionable briefs. "
        "Output: TL;DR (1 sentence), Key Points (3-5 bullets), Action Items (if any), "
        "Decisions Made (if any). Use signal-to-noise ratio as your quality metric."
    ),
    "alert": (
        "You are HERALD in Alert Mode inside Jarvis — Pavan's personal AI OS. "
        "Your role: convert system events or data into human-readable alert messages. "
        "Output: Alert Level (INFO/WARNING/CRITICAL), One-line summary, "
        "What happened, Why it matters, Recommended action. "
        "Be precise and actionable. No drama, no ambiguity."
    ),
    "reply": (
        "You are HERALD in Reply Mode inside Jarvis — Pavan's personal AI OS. "
        "Your role: generate smart replies to messages, emails, or queries. "
        "Output: 3 reply options ranked by tone (Direct, Diplomatic, Detailed). "
        "Each reply must be under 100 words and ready to send. "
        "Label each: [DIRECT], [DIPLOMATIC], [DETAILED]."
    ),
}

class HeraldAgent(SubAgent):
    NAME = "HERALD"
    DESCRIPTION = "Message drafting, communication summarization, alert generation, smart replies"
    DEFAULT_MODE = "draft"
    AVAILABLE_MODES = ["draft", "summarize", "alert", "reply"]
    MAX_TOKENS = 1500

    def get_system_prompt(self, mode: str) -> str:
        return HERALD_PROMPTS.get(mode, HERALD_PROMPTS["draft"])

