"""
Module: core.agents.adapters.__init__
Auto-reconstructed backend component.
.. deprecated:: 2026-01
   This module is retained for compatibility. It will be removed once all
   importers have migrated to the canonical active path.

   Canonical active path:
   - core.agents.graph
   - core.agents.executor
   - core.planner
   - core.pipeline.pipeline

   Do not import from this module in new code. Existing importers should
   migrate away as part of routine archive/deprecation cycles.

"""
from __future__ import annotations
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

class DynamicMeta(type):
    def __getattr__(cls, name: str) -> Any:
        return name

# Re-exports
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


def __getattr__(name: str) -> Any:
    class DynamicStub(metaclass=DynamicMeta):
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, *args, **kwargs):
            return self
        def __getattr__(self, item):
            return DynamicStub()
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
    return DynamicStub()
