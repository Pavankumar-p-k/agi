"""
Module: core.permission.__init__
Permission subsystem re-exports.
"""
from __future__ import annotations
from typing import Any
import logging

logger = logging.getLogger(__name__)

from core.permission.models import Permission, Decision, AuditEntry, PermissionCategory, RiskLevel, ALL_PERMISSIONS
from core.permission.registry import PermissionRegistry, permission_registry
from core.permission.manager import PermissionManager, permission_manager
from core.permission.policy import PolicyEngine, PolicyProfile, PolicyRule, PolicyMatchMode, policy_engine
from core.permission.audit import PermissionAudit, permission_audit
from core.permission.observer import RuntimeObserver, Observation, ObservationType


def __getattr__(name: str) -> Any:
    _exports = {
        "Permission": Permission,
        "Decision": Decision,
        "AuditEntry": AuditEntry,
        "PermissionCategory": PermissionCategory,
        "RiskLevel": RiskLevel,
        "ALL_PERMISSIONS": ALL_PERMISSIONS,
        "PermissionRegistry": PermissionRegistry,
        "permission_registry": permission_registry,
        "PermissionManager": PermissionManager,
        "permission_manager": permission_manager,
        "PolicyEngine": PolicyEngine,
        "PolicyProfile": PolicyProfile,
        "PolicyRule": PolicyRule,
        "PolicyMatchMode": PolicyMatchMode,
        "policy_engine": policy_engine,
        "PermissionAudit": PermissionAudit,
        "permission_audit": permission_audit,
        "RuntimeObserver": RuntimeObserver,
        "Observation": Observation,
        "ObservationType": ObservationType,
    }
    if name in _exports:
        return _exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
