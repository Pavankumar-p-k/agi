"""
backend/autonomy/__init__.py
Initialization bridge for 4-layer autonomous system.
Wraps autonomous initialization and exposes router for inclusion in core/main.py
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Singleton instances - initialized at boot
_brain_layer: Optional[object] = None
_assistant_layer: Optional[object] = None
_executor_layer: Optional[object] = None
_controller_layer: Optional[object] = None
_orchestrator: Optional[object] = None
_proactive_worker: Optional[object] = None

def is_initialized() -> bool:
    """Check if autonomous layers are initialized"""
    return _orchestrator is not None

def get_brain_layer():
    """Get the Brain layer (L1)"""
    return _brain_layer

def get_assistant_layer():
    """Get the Assistant layer (L2)"""
    return _assistant_layer

def get_executor_layer():
    """Get the Executor layer (L3)"""
    return _executor_layer

def get_controller_layer():
    """Get the Controller layer (L4)"""
    return _controller_layer

def get_orchestrator():
    """Get the Autonomous Orchestrator"""
    return _orchestrator

def get_proactive_worker():
    """Get the Proactive Worker"""
    return _proactive_worker

async def initialize_autonomous_stack():
    """
    Initialize all 4 layers of autonomous intelligence.
    Called from core/main.py lifespan context during startup.
    
    This function gracefully handles missing dependencies and will log
    errors rather than crashing the main system if any layer fails.
    """
    global _brain_layer, _assistant_layer, _executor_layer, _controller_layer, _orchestrator, _proactive_worker
    
    logger.info("[AUTONOMY] Initializing 4-layer autonomous stack...")
    
    try:
        # Try to get existing core modules
        try:
            from core.world_state import world_state
        except:
            world_state = None
            
        try:
            from jarvis_os.memory.memory_manager import MemoryManager
            semantic_store = MemoryManager(None) # Or appropriate init
        except:
            semantic_store = None
            
        try:
            from core.fusion_engine import fusion_engine
        except:
            fusion_engine = None
            
        try:
            from core.personality_layer import pf as personality_filter
        except:
            personality_filter = None
            
        try:
            from core.decision_engine import decision_engine
        except:
            decision_engine = None
            
        try:
            from core.notification_hub import notification_hub
        except:
            notification_hub = None
        
        # L1 — Brain Layer
        try:
            logger.info("[AUTONOMY] L1 Brain Layer...")
            from autonomy.l1_brain.brain_layer import BrainLayer
            from orchestrator.brain import get_brain

            brain = get_brain()

            _brain_layer = BrainLayer(
                brain=brain,
                fusion_engine=fusion_engine,
                semantic_store=semantic_store,
                world_state=world_state,
                personality=personality_filter
            )
            logger.info("[AUTONOMY] [OK] L1 Brain Layer online")
        except Exception as e:
            logger.error(f"[AUTONOMY] L1 Brain Layer failed: {e}")
            _brain_layer = None

        # L2 — Assistant Layer  
        try:
            logger.info("[AUTONOMY] L2 Assistant Layer...")
            from autonomy.l2_assistant.assistant_layer import AssistantLayer

            pool = None
            try:
                pool = brain.pool
            except Exception:
                pool = None

            project_root = Path(__file__).resolve().parents[2]
            _assistant_layer = AssistantLayer(
                pool=pool,
                project_root=str(project_root),
            )
            # Async scan in background (scan is blocking, run in thread)
            asyncio.create_task(asyncio.to_thread(_assistant_layer.scan, str(project_root)))
            logger.info("[AUTONOMY] [OK] L2 Assistant Layer online (scanning project...)")
        except Exception as e:
            logger.error(f"[AUTONOMY] L2 Assistant Layer failed: {e}")
            _assistant_layer = None
        
        # L3 — Executor Layer
        try:
            logger.info("[AUTONOMY] L3 Executor Layer...")
            from autonomy.l3_executor.executor_layer import ExecutorLayer
            
            try:
                from tool_registry import ToolRegistry
                tool_registry = ToolRegistry()
            except:
                tool_registry = None
            
            _executor_layer = ExecutorLayer()
            logger.info("[AUTONOMY] [OK] L3 Executor Layer online")
        except Exception as e:
            logger.error(f"[AUTONOMY] L3 Executor Layer failed: {e}")
            _executor_layer = None
        
        # L4 — Controller Layer
        try:
            logger.info("[AUTONOMY] L4 Controller Layer...")
            from autonomy.l4_controller.controller_layer import ControllerLayer
            
            try:
                from automation.pc_automation import PCAutomation
                pc = PCAutomation()
            except:
                pc = None
                
            try:
                from automation.adb_controller import ADBController
                adb = ADBController()
            except:
                adb = None
            
            # ControllerLayer expects workspace path and optional adb controller
            _controller_layer = ControllerLayer(
                adb=adb,
                workspace=str(project_root),
                strict=True,
            )
            logger.info("[AUTONOMY] [OK] L4 Controller Layer online")
        except Exception as e:
            logger.error(f"[AUTONOMY] L4 Controller Layer failed: {e}")
            _controller_layer = None
        
        # Orchestrator — wires all 4
        try:
            logger.info("[AUTONOMY] Wiring Orchestrator...")
            from autonomy.core.autonomous_orchestrator import AutonomousOrchestrator
            
            if all([_brain_layer, _assistant_layer, _executor_layer, _controller_layer]):
                _orchestrator = AutonomousOrchestrator(
                    _brain_layer,
                    _assistant_layer,
                    _executor_layer,
                    _controller_layer,
                    world_state,
                    personality_filter,
                    fusion_engine,
                    semantic_store,
                    notification_hub,
                )
                logger.info("[AUTONOMY] [OK] Orchestrator wired, 4 layers integrated")
            else:
                logger.warning("[AUTONOMY] Not all 4 layers initialized, skipping orchestrator")
                _orchestrator = None
        except Exception as e:
            logger.error(f"[AUTONOMY] Orchestrator wiring failed: {e}")
            _orchestrator = None
        
        # Proactive Worker — monitors and acts autonomously
        try:
            if _orchestrator and world_state is not None:
                logger.info("[AUTONOMY] Starting Proactive Worker...")
                from autonomy.core.proactive_worker import ProactiveWorker
                
                _proactive_worker = ProactiveWorker(
                    world_state=world_state,
                    executor=_executor_layer,
                    hub=notification_hub,
                    semantic_store=semantic_store,
                    personality=personality_filter,
                )
                asyncio.create_task(_proactive_worker.run())
                logger.info("[AUTONOMY] [OK] Proactive Worker running (background, 30s checks)")
        except Exception as e:
            logger.error(f"[AUTONOMY] Proactive Worker failed: {e}")
            _proactive_worker = None
        
        if is_initialized():
            # Inject references into the API router so endpoints can use them
            try:
                from autonomy.api.autonomous_routes import inject_autonomous
                inject_autonomous(
                    orchestrator=_orchestrator,
                    brain=_brain_layer,
                    assistant=_assistant_layer,
                    executor=_executor_layer,
                    controller=_controller_layer,
                    store=semantic_store,
                    proactive=_proactive_worker,
                )
                logger.info("[AUTONOMY] Routed dependencies injected into API")
            except Exception as e:
                logger.warning(f"[AUTONOMY] Failed to inject API dependencies: {e}")

            logger.info("[AUTONOMY] All layers ONLINE [OK]")
            return True
        else:
            logger.warning("[AUTONOMY] Initialization incomplete, some layers missing")
            return False
        
    except Exception as e:
        logger.error(f"[AUTONOMY] Critical initialization failure: {e}", exc_info=True)
        return False

def get_router():
    """Returns the autonomous API router for inclusion in FastAPI app."""
    from fastapi import APIRouter

    # Always return the router so endpoints exist even if layers are not ready yet.
    # Endpoints themselves will raise 503 if the stack isn't initialized.
    try:
        from autonomy.api.autonomous_routes import router
        return router
    except ImportError as e:
        logger.error(f"[AUTONOMY] Could not import autonomous routes: {e}")
        return APIRouter()

__all__ = [
    "is_initialized",
    "initialize_autonomous_stack",
    "get_router",
    "get_brain_layer",
    "get_assistant_layer",
    "get_executor_layer",
    "get_controller_layer",
    "get_orchestrator",
    "get_proactive_worker",
]
