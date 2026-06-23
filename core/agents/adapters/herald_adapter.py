from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES
from core.sub_agents.agents.herald import HeraldAgent as HeraldSubAgent


class HeraldAdapter(SubAgentAdapter):
    agent_id = "herald"
    capabilities = CAPABILITIES["herald"]
    sub_agent_class = HeraldSubAgent
    default_mode = "draft"
