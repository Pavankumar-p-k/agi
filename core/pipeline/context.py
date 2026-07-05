from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineContext:
    """The single mutable context object flowing through the pipeline.

    Every stage reads from and writes to this context.  No stage interacts
    with external systems without going through the context first.
    """

    # ── Identity / Routing ──────────────────────────────────────────────────
    request_id: str
    """Unique identifier for this request."""

    transport: str
    """Name of the transport that originated this request
    (e.g. ``"rest"``, ``"websocket"``, ``"telegram"``, ``"cli"``)."""

    user_id: str | None = None
    session_id: str | None = None

    # ── Raw / Parsed Request ────────────────────────────────────────────────
    raw_input: str = ""
    """Original text or serialised payload from the transport."""

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
    """One of ``"pending"``, ``"running"``, ``"completed"``, ``"failed"``."""

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

    # ── Response ────────────────────────────────────────────────────────────
    formatted_response: dict[str, Any] | None = None
    """Final response payload (set by the Formatter stage, last in pipeline).
    The transport adapter reads this and sends it to the client."""

    # ── Metrics / Metadata ──────────────────────────────────────────────────
    metrics: dict[str, Any] = field(default_factory=dict)
    """Aggregated metrics for this request (timing, tokens, retries)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extensible bag for arbitrary metadata that stages may need to share."""
