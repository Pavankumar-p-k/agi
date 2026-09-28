"""Permission — capability permission gating."""
from core.permission.audit import PermissionAudit
from core.permission.manager import (
    PermissionManager,
    PermissionResolution,
    PermissionResult,
    permission_manager,
)
from core.permission.models import (
    ALL_PERMISSIONS,
    AuditEntry,
    Decision,
    Permission,
    PermissionCategory,
    RiskLevel,
)
from core.permission.observer import RuntimeObserver, Violation
from core.permission.policy import PolicyEngine, PolicyProfile, PolicyRule
from core.permission.registry import PermissionRegistry, permission_registry

__all__ = [
    "PermissionAudit",
    "PermissionManager", "PermissionResolution", "PermissionResult",
    "permission_manager",
    "ALL_PERMISSIONS", "AuditEntry", "Decision", "Permission",
    "PermissionCategory", "RiskLevel",
    "RuntimeObserver", "Violation",
    "PolicyEngine", "PolicyProfile", "PolicyRule",
    "PermissionRegistry", "permission_registry",
]
