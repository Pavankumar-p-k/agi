from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES
from core.agents._legacy.forge import ForgeAgent as ForgeSubAgent


class ForgeAdapter(SubAgentAdapter):
    agent_id = "forge"
    capabilities = CAPABILITIES["forge"]
    sub_agent_class = ForgeSubAgent
    default_mode = "generate"

