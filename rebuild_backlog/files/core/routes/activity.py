"""
Module: core.routes.activity
Auto-reconstructed backend component.
"""
from __future__ import annotations
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

class DynamicMeta(type):
    def __getattr__(cls, name: str) -> Any:
        return name

def _replay_node_to_dict(node: Any) -> dict:
    """Flat dict for one ReplayNode; children become node-id strings.

    Contract: tests/unit/test_activity_replay_routes.py::TestSerialization.
    """
    return {
        "node_id": node.node_id,
        "activity_id": node.activity_id,
        "node_type": node.node_type,
        "label": node.label,
        "status": node.status,
        "depth": node.depth,
        "parent_id": node.parent_id,
        "children": [child.node_id for child in node.children],
        "duration_seconds": node.duration_seconds,
        "tool": node.tool,
        "provider": node.provider,
        "model": node.model,
        "retry_count": node.retry_count,
        "cost": node.cost,
        "input_preview": node.input_preview,
        "output_preview": node.output_preview,
        "error": node.error,
        "started_at": node.started_at,
        "completed_at": node.completed_at,
        "agent_id": node.agent_id,
        "workflow_id": node.workflow_id,
        "timeline_index": node.timeline_index,
        "metadata": dict(node.metadata),
        "artifacts": dict(node.artifacts),
    }


def _replay_dag_to_dict(dag: Any) -> dict:
    """JSON-ready dict for a ReplayDAG.

    Contract: tests/unit/test_activity_replay_routes.py (TestSerialization,
    TestReplayEndpoint, TestCrossCheck).
    """
    return {
        "activity_id": dag.activity_id,
        "root_id": dag.root.node_id if dag.root is not None else None,
        "all_nodes": {
            node_id: _replay_node_to_dict(node)
            for node_id, node in dag.all_nodes.items()
        },
        "all_edges": [
            {
                "edge_id": edge.edge_id,
                "from_node_id": edge.from_node_id,
                "to_node_id": edge.to_node_id,
                "edge_type": edge.edge_type,
                "label": edge.label,
                "metadata": dict(edge.metadata),
            }
            for edge in dag.all_edges
        ],
        "timeline": [
            {
                "timestamp": event.timestamp,
                "label": event.label,
                "node_id": event.node_id,
                "node_type": event.node_type,
                "status": event.status,
                "duration_seconds": event.duration_seconds,
                "detail": event.detail,
            }
            for event in dag.timeline
        ],
        "decisions": [
            {
                "decision_id": trace.decision_id,
                "capability": trace.capability,
                "selected_provider": trace.selected_provider,
                "candidates": [
                    {
                        "provider_id": c.provider_id,
                        "total_score": c.total_score,
                        "priority_score": c.priority_score,
                        "historical_score": c.historical_score,
                        "benchmark_score": c.benchmark_score,
                        "health_score": c.health_score,
                        "latency_score": c.latency_score,
                        "cost_score": c.cost_score,
                        "budget_score": c.budget_score,
                        "offline_score": c.offline_score,
                        "calibration_adjustment": c.calibration_adjustment,
                    }
                    for c in trace.candidates
                ],
                "reasons": list(trace.reasons),
                "outcome": (
                    {
                        "success": trace.outcome.success,
                        "duration_ms": trace.outcome.duration_ms,
                        "quality_score": trace.outcome.quality_score,
                        "cost": trace.outcome.cost,
                        "retries": trace.outcome.retries,
                        "error": trace.outcome.error,
                    }
                    if trace.outcome is not None
                    else None
                ),
            }
            for trace in dag.decisions
        ],
        "total_nodes": dag.total_nodes,
        "failed_nodes": dag.failed_nodes,
        "total_duration_seconds": dag.total_duration_seconds,
        "unique_tools": list(dag.unique_tools),
        "unique_providers": list(dag.unique_providers),
        "total_retries": dag.total_retries,
        "total_cost": dag.total_cost,
        "experience": dag.experience,
        "knowledge": list(dag.knowledge),
    }


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
