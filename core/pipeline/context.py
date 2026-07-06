from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """The single mutable context object flowing through the pipeline.

    Every stage reads from and writes to this context.  No stage interacts
    with external systems without going through the context first.

    **Field ownership** (see ``STAGE_OWNERSHIP`` in ``base.py``): each
    context field is owned by exactly one stage.  Non-owner stages may
    *read* a field but must call ``set_stage_field()`` to *write* it;
    violations produce a runtime warning.
    """

    # ── Identity / Routing ──────────────────────────────────────────────────
    request_id: str
    """Unique identifier for this request."""

    transport: str
    """Name of the transport that originated this request
    (e.g. ``"rest"``, ``"websocket"``, ``"telegram"``, ``"cli"``)."""

    user_id: str | None = None
    session_id: str | None = None

    # ── Pipeline metadata ───────────────────────────────────────────────────
    pipeline_version: str = "1.0"
    """Version of the pipeline architecture that processed this request."""

    # ── Raw / Parsed Request ────────────────────────────────────────────────
    raw_input: str = ""
    """Original text from the transport."""

    attachments: list[dict[str, Any]] = field(default_factory=list)
    """File attachments included with the request."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    """Chat history (e.g. ``[{"role": "user", "content": …}]``)."""

    parsed_request: dict[str, Any] | None = None
    """Transport-agnostic structured representation of the request,
    set by the Receive stage."""

    # ── Classification / Planning ───────────────────────────────────────────
    classification: dict[str, Any] | None = None
    """Output of Intent Classification — mode, confidence, sub_type, etc."""

    selected_capabilities: list[str] = field(default_factory=list)
    """Capabilities matched to the classified intent."""

    plan: dict[str, Any] | None = None
    """Executable plan produced by the Planner stage."""

    # ── Execution ───────────────────────────────────────────────────────────
    execution_state: str = "pending"
    """One of ``"pending"``, ``"running"``, ``"completed"``, ``"failed"``,
    ``"short_circuited"``, ``"deferred"``, ``"cancelled"``."""

    error: str | None = None
    """Error message if the pipeline failed or was short-circuited."""

    execution_result: Any = None
    """Raw output from the Execution stage (before verification / formatting)."""

    # ── Verification ────────────────────────────────────────────────────────
    verification_result: dict[str, Any] | None = None
    """Output of the Verification stage (safety, quality, schema checks)."""

    # ── Epistemic Tagging ───────────────────────────────────────────────────
    epistemic_tags: dict[str, float] = field(default_factory=dict)
    """Confidence, provenance, source attribution (set by EpistemicTagging)."""

    # ── Memory ──────────────────────────────────────────────────────────────
    memory_refs: list[str] = field(default_factory=list)
    """References stored in the memory facade during the Memory stage."""

    # ── Activity / Tracing ──────────────────────────────────────────────────
    activity_id: str | None = None
    """ActivityGraph node id for this request (set on pipeline start)."""

    trace_id: str = ""
    """Distributed tracing identifier."""

    span_stack: list[str] = field(default_factory=list)
    """Nested span names for observability within this request."""

    # ── Cancellation ────────────────────────────────────────────────────────
    cancelled: bool = False
    """Set to ``True`` when the pipeline is cancelled externally.
    Stages should check this flag between long-running operations."""

    # ── Response ────────────────────────────────────────────────────────────
    formatted_response: dict[str, Any] | None = None
    """Final response payload (set by the Formatter stage, last in pipeline).
    The transport adapter reads this and sends it to the client."""

    # ── Metrics / Metadata ──────────────────────────────────────────────────
    metrics: dict[str, Any] = field(default_factory=dict)
    """Aggregated metrics for this request (timing, tokens, retries)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extensible bag for arbitrary metadata that stages may need to share."""

    # ── Field ownership (internal) ──────────────────────────────────────────
    _owned_fields_set: set[str] = field(default_factory=set, repr=False)
    """Tracks which owned fields have been set during this request."""

    def set_stage_field(self, stage_name: str, field_name: str, value: Any) -> None:
        """Set a context field on behalf of *stage_name*.

        If *field_name* is listed in ``STAGE_OWNERSHIP`` for a different
        stage, a runtime warning is logged.  Call this instead of setting
        attributes directly when writing to an owned field.
        """
        from core.pipeline.base import STAGE_OWNERSHIP

        expected_owner = _field_owner(field_name)
        if expected_owner and expected_owner != stage_name:
            logger.warning(
                "Stage '%s' wrote to '%s', which is owned by '%s'",
                stage_name, field_name, expected_owner,
            )
        object.__setattr__(self, field_name, value)
        self._owned_fields_set.add(field_name)


def _field_owner(field_name: str) -> str | None:
    """Return the stage that owns *field_name*, or ``None`` if unowned."""
    from core.pipeline.base import STAGE_OWNERSHIP

    for stage, fields in STAGE_OWNERSHIP.items():
        if field_name in fields:
            return stage
    return None
