from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES
from core.sub_agents.agents.atlas import AtlasAgent as AtlasSubAgent


class AtlasAdapter(SubAgentAdapter):
    agent_id = "atlas"
    capabilities = CAPABILITIES["atlas"]
    sub_agent_class = AtlasSubAgent
    default_mode = "analyze"
