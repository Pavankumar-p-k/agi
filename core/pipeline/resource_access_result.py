"""Typed result of the ResourceAccessStage.

Only ``ResourceAccessStage`` may construct this dataclass.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.identity.resource_scope import ResourceScope, Visibility


@dataclass(frozen=True)
class ResourceAccessResult:
    """Whether the request's identity may access the requested resource.

    Created once by ResourceAccessStage and never mutated.
    """

    allowed: bool
    """``True`` when the caller is permitted to access the resource."""

    reason: str
    """Human-readable explanation (e.g. ``"owner access granted"``)."""

    resource_scope: ResourceScope
    """The resource scope that was evaluated."""

    requested_action: str
    """The action that was requested (e.g. ``"read"``, ``"write"``)."""

    effective_visibility: Visibility
    """The visibility level that governed this access decision."""
