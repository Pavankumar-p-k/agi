import asyncio
import logging
from typing import Any, Optional, Dict
from importlib import import_module

def _optional_import(module_path: str, symbol: str):
    try:
        module = import_module(module_path, package=__name__)
        return getattr(module, symbol)
    except Exception:
        return None


AIOrchestratorAdapter = _optional_import(".adapters", "AIOrchestratorAdapter")
CognitiveAgentAdapter = _optional_import(".adapters", "CognitiveAgentAdapter")
HybridOrchestratorAdapter = _optional_import(".adapters", "HybridOrchestratorAdapter")
JarvisBrainAdapter = _optional_import(".adapters", "JarvisBrainAdapter")
AuthorityStack = _optional_import(".AuthorityStack", "AuthorityStack")
AdaptiveSelfRepair = _optional_import(".AdaptiveSelfRepair", "AdaptiveSelfRepair") or _optional_import(".AdaptiveSelfRepair", "AutonomousSelfRepairV3")
ContinuousCognitionLoop = _optional_import(".ContinuousCognitionLoop", "ContinuousCognitionLoop") or _optional_import(".ContinuousCognitionLoop", "ContinuousCognitionLoopV3")
CounterfactualSimulator = _optional_import(".CounterfactualSimulator", "CounterfactualSimulator")
MetaCognitionEngine = _optional_import(".MetaCognitionEngine", "MetaCognitionEngine") or _optional_import(".MetaCognitionEngine", "ExecutiveMetaCognitionV3")
SelfGovernanceMonitor = _optional_import(".SelfGovernanceMonitor", "SelfGovernanceMonitor")
TemporalMemoryCore = _optional_import(".TemporalMemoryCore", "TemporalMemoryCore")
WorldStateEngine = _optional_import(".WorldStateEngine", "WorldStateEngine")
BrainExecutionContext = _optional_import(".execution_context", "BrainExecutionContext")
BrainResult = _optional_import("orchestrator.brain", "BrainResult")

logger = logging.getLogger(__name__)
