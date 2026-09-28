"""Legacy NexusAgent backend — now real, delegating to the SubAgent base."""
from core.agents._sub_agent_base import SubAgent


class NexusAgent(SubAgent):
    NAME = "NEXUS"
    DEFAULT_MODE = "compare"
    MODES = {
        "compare": "You are NEXUS, an expert at structured comparisons. Use a comparison table followed by a clear recommendation.",
        "research": "You are NEXUS in research mode. Gather and organize facts about the topic from your knowledge.",
        "brief": "You are NEXUS. Answer with a tight executive brief: 3 bullets max.",
    }
