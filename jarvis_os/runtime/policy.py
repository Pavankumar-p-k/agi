from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..utils import context_sandbox_root, path_within_root, resolve_workspace_path
from .exceptions import GovernanceViolation, SecurityViolation


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""
    risk_level: str = "safe"
    requires_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "requires_approval": self.requires_approval,
        }


class PolicyEngine:
    PATH_ARGUMENTS = {"path", "destination", "script_path"}
    APPROVAL_REQUIRED_TOOLS = {"delete_file", "git_push", "run_terminal_command", "run_python"}
    DANGEROUS_COMMAND_TOKENS = (
        " rm ",
        " del ",
        " remove-item ",
        " rmdir ",
        " format ",
        " shutdown",
        " reboot",
        " restart-computer",
        " stop-computer",
        " reset --hard",
    )

    def __init__(self, strict_mode: bool = True, *, workspace_root: Any | None = None) -> None:
        self.strict_mode = strict_mode
        self.workspace_root = context_sandbox_root({"sandbox_root": workspace_root} if workspace_root else None)

    def evaluate(self, step: Any, registry: Any, context: dict[str, Any] | None = None) -> PolicyDecision:
        if not self.strict_mode:
            return PolicyDecision(True, "strict mode disabled")
        ctx = context or {}
        spec = next((item for item in registry.catalog() if item["name"] == step.tool), None)
        permission = str(spec.get("permission", "safe")) if spec else "safe"
        risk_level = "elevated" if permission == "elevated" else "safe"
        elevated = permission == "elevated"
        command = str(step.arguments.get("command", "")).lower()

        if elevated and ctx.get("read_only", False):
            return PolicyDecision(False, f"tool `{step.tool}` blocked in read-only context", risk_level=risk_level)

        sandbox_decision = self._check_workspace_sandbox(step, ctx, risk_level)
        if sandbox_decision is not None:
            return sandbox_decision

        if step.tool in self.APPROVAL_REQUIRED_TOOLS and not self._approved(step, ctx):
            return PolicyDecision(
                False,
                f"tool `{step.tool}` requires explicit approval",
                risk_level="dangerous",
                requires_approval=True,
            )

        if step.tool == "run_terminal_command" and any(token in f" {command} " for token in self.DANGEROUS_COMMAND_TOKENS):
            if not ctx.get("allow_unsafe", False):
                return PolicyDecision(False, "dangerous shell command blocked by policy", risk_level="dangerous")

        return PolicyDecision(True, "allowed", risk_level=risk_level)

    def review_plan(self, plan: Any, registry: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        steps: list[dict[str, Any]] = []
        blocked = 0
        approvals = 0
        for step in plan.steps:
            decision = self.evaluate(step, registry, ctx)
            steps.append({"step_id": step.step_id, "tool": step.tool, "decision": decision.to_dict()})
            if not decision.allowed:
                blocked += 1
            if decision.requires_approval:
                approvals += 1
        return {
            "allowed": blocked == 0,
            "blocked_steps": blocked,
            "pending_approvals": approvals,
            "steps": steps,
            "strict_mode": self.strict_mode,
            "workspace_root": str(self.workspace_root),
        }

    def describe(self) -> dict[str, Any]:
        return {
            "strict_mode": self.strict_mode,
            "workspace_root": str(self.workspace_root),
            "approval_required_tools": sorted(self.APPROVAL_REQUIRED_TOOLS),
            "sandbox_path_arguments": sorted(self.PATH_ARGUMENTS),
        }

    def enforce(self, step: Any, registry: Any, context: dict[str, Any] | None = None) -> PolicyDecision:
        decision = self.evaluate(step, registry, context)
        if not decision.allowed:
            reason = decision.reason or "policy denied execution"
            if "sandbox" in reason or "path" in reason or "dangerous" in decision.risk_level:
                raise SecurityViolation(reason)
            raise GovernanceViolation(reason)
        return decision

    def _approved(self, step: Any, context: dict[str, Any]) -> bool:
        if context.get("approved", False):
            return True
        approved_tools = {str(item).strip() for item in context.get("approved_tools", []) if str(item).strip()}
        approved_actions = {str(item).strip().lower() for item in context.get("approved_actions", []) if str(item).strip()}
        if step.tool in approved_tools:
            return True
        if step.action.strip().lower() in approved_actions:
            return True
        return False

    def _check_workspace_sandbox(self, step: Any, context: dict[str, Any], risk_level: str) -> PolicyDecision | None:
        if context.get("allow_workspace_escape", False):
            return None
        workspace_root = context_sandbox_root(context, self.workspace_root)
        for argument, value in step.arguments.items():
            if argument not in self.PATH_ARGUMENTS or not value:
                continue
            target = resolve_workspace_path(str(value), {"workspace_root": workspace_root}, workspace_root)
            if not path_within_root(target, workspace_root):
                return PolicyDecision(
                    False,
                    f"path `{target}` escapes workspace sandbox",
                    risk_level="dangerous" if risk_level == "elevated" else risk_level,
                )
        return None
