from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES
from core.agents._legacy.nexus import NexusAgent as NexusSubAgent


class NexusAdapter(SubAgentAdapter):
    agent_id = "nexus"
    capabilities = CAPABILITIES["nexus"]
    sub_agent_class = NexusSubAgent
    default_mode = "research"

