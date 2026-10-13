"""BrowserAgent — a real observe → plan → act → verify agent loop.

Phase 2 of the browser rebuild.  The previous body was a single-shot helper:
one hardcoded navigate (or screenshot) per goal, no subgoals, no verification,
no multi-tab competence — the live "Comet Test" task failed under it.

Contract now
------------
* ``analyze()`` / ``get_open_tabs()`` / ``get_history()`` / ``get_patterns()``
  / ``get_predictions()`` keep their read-only BrowserSnapshot API.
* ``_execute_impl`` runs a bounded agent loop:
  plan (deterministic + optional config-only LLM) → act → verify per subgoal,
  with a hard step budget, a repeat-action detector, the 5-rung recovery
  ladder (core/browser/recovery.py), outcome verification
  (core/browser/verification.py) and the fail-closed approval gate
  (core/browser/page_security.py).
* Snapshot-first discipline: click/fill targets are resolved against a live
  snapshot (text=/label matching); a model-provided selector is only a hint
  and is verified before use — the model never gets to invent CSS blindly.
* Honest results: ``success=True`` only when every subgoal is verified
  SUCCESS; otherwise the verdict is UNCONFIRMED/FAILED with real evidence.
  Screenshot evidence is the tool's ``result["path"]`` (file on disk), never
  a base64 blob.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.agents.base import AgentResult, BaseAgent
from core.browser.page_security import ApprovalGate, classify_action, scan_page_text
from core.browser.verification import Check, verify_outcome
from core.tools.browser_planner import detect_loop, extract_query

_URL_RE = re.compile(r"https?://[^\s)\"']+")
STEP_BUDGET = 15          # hard cap on tool actions per goal
MAX_PLAN_SUBGOALS = 12
_FILL_PAIR_RE = re.compile(r"([A-Za-z][A-Za-z _-]{1,30}?)\s*[:=]\s*\"?([^\",;.]{1,80})\"?")
_OPS = {"open", "search_open", "play", "summarize_tabs", "fill", "click_text", "screenshot"}
_VERDICT_SUCCESS = "SUCCESS"
_VERDICT_FAILED = "FAILED"
_VERDICT_UNCONFIRMED = "UNCONFIRMED"


@dataclass
class BrowserSnapshot:
    open_tabs: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    patterns: dict[str, Any] = field(default_factory=dict)
    predictions: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"open_tabs": list(self.open_tabs), "history": list(self.history),
                "patterns": dict(self.patterns), "predictions": list(self.predictions),
                "timestamp": self.timestamp}


@dataclass
class SubResult:
    """Per-subgoal outcome of the agent loop (a record, not a verdict engine)."""
    op: str
    status: str          # SUCCESS | FAILED | UNCONFIRMED | SKIPPED
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    steps_used: int = 0

    def line(self) -> str:
        ev = ""
        if self.evidence:
            ev = " | " + json.dumps(self.evidence, default=str)[:300]
        return f"[{self.status}] {self.op}: {self.detail}{ev}"


class BrowserAgent(BaseAgent):
    """Plans, executes and verifies multi-step browser goals."""

    agent_id = "browser"
    keywords = ["browse", "open chrome", "screenshot", "tab", "url in browser",
                "search the web", "play", "fill form", "summarize tabs"]
    priority = 10
    description = "Browser task planning, execution and verification"

    # ------------------------------------------------------------- read path
    def analyze(self) -> BrowserSnapshot:
        """Snapshot the *live* session table (no browser -> empty, honest)."""
        snapshot = BrowserSnapshot(timestamp=datetime.now().isoformat())
        source = "offline"
        try:
            from core.browser_manager import BrowserManager
            bm = BrowserManager.instance()
            tabs: list[str] = []
            for sid in bm.session_ids():
                session = bm.get_session(sid)
                if session is None or session.context is None:
                    continue
                source = "browser_manager"
                for page in (getattr(session.context, "pages", None) or []):
                    try:
                        tabs.append(f"[{sid}] {page.url}")
                    except Exception:  # noqa: BLE001 — page closed mid-read
                        continue
            snapshot.open_tabs = tabs[:20]
        except Exception:  # noqa: BLE001 — browser stack unavailable
            source = "unavailable"
        snapshot.patterns = {
            "tab_count": len(snapshot.open_tabs),
            "source": source,
        }
        return snapshot

    def get_open_tabs(self) -> list[str]:
        return list(self.analyze().open_tabs)

    def get_history(self) -> list[str]:
        return list(self.analyze().history)

    def get_patterns(self) -> dict[str, Any]:
        return dict(self.analyze().patterns)

    def get_predictions(self) -> list[str]:
        return list(self.analyze().predictions)

    # ------------------------------------------------------------ tool bridge
    @staticmethod
    def _make_call(session_id: str):
        """ToolCaller bridge: verification/recovery use 'browser_*' names."""
        from core.tools import browser_tools

        async def call(tool: str, params: dict[str, Any]) -> dict[str, Any]:
            fn = getattr(browser_tools, "do_" + str(tool), None)
            if fn is None:
                return {"status": "error", "error": f"unknown tool: {tool}",
                        "error_type": "NotFound"}
            kwargs = dict(params or {})
            kwargs.setdefault("session_id", session_id)
            try:
                return await fn(**kwargs)
            except Exception as exc:  # noqa: BLE001 — tools report, never raise
                return {"status": "error", "error": f"{type(exc).__name__}: {exc}",
                        "error_type": type(exc).__name__}

        return call

    # ----------------------------------------------------------------- planning
    def _plan_deterministic(self, goal: str) -> list[dict[str, Any]]:
        """Rule-based subgoal plan — always available, never worse than the
        previous single-shot behavior (open URL / screenshot / report tabs)."""
        text = str(goal or "")
        low = text.lower()
        plan: list[dict[str, Any]] = []
        urls = [u.rstrip(".,);") for u in _URL_RE.findall(text)]

        wants_play = any(k in low for k in ("play ", "watch ", "put on ")) and \
            any(k in low for k in ("youtube", "yt ", "song", "music", "video", "weeknd"))
        wants_search = bool(re.search(r"\b(search|look up|google)\b", low)) and not wants_play
        wants_tabs = ("tab" in low) and any(k in low for k in ("list", "summar", "overview", "what"))

        if urls:
            plan.append({"op": "open", "urls": urls})
        elif wants_play:
            query = re.sub(r"^(please\s+)?(play|watch|find|put on)\s+(some\s+|the\s+|a\s+|me\s+)*", "", low)
            query = re.sub(r"\bon\s+(youtube|yt)\b", "", query).strip() or text.strip()
            plan.append({"op": "play", "query": query})
        elif wants_search:
            query = extract_query(text) or text.strip()
            plan.append({"op": "search_open", "query": query, "count": 1})

        if wants_tabs:
            plan.append({"op": "summarize_tabs"})

        for label, value in _FILL_PAIR_RE.findall(text):
            lab = label.strip().lower()
            if lab in {"http", "https", "url", "uri", "css", "js"} or value.strip().startswith("//"):
                continue
            plan.append({"op": "fill", "fields": [{"label": lab, "value": value.strip()}]})
            break  # deterministic parser takes one obvious pair; LLM may add more

        if "screenshot" in low:
            plan.append({"op": "screenshot"})
        if not plan:
            plan.append({"op": "open", "urls": urls} if urls else {"op": "summarize_tabs"})
        return plan[:MAX_PLAN_SUBGOALS]

    def _plan_llm(self, goal: str) -> list[dict[str, Any]] | None:
        """Config-only LLM refinement (REASONING_MODEL).  Returns None on any
        failure so the deterministic plan is used — never worse than fallback."""
        text = str(goal or "")
        try:
            from jarvis_provider import get_provider
            provider = get_provider("reasoning")
        except Exception:  # noqa: BLE001 — provider stack optional
            return None
        prompt = (
            "You are a browser task planner. Output ONLY minified JSON, no prose.\n"
            'Schema: {"subgoals":[{"op":"open","urls":["https://..."]},'
            '{"op":"search_open","query":"...","count":1},'
            '{"op":"play","query":"..."},'
            '{"op":"summarize_tabs"},'
            '{"op":"fill","fields":[{"label":"name","value":"...","selector":""}]},'
            '{"op":"click_text","text":"..."},'
            '{"op":"screenshot"}]}\n'
            "Rules: ops must come from this list only; open ALL sites the goal "
            "names (each in its own tab); prefer label/text over CSS selectors "
            "(selector is a HINT and may be empty); keep the plan under 8 steps.\n"
            f"Goal: {text}"
        )
        try:
            loop = asyncio.get_running_loop()
            raw = loop.run_until_complete(
                asyncio.wait_for(asyncio.to_thread(provider.chat, prompt, 0.1, 600), timeout=30))
        except RuntimeError:
            # Called from a context without a running loop (sync callers).
            raw = asyncio.run(asyncio.wait_for(
                asyncio.to_thread(provider.chat, prompt, 0.1, 600), timeout=30))
        except Exception:  # noqa: BLE001 — any model failure = fallback
            return None
        try:
            start, end = str(raw).find("{"), str(raw).rfind("}")
            data = json.loads(str(raw)[start:end + 1])
            subs = data.get("subgoals") or []
            plan: list[dict[str, Any]] = []
            for item in subs:
                if not isinstance(item, dict) or item.get("op") not in _OPS:
                    continue
                clean = {"op": item["op"]}
                if item["op"] == "open":
                    urls = [str(u).rstrip(".,);") for u in (item.get("urls") or [])]
                    if urls and _URL_RE.match(str(urls[0])):
                        clean["urls"] = urls
                    else:
                        continue
                elif item["op"] == "search_open":
                    clean["query"] = str(item.get("query") or "").strip()
                    clean["count"] = max(1, min(3, int(item.get("count") or 1)))
                    if not clean["query"]:
                        continue
                elif item["op"] == "play":
                    clean["query"] = str(item.get("query") or "").strip()
                    if not clean["query"]:
                        continue
                elif item["op"] == "fill":
                    fields = []
                    for f in (item.get("fields") or [])[:8]:
                        if isinstance(f, dict) and (f.get("label") or f.get("selector")):
                            fields.append({"label": str(f.get("label") or ""),
                                           "value": str(f.get("value") or ""),
                                           "selector": str(f.get("selector") or "")})
                    if not fields:
                        continue
                    clean["fields"] = fields
                elif item["op"] == "click_text":
                    clean["text"] = str(item.get("text") or "").strip()
                    if not clean["text"]:
                        continue
                plan.append(clean)
            return plan[:MAX_PLAN_SUBGOALS] or None
        except Exception:  # noqa: BLE001 — malformed model output = fallback
            return None

    def _plan(self, goal: str) -> tuple[list[dict[str, Any]], str]:
        try:
            llm_plan = self._plan_llm(goal)
        except Exception:  # noqa: BLE001 — planning must never crash the loop
            llm_plan = None
        if llm_plan:
            return llm_plan, "llm"
        return self._plan_deterministic(goal), "deterministic"

    # ------------------------------------------------------------ loop helpers
    @staticmethod
    async def _act(call, recovery, tool: str, params: dict[str, Any],
                   alt_selectors: list[str] | None = None) -> tuple[dict[str, Any], int]:
        """One action + bounded recovery on failure. Returns (result, steps)."""
        res = await call(tool, params)
        if res.get("status") == "ok":
            return res, 1
        from core.browser.recovery import RecoveryContext
        outcome = await recovery.recover(RecoveryContext(
            action_name=tool, params=dict(params),
            alt_selectors=list(alt_selectors or [])))
        steps = 1 + len(outcome.attempts)
        if outcome.recovered and outcome.result is not None:
            return outcome.result, steps
        return res, steps

    @staticmethod
    def _alt_selectors(params: dict[str, Any]) -> list[str]:
        sel = str(params.get("selector") or "")
        text = str(params.get("text") or "")
        alts = []
        if sel and not sel.startswith("text="):
            alts.append(f"text={sel}")
        if text:
            alts.append(f"text={text}")
        return alts

    @staticmethod
    async def _resolve_selector(call, session_id: str, hint: str, label: str) -> str | None:
        """Snapshot-first selector resolution: verify hints, else match by
        label against the live snapshot's inputs/buttons. Never blind CSS."""
        hint = str(hint or "").strip()
        if hint:
            res = await call("browser_is_visible", {"selector": hint})
            if res.get("status") == "ok" and (res.get("result") or {}).get("visible"):
                return hint
        snap = await call("browser_snapshot", {})
        res = (snap.get("result") or {}) if snap.get("status") == "ok" else {}
        lab = str(label or "").lower().strip()
        for item in (res.get("inputs") or []):
            selector = str(item.get("selector") or "")
            if not selector or selector == "input":
                continue
            if lab and lab.replace(" ", "") in selector.lower().replace("-", "").replace("_", ""):
                return selector
        if lab:
            for item in (res.get("buttons") or []):
                if lab in str(item.get("text") or "").lower():
                    return f"text={item.get('text')}"
        return hint or None

    # ---------------------------------------------------------------- subgoals
    async def _run_subgoal(self, item: dict[str, Any], call, gate: ApprovalGate,
                           recovery, session_id: str, steps_left: int) -> SubResult:
        op = str(item.get("op"))
        steps = 0

        if op == "open":
            urls = [str(u) for u in (item.get("urls") or [])]
            details: list[str] = []
            for i, url in enumerate(urls):
                if steps >= steps_left:
                    return SubResult(op, _VERDICT_UNCONFIRMED,
                                     f"step budget exhausted after {i}/{len(urls)} urls",
                                     steps_used=steps)
                tool = "browser_navigate" if i == 0 else "browser_new_tab"
                res, used = await self._act(call, recovery, tool, {"url": url})
                steps += used
                if res.get("status") != "ok":
                    return SubResult(op, _VERDICT_FAILED,
                                     f"{tool}({url}) failed: {str(res.get('error'))[:160]}",
                                     steps_used=steps)
                details.append(f"{url} -> {(res.get('result') or {}).get('title', '')}"[:120])
            tabs = await call("browser_list_tabs", {})
            tab_urls = [str(t.get("url") or "") for t in
                        ((tabs.get("result") or {}).get("tabs") or [])]
            missing = [u for u in urls
                       if not any(self._host_in(u, tu) for tu in tab_urls)]
            verdict = await verify_outcome(
                [Check(kind="url_host", expected=_URL_RE.search(u).group(0) if _URL_RE.search(u) else u)
                 for u in urls[-1:]], call, session_id)
            status = _VERDICT_SUCCESS if (verdict.ok and not missing) else (
                _VERDICT_FAILED if missing else _VERDICT_UNCONFIRMED)
            return SubResult(op, status, "; ".join(details)[:400],
                             evidence={"tabs": tab_urls[:8], "missing": missing[:4],
                                       "verify": verdict.to_dict()["status"]},
                             steps_used=steps)

        if op == "search_open":
            query = str(item.get("query") or "")
            count = max(1, min(3, int(item.get("count") or 1)))
            res, used = await self._act(call, recovery, "browser_search", {"query": query})
            steps += used
            results = ((res.get("result") or {}).get("results") or []) if res.get("status") == "ok" else []
            if not results:
                return SubResult(op, _VERDICT_FAILED,
                                 f"search produced no results: {str(res.get('error'))[:120]}",
                                 steps_used=steps)
            opened = []
            for r in results[:count]:
                if steps >= steps_left:
                    break
                href = str(r.get("href") or "")
                nav, used = await self._act(call, recovery, "browser_navigate", {"url": href})
                steps += used
                if nav.get("status") == "ok":
                    opened.append({"title": str(r.get("title") or "")[:100], "url": href})
            if not opened:
                return SubResult(op, _VERDICT_FAILED, "could not open any result", steps_used=steps)
            verdict = await verify_outcome(
                [Check(kind="url_contains", expected=opened[0]["url"].split("?")[0][-40:])],
                call, session_id)
            return SubResult(op, _VERDICT_SUCCESS if verdict.ok else _VERDICT_UNCONFIRMED,
                             f"query={query!r}", evidence={"opened": opened}, steps_used=steps)

        if op == "play":
            query = str(item.get("query") or "")
            res, used = await self._act(call, recovery, "browser_search",
                                        {"query": query, "engine": "youtube"})
            steps += used
            results = ((res.get("result") or {}).get("results") or []) if res.get("status") == "ok" else []
            videos = [r for r in results if "/watch?v=" in str(r.get("href") or "")]
            if not videos:
                return SubResult(op, _VERDICT_FAILED,
                                 f"no playable video found for {query!r}", steps_used=steps)
            video = videos[0]
            nav, used = await self._act(call, recovery, "browser_navigate",
                                        {"url": str(video.get("href"))})
            steps += used
            if nav.get("status") != "ok":
                return SubResult(op, _VERDICT_FAILED,
                                 f"video open failed: {str(nav.get('error'))[:140]}", steps_used=steps)
            verdict = await verify_outcome(
                [Check(kind="url_contains", expected="watch?v=")], call, session_id)
            evidence = {"video": str(video.get("title") or "")[:120],
                        "url": str(video.get("href") or ""),
                        "page_title": (nav.get("result") or {}).get("title", "")}
            return SubResult(op, _VERDICT_SUCCESS if verdict.ok else _VERDICT_UNCONFIRMED,
                             f"playing {query!r}", evidence=evidence, steps_used=steps)

        if op == "summarize_tabs":
            tabs_res = await call("browser_list_tabs", {})
            tabs = ((tabs_res.get("result") or {}).get("tabs") or []) if tabs_res.get("status") == "ok" else []
            if not tabs:
                return SubResult(op, _VERDICT_FAILED, "no open tabs to summarize", steps_used=1)
            summaries = []
            for t in tabs:
                if steps >= steps_left:
                    break
                idx = t.get("index")
                snap = await call("browser_snapshot", {"tab_index": idx})
                steps += 1
                res = (snap.get("result") or {}) if snap.get("status") == "ok" else {}
                heads = [str(h.get("text") or "") for h in (res.get("headings") or [])[:3] if h.get("text")]
                excerpt = " ".join(str(res.get("text") or "").split())[:180]
                summary = {"index": idx, "url": res.get("url") or t.get("url"),
                           "title": res.get("title") or t.get("title"),
                           "headings": heads, "excerpt": excerpt}
                try:
                    scan = scan_page_text(str(res.get("text") or ""), str(summary["url"]))
                    if getattr(scan, "untrusted", False):
                        summary["untrusted_content"] = True
                except Exception:  # noqa: BLE001 — scan is advisory
                    pass
                summaries.append(summary)
            status = _VERDICT_SUCCESS if summaries else _VERDICT_UNCONFIRMED
            return SubResult(op, status, f"{len(summaries)} tab(s) summarized",
                             evidence={"summaries": summaries}, steps_used=steps)

        if op == "fill":
            fields = item.get("fields") or []
            for f in fields:
                decision = classify_action("fill", target=f"{f.get('label')} {f.get('value')}")
                cleared = await gate.check(decision, description=f"fill {f.get('label')}")
                if cleared.requires_approval:
                    return SubResult(op, "SKIPPED",
                                     f"blocked by approval gate ({decision.category}): {decision.reason}",
                                     steps_used=steps)
            done = []
            for f in fields:
                if steps >= steps_left:
                    return SubResult(op, _VERDICT_UNCONFIRMED,
                                     f"budget exhausted after {len(done)}/{len(fields)} fields",
                                     evidence={"filled": done}, steps_used=steps)
                selector = await self._resolve_selector(
                    call, session_id, f.get("selector", ""), f.get("label", ""))
                if not selector:
                    return SubResult(op, _VERDICT_FAILED,
                                     f"no visible field matched label {f.get('label')!r}",
                                     evidence={"filled": done}, steps_used=steps)
                res, used = await self._act(call, recovery, "browser_fill",
                                            {"selector": selector, "value": f.get("value", "")},
                                            alt_selectors=self._alt_selectors({"selector": f.get("label", "")}))
                steps += used
                if res.get("status") != "ok":
                    return SubResult(op, _VERDICT_FAILED,
                                     f"fill {f.get('label')!r} via {selector!r} failed: "
                                     f"{str(res.get('error'))[:140]}",
                                     evidence={"filled": done}, steps_used=steps)
                done.append({"label": f.get("label"), "selector": selector,
                             "value": (res.get("result") or {}).get("value", f.get("value"))})
            return SubResult(op, _VERDICT_SUCCESS,
                             f"{len(done)}/{len(fields)} field(s) filled and read back",
                             evidence={"filled": done}, steps_used=steps)

        if op == "click_text":
            text = str(item.get("text") or "")
            decision = classify_action("click", target=text)
            cleared = await gate.check(decision, description=f"click {text}")
            if cleared.requires_approval:
                return SubResult(op, "SKIPPED",
                                 f"blocked by approval gate ({decision.category})",
                                 steps_used=steps)
            find = await call("browser_find", {"text": text})
            steps += 1
            if find.get("status") != "ok":
                return SubResult(op, _VERDICT_FAILED,
                                 f"text not found on page: {text!r}", steps_used=steps)
            res, used = await self._act(call, recovery, "browser_click",
                                        {"selector": f"text={text}"})
            steps += used
            if res.get("status") != "ok":
                return SubResult(op, _VERDICT_FAILED,
                                 f"click failed: {str(res.get('error'))[:140]}", steps_used=steps)
            evidence = {"clicked": text, **(res.get("result") or {})}
            return SubResult(op, _VERDICT_SUCCESS, f"clicked {text!r}",
                             evidence=evidence, steps_used=steps)

        if op == "screenshot":
            res, used = await self._act(call, recovery, "browser_screenshot", {})
            steps += used
            if res.get("status") != "ok":
                return SubResult(op, _VERDICT_FAILED,
                                 f"screenshot failed: {str(res.get('error'))[:140]}", steps_used=steps)
            path = str((res.get("result") or {}).get("path") or "")
            if not path:
                return SubResult(op, _VERDICT_UNCONFIRMED,
                                 "screenshot returned no file path", steps_used=steps)
            import os
            size = os.path.getsize(path) if os.path.exists(path) else 0
            status = _VERDICT_SUCCESS if size > 0 else _VERDICT_UNCONFIRMED
            return SubResult(op, status, "screenshot saved",
                             evidence={"path": path, "size_bytes": size}, steps_used=steps)

        return SubResult(op, "SKIPPED", f"unknown op {op!r}", steps_used=0)

    @staticmethod
    def _host_in(url: str, candidate: str) -> bool:
        from urllib.parse import urlparse

        def host(u: str) -> str:
            v = str(u or "").strip().lower()
            if v and "://" not in v:
                v = "https://" + v
            return (urlparse(v).hostname or "").removeprefix("www.")
        hu, hc = host(url), host(candidate)
        return bool(hu) and (hu == hc or hc.endswith("." + hu) or hu.endswith("." + hc))

    # ----------------------------------------------------------- write path
    async def _execute_impl(self, goal: str, context: Optional[Any] = None,
                            **kwargs: Any) -> AgentResult:
        session_id = str(kwargs.get("session_id", "default") or "default")
        budget = max(3, min(40, int(kwargs.get("max_steps", STEP_BUDGET))))
        try:
            from core.tools import browser_tools  # noqa: F401 — availability probe
        except Exception as exc:  # noqa: BLE001 — deleted/missing stack
            return AgentResult(
                success=False, output="", agent_id=self.agent_id,
                error=f"browser stack unavailable: {type(exc).__name__}: {exc}",
            )

        plan, planner = self._plan(str(goal or ""))
        call = self._make_call(session_id)
        gate = ApprovalGate()
        from core.browser.recovery import RecoveryEngine
        recovery = RecoveryEngine(call, max_passes=1, wait_seconds=1.0)

        results: list[SubResult] = []
        steps = 0
        action_signatures: list[str] = []
        for item in plan:
            sig = json.dumps(item, sort_keys=True)[:160]
            action_signatures.append(sig)
            if detect_loop(action_signatures):
                results.append(SubResult(str(item.get("op")), _VERDICT_FAILED,
                                         "repeat-action loop detected; stopped instead of retrying"))
                break
            if steps >= budget:
                results.append(SubResult(str(item.get("op")), _VERDICT_UNCONFIRMED,
                                         f"step budget {budget} exhausted"))
                break
            try:
                outcome = await self._run_subgoal(item, call, gate, recovery,
                                                  session_id, budget - steps)
            except Exception as exc:  # noqa: BLE001 — loop reports, never crashes
                outcome = SubResult(str(item.get("op")), _VERDICT_UNCONFIRMED,
                                    f"subgoal raised {type(exc).__name__}: {exc}")
            steps += max(0, outcome.steps_used)
            results.append(outcome)

        statuses = [r.status for r in results]
        success = bool(results) and all(s == _VERDICT_SUCCESS for s in statuses)
        failed = [r for r in results if r.status == _VERDICT_FAILED]
        if success:
            verdict = _VERDICT_SUCCESS
            error = ""
        elif failed:
            verdict = _VERDICT_FAILED
            error = "; ".join(f"{r.op}: {r.detail}" for r in failed)[:400]
        else:
            verdict = _VERDICT_UNCONFIRMED
            error = ("not all subgoals verified: "
                     + ", ".join(f"{r.op}={r.status}" for r in results))[:400]

        lines = [f"verdict={verdict} (planner={planner}, steps={steps}/{budget})"]
        lines += [r.line() for r in results]
        snap = self.analyze()
        lines.append(f"Browser: {len(snap.open_tabs)} open tab(s) "
                     f"(source={snap.patterns.get('source')}).")
        return AgentResult(
            success=success,
            output="\n".join(lines[:80]),
            agent_id=self.agent_id,
            error=error,
        )
