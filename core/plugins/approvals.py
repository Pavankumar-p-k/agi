from __future__ import annotations

import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RiskLevel(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


RISK_TO_AUTO_APPROVE: dict[RiskLevel, bool] = {
    RiskLevel.LOW: True,
    RiskLevel.MEDIUM: False,
    RiskLevel.HIGH: False,
    RiskLevel.CRITICAL: False,
}


@dataclass
class ApprovalRequest:
    token: str
    plugin_name: str
    action: str
    params: dict
    risk_level: RiskLevel
    description: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    approved: bool | None = None
    resolved_by: str | None = None
    resolved_at: float | None = None

    @property
    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.time() > self.expires_at


class ApprovalChain:
    def __init__(self, timeout: float = 300.0):
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[ApprovalRequest] = []
        self._timeout = timeout
        self._resolver: Callable[[ApprovalRequest], None] | None = None
        self._max_history = 100

    def set_resolver(self, resolver: Callable[[ApprovalRequest], None]) -> None:
        self._resolver = resolver

    def request_approval(
        self,
        plugin_name: str,
        action: str,
        params: dict | None = None,
        risk_level: str | RiskLevel = RiskLevel.MEDIUM,
        description: str = "",
    ) -> ApprovalRequest:
        if isinstance(risk_level, str):
            risk_level = RiskLevel(risk_level)

        token = uuid.uuid4().hex[:16]
        req = ApprovalRequest(
            token=token,
            plugin_name=plugin_name,
            action=action,
            params=params or {},
            risk_level=risk_level,
            description=description or f"{plugin_name}: {action}",
            expires_at=time.time() + self._timeout,
        )

        if RISK_TO_AUTO_APPROVE.get(risk_level, False):
            req.approved = True
            req.resolved_by = "auto"
            req.resolved_at = time.time()
            self._history.append(req)
            if len(self._history) > self._max_history:
                self._history.pop(0)
            logger.info("[Approval] Auto-approved %s/%s (risk=%s)", plugin_name, action, risk_level.value)
            return req

        self._pending[token] = req
        if self._resolver:
            try:
                self._resolver(req)
            except Exception as e:
                logger.warning("[Approval] Resolver failed: %s", e)
        logger.info("[Approval] Pending: %s/%s (token=%s, risk=%s)", plugin_name, action, token, risk_level.value)
        return req

    def resolve(self, token: str, approved: bool, resolved_by: str = "user") -> ApprovalRequest | None:
        req = self._pending.pop(token, None)
        if req is None:
            logger.warning("[Approval] Token not found: %s", token)
            return None
        req.approved = approved
        req.resolved_by = resolved_by
        req.resolved_at = time.time()
        self._history.append(req)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        logger.info("[Approval] Resolved %s/%s: %s (by %s)", req.plugin_name, req.action, "approved" if approved else "denied", resolved_by)
        return req

    def check(self, plugin_name: str, action: str, params: dict | None = None, risk: str | RiskLevel = RiskLevel.MEDIUM) -> ApprovalRequest:
        return self.request_approval(plugin_name, action, params, risk)

    def status(self, token: str) -> dict | None:
        req = self._pending.get(token)
        if req:
            return {
                "token": token,
                "status": "pending",
                "plugin": req.plugin_name,
                "action": req.action,
                "risk": req.risk_level.value,
                "expired": req.is_expired,
            }
        for h in self._history:
            if h.token == token:
                return {
                    "token": token,
                    "status": "resolved",
                    "approved": h.approved,
                    "resolved_by": h.resolved_by,
                    "plugin": h.plugin_name,
                    "action": h.action,
                }
        return None

    def pending_count(self) -> int:
        self._evict_expired()
        return len(self._pending)

    def list_pending(self) -> list[dict]:
        self._evict_expired()
        return [
            {
                "token": t,
                "plugin": r.plugin_name,
                "action": r.action,
                "risk": r.risk_level.value,
                "description": r.description,
                "expires_in": max(0.0, r.expires_at - time.time()),
            }
            for t, r in self._pending.items()
        ]

    def list_history(self, limit: int = 20) -> list[dict]:
        return [
            {
                "token": r.token,
                "plugin": r.plugin_name,
                "action": r.action,
                "risk": r.risk_level.value,
                "approved": r.approved,
                "resolved_by": r.resolved_by,
                "resolved_at": r.resolved_at,
            }
            for r in self._history[-limit:]
        ]

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [t for t, r in self._pending.items() if r.is_expired]
        for t in expired:
            req = self._pending.pop(t, None)
            if req:
                req.approved = False
                req.resolved_by = "timeout"
                req.resolved_at = now
                self._history.append(req)
                logger.info("[Approval] Expired: %s/%s (token=%s)", req.plugin_name, req.action, t)
