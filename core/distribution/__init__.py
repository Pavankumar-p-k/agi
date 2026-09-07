"""
Module: core.distribution.__init__
Auto-reconstructed backend component.
"""
# Re-exports
from core.distribution.contracts import CapabilityDescriptor, ExecutionAffinity, HealthStatus, VersionCheck, WorkerRequest, WorkerResponse, WorkerStatus
from core.distribution.graph import DependencyAwareScheduler, DistributedGraph, GraphCheckpointer, GraphEdge, GraphExecutor, GraphNode, GraphRecovery, GraphState, NodeStatus
from core.distribution.registry import InMemoryWorkerRegistry, WorkerRegistration, WorkerRegistry, get_worker_registry, set_worker_registry
from core.distribution.worker import WorkerControl, WorkerEndpoint
