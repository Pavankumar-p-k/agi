from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES
from core.agents._legacy.oracle import OracleAgent as OracleSubAgent


class OracleAdapter(SubAgentAdapter):
    agent_id = "oracle"
    capabilities = CAPABILITIES["oracle"]
    sub_agent_class = OracleSubAgent
    default_mode = "plan"

