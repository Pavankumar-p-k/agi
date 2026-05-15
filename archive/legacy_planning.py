"""Goal planning for the JARVIS AI Operating System."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .contracts import Plan, PlanStep, ToolSelection


class PlanningEngine:
    def __init__(self, tool_router: Any, observability: Any, config: Optional[dict] = None):
        self.tool_router = tool_router
        self.observability = observability
        self.config = config or {}

    async def build_plan(self, goal: Any, analysis: Dict[str, Any]) -> Plan:
        if analysis.get("intent") == "workspace":
            workspace_plan = self._build_workspace_plan(goal, analysis)
            if workspace_plan is not None:
                self.observability.record_event(
                    "planning.plan_created",
                    {
                        "goal_id": goal.goal_id,
                        "plan_id": workspace_plan.plan_id,
                        "steps": len(workspace_plan.steps),
                        "strategy": workspace_plan.strategy,
                        "requires_approval": workspace_plan.requires_approval,
                    },
                )
                return workspace_plan
        if analysis.get("intent") in {"browser", "automation"}:
            browser_plan = self._build_browser_plan(goal, analysis)
            if browser_plan is not None:
                self.observability.record_event(
                    "planning.plan_created",
                    {
                        "goal_id": goal.goal_id,
                        "plan_id": browser_plan.plan_id,
                        "steps": len(browser_plan.steps),
                        "strategy": browser_plan.strategy,
                        "requires_approval": browser_plan.requires_approval,
                    },
                )
                return browser_plan

        subtasks = analysis.get("subtasks") or [goal.prompt]
        steps: List[PlanStep] = []
        reasoning: List[str] = []

        for index, subtask in enumerate(subtasks, start=1):
            selection = self._select_tool(subtask, analysis)
            args = self._arguments_for_selection(selection.tool, subtask, goal.context)
            step = PlanStep(
                action=subtask,
                tool=selection.tool,
                args=args,
                expected_outcome=f"Complete subtask {index}: {subtask}",
                timeout_s=self._timeout_for_tool(selection.tool),
                metadata={
                    "selection": selection.to_dict(),
                    "subtask_index": index,
                    "intent": analysis.get("intent", goal.intent),
                },
            )
            steps.append(step)
            reasoning.append(f"Step {index} routed to {selection.tool}: {selection.rationale}")

        requires_approval = any(step.tool in {"automation", "adb"} for step in steps)
        plan = Plan(
            goal_id=goal.goal_id,
            steps=steps,
            strategy="multi_step" if len(steps) > 1 else "direct",
            reasoning=reasoning,
            confidence=float(analysis.get("confidence", 0.5)),
            requires_approval=requires_approval,
        )
        self.observability.record_event(
            "planning.plan_created",
            {
                "goal_id": goal.goal_id,
                "plan_id": plan.plan_id,
                "steps": len(steps),
                "strategy": plan.strategy,
                "requires_approval": plan.requires_approval,
            },
        )
        return plan

    def _build_workspace_plan(self, goal: Any, analysis: Dict[str, Any]) -> Plan | None:
        lowered = goal.prompt.lower()
        workspace_path = goal.context.get("workspace_root") or goal.context.get("cwd") or "."
        coding_keywords = ("build", "develop", "implement", "fix", "debug", "refactor", "review", "understand", "analyze")
        if not any(token in lowered for token in coding_keywords):
            return None

        steps = [
            PlanStep(
                action=f"Inspect workspace for: {goal.prompt}",
                tool="workspace",
                args={"query": goal.prompt, "path": workspace_path},
                expected_outcome="Understand repository scope and structure for the requested task.",
                timeout_s=self._timeout_for_tool("workspace"),
                metadata={"intent": "workspace", "phase": "observe"},
            ),
            PlanStep(
                action=f"List workspace root for: {goal.prompt}",
                tool="filesystem",
                args={"path": workspace_path, "action": "list", "content": ""},
                expected_outcome="Expose top-level project structure for planning.",
                timeout_s=self._timeout_for_tool("filesystem"),
                metadata={"intent": "workspace", "phase": "analyze"},
            ),
            PlanStep(
                action=f"Summarize findings and propose next development actions for: {goal.prompt}",
                tool="assistant_chat",
                args={
                    "prompt": f"Summarize the workspace findings and propose the next concrete development actions for: {goal.prompt}",
                    "context": goal.context,
                },
                expected_outcome="Produce a concrete plan grounded in the inspected workspace.",
                timeout_s=self._timeout_for_tool("assistant_chat"),
                metadata={"intent": "workspace", "phase": "plan"},
            ),
        ]
        return Plan(
            goal_id=goal.goal_id,
            steps=steps,
            strategy="workspace_loop",
            reasoning=[
                "Observe the current repository state before proposing changes.",
                "Inspect the filesystem so development planning is grounded in the actual workspace.",
                "Use the assistant only after workspace evidence has been captured.",
            ],
            confidence=float(analysis.get("confidence", 0.5)),
            requires_approval=False,
        )

    def _build_browser_plan(self, goal: Any, analysis: Dict[str, Any]) -> Plan | None:
        lowered = self._normalize_browser_text(goal.prompt.lower())
        browser_keywords = ("open ", "search", "amazon", "cart", "checkout", "website", "in chrome", "browser")
        if not any(token in lowered for token in browser_keywords):
            return None

        raw_subtasks = analysis.get("subtasks") or [goal.prompt]
        steps: List[PlanStep] = []
        reasoning: List[str] = []
        current_site = ""

        for index, raw_subtask in enumerate(raw_subtasks, start=1):
            subtask = self._normalize_browser_text(raw_subtask)
            site_hint = self._extract_site_name(subtask) or current_site
            if self._is_summary_action(subtask):
                steps.append(
                    PlanStep(
                        action="summarize current browser page",
                        tool="browser",
                        args={"action": "summarize_page", "context": goal.context},
                        expected_outcome=f"Summarize the active browser page for step {index}.",
                        timeout_s=self._timeout_for_tool("browser"),
                        metadata={"intent": "browser", "phase": "summarize", "site": site_hint or current_site},
                    )
                )
                reasoning.append("Step {index} summarizes the currently open browser page instead of falling back to generic chat.".format(index=index))
                continue
            if self._is_cart_action(subtask):
                if site_hint:
                    action = f"add current selected item to cart on {site_hint}"
                else:
                    action = "add current selected item to cart"
                steps.append(
                    PlanStep(
                        action=action,
                        tool="browser",
                        args={"command": action, "context": goal.context},
                        expected_outcome=f"Attempt browser cart step {index}.",
                        timeout_s=self._timeout_for_tool("browser"),
                        metadata={"intent": "browser", "phase": "act", "site": site_hint, "requires_approval": True},
                    )
                )
                reasoning.append(f"Step {index} keeps browser state and attempts a cart action for {site_hint or 'current site'}.")
                continue

            if subtask.startswith("open "):
                current_site = self._extract_site_name(subtask) or current_site
                steps.append(
                    PlanStep(
                        action=subtask,
                        tool="browser",
                        args={"command": subtask, "target": self._extract_browser_target(subtask), "context": goal.context},
                        expected_outcome=f"Open requested browser target for step {index}.",
                        timeout_s=self._timeout_for_tool("browser"),
                        metadata={"intent": "browser", "phase": "open", "site": current_site},
                    )
                )
                reasoning.append(f"Step {index} opens the browser/site directly instead of using desktop automation.")
                continue

            if "search" in subtask or site_hint:
                current_site = site_hint or current_site
                command = subtask
                if current_site and not command.startswith(f"in {current_site}"):
                    command = f"in {current_site} {command}"
                steps.append(
                    PlanStep(
                        action=command,
                        tool="browser",
                        args={"command": command, "context": goal.context},
                        expected_outcome=f"Run browser search/navigation step {index}.",
                        timeout_s=self._timeout_for_tool("browser"),
                        metadata={"intent": "browser", "phase": "search", "site": current_site},
                    )
                )
                reasoning.append(f"Step {index} uses the browser tool with site context {current_site or 'web'}.")
                continue

            selection = self._select_tool(subtask, analysis)
            args = self._arguments_for_selection(selection.tool, subtask, goal.context)
            steps.append(
                PlanStep(
                    action=subtask,
                    tool=selection.tool,
                    args=args,
                    expected_outcome=f"Complete browser-adjacent subtask {index}: {subtask}",
                    timeout_s=self._timeout_for_tool(selection.tool),
                    metadata={"intent": analysis.get('intent', goal.intent), "subtask_index": index},
                )
            )
            reasoning.append(f"Step {index} fell back to {selection.tool}.")

        if not steps:
            return None
        return Plan(
            goal_id=goal.goal_id,
            steps=steps,
            strategy="browser_loop",
            reasoning=reasoning,
            confidence=float(analysis.get("confidence", 0.5)),
            requires_approval=False,
        )

    def _select_tool(self, subtask: str, analysis: Dict[str, Any]) -> ToolSelection:
        lowered = subtask.lower().strip()
        if any(token in lowered for token in ("send whatsapp", "send instagram", "send telegram", "send discord", "send slack", "notify me on")):
            return ToolSelection(tool="gateway", confidence=0.9, rationale="Messaging send belongs to the channel gateway", capability="gateway")
        if analysis.get("intent") in {"browser", "automation"} and (
            lowered.startswith("in ")
            or self._is_cart_action(lowered)
            or any(token in lowered for token in ("search", "amazon", "website", "tab", "browser"))
        ):
            return ToolSelection(tool="browser", confidence=0.86, rationale="Continuation of browser workflow", capability="browser")
        recommendations = self.tool_router.recommend_tools(subtask)
        if recommendations:
            return recommendations[0]
        candidates = analysis.get("tool_candidates", [])
        if candidates:
            top = candidates[0]
            if isinstance(top, dict):
                return ToolSelection(
                    tool=top["tool"],
                    confidence=top["confidence"],
                    rationale=top["rationale"],
                    capability=top.get("capability", ""),
                )
        return ToolSelection(tool="assistant_chat", confidence=0.3, rationale="Fallback conversational tool")

    def _arguments_for_selection(self, tool: str, subtask: str, context: Dict[str, Any]) -> Dict[str, Any]:
        lowered = subtask.lower()
        if tool == "filesystem":
            path = self._extract_path(subtask) or context.get("path", ".")
            action = "read"
            if any(token in lowered for token in ["list", "show files", "dir ", "ls "]):
                action = "list"
            elif any(token in lowered for token in ["write", "save", "create"]):
                action = "write"
            return {"path": path, "action": action, "content": context.get("content", "")}
        if tool == "automation":
            return {"command": subtask}
        if tool == "browser":
            return {"command": subtask, "target": self._extract_browser_target(subtask)}
        if tool == "vision":
            return {"prompt": subtask, "image_b64": context.get("image_b64", "")}
        if tool == "adb":
            return {"command": subtask}
        if tool == "learning":
            return {"prompt": subtask, "topic": context.get("topic", subtask)}
        if tool == "memory":
            return {"query": subtask, "top_k": 5}
        if tool == "realtime":
            return {"query": subtask}
        if tool == "workspace":
            return {"query": subtask, "path": context.get("workspace_root") or context.get("cwd") or "."}
        if tool == "shell":
            return {"command": subtask, "cwd": context.get("workspace_root") or context.get("cwd") or ".", "timeout_s": 30}
        if tool == "skills":
            return {"action": "list" if "list" in lowered else "get", "skill_name": self._extract_skill_name(subtask)}
        if tool == "models":
            return {"action": "generate" if subtask.strip() else "status", "prompt": subtask, "task": context.get("task", "chat")}
        if tool == "gateway":
            return {
                "action": "send" if any(token in lowered for token in ("send", "notify")) else "status",
                "channel": self._extract_channel_name(subtask),
                "recipient": self._extract_recipient_name(subtask),
                "message": self._extract_message_text(subtask),
            }
        if tool == "mobile":
            return {
                "action": "queue_sync" if "sync" in lowered else "scan",
                "target": self._extract_mobile_target(subtask),
                "scope": "messages" if "message" in lowered else "files" if "file" in lowered else "messages",
            }
        if tool == "scheduler":
            return {
                "action": "add" if any(token in lowered for token in ("schedule", "daily", "every day", "heartbeat", "remind")) else "status",
                "job_name": self._extract_schedule_name(subtask),
                "prompt": subtask,
                "interval_s": self._extract_interval_seconds(subtask),
                "channel": self._extract_channel_name(subtask) or "local",
            }
        if tool == "access":
            return {
                "action": "grant" if "grant" in lowered else "request" if any(token in lowered for token in ("approval", "allow", "permission")) else "status",
                "profile": self._extract_access_profile(subtask),
                "scope": self._extract_access_scope(subtask),
                "reason": subtask,
                "requested_action": subtask,
            }
        return {"prompt": subtask, "context": context}

    def _extract_path(self, text: str) -> str:
        match = re.search(r"([A-Za-z]:\\[^\s]+|[./~][^\s]*)", text)
        return match.group(1) if match else ""

    def _timeout_for_tool(self, tool: str) -> int:
        return {
            "automation": 90,
            "browser": 90,
            "adb": 90,
            "vision": 45,
            "filesystem": 15,
            "learning": 60,
            "realtime": 20,
            "workspace": 25,
            "shell": 45,
            "gateway": 20,
            "mobile": 20,
            "scheduler": 20,
            "access": 15,
        }.get(tool, 30)

    def _extract_browser_target(self, text: str) -> str:
        lowered = text.lower()
        if lowered.startswith("open "):
            cleaned = re.sub(r"^open\s+", "", text, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"\bin chrome\b", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"\band.*$", "", cleaned, flags=re.IGNORECASE).strip()
            return cleaned
        return ""

    def _extract_skill_name(self, text: str) -> str:
        match = re.search(r"(?:skill|plugin|extension)\s+([A-Za-z0-9_.-]+)", text, flags=re.IGNORECASE)
        return match.group(1) if match else ""

    def _extract_channel_name(self, text: str) -> str:
        lowered = text.lower()
        for channel in ("whatsapp", "instagram", "telegram", "discord", "slack", "cli", "desktop"):
            if channel in lowered:
                return channel
        return ""

    def _extract_message_text(self, text: str) -> str:
        match = re.search(r"(?:saying|message|notify(?: me)?(?: that)?)\s+(.+)$", text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else text.strip()

    def _extract_recipient_name(self, text: str) -> str:
        match = re.search(r"(?:to|for)\s+([A-Za-z0-9_@.+-]+)\s+(?:saying|message|notify|that)", text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _extract_mobile_target(self, text: str) -> str:
        lowered = text.lower()
        if "android" in lowered:
            return "android"
        if "phone" in lowered:
            return "phone"
        return "android"

    def _extract_schedule_name(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.strip())
        return cleaned[:60] or "scheduled task"

    def _extract_interval_seconds(self, text: str) -> int:
        lowered = text.lower()
        if "every minute" in lowered:
            return 60
        if "hour" in lowered:
            return 3600
        if "daily" in lowered or "every day" in lowered:
            return 86400
        return 3600

    def _extract_access_profile(self, text: str) -> str:
        lowered = text.lower()
        for profile in ("workspace", "desktop", "mobile_sync", "personal_assistant"):
            if profile.replace("_", " ") in lowered or profile in lowered:
                return profile
        return ""

    def _extract_access_scope(self, text: str) -> str:
        lowered = text.lower()
        hints = {
            "shell.workspace": ("shell", "terminal", "command"),
            "browser.basic": ("browser", "website", "web"),
            "app.launch": ("app", "launch", "open"),
            "mobile.sync": ("mobile", "phone", "sync"),
            "message.send": ("message", "whatsapp", "telegram", "discord", "slack"),
        }
        for scope, tokens in hints.items():
            if any(token in lowered for token in tokens):
                return scope
        return "workspace.read"

    def _normalize_browser_text(self, text: str) -> str:
        normalized = text.strip()
        replacements = {
            r"\bserch\b": "search",
            r"\bamzon\b": "amazon",
            r"\bamazone\b": "amazon",
            r"\binto cart\b": "add to cart",
            r"\bintocart\b": "add to cart",
        }
        for pattern, replacement in replacements.items():
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        return normalized

    def _extract_site_name(self, text: str) -> str:
        lowered = text.lower()
        for site in ("amazon", "flipkart", "instagram", "whatsapp", "github", "google", "youtube"):
            if site in lowered:
                return site
        return ""

    def _is_cart_action(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in ("add to cart", "into cart", "cart", "checkout", "buy now"))

    def _is_summary_action(self, text: str) -> bool:
        lowered = text.lower()
        return any(
            token in lowered
            for token in (
                "summarize",
                "summarise",
                "summary",
                "give summary",
                "tell me about that",
                "about that",
            )
        )
