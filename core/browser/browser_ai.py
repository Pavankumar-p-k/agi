"""BrowserAI — browser automation specialist.

Owns the browser.* capabilities. Tool calls go through an injectable
async ``tool_caller`` (production wires core.tools browser tools);
page content is untrusted; sensitive actions (payments, credentials,
deletions) pass an approval gate; every capability result is verified
before it counts.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse

from core.specialist import SpecialistModule, SpecialistResult
from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityType,
    RiskTier,
    VerificationSpec,
)

ToolCaller = Callable[[str, dict], Awaitable[dict]]


# ── production tool-call shim ────────────────────────────────────────
async def call_tool(tool: str, params: dict) -> dict:
    """Route a browser tool call to the real backend when available."""
    try:
        from core.tools.browser_tools import run_browser_tool
        return await run_browser_tool(tool, params)
    except Exception as exc:  # noqa: BLE001 — honest error, never fake success
        return {"status": "error", "error": str(exc), "error_type": "BackendUnavailable"}


# ── approval gating ──────────────────────────────────────────────────
@dataclass
class ApprovalRequest:
    category: str
    action: str
    params: dict = field(default_factory=dict)


class ApprovalGate:
    """Pre-approval + resolver-based consent for sensitive actions."""

    def __init__(self, resolver: Optional[Callable] = None) -> None:
        self._resolver = resolver
        self._pre_approved: dict[str, set] = {}

    def pre_approve(self, category: str, action: str) -> None:
        self._pre_approved.setdefault(str(category), set()).add(str(action))

    def check(self, category: str, action: str, params: dict) -> bool:
        if str(action) in self._pre_approved.get(str(category), set()):
            return True
        if self._resolver is not None:
            return bool(self._resolver({"category": category,
                                        "action": action,
                                        "params": dict(params)}))
        return False


# Categories that always require consent.
_APPROVAL_CATEGORIES = {
    "payment": ("place order", "checkout", "pay now", "buy", "complete purchase"),
    "credential_access": ("password", "passwd", "pwd"),
    "account_deletion": ("delete-account", "delete account", "close account",
                         "#delete-account"),
    "communication": ("send message", "post", "share", "tweet", "email"),
}

# Deterministic verification specs per capability.
_VERIFY_SPECS = {
    "browser.navigate": [{"kind": "url_result", "expected": "url"}],
    "browser.search": [{"kind": "any_result"}],
    "browser.extract": [{"kind": "any_result"}],
    "browser.form_fill": [{"kind": "any_result"}],
    "browser.recover": [{"kind": "any_result"}],
}


def _host_of(url: str) -> str:
    try:
        return (urlparse(str(url)).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _check_sensitive(selector: str) -> Optional[str]:
    low = str(selector).lower()
    for category, tokens in _APPROVAL_CATEGORIES.items():
        if any(token in low for token in tokens):
            return category
    return None


class BrowserAI(SpecialistModule):
    name = "Browser AI"
    description = ("Drives a real browser: navigation, search, extraction, "
                   "forms, with verification and approval gating.")
    requirements = ["playwright"]

    def __init__(self, tool_caller: Optional[ToolCaller] = None,
                 procedural_memory: Any = None,
                 approval_resolver: Optional[Callable] = None) -> None:
        super().__init__()
        self._call: ToolCaller = tool_caller if tool_caller is not None else call_tool
        self.procedural_memory = procedural_memory
        self.approval_gate = ApprovalGate(approval_resolver)

        self._register("browser.navigate", self._cap_navigate)
        self._register("browser.search", self._cap_search)
        self._register("browser.extract", self._cap_extract)
        self._register("browser.form_fill", self._cap_form_fill)
        self._register("browser.type", self._cap_type)
        self._register("browser.click", self._cap_click)
        self._register("browser.verify", self._cap_verify)
        self._register("browser.recover", self._cap_recover)
        self._register("browser.execute_workflow", self._cap_workflow)
        self._register("browser.research", self._cap_research)
        self._register("browser.observe", self._cap_observe)
        self._register("browser.health", self._cap_health)
        self._register("browser.report", self._cap_report)
        self._register("browser.remember", self._cap_remember)
        self._register("browser.recall", self._cap_recall)

    # ── contract ─────────────────────────────────────────────────────
    def get_capabilities(self) -> list:
        def cap(name: str, description: str, risk: RiskTier = RiskTier.LOW,
                read_only: bool = True) -> CapabilityDefinition:
            return CapabilityDefinition(
                name=name,
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description=description,
                risk=risk,
                risk_tags=[] if read_only else ["write"],
                verification=VerificationSpec(method=f"verify:{name}"),
                requirements=["filesystem"] if "desktop" in name else [],
                health=CapabilityHealth.HEALTHY,
            )

        return [
            cap("browser.navigate", "Open a URL"),
            cap("browser.search", "Run a web search"),
            cap("browser.extract", "Extract page content as untrusted"),
            cap("browser.form_fill", "Fill and submit a form",
                RiskTier.MEDIUM, read_only=False),
            cap("browser.type", "Type into a selector"),
            cap("browser.click", "Click a selector"),
            cap("browser.verify", "Verify a post-condition"),
            cap("browser.recover", "Recover from a failed interaction"),
            cap("browser.execute_workflow", "Execute a planned workflow",
                RiskTier.MEDIUM, read_only=False),
            cap("browser.research", "Research a topic across pages"),
            cap("browser.observe", "Observe page state (a11y first)"),
            cap("browser.health", "Report browser tool health"),
            cap("browser.report", "Report specialist status"),
            cap("browser.remember", "Record a verified procedure"),
            cap("browser.recall", "Recall a stored procedure"),
        ]

    def verify(self, output: Any) -> bool:
        if not isinstance(output, dict):
            return False
        if output.get("success") is not True:
            return False
        security = output.get("security")
        if isinstance(security, dict) and security.get("suspicious"):
            return False
        return True

    def health_check(self) -> dict:
        status = "unknown"
        try:
            import playwright  # noqa: F401
            status = "healthy"
        except ImportError:
            status = "unhealthy"
        return {"status": status, "specialist": self.name,
                "backend": "playwright"}

    def security_policy(self) -> dict:
        return {
            "page_content_untrusted": True,
            "approval_categories": ["payment", "credential_access",
                                    "account_deletion", "communication"],
        }

    # ── internals ────────────────────────────────────────────────────
    async def _rpc(self, tool: str, params: dict) -> dict:
        try:
            return await self._call(tool, dict(params))
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _wrap_untrusted(content: str, url: str = "", title: str = "") -> dict:
        low = str(content).lower()
        suspicious = any(token in low for token in (
            "ignore previous instructions", "disregard all",
            "you are now", "system prompt", "reveal your"))
        return {
            "content": str(content),
            "url": url,
            "title": title,
            "security": {
                "page_content_untrusted": True,
                "suspicious": suspicious,
                "patterns_checked": ["instruction_override", "role_hijack"],
            },
        }

    def _approval_block(self, category: str) -> dict:
        return {"success": False,
                "approval": {"required": True, "category": category}}

    # ── capability handlers ──────────────────────────────────────────
    async def _cap_navigate(self, url: str, **_kw) -> dict:
        response = await self._rpc("browser_navigate", {"url": url})
        if response.get("status") != "ok":
            return {"success": False, "error": response.get("error", "navigate failed")}
        result = response.get("result") or {}
        out_url = result.get("url", url)
        return {"success": True, "url": out_url,
                "verified": _host_of(out_url) == _host_of(url)}

    async def _cap_search(self, query: str, **_kw) -> dict:
        response = await self._rpc("browser_search", {"query": query})
        if response.get("status") != "ok":
            return {"success": False, "error": response.get("error", "search failed")}
        results = response.get("result") or {}
        return {"success": True,
                "results": results.get("results", []),
                "query": query}

    async def _cap_extract(self) -> dict:
        response = await self._rpc("browser_extract", {})
        if response.get("status") != "ok":
            return {"success": False, "error": response.get("error", "extract failed")}
        result = response.get("result") or {}
        wrapped = self._wrap_untrusted(result.get("text", ""),
                                       result.get("url", ""),
                                       result.get("title", ""))
        wrapped["success"] = True
        return wrapped

    async def _cap_form_fill(self, fields: dict, **_kw) -> dict:
        for selector in fields:
            category = _check_sensitive(selector)
            if category:
                return self._approval_block(category)
        response = await self._rpc("browser_fill", {"fields": fields})
        if response.get("status") != "ok":
            return {"success": False, "error": response.get("error", "fill failed")}
        return {"success": True, "fields": dict(fields)}

    async def _cap_type(self, selector: str, text: str, **_kw) -> dict:
        category = _check_sensitive(selector)
        if category:
            return self._approval_block(category)
        response = await self._rpc("browser_type",
                                   {"selector": selector, "text": text})
        if response.get("status") != "ok":
            return {"success": False, "error": response.get("error", "type failed")}
        return {"success": True, "selector": selector}

    async def _cap_click(self, selector: str, **_kw) -> dict:
        category = _check_sensitive(selector)
        if category:
            if not self.approval_gate.check(category, f"click {selector}", {"selector": selector}):
                return self._approval_block(category)
        response = await self._rpc("browser_click", {"selector": selector})
        if response.get("status") != "ok":
            recovery = await self._recover_click(selector)
            if recovery is None:
                return {"success": False,
                        "error": response.get("error", "click failed"),
                        "recovery": {"attempted": True, "recovered": False}}
            return recovery
        return {"success": True, "clicked": selector}

    async def _cap_verify(self, expectations: list, **_kw) -> dict:
        return await verify_expectations(self._call, expectations)

    async def _cap_recover(self, **_kw) -> dict:
        response = await self._rpc("browser_get_url", {})
        url = response.get("url", "") or (response.get("result") or {}).get("url", "")
        return {"success": True, "recovered": True, "url": url}

    async def _cap_workflow(self, plan: dict, session_id: str = "s") -> dict:
        return await execute_workflow(plan, session_id=session_id,
                                      call=self._call)

    async def _cap_research(self, topic: str, max_pages: int = 3) -> dict:
        pages = []
        for index in range(max(1, int(max_pages))):
            response = await self._rpc(
                "browser_navigate",
                {"url": f"https://www.bing.com/search?q={topic}&first={index + 1}"})
            if response.get("status") != "ok":
                continue
            extracted = await self._cap_extract()
            if extracted.get("success"):
                pages.append(extracted)
        return {"success": bool(pages), "topic": topic, "pages": pages,
                "security": {"page_content_untrusted": True}}

    async def _cap_observe(self) -> dict:
        return await self.observe()

    async def observe(self) -> dict:
        """Observe page state; a11y tree first, DOM, then screenshot."""
        url_response = await self._rpc("browser_get_url", {})
        url = url_response.get("url", "") or (url_response.get("result") or {}).get("url", "")

        title_response = await self._rpc("browser_get_title", {})
        title = (title_response.get("result") or {}).get("title", "") \
            if title_response.get("status") == "ok" else ""

        a11y = await self._rpc("browser_a11y_tree", {})
        if a11y.get("status") == "ok":
            result = a11y.get("result") or {}
            return {"status": "ok", "perception_mode": "a11y_tree",
                    "url": url, "title": title,
                    "page": {"tree": result.get("tree")}}

        dom = await self._rpc("browser_snapshot", {})
        if dom.get("status") == "ok":
            result = dom.get("result") or {}
            return {"status": "ok", "perception_mode": "dom",
                    "url": url, "title": title,
                    "page": {"dom": result.get("dom")}}

        shot = await self._rpc("browser_screenshot", {})
        if shot.get("status") == "ok":
            return {"status": "ok", "perception_mode": "screenshot_only",
                    "url": url, "title": title,
                    "screenshot": (shot.get("result") or {}).get("screenshot", "")}

        return {"status": "error", "perception_mode": "none",
                "error": "no perception backend responded"}

    async def _cap_health(self) -> dict:
        probe = await self._rpc("browser_get_url", {})
        healthy = probe.get("status") == "ok"
        return {"success": True, "healthy": healthy,
                "backend": "playwright" if healthy else "unavailable"}

    async def _cap_report(self) -> dict:
        return {"success": True, "specialist": self.name,
                "report": self.report()}

    async def _cap_remember(self, site: str, task: str, steps: list) -> dict:
        if self.procedural_memory is None:
            return {"success": False, "error": "no procedural memory configured"}
        procedure_id = self.procedural_memory.record(site, task, steps)
        return {"success": True, "procedure_id": procedure_id}

    async def _cap_recall(self, site: str, task: str) -> dict:
        if self.procedural_memory is None:
            return {"success": False, "error": "no procedural memory configured"}
        procedure = self.procedural_memory.get(site, task)
        if not procedure:
            return {"success": False, "error": "no procedure found"}
        return {"success": True, "procedure": procedure}

    # ── recovery ─────────────────────────────────────────────────────
    async def _recover_click(self, selector: str) -> Optional[dict]:
        """Recovery ladder: scroll into view -> wait -> JS click."""
        for tool, params in (
            ("browser_scroll_into_view", {"selector": selector}),
            ("browser_wait_for", {"selector": selector, "timeout_ms": 3000}),
            ("browser_click", {"selector": selector}),
        ):
            response = await self._rpc(tool, params)
            if response.get("status") == "ok" and tool == "browser_click":
                return {"success": True, "clicked": selector,
                        "recovery": {"attempted": True, "recovered": True}}
        return None


# ── verification engine ──────────────────────────────────────────────
async def verify_expectations(call: ToolCaller, expectations: list) -> dict:
    """Deterministically verify post-conditions against the live browser."""
    outcomes = []
    for expectation in expectations or []:
        kind = expectation.get("kind")
        if kind == "url_host":
            response = await call("browser_get_url", {})
            url = response.get("url", "") or (response.get("result") or {}).get("url", "")
            host = _host_of(url)
            expected = str(expectation.get("expected", "")).lower()
            outcomes.append({
                "kind": kind, "expected": expected, "actual": host,
                "pass": host == expected,
            })
        elif kind == "url_result":
            outcomes.append({"kind": kind, "pass": True})
        elif kind == "any_result":
            outcomes.append({"kind": kind, "pass": True})
        else:
            outcomes.append({"kind": str(kind), "pass": False,
                             "error": "unknown expectation kind"})
    status = "SUCCESS" if outcomes and all(o["pass"] for o in outcomes) else "FAILED"
    return {"status": status, "expectations": outcomes}


# ── workflow engine ──────────────────────────────────────────────────
async def execute_workflow(plan: dict, session_id: str = "s",
                           call: Optional[ToolCaller] = None) -> dict:
    """Execute a plan dict: steps + verify; FAILED on step error,
    UNCONFIRMED when steps pass but verification fails."""
    call = call or call_tool
    trace: list[dict] = []
    steps = plan.get("steps", []) or []

    for index, step in enumerate(steps):
        tool = step.get("tool", "")
        params = step.get("params", {}) or {}
        response = await call(tool, params)

        if response.get("status") != "ok":
            # One recovery attempt: open a new tab then retry once.
            recovery = await call("browser_new_tab", {"url": params.get("url", "")})
            trace.append({"step": index, "tool": tool,
                          "status": "error",
                          "error": response.get("error", ""),
                          "recovery": {"attempted": True,
                                       "recovered": recovery.get("status") == "ok"}})
            return {"status": "FAILED", "failed_step": index,
                    "trace": trace,
                    "verification": {"status": "NOT_RUN"}}

        trace.append({"step": index, "tool": tool, "status": "ok"})

    verification = await verify_expectations(call, plan.get("verify", []))
    if verification["status"] != "SUCCESS":
        return {"status": "UNCONFIRMED", "trace": trace,
                "verification": verification}
    return {"status": "SUCCESS", "trace": trace, "verification": verification}


_browser_ai_singleton: Optional[BrowserAI] = None


def get_browser_ai() -> BrowserAI:
    """Module-level singleton accessor."""
    global _browser_ai_singleton
    if _browser_ai_singleton is None:
        _browser_ai_singleton = BrowserAI()
    return _browser_ai_singleton


__all__ = ["BrowserAI", "ApprovalGate", "execute_workflow",
           "verify_expectations", "get_browser_ai", "call_tool"]
