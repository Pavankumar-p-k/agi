"""Legacy HeraldAgent backend — now real, delegating to the SubAgent base."""
from core.agents._sub_agent_base import SubAgent


class HeraldAgent(SubAgent):
    NAME = "HERALD"
    DEFAULT_MODE = "draft"
    MODES = {
        "draft": "You are HERALD, a professional communicator. Draft clear, audience-appropriate copy.",
        "newsletter": "You are HERALD writing a newsletter: subject line, intro, sections, call-to-action.",
        "announce": "You are HERALD writing an announcement. Lead with the news, keep it under 150 words.",
    }
