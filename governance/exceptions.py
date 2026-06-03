class GovernanceViolation(Exception):
    """Raised when a governance policy is violated."""
    def __init__(self, policy: str, reason: str = "Unspecified violation", severity: str = "warning"):
        self.policy = policy
        self.reason = reason
        self.severity = severity
        super().__init__(f"[{severity.upper()}] {policy}: {reason}")

class SecurityViolation(Exception):
    """Raised when a security boundary is crossed or bypassed."""

class RuntimeBoundaryViolation(Exception):
    """Raised when runtime enters an unsafe or undefined operating boundary."""
