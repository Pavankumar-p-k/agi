# core/spawning/__init__.py
from .manager import subagent_manager, SubagentManager, SpawnResult
from .store import SubagentStore
from .orphan import orphan_recovery, OrphanRecovery

__all__ = [
    "subagent_manager", 
    "SubagentManager", 
    "SpawnResult", 
    "SubagentStore", 
    "orphan_recovery", 
    "OrphanRecovery"
]
