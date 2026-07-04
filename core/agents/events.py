"""Agent-level event types for the multi-agent graph.

Preserves the WorkflowEvent pattern from core/workflow/events.py
while adding agent-specific semantics.
"""

from core.event_bus import WorkflowEvent

AGENT_STARTED = "agent_started"
AGENT_COMPLETED = "agent_completed"
AGENT_FAILED = "agent_failed"
AGENT_HANDOFF = "agent_handoff"
NODE_STARTED = "node_started"
NODE_COMPLETED = "node_completed"
NODE_FAILED = "node_failed"
NODE_WAITING = "node_waiting"
GRAPH_COMPLETED = "graph_completed"


class AgentEvent(WorkflowEvent):
    """An event emitted by an agent during its lifecycle.

    Fields inherited from WorkflowEvent:
      event_id, workflow_id, event_type, data, timestamp
    """

    @classmethod
    def started(cls, workflow_id: str, agent_id: str, goal: str, **extra) -> "AgentEvent":
        return cls(
            event_id=f"{workflow_id}_agent_{agent_id}_start",
            workflow_id=workflow_id,
            event_type=AGENT_STARTED,
            data={"agent_id": agent_id, "goal": goal, **extra},
        )

    @classmethod
    def completed(cls, workflow_id: str, agent_id: str, result: dict, **extra) -> "AgentEvent":
        return cls(
            event_id=f"{workflow_id}_agent_{agent_id}_done",
            workflow_id=workflow_id,
            event_type=AGENT_COMPLETED,
            data={"agent_id": agent_id, "result": result, **extra},
        )

    @classmethod
    def failed(cls, workflow_id: str, agent_id: str, error: str, **extra) -> "AgentEvent":
        return cls(
            event_id=f"{workflow_id}_agent_{agent_id}_fail",
            workflow_id=workflow_id,
            event_type=AGENT_FAILED,
            data={"agent_id": agent_id, "error": error, **extra},
        )

    @classmethod
    def handoff(cls, workflow_id: str, from_agent: str, to_agent: str,
                goal: str, **extra) -> "AgentEvent":
        return cls(
            event_id=f"{workflow_id}_handoff_{from_agent}_to_{to_agent}",
            workflow_id=workflow_id,
            event_type=AGENT_HANDOFF,
            data={"from_agent": from_agent, "to_agent": to_agent, "goal": goal, **extra},
        )

    # ── Graph node events ──────────────────────────────────────────
    @classmethod
    def node_started(cls, workflow_id: str, node_id: str, agent_id: str,
                     goal: str, phase: int, **extra) -> "AgentEvent":
        return cls(
            event_id=f"{workflow_id}_node_{node_id}_start",
            workflow_id=workflow_id,
            event_type=NODE_STARTED,
            data={"node_id": node_id, "agent_id": agent_id, "goal": goal,
                  "phase": phase, **extra},
        )

    @classmethod
    def node_completed(cls, workflow_id: str, node_id: str, agent_id: str,
                       result: dict, **extra) -> "AgentEvent":
        return cls(
            event_id=f"{workflow_id}_node_{node_id}_done",
            workflow_id=workflow_id,
            event_type=NODE_COMPLETED,
            data={"node_id": node_id, "agent_id": agent_id, "result": result, **extra},
        )

    @classmethod
    def node_failed(cls, workflow_id: str, node_id: str, agent_id: str,
                    error: str, **extra) -> "AgentEvent":
        return cls(
            event_id=f"{workflow_id}_node_{node_id}_fail",
            workflow_id=workflow_id,
            event_type=NODE_FAILED,
            data={"node_id": node_id, "agent_id": agent_id, "error": error, **extra},
        )

    @classmethod
    def node_waiting(cls, workflow_id: str, node_id: str, agent_id: str,
                     reason: str, **extra) -> "AgentEvent":
        return cls(
            event_id=f"{workflow_id}_node_{node_id}_wait",
            workflow_id=workflow_id,
            event_type=NODE_WAITING,
            data={"node_id": node_id, "agent_id": agent_id, "reason": reason, **extra},
        )

    @classmethod
    def graph_completed(cls, workflow_id: str, total_nodes: int,
                        failed_nodes: int, **extra) -> "AgentEvent":
        return cls(
            event_id=f"{workflow_id}_graph_done",
            workflow_id=workflow_id,
            event_type=GRAPH_COMPLETED,
            data={"total_nodes": total_nodes, "failed_nodes": failed_nodes, **extra},
        )
