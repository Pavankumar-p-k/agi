"""Browser AI specialist module implementing the standard SpecialistModule contract.

Browser AI is the web specialist of the JARVIS specialist architecture
(Desktop AI, Coding AI, Browser AI, ...).  It conforms to the same clean
specialist boundary so a future Super-Brain can simply discover capabilities
like browser.navigate, browser.search, browser.extract, browser.form_fill,
browser.verify and browser.recover without understanding browser internals.

Reuse map (no parallel architecture was created):
    core/browser_manager.py        browser lifecycle foundation
    core/tools/browser_tools.py    verified action primitives (do_browser_*)
    tools/registry.py              authoritative capability registration
    core/desktop/task_graph.py     multi-step workflow execution (via core.browser.workflow)
    memory/memory_facade.py        episodic mirror of browser experience
    core/browser/procedural_memory.py  site/task procedures (sqlite in data/memory.db)
    core/tools/policy.py           tool policy engine hooks
    core/browser/page_security.py  untrusted page content + approval gates
    core/browser/verification.py   SUCCESS/FAILED/UNCONFIRMED verification
    core/browser/recovery.py       bounded recovery ladder

Specialist contract (core/specialist.py):
    identity (name/description) / capabilities / requirements / health() /
    observe() / execute() / verify() / recover() / report()
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from core.specialist import SpecialistModule, SpecialistResult
from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    RiskTier,
    VerificationSpec,
)

logger = logging.getLogger(__name__)

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


async def call_tool(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    """Default tool caller: invoke the verified do_browser_* primitives."""
    # Direct submodule import: `from core.tools import browser_tools` resolves
    # through the package attribute and can hit core.tools.__getattr__'s
    # DynamicStub fallback, producing a non-awaitable "handler".
    import core.tools.browser_tools as browser_tools
    handler = getattr(browser_tools, f"do_{tool}", None)
    if handler is None or not tool.startswith("browser_"):
        return {"status": "error", "error": f"unknown browser tool: {tool}", "error_type": "NotFound"}
    try:
        return await handler(**params)
    except TypeError as exc:
        return {"status": "error", "error": f"bad params for {tool}: {exc}", "error_type": "BadParams"}
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}", "error_type": type(exc).__name__}


# ---------------------------------------------------------------------------
# Workflow execution (goal -> steps -> verified result), on the existing
# desktop TaskGraph action-dict shape so Browser AI gains rollback/consent
# semantics for free.
# ---------------------------------------------------------------------------

async def execute_workflow(
    plan: dict[str, Any],
    session_id: str = "default",
    call: ToolCaller | None = None,
) -> dict[str, Any]:
    """Execute a browser workflow of steps and verify the final outcome.

    plan shape: {"goal": str, "steps": [{"tool": "browser_click", "params": {...}}, ...],
                 "verify": [{"kind": "url_host", "expected": "github.com"}, ...]}

    Steps run in order; a failed step triggers bounded recovery; the goal is
    only reported SUCCESS when the verification checks pass.
    """
    from core.browser.recovery import RecoveryContext, RecoveryEngine
    from core.browser.verification import Check, verify_outcome

    run = call or call_tool
    steps = plan.get("steps") or []
    verify_spec = plan.get("verify") or []
    engine = RecoveryEngine(run)
    trace: list[dict[str, Any]] = []

    for index, step in enumerate(steps):
        tool = str(step.get("tool") or "")
        params = dict(step.get("params") or {})
        params.setdefault("session_id", session_id)
        result = await run(tool, params)
        entry = {"step": index, "tool": tool, "status": result.get("status"), "error": result.get("error")}
        if result.get("status") != "ok":
            alt_selectors = [s for s in (step.get("alt_selectors") or []) if s]
            recovery = await engine.recover(RecoveryContext(
                action_name=tool,
                params=params,
                alt_selectors=alt_selectors,
                alternative_workflows=[(t, dict(p)) for t, p in (step.get("alternatives") or [])],
            ))
            entry["recovery"] = recovery.to_dict()
            if not recovery.recovered:
                return {
                    "status": "FAILED",
                    "goal": plan.get("goal", ""),
                    "failed_step": index,
                    "trace": trace + [entry],
                    "error": result.get("error", "step failed and recovery could not fix it"),
                }
            result = recovery.result
        trace.append(entry)

    outcome = await verify_outcome(
        [Check(kind=c["kind"], expected=c.get("expected", "")) for c in verify_spec],
        run,
        session_id,
    )
    return {
        "status": outcome.status,
        "goal": plan.get("goal", ""),
        "trace": trace,
        "verification": outcome.to_dict(),
    }


# ---------------------------------------------------------------------------
# Specialist
# ---------------------------------------------------------------------------

class BrowserAI(SpecialistModule):
    """Encapsulated Browser AI specialist (web perception, actions, research,
    verification, recovery, procedural memory, security boundaries)."""

    def __init__(
        self,
        *,
        tool_caller: ToolCaller | None = None,
        approval_resolver: Any | None = None,
        session_id: str = "default",
        procedural_memory: Any | None = None,
    ) -> None:
        self._call = tool_caller or call_tool
        self.session_id = session_id
        from core.browser.page_security import ApprovalGate
        from core.browser.procedural_memory import BrowserProceduralMemory
        self.approval_gate = ApprovalGate(resolver=approval_resolver)
        self.procedural_memory = procedural_memory or BrowserProceduralMemory()

    # -- identity ----------------------------------------------------------
    @property
    def name(self) -> str:
        return "Browser AI"

    @property
    def description(self) -> str:
        return (
            "Web browser specialist: DOM/accessibility perception, reliable "
            "browser actions, web research, verified outcomes, bounded recovery, "
            "procedural memory of site workflows, and page-content security."
        )

    @property
    def requirements(self) -> list[str]:
        return ["playwright", "network", "chromium"]

    # -- health ------------------------------------------------------------
    async def health(self) -> dict[str, Any]:
        result = await self._call("browser_health", {})
        healthy = result.get("healthy") is True
        return {
            "status": CapabilityHealth.HEALTHY.value if healthy else CapabilityHealth.UNHEALTHY.value,
            "details": result,
        }

    # -- perception --------------------------------------------------------
    async def observe(self, session_id: str | None = None) -> dict[str, Any]:
        """Perceive the current page: URL/title first, then a11y tree, DOM
        snapshot fallback, screenshot as last resort.  All page text is
        wrapped as untrusted data."""
        session_id = session_id or self.session_id
        from core.browser.page_security import wrap_page_payload

        state = await self._call("browser_get_url", {"session_id": session_id})
        if state.get("status") != "ok":
            return {"status": "error", "error": state.get("error", "browser unavailable")}

        url = str(state.get("url") or state.get("result", {}).get("url") or "")
        title_res = await self._call("browser_get_title", {"session_id": session_id})
        title = str(title_res.get("result", {}).get("title") or "") if title_res.get("status") == "ok" else ""

        a11y = await self._call("browser_a11y_tree", {"session_id": session_id})
        if a11y.get("status") == "ok":
            perception_mode = "a11y_tree"
            page_payload = a11y.get("result", {})
        else:
            dom = await self._call("browser_snapshot", {"session_id": session_id})
            if dom.get("status") != "ok":
                screenshot = await self._call("browser_screenshot", {"session_id": session_id})
                return {
                    "status": "ok" if screenshot.get("status") == "ok" else "error",
                    "url": url,
                    "title": title,
                    "perception_mode": "screenshot_only",
                    "screenshot": screenshot.get("result", {}).get("screenshot") if screenshot.get("status") == "ok" else None,
                }
            perception_mode = "dom_snapshot"
            page_payload = dom.get("result", {})

        # Scan ALL page-derived text — including nested structures (links,
        # headings, a11y tree nodes).  Scanning only top-level text keys lets
        # injected instructions hide inside deep page content.
        from core.browser.page_security import scan_page_text
        import json as _json
        try:
            deep_text = _json.dumps(page_payload, ensure_ascii=False, default=str)
        except Exception:
            deep_text = str(page_payload)
        scan = scan_page_text(deep_text)
        safe_payload, _ = wrap_page_payload(page_payload)
        return {
            "status": "ok",
            "url": url,
            "title": title,
            "perception_mode": perception_mode,
            "page": safe_payload,
            "security": scan.to_dict(),
        }

    # -- capabilities ------------------------------------------------------
    def get_capabilities(self) -> list[CapabilityDefinition]:
        owner = self.name
        def cap(name: str, desc: str, inputs: dict, outputs: dict, risk: RiskTier,
                verification: str, handler: Any, *, requirements: list[str] | None = None,
                tags: list[str] | None = None, read_only: bool = False) -> CapabilityDefinition:
            return CapabilityDefinition(
                name=name,
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=owner,
                description=desc,
                inputs=inputs,
                outputs=outputs,
                requirements=requirements or self.requirements,
                risk=risk,
                risk_tags=tags or [],
                health=CapabilityHealth.HEALTHY,
                health_check=lambda: True,  # live health comes from health()
                verification=VerificationSpec(method=verification),
                handler=handler,
                metadata={"read_only": read_only},
            )

        return [
            cap("browser.health", "Report browser backend health and availability", {},
                {"healthy": {"type": "boolean"}}, RiskTier.LOW, "health_reported", self._cap_health),
            cap("browser.observe", "Perceive the current page (a11y tree / DOM / screenshot) as untrusted data",
                {"session_id": {"type": "string"}},
                {"url": {"type": "string"}, "perception_mode": {"type": "string"}}, RiskTier.LOW,
                "perception_returned", self._cap_observe, read_only=True),
            cap("browser.navigate", "Navigate to a URL with destination verification",
                {"url": {"type": "string"}, "session_id": {"type": "string"}},
                {"url": {"type": "string"}}, RiskTier.MEDIUM, "destination_verified", self._cap_navigate,
                tags=["navigation"]),
            cap("browser.search", "Run a web search in the browser and extract result links",
                {"query": {"type": "string"}, "engine": {"type": "string"}},
                {"results": {"type": "array"}}, RiskTier.LOW, "results_extracted", self._cap_search,
                read_only=True),
            cap("browser.extract", "Extract bounded page text (verification-ready evidence)",
                {"selector": {"type": "string"}, "max_chars": {"type": "integer"}},
                {"text": {"type": "string"}}, RiskTier.LOW, "text_extracted", self._cap_extract,
                read_only=True),
            cap("browser.click", "Click an element by selector/text with bounded recovery",
                {"selector": {"type": "string"}, "alt_selectors": {"type": "array"}},
                {"clicked": {"type": "string"}}, RiskTier.MEDIUM, "click_dispatched", self._cap_click,
                tags=["action"]),
            cap("browser.type", "Type text into a field (read-back verified)",
                {"selector": {"type": "string"}, "value": {"type": "string"}},
                {"selector": {"type": "string"}}, RiskTier.MEDIUM, "fill_verified", self._cap_type,
                tags=["action", "form"]),
            cap("browser.select", "Select an option and verify the selection",
                {"selector": {"type": "string"}, "value": {"type": "string"}},
                {"selected": {"type": "string"}}, RiskTier.MEDIUM, "selection_verified", self._cap_select,
                tags=["action", "form"]),
            cap("browser.form_fill", "Fill and verify multiple form fields",
                {"fields": {"type": "object"}},
                {"filled": {"type": "integer"}}, RiskTier.MEDIUM, "fields_verified", self._cap_form_fill,
                tags=["action", "form"]),
            cap("browser.upload", "Upload files through a file input (approval-gated for sensitive data)",
                {"selector": {"type": "string"}, "files": {"type": "array"}},
                {"uploaded": {"type": "array"}}, RiskTier.HIGH, "files_attached", self._cap_upload,
                tags=["upload"]),
            cap("browser.download", "Download a file via link click or URL, verified by size",
                {"selector": {"type": "string"}, "url": {"type": "string"}, "save_path": {"type": "string"}},
                {"path": {"type": "string"}}, RiskTier.MEDIUM, "file_saved", self._cap_download,
                tags=["download"]),
            cap("browser.tab_manage", "Open/switch/close/list tabs",
                {"action": {"type": "string", "enum": ["new", "switch", "close", "list"]}, "index": {"type": "integer"}, "url": {"type": "string"}},
                {"tabs": {"type": "array"}}, RiskTier.LOW, "tab_state_reported", self._cap_tabs),
            cap("browser.verify", "Verify an expected outcome against live page state (SUCCESS/FAILED/UNCONFIRMED)",
                {"checks": {"type": "array", "description": "[{kind, expected, negate?}]"}},
                {"status": {"type": "string"}}, RiskTier.LOW, "verification_reported", self._cap_verify,
                read_only=True),
            cap("browser.recover", "Attempt bounded recovery for a failed browser action",
                {"action_name": {"type": "string"}, "params": {"type": "object"}, "alt_selectors": {"type": "array"}},
                {"recovered": {"type": "boolean"}}, RiskTier.LOW, "recovery_attempted", self._cap_recover,
                read_only=True),
            cap("browser.execute_workflow", "Execute a multi-step browser workflow with per-step recovery and final verification",
                {"plan": {"type": "object", "description": "{goal, steps:[{tool, params}], verify:[{kind, expected}]}"}},
                {"status": {"type": "string"}}, RiskTier.HIGH, "workflow_verified", self._cap_workflow,
                tags=["workflow"]),
            cap("browser.research", "Evidence-backed web research: search, open, extract, compare sources",
                {"question": {"type": "string"}, "max_pages": {"type": "integer"}},
                {"facts": {"type": "array"}, "sources_consulted": {"type": "array"}}, RiskTier.LOW,
                "report_synthesized", self._cap_research, read_only=True),
            cap("browser.remember_procedure", "Record a successful site procedure into browser procedural memory",
                {"site": {"type": "string"}, "task": {"type": "string"}, "steps": {"type": "array"}, "selectors": {"type": "object"}, "success": {"type": "boolean"}},
                {"procedure_id": {"type": "string"}}, RiskTier.LOW, "procedure_recorded", self._cap_remember,
                read_only=True),
            cap("browser.recall_procedure", "Recall a stored site procedure with freshness/confidence info",
                {"site": {"type": "string"}, "task": {"type": "string"}},
                {"procedure": {"type": "object"}}, RiskTier.LOW, "procedure_returned", self._cap_recall,
                read_only=True),
            cap("browser.report", "Produce a specialist report: health, memory, capabilities, security posture",
                {}, {"report": {"type": "object"}}, RiskTier.LOW, "report_generated", self._cap_report,
                read_only=True),
        ]

    # -- capability handlers ----------------------------------------------
    async def _cap_health(self) -> dict[str, Any]:
        return await self.health()

    async def _cap_observe(self, session_id: str | None = None) -> dict[str, Any]:
        return await self.observe(session_id)

    async def _cap_navigate(self, url: str, session_id: str | None = None) -> dict[str, Any]:
        session_id = session_id or self.session_id
        result = await self._call("browser_navigate", {"url": url, "session_id": session_id})
        ok = result.get("status") == "ok"
        return {
            "success": ok,
            **(result.get("result", {}) if ok else {}),
            "error": result.get("error"),
        }

    async def _cap_search(self, query: str, engine: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        result = await self._call("browser_search", {"query": query, "engine": engine, "session_id": session_id or self.session_id})
        if result.get("status") == "ok":
            safe, _scan = self._wrap_search_results(result.get("result", {}))
            return {"success": True, **safe}
        return {"success": False, "error": result.get("error")}

    @staticmethod
    def _wrap_search_results(payload: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        from core.browser.page_security import wrap_page_payload
        return wrap_page_payload(payload, text_keys=("title",))

    async def _cap_extract(self, selector: str = "body", max_chars: int = 20000, session_id: str | None = None) -> dict[str, Any]:
        result = await self._call("browser_extract", {"selector": selector, "max_chars": max_chars, "session_id": session_id or self.session_id})
        if result.get("status") == "ok":
            from core.browser.page_security import wrap_page_payload
            safe, scan = wrap_page_payload(result.get("result", {}))
            return {"success": True, **safe, "security": scan.to_dict()}
        return {"success": False, "error": result.get("error")}

    async def _cap_click(self, selector: str, alt_selectors: list[str] | None = None, session_id: str | None = None) -> dict[str, Any]:
        session_id = session_id or self.session_id
        gate = await self.approval_gate.check(
            self._classify_with_context("click", selector),
            description=f"click {selector}",
        )
        if gate.requires_approval:
            return {"success": False, "error": f"approval required: {gate.category} ({gate.reason})", "approval": gate.to_dict()}
        result = await self._call("browser_click", {"selector": selector, "session_id": session_id})
        if result.get("status") == "ok":
            return {"success": True, **result.get("result", {})}
        from core.browser.recovery import RecoveryContext, RecoveryEngine
        recovery = await RecoveryEngine(self._call).recover(RecoveryContext(
            action_name="browser_click", params={"selector": selector, "session_id": session_id},
            alt_selectors=alt_selectors or [],
        ))
        return {"success": recovery.recovered, "recovery": recovery.to_dict()}

    async def _cap_type(self, selector: str, value: str, session_id: str | None = None) -> dict[str, Any]:
        session_id = session_id or self.session_id
        gate = await self.approval_gate.check(
            self._classify_with_context("fill", f"{selector} {value}"),
            description=f"type into {selector}",
        )
        if gate.requires_approval:
            return {"success": False, "error": f"approval required: {gate.category} ({gate.reason})", "approval": gate.to_dict()}
        result = await self._call("browser_fill", {"selector": selector, "value": value, "session_id": session_id})
        return {"success": result.get("status") == "ok", **result.get("result", {}), "error": result.get("error")}

    async def _cap_select(self, selector: str, value: str, session_id: str | None = None) -> dict[str, Any]:
        result = await self._call("browser_select", {"selector": selector, "value": value, "session_id": session_id or self.session_id})
        return {"success": result.get("status") == "ok", **result.get("result", {}), "error": result.get("error")}

    async def _cap_form_fill(self, fields: Any, session_id: str | None = None) -> dict[str, Any]:
        session_id = session_id or self.session_id
        if isinstance(fields, dict):
            joined = " ".join(f"{k} {v}" for k, v in fields.items())
        else:
            joined = " ".join(str(f.get("selector", "")) + " " + str(f.get("value", "")) for f in fields if isinstance(f, dict))
        gate = await self.approval_gate.check(
            self._classify_with_context("fill", joined),
            description="form_fill",
        )
        if gate.requires_approval:
            return {"success": False, "error": f"approval required: {gate.category} ({gate.reason})", "approval": gate.to_dict()}
        result = await self._call("browser_form_fill", {"fields": fields, "session_id": session_id})
        return {"success": result.get("status") == "ok", **result.get("result", {}), "error": result.get("error")}

    async def _cap_upload(self, selector: str, files: list[str], session_id: str | None = None) -> dict[str, Any]:
        session_id = session_id or self.session_id
        gate = await self.approval_gate.check(
            self._classify_with_context("upload", selector),
            description=f"upload {files}",
        )
        if gate.requires_approval:
            return {"success": False, "error": f"approval required: {gate.category} ({gate.reason})", "approval": gate.to_dict()}
        result = await self._call("browser_upload", {"selector": selector, "files": files, "session_id": session_id})
        return {"success": result.get("status") == "ok", **result.get("result", {}), "error": result.get("error")}

    async def _cap_download(self, selector: str | None = None, url: str | None = None, save_path: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        result = await self._call("browser_download", {"selector": selector, "url": url, "save_path": save_path, "session_id": session_id or self.session_id})
        return {"success": result.get("status") == "ok", **result.get("result", {}), "error": result.get("error")}

    async def _cap_tabs(self, action: str = "list", index: int | None = None, url: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        session_id = session_id or self.session_id
        if action == "new":
            result = await self._call("browser_new_tab", {"url": url, "session_id": session_id})
        elif action == "switch":
            result = await self._call("browser_switch_tab", {"index": int(index or 0), "session_id": session_id})
        elif action == "close":
            result = await self._call("browser_close_tab", {"index": int(index or 0), "session_id": session_id})
        else:
            result = await self._call("browser_list_tabs", {"session_id": session_id})
        return {"success": result.get("status") == "ok", **result.get("result", {}), "error": result.get("error")}

    async def _cap_verify(self, checks: list[dict[str, Any]], session_id: str | None = None) -> dict[str, Any]:
        from core.browser.verification import Check, verify_outcome
        parsed = [Check(kind=str(c.get("kind", "")), expected=str(c.get("expected", "")), negate=bool(c.get("negate", False))) for c in checks]
        outcome = await verify_outcome(parsed, self._call, session_id or self.session_id)
        return {"success": outcome.status == "SUCCESS", **outcome.to_dict()}

    async def _cap_recover(self, action_name: str, params: dict[str, Any] | None = None,
                           alt_selectors: list[str] | None = None) -> dict[str, Any]:
        from core.browser.recovery import RecoveryContext, RecoveryEngine
        recovery = await RecoveryEngine(self._call).recover(RecoveryContext(
            action_name=action_name, params=dict(params or {}), alt_selectors=alt_selectors or [],
        ))
        return {"success": recovery.recovered, **recovery.to_dict()}

    async def _cap_workflow(self, plan: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
        return await execute_workflow(plan, session_id or self.session_id)

    async def _cap_research(self, question: str, max_pages: int = 3, session_id: str | None = None) -> dict[str, Any]:
        from core.tools.browser_research import do_browser_research
        report = await do_browser_research(question=str(question), max_pages=max_pages, session_id=session_id or self.session_id)
        return {"success": bool(report.get("facts")), **report}

    async def _cap_remember(self, site: str, task: str, steps: list[dict[str, Any]],
                            selectors: dict[str, str] | None = None, success: bool = True) -> dict[str, Any]:
        proc_id = self.procedural_memory.record(site, task, steps, success=success, selectors=selectors)
        return {"success": bool(proc_id), "procedure_id": proc_id}

    async def _cap_recall(self, site: str, task: str) -> dict[str, Any]:
        procedure = self.procedural_memory.get(site, task)
        return {"success": procedure is not None, "procedure": procedure}

    async def _cap_report(self) -> dict[str, Any]:
        report = self.report()
        return {"success": True, **report}

    # -- security helpers ---------------------------------------------------
    @staticmethod
    def _classify_with_context(action: str, target: str) -> Any:
        from core.browser.page_security import classify_action
        return classify_action(action, target)

    # -- SpecialistModule sync interface ------------------------------------
    def health_check(self) -> dict[str, Any]:
        """Synchronous health probe for the discovery service (no browser launch)."""
        try:
            from core.browser_manager import BrowserManager
            manager = BrowserManager.instance()
            started = bool(manager._started)
            return {
                "status": CapabilityHealth.HEALTHY.value if started else CapabilityHealth.UNKNOWN.value,
                "details": {"browser_started": started, "sessions": len(manager._sessions)},
            }
        except Exception as exc:
            return {"status": CapabilityHealth.UNHEALTHY.value, "details": {"error": str(exc)}}

    def execute_capability(
        self,
        capability_name: str,
        params: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> SpecialistResult:
        caps = {c.name: c for c in self.get_capabilities()}
        if capability_name not in caps:
            return SpecialistResult(
                success=False,
                error=f"Capability '{capability_name}' not owned by {self.name}. Available: {sorted(caps.keys())}",
            )
        handler = caps[capability_name].handler
        if handler is None:
            return SpecialistResult(success=False, error=f"Capability '{capability_name}' has no handler")
        import asyncio
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    output = pool.submit(lambda: asyncio.run(handler(**(params or {})))).result(timeout=300)
            else:
                output = asyncio.run(handler(**(params or {})))
            success = bool(output.get("success", output.get("status") == "ok")) if isinstance(output, dict) else True
            result = SpecialistResult(success=success, output=output, error=output.get("error") if isinstance(output, dict) else None)
            verified, reason = self.verify(capability_name, result)
            result.verified = verified
            result.verification_reason = reason
            self._emit_outcome_event(capability_name, params, result)
            return result
        except Exception as exc:
            self._emit_outcome_event(
                capability_name, params,
                SpecialistResult(success=False, verified=False,
                                 verification_reason="Exception raised during execution"),
            )
            return SpecialistResult(
                success=False,
                error=f"Execution of {capability_name} failed: {exc}",
                verified=False,
                verification_reason="Exception raised during execution",
            )

    def _emit_outcome_event(self, capability_name: str, params: dict[str, Any], result: SpecialistResult) -> None:
        """Publish verified outcomes to the EventBus for the learning subsystem.

        Goal-level capabilities (workflow/research) emit ``goal.completed`` so
        the experience layer stores a reusable procedure; action primitives
        emit ``action.verified`` for habit tracking.  Publishing is
        best-effort: learning must never break browser execution.
        """
        try:
            from core.event_bus import global_event_bus
            output = result.output if isinstance(result.output, dict) else {}
            goal_level = capability_name in ("browser.execute_workflow", "browser.research")
            goal = str(output.get("goal") or (params or {}).get("goal") or capability_name)
            data = {
                "goal": goal,
                "success": bool(result.success),
                "verified": bool(result.verified),
                "actions": output.get("steps") or output.get("actions") or [{"capability": capability_name}],
                "error": result.error,
                "evidence": {
                    "capability": capability_name,
                    "verification_reason": result.verification_reason,
                },
                "specialist": self.name,
            }
            global_event_bus.publish_sync("goal.completed" if goal_level else "action.verified", data)
        except Exception:
            pass

    def verify(self, capability_name: str, result: SpecialistResult) -> tuple[bool, str]:
        if not result.success:
            return False, f"Execution reported failure: {result.error}"
        per_cap = {
            "browser.navigate": ("result contains url", lambda r: bool((r.output or {}).get("url"))),
            "browser.search": ("search results present", lambda r: bool((r.output or {}).get("results"))),
            "browser.extract": ("extracted text present", lambda r: bool((r.output or {}).get("text"))),
            "browser.verify": ("verification reached a conclusion", lambda r: (r.output or {}).get("status") in ("SUCCESS", "FAILED", "UNCONFIRMED")),
            "browser.execute_workflow": ("workflow reached verified conclusion", lambda r: (r.output or {}).get("status") in ("SUCCESS", "FAILED", "UNCONFIRMED")),
            "browser.research": ("research report produced", lambda r: isinstance(r.output, dict) and "total_facts" in (r.output or {})),
            "browser.remember_procedure": ("procedure stored", lambda r: bool((r.output or {}).get("procedure_id"))),
            "browser.recall_procedure": ("procedure lookup completed", lambda r: "procedure" in (r.output or {})),
        }
        if capability_name in per_cap:
            reason, check = per_cap[capability_name]
            try:
                return bool(check(result)), reason
            except Exception as exc:
                return False, f"verification error: {exc}"
        return True, "verified by default specialist rule"

    # -- recovery / report ---------------------------------------------------
    async def recover(self, action_name: str, params: dict[str, Any] | None = None,
                      alt_selectors: list[str] | None = None) -> dict[str, Any]:
        from core.browser.recovery import RecoveryContext, RecoveryEngine
        recovery = await RecoveryEngine(self._call).recover(RecoveryContext(
            action_name=action_name, params=dict(params or {}), alt_selectors=alt_selectors or [],
        ))
        return recovery.to_dict()

    def report(self) -> dict[str, Any]:
        """Specialist status report for the future Super-Brain."""
        try:
            memory_summary = self.procedural_memory.summary()
        except Exception:
            memory_summary = {}
        return {
            "specialist": self.name,
            "description": self.description,
            "requirements": self.requirements,
            "health_check": self.health_check(),
            "capabilities": [c.name for c in self.get_capabilities()],
            "procedural_memory": memory_summary,
            "security": {
                "page_content_untrusted": True,
                "approval_categories": [
                    "payment", "account_deletion", "publishing", "messaging",
                    "destructive", "credential_access", "sensitive_upload",
                ],
            },
        }


_BROWSER_AI: BrowserAI | None = None


def get_browser_ai() -> BrowserAI:
    """Process-wide BrowserAI instance."""
    global _BROWSER_AI
    if _BROWSER_AI is None:
        _BROWSER_AI = BrowserAI()
    return _BROWSER_AI
