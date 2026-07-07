from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.identity.models import IdentityContext


@dataclass
class Request:
    """Transport-agnostic request passed into ``process_message()``.

    This is the public input type that transport adapters construct and pass
    to ``process_message()``.  It is deliberately minimal — the pipeline
    enriches it into a full ``PipelineContext`` internally.
    """

    text: str
    """The user's input text."""

    transport: str
    """Name of the originating transport
    (``"rest"``, ``"websocket"``, ``"telegram"``, ``"cli"``, ``"voice"``, …)."""

    user_id: str | None = None
    session_id: str | None = None
    identity: IdentityContext | None = None

    attachments: list[dict[str, Any]] = field(default_factory=list)
    """Optional file attachments (e.g. ``[{"name": "photo.jpg", "data": …}]``)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Arbitrary transport-specific metadata that stages may access."""


@dataclass
class Response:
    """Transport-agnostic response returned by ``process_message()``.

    Transport adapters read this and convert it to the wire format.
    """

    text: str
    """The canonical response text."""

    error: str | None = None
    """Error message if the pipeline failed."""

    data: dict[str, Any] | None = None
    """Optional structured data payload."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Response metadata (e.g. token count, duration, traces)."""
