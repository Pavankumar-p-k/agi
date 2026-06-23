from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES
from core.sub_agents.agents.phantom import PhantomAgent as PhantomSubAgent


class PhantomAdapter(SubAgentAdapter):
    agent_id = "phantom"
    capabilities = CAPABILITIES["phantom"]
    sub_agent_class = PhantomSubAgent
    default_mode = "scrape"
