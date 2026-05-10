"""Bootstrap module for JARVIS OS - Phase 7 Mythos Omega."""

from __future__ import annotations

from pathlib import Path

from .agents.hub import AgentHub
from .agents.runtime import AgentRuntimeManager
from .compat import CompatibilityBridge
from .core.agent import JarvisOS
from .core.critic import CriticEngine
from .core.executor import ExecutionEngine
from .core.intent import IntentEngine
from .core.loop import AgentLoop
from .core.meta_controller import MetaController
from .core.planner import PlanningEngine
from .core.reasoning import ReasoningEngine
from .core.reflection import ReflectionEngine
from .extensions.manager import ExtensionsManager
from .links.manager import LinksManager
from .memory.memory_manager import MemoryManager
from .model_runtime_manager import ModelRuntimeManager
from .models.ollama_router import OllamaRouter
from .models.rest_adapter import RestModelAdapter
from .models.fallback_adapter import FallbackModelAdapter
from .plugins.loader import PluginManager
from .provider_health_registry import ProviderHealthRegistry
from .ProviderDecisionMatrix import ProviderDecisionMatrix
from .ProviderStrategicMemory import ProviderStrategicMemory
from .ProviderTrustRegistry import ProviderTrustRegistry
from .RuntimeGovernanceLayer import RuntimeGovernanceLayer
from .runtime.config import JarvisConfig
from .runtime.daemon import DaemonService
from .runtime.jobs import JobManager
from .runtime.logger import configure_logging, get_logger
from .runtime.monitor import RuntimeMonitor
from .runtime.policy import PolicyEngine
from .runtime.scheduler import SchedulerService
from .runtime.telemetry import TelemetryStore
from .self_improve.loop import SelfImprovementLoop
from .skills.registry import SkillRegistry
from .tools import create_tool_registry

# Phase 7 imports
from .core.sovereign_router import SovereignRouter, TaskClassification, RoutingPlan
from .core.stage_pruner import StagePruner
from .economics.cost_model import CostModel
from .economics.latency_model import LatencyModel


