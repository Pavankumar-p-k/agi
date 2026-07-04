from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES
from core.agents._legacy.scribe import ScribeAgent as ScribeSubAgent


class ScribeAdapter(SubAgentAdapter):
    agent_id = "scribe"
    capabilities = CAPABILITIES["scribe"]
    sub_agent_class = ScribeSubAgent
    default_mode = "docs"

