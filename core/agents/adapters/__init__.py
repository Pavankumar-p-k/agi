"""Adapters — bridge core/sub_agents (SubAgent) into core/agents/ (BaseAgent).

Each adapter wraps a SubAgent as a BaseAgent, making LLM-prompt-based
specialists routable through the AgentRouter and executable in the
ParallelAgentGraph alongside tool-based agents.
"""

from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.adapters.atlas_adapter import AtlasAdapter
from core.agents.adapters.cipher_adapter import CipherAdapter
from core.agents.adapters.forge_adapter import ForgeAdapter
from core.agents.adapters.herald_adapter import HeraldAdapter
from core.agents.adapters.nexus_adapter import NexusAdapter
from core.agents.adapters.oracle_adapter import OracleAdapter
from core.agents.adapters.phantom_adapter import PhantomAdapter
from core.agents.adapters.scribe_adapter import ScribeAdapter
from core.agents.adapters.sentinel_adapter import SentinelAdapter

__all__ = [
    "AtlasAdapter",
    "CipherAdapter",
    "ForgeAdapter",
    "HeraldAdapter",
    "NexusAdapter",
    "OracleAdapter",
    "PhantomAdapter",
    "ScribeAdapter",
    "SentinelAdapter",
    "SubAgentAdapter",
]
