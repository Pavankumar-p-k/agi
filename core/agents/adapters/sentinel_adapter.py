from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES
from core.sub_agents.agents.sentinel import SentinelAgent as SentinelSubAgent


class SentinelAdapter(SubAgentAdapter):
    agent_id = "sentinel"
    capabilities = CAPABILITIES["sentinel"]
    sub_agent_class = SentinelSubAgent
    default_mode = "diagnose"
