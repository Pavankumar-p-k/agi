"""Canonical runtime scopes for the pipeline authorization layer.

These are the only scopes that AuthorizationStage evaluates.
Scopes follow a ``resource.action`` naming convention.

Sprint 3 covers pipeline-level scopes only.  Tenant scopes
(``tenant:workspace:read``) belong in Sprint 4.
"""

CANONICAL_SCOPES = frozenset({
    "chat.execute",
    "memory.read",
    "memory.write",
    "scheduler.enqueue",
    "scheduler.execute",
    "capability.use",
    "provider.invoke",
    "admin.runtime",
})
"""Every valid scope an AuthorizationStage may evaluate."""
