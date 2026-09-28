"""Specialist LLM adapters (SubAgent -> router contract bridge)."""
from core.agents.adapters.atlas_adapter import AtlasAdapter
from core.agents.adapters.base_adapter import ADAPTER_TIMEOUT, SubAgentAdapter
from core.agents.adapters.cipher_adapter import CipherAdapter
from core.agents.adapters.forge_adapter import ForgeAdapter
from core.agents.adapters.herald_adapter import HeraldAdapter
from core.agents.adapters.nexus_adapter import NexusAdapter
from core.agents.adapters.oracle_adapter import OracleAdapter
from core.agents.adapters.phantom_adapter import PhantomAdapter
from core.agents.adapters.scribe_adapter import ScribeAdapter
from core.agents.adapters.sentinel_adapter import SentinelAdapter

__all__ = [
    "AtlasAdapter", "CipherAdapter", "ForgeAdapter", "HeraldAdapter",
    "NexusAdapter", "OracleAdapter", "PhantomAdapter", "ScribeAdapter",
    "SentinelAdapter", "SubAgentAdapter", "ADAPTER_TIMEOUT",
]
