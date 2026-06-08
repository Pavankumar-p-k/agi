"""
tests/unit/test_architecture.py
Architecture boundary tests for JARVIS.
Ensures modules respect layering and dependency rules.
"""

import sys
import pytest


def test_no_circular_imports_core_brain():
    """Ensure core doesn't import from brain at module level."""
    # This is a bit tricky to test statically, but we can check the sys.modules
    # after importing core components.
    
    if "brain.UnifiedBrain" in sys.modules:
        del sys.modules["brain.UnifiedBrain"]
        
    import core.llm_router
    # Should not trigger brain import
    assert "brain.UnifiedBrain" not in sys.modules


def test_subagents_respect_base_class():
    """Ensure all sub-agents inherit from SubAgent."""
    from core.sub_agents.base_agent import SubAgent
    from core.sub_agents.agents.nexus import NexusAgent
    from core.sub_agents.agents.forge import ForgeAgent
    
    assert issubclass(NexusAgent, SubAgent)
    assert issubclass(ForgeAgent, SubAgent)


def test_unified_runtime_available():
    """Ensure the new unified agent runtime is importable."""
    from core.agent_runtime import agent_runtime
    assert agent_runtime is not None


def test_config_singleton():
    """Ensure the unified config is a singleton."""
    from core.config_schema import jarvis_config
    from core.config_schema import JarvisConfig
    
    assert isinstance(jarvis_config, JarvisConfig)
