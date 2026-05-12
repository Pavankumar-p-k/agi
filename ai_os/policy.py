import re
from typing import Any
from .config import AIOSConfig
from jarvis_os.runtime.exceptions import GovernanceViolation


class PolicyEngine:
    def __init__(self, config: AIOSConfig | None = None):
        self.config = config or AIOSConfig()
        self.allow_apps = set(self.config.tool_policy_allow_apps)
        self.block_patterns = [re.compile(re.escape(w), re.IGNORECASE) for w in self.config.tool_policy_block_words]

    def assess_step(self, step: dict[str, Any]) -> dict[str, Any]:
        tool = step.get("tool", "").lower()
        advice = "safe"
        detail = ""

        if tool == "open_app":
            app = (step.get("args", {}).get("path") or "").lower()
            if app and app not in self.allow_apps:
                return {"allowed": False, "risk": "blocked", "reason": f"Application '{app}' not allowlisted"}
            return {"allowed": True, "risk": "safe", "reason": "allowlisted app"}

        if tool == "safe_shell":
            cmd = str(step.get("args", {}).get("cmd", "")).lower()
            for pat in self.block_patterns:
                if pat.search(cmd):
                    return {"allowed": False, "risk": "blocked", "reason": f"command contains prohibited content: {pat.pattern}"}
            if len(cmd) > 512:
                return {"allowed": False, "risk": "blocked", "reason": "command too long"}
            return {"allowed": True, "risk": "safe", "reason": "shell command validated"}

        # generic policy for unknown tool categories
        if tool in {"browser_control", "file_ops", "code_agent"}:
            return {"allowed": True, "risk": "safe", "reason": f"{tool} is allowed"}

        return {"allowed": False, "risk": "blocked", "reason": f"Unknown tool: {tool}"}

    def enforce(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for step in steps:
            assessment = self.assess_step(step)
            results.append({"step": step, "policy": assessment})
            if not assessment.get("allowed", False):
                raise GovernanceViolation(f"Policy enforcement failed: {assessment.get('reason', 'Unknown reason')}")
        return results