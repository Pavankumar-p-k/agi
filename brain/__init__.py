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


class UnifiedBrain:
    """Unified brain facade for conversational, strategic, and autonomous reasoning."""

    def __init__(self):
        if not all(
            [
                WorldStateEngine,
                TemporalMemoryCore,
                CounterfactualSimulator,
                AuthorityStack,
                SelfGovernanceMonitor,
                AdaptiveSelfRepair,
                MetaCognitionEngine,
                ContinuousCognitionLoop,
                JarvisBrainAdapter,
                AIOrchestratorAdapter,
                HybridOrchestratorAdapter,
                CognitiveAgentAdapter,
            ]
        ):
            raise RuntimeError("UnifiedBrain dependencies are not fully available in this build.")
        self.world_state = WorldStateEngine()
        self.memory_core = TemporalMemoryCore()
        self.simulator = CounterfactualSimulator()
        self.archive = AuthorityStack(self.world_state)
        self.monitor = SelfGovernanceMonitor(self.archive.identity, self.archive.validator)
        self.self_repair = AdaptiveSelfRepair(self.monitor, self.world_state, self.memory_core)
        self.metacognition = MetaCognitionEngine(
            self.world_state,
            self.memory_core,
            self.archive.identity,
            self.archive,
            self.monitor,
        )
        self.cognition = ContinuousCognitionLoop(
            self.world_state,
            self.memory_core,
            self.simulator,
            self.archive,
            self.self_repair,
            self.metacognition,
        )
        self.jarvis = JarvisBrainAdapter()
        self.ai_os = AIOrchestratorAdapter()
        self.hybrid = HybridOrchestratorAdapter()
        self.cognitive = CognitiveAgentAdapter()

    async def think(self, context: BrainExecutionContext) -> BrainResult:
        """Conversational thinking through the main Jarvis brain with governance oversight."""
        await self.world_state.update({"user": {"intent": context.goal}}, event="think_intent")
        decision = await self.archive.evaluate(context)
        if not decision.get("allowed", True):
            raise RuntimeError(f"Governance denied conversational action: {decision.get('reason')}")
        result = await self.jarvis.think(context)
        notification = {"success": True, "trust_risk": 0.0, "delegate": "JarvisBrain"}
        self.monitor.observe(decision, notification, context)
        await self.metacognition.audit_decision_chain(decision, context, notification)
        await self.metacognition.audit_subsystem_performance("JarvisBrain", notification, context)
        await self.metacognition.audit_goal_outcomes(context.goal, notification, context)
        return result

    async def execute_goal(
        self,
        goal: str,
        context: Optional[BrainExecutionContext] = None,
        mode: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a strategic goal under executive governance."""
        if context is None:
            context = BrainExecutionContext(goal=goal)
        context.goal = goal

        await self.world_state.update({"tasks": [{"goal": goal, "status": "pending"}]}, event="execute_goal")
        decision = await self.archive.evaluate(context)

        if not decision.get("allowed", True):
            return {"success": False, "reason": decision.get("reason"), "trust_risk": 1.0}

        delegate_to = decision["delegate_to"]
        if mode is None:
            mode = delegate_to.lower().replace("brain", "") if delegate_to else "ai_os"

        if delegate_to == "JarvisBrain":
            result = await self.jarvis.think(context)
            result_dict = {"success": True, "result": result.reply, "delegate": delegate_to}
        elif delegate_to == "AIOrchestrator":
            result = await self.ai_os.execute_goal(goal, context)
            result_dict = {**result, "delegate": delegate_to}
        elif delegate_to == "HybridOrchestrator":
            result = await self.hybrid.execute_goal(goal, context)
            result_dict = {**result, "delegate": delegate_to}
        elif delegate_to == "CognitiveAgent":
            result = await self.cognitive.execute_goal(goal, context)
            result_dict = {**result, "delegate": delegate_to}
        else:
            result_dict = {"success": False, "reason": "No qualified subsystem found.", "delegate": None}

        self.monitor.observe(decision, result_dict, context)
        await self.metacognition.audit_decision_chain(decision, context, result_dict)
        await self.metacognition.audit_subsystem_performance(delegate_to or "unknown", result_dict, context)
        await self.metacognition.audit_goal_outcomes(goal, result_dict, context)
        await self.metacognition.audit_strategy_quality(decision, context)
        if await self.metacognition.detect_trust_drift():
            await self.metacognition.repair_trust_strategy()
        return result_dict

    def status(self) -> Dict[str, Any]:
        return {
            "governance": {
                "authority": "ExecutiveGovernor",
                "identity": self.archive.identity.profile.mission,
                "valid": True,
            },
            "jarvis": self.jarvis.status(),
            "ai_os": self.ai_os.status(),
            "hybrid": self.hybrid.status(),
            "cognitive": self.cognitive.status(),
        }


_unified_brain: Optional[UnifiedBrain] = None


def get_brain() -> UnifiedBrain:
    global _unified_brain
    if _unified_brain is None:
        _unified_brain = UnifiedBrain()
    return _unified_brain
