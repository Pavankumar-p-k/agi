from __future__ import annotations

import logging
import time
import uuid
from enum import Enum
from typing import Any

from core.execution import ExecutionManager, ExecutionContext
from core.graph.graph import StateGraph
from core.graph.state import AgentState
from core.pipeline.messages import Request, Response
from core.pipeline.pipeline import Pipeline, get_pipeline, process_message
from core.runtime.context import RuntimeContext
from core.runtime.registry import RuntimeRegistry, get_registry

logger = logging.getLogger(__name__)


class RuntimeState(Enum):
    CREATED = "created"
    INITIALIZING = "initializing"
    AUTHENTICATING = "authenticating"
    ROUTING = "routing"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeManager:
    """Single runtime manager for all request processing.

    Consolidates ``Pipeline``, ``StateGraph``, and ``ExecutionManager``
    into one lifecycle with one state machine.

    Lifecycle:
        Created → Initializing → Authenticating → Routing →
        Executing → Completed | Failed | Cancelled
    """

    def __init__(
        self,
        pipeline: Pipeline | None = None,
        graph: StateGraph | None = None,
        execution_manager: ExecutionManager | None = None,
        registry: RuntimeRegistry | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._graph = graph
        self._execution_manager = execution_manager or ExecutionManager()
        self._registry = registry or get_registry()
        self._state = RuntimeState.CREATED
        self._run_id: str = ""

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def run_id(self) -> str:
        return self._run_id

    # ── Lifecycle mutations ─────────────────────────────────────────

    def _transition(self, new_state: RuntimeState, exec_ctx: ExecutionContext) -> None:
        old = self._state
        self._state = new_state
        self._execution_manager.publish_progress(
            exec_ctx, f"state:{old.value}->{new_state.value}",
        )
        logger.debug("[Runtime] %s → %s (run=%s)", old.value, new_state.value, self._run_id)

    # ── Single entry point ───────────────────────────────────────────

    async def process(
        self,
        request: Request,
        *,
        graph: StateGraph | None = None,
        run_id: str | None = None,
    ) -> Response:
        """Process a request through the consolidated runtime.

        Steps:
        1. Initialize runtime context and execution context
        2. Route through Pipeline stages (auth, rate-limit, capability)
        3. Execute via StateGraph or ExecutionManager
        4. Return standardized Response
        """
        self._run_id = run_id or uuid.uuid4().hex
        exec_ctx = ExecutionManager.create_context(
            source="runtime_manager",
            request_id=self._run_id,
        )
        exec_ctx.workflow_id = self._run_id

        self._transition(RuntimeState.INITIALIZING, exec_ctx)

        try:
            # Step 1: Route through Pipeline stages
            self._transition(RuntimeState.AUTHENTICATING, exec_ctx)
            pipeline = self._get_pipeline()
            response = await process_message(request)

            if response.error:
                self._transition(RuntimeState.FAILED, exec_ctx)
                self._execution_manager.publish_failed(exec_ctx, response.error)
                return response

            # Step 2: Execute via graph or direct
            self._transition(RuntimeState.ROUTING, exec_ctx)
            use_graph = graph is not None
            if use_graph:
                exec_result = await self._execute_graph(graph, exec_ctx, request)
            else:
                exec_result = await self._execute_direct(exec_ctx, response)

            # Step 3: Complete
            self._transition(RuntimeState.COMPLETED, exec_ctx)
            self._execution_manager.publish_completed(exec_ctx, exec_result)
            self._execution_manager.record_decision(
                exec_ctx, "runtime_complete", str(response), True,
            )

            return response

        except Exception as exc:
            logger.exception("[Runtime] process failed (run=%s)", self._run_id)
            self._transition(RuntimeState.FAILED, exec_ctx)
            self._execution_manager.publish_failed(exec_ctx, str(exc))
            return Response(
                request_id=self._run_id,
                error=str(exc),
            )

    async def _execute_graph(
        self,
        graph: StateGraph | None,
        exec_ctx: ExecutionContext,
        request: Request,
    ) -> dict[str, Any]:
        g = graph or self._get_graph()
        g.execution_manager = self._execution_manager
        state = AgentState(
            run_id=self._run_id,
            messages=[{"role": "user", "content": request.text}],
            owner=request.user_id or "",
            session_id=request.session_id or "",
        )
        self._transition(RuntimeState.EXECUTING, exec_ctx)
        events: list[str] = []
        async for event in g.execute(state):
            events.append(event)
        self._execution_manager.record_trace(
            exec_ctx, "graph_execute", f"executed {len(events)} events", True,
        )
        return {"events": events, "state": state.to_dict() if hasattr(state, "to_dict") else str(state)}

    async def _execute_direct(
        self,
        exec_ctx: ExecutionContext,
        response: Response,
    ) -> dict[str, Any]:
        self._transition(RuntimeState.EXECUTING, exec_ctx)
        self._execution_manager.record_trace(
            exec_ctx, "direct_execute", "completed through pipeline", True,
        )
        return {"response": response.text if hasattr(response, "text") else str(response)}

    def _get_pipeline(self) -> Pipeline:
        if self._pipeline is not None:
            return self._pipeline
        return get_pipeline()

    def _get_graph(self) -> StateGraph:
        if self._graph is not None:
            return self._graph
        from core.graph import build_default_graph
        return build_default_graph()
