"""Distribution layer: worker registry, transport, runtime, pools, graphs."""
from __future__ import annotations

from core.distribution.contracts import (
    CapabilityDescriptor,
    ExecutionAffinity,
    HealthStatus,
    VersionCheck,
    WorkerRequest,
    WorkerResponse,
    WorkerStatus,
)
from core.distribution.graph import (
    DependencyAwareScheduler,
    DistributedGraph,
    GraphCheckpointer,
    GraphEdge,
    GraphExecutor,
    GraphNode,
    GraphRecovery,
    GraphState,
    NodeStatus,
)
from core.distribution.health import HealthChecker
from core.distribution.local_worker import LocalWorker
from core.distribution.pool import WorkerPool
from core.distribution.registry import (
    InMemoryWorkerRegistry,
    WorkerRegistration,
    WorkerRegistry,
    get_worker_registry,
    set_worker_registry,
)
from core.distribution.retry import RetryPolicy
from core.distribution.runtime import RemoteExecutionRuntime
from core.distribution.scheduler import DistributionScheduler
from core.distribution.transport import InProcessTransport, Transport
from core.distribution.worker import WorkerControl, WorkerEndpoint

__all__ = [
    # contracts
    "CapabilityDescriptor", "ExecutionAffinity", "HealthStatus", "VersionCheck",
    "WorkerRequest", "WorkerResponse", "WorkerStatus",
    # registry
    "InMemoryWorkerRegistry", "WorkerRegistration", "WorkerRegistry",
    "get_worker_registry", "set_worker_registry",
    # transport / runtime
    "Transport", "InProcessTransport", "RemoteExecutionRuntime",
    "DistributionScheduler", "LocalWorker", "WorkerEndpoint", "WorkerControl",
    # operations
    "WorkerPool", "HealthChecker", "RetryPolicy",
    # graph
    "DependencyAwareScheduler", "DistributedGraph", "GraphCheckpointer",
    "GraphEdge", "GraphExecutor", "GraphNode", "GraphRecovery", "GraphState",
    "NodeStatus",
]
