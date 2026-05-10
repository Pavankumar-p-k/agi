from __future__ import annotations


class GovernanceViolation(Exception):
    """Raised when governance policy is violated for sensitive operations."""


class SecurityViolation(Exception):
    """Raised when a security boundary is crossed or bypassed."""


class RuntimeBoundaryViolation(Exception):
    """Raised when runtime enters an unsafe or undefined operating boundary."""