def build_jarvis_os(config: JarvisConfig | None = None) -> JarvisOS:
    """Build and return a fully wired JARVIS OS instance."""
    runtime_config = config or JarvisConfig.from_env()
    configure_logging(runtime_config.log_level, runtime_config.log_file)

    # === Core components (defined FIRST) ===
    memory = MemoryManager(runtime_config)
    ollama_provider = OllamaRouter(runtime_config)
    providers = {"ollama": ollama_provider}
    if runtime_config.allow_network and runtime_config.model_api_base_url:
        providers["rest"] = RestModelAdapter(runtime_config)
    providers["fallback"] = FallbackModelAdapter(runtime_config)

    health_registry = ProviderHealthRegistry(providers)
    trust_registry = ProviderTrustRegistry(providers)
    strategic_memory = ProviderStrategicMemory(runtime_config)
    decision_matrix = ProviderDecisionMatrix(runtime_config, trust_registry, strategic_memory)
    governance_layer = RuntimeGovernanceLayer(
        trust_registry,
        health_registry,
        decision_matrix,
        strategic_memory,
        runtime_config,
    )

    runtime_manager = ModelRuntimeManager(
        providers=providers,
        default_provider=runtime_config.model_provider,
        health_registry=health_registry,
        trust_registry=trust_registry,
        strategic_memory=strategic_memory,
        decision_matrix=decision_matrix,
        governance_layer=governance_layer,
        config=runtime_config,
    )

    active_provider = runtime_manager.active_provider
    if active_provider.name != runtime_config.model_provider:
        logger = get_logger("jarvis_os.bootstrap")
        logger.warning(
            "Requested model provider '%s' not governance-selected; using '%s' instead.",
            runtime_config.model_provider,
            active_provider.name,
        )

    model_manager = runtime_manager
    registry = create_tool_registry(runtime_config, memory, model_manager)
    compat_root = runtime_config.legacy_backend_root or str((runtime_config.workspace_root).resolve())
    compat = CompatibilityBridge(Path(compat_root))
    compat.register_tools(registry)
    agent_runtime = AgentRuntimeManager(runtime_config)
    plugins = PluginManager(runtime_config)
    plugins.discover()
    plugins.register(registry, model_manager)
    skills = SkillRegistry(runtime_config.data_dir)
    policy = PolicyEngine(strict_mode=runtime_config.strict_policy, workspace_root=runtime_config.workspace_root)
    telemetry = TelemetryStore(runtime_config.data_dir)
    scheduler = SchedulerService(runtime_config.data_dir)
    daemon = DaemonService(runtime_config.data_dir, interval_s=runtime_config.daemon_interval_s)

    # Create core AI components
    intent_engine = IntentEngine(registry)
    reasoning = ReasoningEngine(model_manager, registry, memory)
    planner = PlanningEngine(registry, model_manager, skill_registry=skills)
    executor = ExecutionEngine(registry, memory, policy=policy, telemetry=telemetry)
    critic = CriticEngine(model_manager)
    meta_controller = MetaController()
    reflection = ReflectionEngine(memory)

    agents = AgentHub(reasoning, planner, runtime_manager=agent_runtime)
    self_improve = SelfImprovementLoop(memory, skill_registry=skills)
    jobs = JobManager(runtime_config.data_dir)
    monitor = RuntimeMonitor(
        config=runtime_config,
        jobs=jobs,
        agent_runtime=agent_runtime,
        scheduler=scheduler,
        daemon=daemon,
        telemetry=telemetry,
        models=model_manager,
    )

    # === Phase 7 components (defined SECOND) ===
    sovereign_router = SovereignRouter()
    stage_pruner = StagePruner()
    cost_model = CostModel(runtime_config)
    latency_model = LatencyModel(runtime_config)

    # Grounding (if available)
    try:
        from .tools.multi_source_grounding import MultiSourceGrounding
        grounding = MultiSourceGrounding()
    except ImportError:
        grounding = None
        logger = get_logger("jarvis_os.bootstrap")
        logger.warning("MultiSourceGrounding not available")

    # Adversarial Verifier (if available)
    try:
        from .verification.adversarial_verifier import AdversarialVerifier
        adversarial_verifier = AdversarialVerifier(model_manager)
    except ImportError:
        adversarial_verifier = None
        logger = get_logger("jarvis_os.bootstrap")
        logger.warning("AdversarialVerifier not available")

    # Confidence Calibrator (if available)
    try:
        from .trust.confidence_calibrator import ConfidenceCalibrator
        calibrator = ConfidenceCalibrator(runtime_config)
    except ImportError:
        calibrator = None
        logger = get_logger("jarvis_os.bootstrap")
        logger.warning("ConfidenceCalibrator not available")

    # Create AgentLoop with NEW Phase 7 parameters
    loop = AgentLoop(
        sovereign_router=sovereign_router,
        cost_model=cost_model,
        latency_model=latency_model,
        stage_pruner=stage_pruner,
        adversarial_verifier=adversarial_verifier,
        calibrator=calibrator,
        grounding=grounding,
        executor=None,  # Will be set later
        config=runtime_config,
    )

    # Create extensions and links managers
    extensions_manager = ExtensionsManager(str(runtime_config.data_dir))
    links_manager = LinksManager(str(runtime_config.data_dir))

    # === Create JarvisOS LAST (after all components are defined) ===
    return JarvisOS(
        config=runtime_config,
        memory=memory,
        models=model_manager,
        tools=registry,
        intent_engine=intent_engine,
        reasoning=reasoning,
        planner=planner,
        executor=executor,
        reflection=reflection,
        loop=loop,
        agents=agents,
        agent_runtime=agent_runtime,
        plugins=plugins,
        self_improve=self_improve,
        jobs=jobs,
        compat=compat,
        skills=skills,
        policy=policy,
        telemetry=telemetry,
        scheduler=scheduler,
        daemon=daemon,
        monitor=monitor,
        extensions_manager=extensions_manager,
        links_manager=links_manager,
    )
