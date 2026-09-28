"""Legacy SubAgent backends (pre-adapter API kept for compatibility)."""
from core.agents._legacy.atlas import AtlasAgent
from core.agents._legacy.cipher import CipherAgent
from core.agents._legacy.forge import ForgeAgent
from core.agents._legacy.herald import HeraldAgent
from core.agents._legacy.nexus import NexusAgent
from core.agents._legacy.oracle import OracleAgent
from core.agents._legacy.phantom import PhantomAgent
from core.agents._legacy.scribe import ScribeAgent
from core.agents._legacy.sentinel import SentinelAgent

__all__ = [
    "AtlasAgent", "CipherAgent", "ForgeAgent", "HeraldAgent", "NexusAgent",
    "OracleAgent", "PhantomAgent", "ScribeAgent", "SentinelAgent",
]
