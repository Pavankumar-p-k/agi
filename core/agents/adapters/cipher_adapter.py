from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES
from core.agents._legacy.cipher import CipherAgent as CipherSubAgent


class CipherAdapter(SubAgentAdapter):
    agent_id = "cipher"
    capabilities = CAPABILITIES["cipher"]
    sub_agent_class = CipherSubAgent
    default_mode = "audit"

