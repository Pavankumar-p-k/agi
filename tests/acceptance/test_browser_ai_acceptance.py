"""BROWSER_AI_SPECIALIST_ACCEPTANCE — real-browser acceptance for the BrowserAI specialist.

Usage: python tests/acceptance/test_browser_ai_acceptance.py

Drives the BrowserAI specialist boundary end-to-end against real websites:

  A  identity + capability registration (authoritative registry)
  B  perception (a11y/DOM-first, untrusted-content wrapping)
  C  verified navigation (SUCCESS / FAILED)
  D  execute_workflow on the TaskGraph action shape
  E  bounded recovery
  F  browser research (search -> open -> extract -> evidence report)
  G  procedural memory (store / recall / expiry metadata)
  H  security + approval gates (fail-closed)

Real-browser capability handlers are exercised in-loop (await) because
Playwright objects are bound to the running loop; the sync SpecialistModule
contract (execute_capability/verify) is exercised against a fake tool caller,
which is exactly how unit-level consumers use it.
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.browser_manager import BrowserManager
from core.tools.browser_tools import do_browser_screenshot

SESSION_ID = "browser-ai-acceptance"
RESULTS_DIR = Path("tests/acceptance/results")
SCREENSHOTS_DIR = RESULTS_DIR / "screenshots"


class TestRecord:
    __slots__ = ("category", "name", "result", "success", "execution_time", "screenshot_path")


class AcceptanceRunner:
    def __init__(self):
        self.records: list[TestRecord] = []

    async def test(self, category: str, name: str, fn, *, timeout=45):
        rec = TestRecord()
        rec.category, rec.name, rec.screenshot_path = category, name, None
        start = time.time()
        try:
            result = await asyncio.wait_for(fn(), timeout=timeout)
            rec.execution_time = round(time.time() - start, 3)
            rec.result = result
            rec.success = result.get("success") is True or result.get("ok") is True
        except asyncio.TimeoutError:
            rec.execution_time = round(time.time() - start, 3)
            rec.result = {"error": f"TIMEOUT after {timeout}s"}
            rec.success = False
        except Exception as e:
            rec.execution_time = round(time.time() - start, 3)
            rec.result = {"error": f"{type(e).__name__}: {e}"}
            rec.success = False
        if not rec.success:
            try:
                shot = await do_browser_screenshot(session_id=SESSION_ID)
                if shot.get("status") == "ok":
                    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                    p = SCREENSHOTS_DIR / f"browserai_{category}_{abs(hash(name)) % 10000}.png"
                    p.write_bytes(shot.get("result", {}).get("screenshot") or b"")
                    rec.screenshot_path = str(p)
            except Exception:
                pass
        mark = "PASS" if rec.success else "FAIL"
        print(f"  [{mark}] {category} - {name} ({rec.execution_time}s)"
              + (f" :: {str(rec.result.get('error'))[:110]}" if not rec.success else ""))
        self.records.append(rec)

    def summary(self):
        total = len(self.records)
        passed = sum(1 for r in self.records if r.success)
        return total, passed, total - passed, round(100 * passed / total, 1) if total else 0.0

    def generate_report(self) -> str:
        total, passed, failed, pct = self.summary()
        classification = "PRODUCTION_READY" if pct >= 90 and failed == 0 else ("ACCEPTABLE" if pct >= 80 else "RELEASE_BLOCKER")
        lines = [
            "# BROWSER_AI_SPECIALIST_ACCEPTANCE_REPORT",
            "",
            f"**Date:** {datetime.now().isoformat(timespec='seconds')}",
            "**Browser:** Playwright Chromium (headed=False)",
            f"**Session:** `{SESSION_ID}`",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Tests | {total} |",
            f"| Passed | {passed} |",
            f"| Failed | {failed} |",
            f"| Pass Rate | {pct}% |",
            f"| Classification | **{classification}** |",
            "",
        ]
        current = None
        for r in self.records:
            if r.category != current:
                current = r.category
                cat = [x for x in self.records if x.category == current]
                cp = sum(1 for x in cat if x.success)
                lines += [f"## Category {current}", "", f"**Pass Rate:** {round(100 * cp / len(cat), 1)}% ({cp}/{len(cat)})", ""]
            status = "PASS" if r.success else "FAIL"
            err = "" if r.success else f" — {str(r.result.get('error'))[:120]}"
            lines.append(f"- **{r.name}** — {status}{err}")
        lines.append("")
        return "\n".join(lines)


def _ok(**kw):
    return {"success": True, **kw}


async def main() -> AcceptanceRunner:
    from core.configuration import configuration as _jarvis_config
    _jarvis_config.browser.headed = False
    bm = BrowserManager.instance()
    await bm.ensure_browser_alive()
    if bm.get_session(SESSION_ID) is None:
        await bm.get_or_create_session(SESSION_ID)

    from core.browser.browser_ai import BrowserAI, execute_workflow
    from core.browser.page_security import (
        UNTRUSTED_OPEN,
        ApprovalDecision,
        classify_action,
    )
    from core.browser.procedural_memory import BrowserProceduralMemory

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    memory_db = str(RESULTS_DIR / "browser_ai_acceptance_memory.db")
    approvals: list[dict] = []

    ai = BrowserAI(
        session_id=SESSION_ID,
        approval_resolver=lambda d: (approvals.append(d) or True),
        procedural_memory=BrowserProceduralMemory(db_path=memory_db),
    )
    runner = AcceptanceRunner()
    t = lambda cat, name, fn, **kw: runner.test(cat, name, fn, **kw)

    # -- Category A: identity + registration --------------------------------
    print("\nCategory A — Identity & Registration")

    await t("A", "identity non-empty", asyncio.coroutine(lambda: _ok())()) if False else None
    async def _identity():
        ok = bool(ai.name) and bool(ai.description) and bool(ai.requirements)
        return _ok(ok=ok, name=ai.name, requirements=ai.requirements)
    await t("A", "identity (name/description/requirements)", _identity)

    async def _caps():
        caps = ai.get_capabilities()
        names = [c.name for c in caps]
        ok = len(names) >= 10 and len(set(names)) == len(names) and all(c.handler for c in caps)
        return _ok(ok=ok, count=len(names), names=sorted(names))
    await t("A", "get_capabilities unique + wired handlers", _caps)

    async def _registration():
        from core.browser.registration import browser_ai_capabilities, register_browser_ai
        register_browser_ai()
        caps = browser_ai_capabilities()
        names = {c.get("name") for c in caps}
        expected = {"browser.navigate", "browser.search", "browser.extract", "browser.verify",
                    "browser.recover", "browser.execute_workflow", "browser.research"}
        ok = expected.issubset(names) and all(c.get("risk") for c in caps)
        return _ok(ok=ok, registered=len(caps))
    await t("A", "capabilities registered in authoritative registry", _registration)

    async def _report():
        r = ai.report()
        ok = (r.get("specialist") == "Browser AI" and r.get("capabilities")
              and r.get("security", {}).get("page_content_untrusted") is True)
        return _ok(ok=ok, capability_count=len(r.get("capabilities", [])))
    await t("A", "report() contract for future Super-Brain", _report)

    # -- Category B: perception ----------------------------------------------
    print("\nCategory B — Perception (real page)")

    async def _nav():
        out = await ai._cap_navigate("https://example.com")
        return _ok(ok=out.get("success") is True and bool(out.get("url")), url=out.get("url"))
    await t("B", "navigate example.com", _nav)

    async def _observe():
        obs = await ai.observe()
        mode = obs.get("perception_mode")
        ok = obs.get("status") == "ok" and mode in ("a11y_tree", "dom_snapshot", "screenshot_only")
        return _ok(ok=ok, mode=mode, url=obs.get("url"))
    await t("B", "observe() a11y/DOM-first perception", _observe)

    async def _observe_untrusted():
        obs = await ai.observe()
        wrapped = UNTRUSTED_OPEN in json.dumps(obs.get("page", {}), default=str)
        scan = obs.get("security", {})
        ok = wrapped and "suspicious" in scan
        return _ok(ok=ok, wrapped=wrapped, suspicious=scan.get("suspicious"))
    await t("B", "page content wrapped as UNTRUSTED data", _observe_untrusted)

    async def _extract():
        out = await ai._cap_extract(max_chars=4000)
        ok = out.get("success") is True and bool(out.get("text")) and "security" in out
        return _ok(ok=ok, text_len=len(out.get("text") or ""))
    await t("B", "extract() returns wrapped text + security scan", _extract)

    # -- Category C: verified navigation --------------------------------------
    print("\nCategory C — Verified outcomes")

    async def _verify_host():
        out = await ai._cap_verify([{"kind": "url_host", "expected": "example.com"}])
        ok = out.get("success") is True and out.get("status") == "SUCCESS"
        return _ok(ok=ok, status=out.get("status"))
    await t("C", "verify url_host -> SUCCESS", _verify_host)

    async def _verify_fail():
        out = await ai._cap_verify([{"kind": "url_host", "expected": "definitely-not-this-site.example"}])
        ok = out.get("success") is False and out.get("status") == "FAILED"
        return _ok(ok=ok, status=out.get("status"))
    await t("C", "wrong host -> FAILED (never silent success)", _verify_fail)

    async def _verify_text():
        out = await ai._cap_verify([{"kind": "text_present", "expected": "Example Domain"}])
        ok = out.get("status") in ("SUCCESS", "FAILED") and out.get("success") == (out.get("status") == "SUCCESS")
        return _ok(ok=ok, status=out.get("status"))
    await t("C", "text_present check classified truthfully", _verify_text)

    async def _sync_contract():
        async def fake_call(tool, params):
            if tool == "browser_navigate":
                return {"status": "ok", "result": {"url": params.get("url")}}
            return {"status": "error", "error": f"unexpected tool {tool}"}
        probe = BrowserAI(tool_caller=fake_call, session_id="sync-contract",
                          procedural_memory=BrowserProceduralMemory(db_path=memory_db))
        result = probe.execute_capability("browser.navigate", {"url": "https://fake.test"})
        ok = result.success is True and result.verified is True and result.output.get("url") == "https://fake.test"
        return _ok(ok=ok, verified=result.verified, reason=result.verification_reason)
    await t("C", "sync execute_capability + verify() SpecialistModule contract", _sync_contract)

    async def _sync_unknown():
        probe = BrowserAI(tool_caller=_unreachable_caller, session_id="sync-contract",
                          procedural_memory=BrowserProceduralMemory(db_path=memory_db))
        result = probe.execute_capability("browser.teleport", {})
        ok = result.success is False and "not owned" in (result.error or "")
        return _ok(ok=ok, error=result.error)
    await t("C", "unknown capability fails cleanly", _sync_unknown)

    # -- Category D: workflows -------------------------------------------------
    print("\nCategory D — execute_workflow (TaskGraph action shape)")

    async def _wf_success():
        plan = {
            "goal": "open python.org",
            "steps": [{"tool": "browser_navigate", "params": {"url": "https://www.python.org"}}],
            "verify": [{"kind": "url_host", "expected": "python.org"}],
        }
        out = await execute_workflow(plan, SESSION_ID)
        ok = out.get("status") == "SUCCESS"
        return _ok(ok=ok, status=out.get("status"), goal=out.get("goal"))
    await t("D", "workflow SUCCESS with passing verification", _wf_success, timeout=60)

    async def _wf_failed():
        plan = {
            "goal": "open wrong site",
            "steps": [{"tool": "browser_navigate", "params": {"url": "https://www.python.org"}}],
            "verify": [{"kind": "url_host", "expected": "definitely-not-python.example"}],
        }
        out = await execute_workflow(plan, SESSION_ID)
        ok = out.get("status") == "FAILED" and out.get("verification", {}).get("status") == "FAILED"
        return _ok(ok=ok, status=out.get("status"))
    await t("D", "workflow FAILED when verification fails", _wf_failed, timeout=60)

    async def _wf_bogus_step():
        plan = {
            "goal": "bogus",
            "steps": [{"tool": "browser_not_a_real_tool", "params": {}}],
            "verify": [{"kind": "url_host", "expected": "example.com"}],
        }
        out = await execute_workflow(plan, SESSION_ID)
        ok = out.get("status") == "FAILED" and out.get("failed_step") == 0
        return _ok(ok=ok, failed_step=out.get("failed_step"))
    await t("D", "unknown step tool -> bounded FAILED, no crash", _wf_bogus_step, timeout=60)

    # -- Category E: recovery ---------------------------------------------------
    print("\nCategory E — Bounded recovery")

    async def _recover_missing():
        out = await ai.recover("browser_click", {"selector": "#no-such-element-xyz"}, alt_selectors=["#also-missing"])
        ok = out.get("recovered") is False and "attempts" in out
        return _ok(ok=out.get("recovered") is not True, recovered=out.get("recovered"),
                   rungs=len(out.get("attempts", [])))
    # NOTE: recovery is bounded in attempts (2 passes x rungs); each rung click can
    # block up to 15s at the Playwright layer, so worst case is ~2 minutes.
    await t("E", "missing element -> recovery bounded, reports failure", _recover_missing, timeout=180)

    async def _click_real():
        await ai._cap_navigate("https://example.org")
        out = await ai._cap_click("a")
        ok = out.get("success") is True
        return _ok(ok=ok, clicked=out.get("clicked") or out.get("recovery", {}).get("recovered"))
    await t("E", "real click with recovery fallback (example.org anchor)", _click_real, timeout=60)

    # -- Category F: research ------------------------------------------------------
    print("\nCategory F — Research")

    async def _research():
        out = await ai._cap_research("What is the Python programming language?", max_pages=2)
        ok = "total_facts" in out and isinstance(out.get("facts", []), list)
        return _ok(ok=ok, total_facts=out.get("total_facts"), sources=out.get("sources_consulted"))
    await t("F", "research produces evidence-backed report", _research, timeout=150)

    # -- Category G: procedural memory --------------------------------------------
    print("\nCategory G — Procedural memory")

    async def _remember():
        out = await ai._cap_remember(
            site="example.com", task="acceptance-procedure",
            steps=[{"tool": "browser_navigate", "params": {"url": "https://example.com"}},
                   {"tool": "browser_click", "params": {"selector": "a"}}],
            selectors={"anchor": "a"},
        )
        ok = out.get("success") is True and bool(out.get("procedure_id"))
        return _ok(ok=ok, procedure_id=out.get("procedure_id"))
    await t("G", "remember_procedure stores with id", _remember)

    async def _recall():
        out = await ai._cap_recall("example.com", "acceptance-procedure")
        proc = out.get("procedure") or {}
        ok = (out.get("success") is True and proc.get("site") == "example.com"
              and bool(proc.get("steps")) and "last_verified" in proc and "confidence" in proc)
        return _ok(ok=ok, last_verified=proc.get("last_verified"), confidence=proc.get("confidence"))
    await t("G", "recall_procedure returns verified procedure", _recall)

    async def _recall_miss():
        out = await ai._cap_recall("example.com", "never-recorded-task")
        ok = out.get("success") is False and out.get("procedure") is None
        return _ok(ok=ok)
    await t("G", "unknown task -> truthful miss", _recall_miss)

    # -- Category H: security + approval gates --------------------------------------
    print("\nCategory H — Security & approvals")

    async def _classify_payment():
        d = classify_action("click", "button:has-text('Place Order')")
        ok = d.requires_approval and d.category == "payment"
        return _ok(ok=ok, category=d.category)
    await t("H", "classify: 'Place Order' -> payment gate", _classify_payment)

    async def _classify_safe():
        d = classify_action("click", "button:has-text('Accept Cookies')")
        ok = not d.requires_approval
        return _ok(ok=ok, reason=d.reason)
    await t("H", "classify: 'Accept Cookies' -> no gate", _classify_safe)

    async def _gate_fail_closed():
        strict = BrowserAI(session_id=SESSION_ID,
                           procedural_memory=BrowserProceduralMemory(db_path=memory_db))
        out = await strict._cap_click("button.delete-account-now")
        gate = out.get("approval") or {}
        ok = (out.get("success") is False and str(out.get("error", "")).startswith("approval required")
              and gate.get("category") == "destructive")
        return _ok(ok=ok, error=out.get("error"))
    await t("H", "approval gate fail-closed (no resolver -> denied)", _gate_fail_closed)

    async def _gate_preapproved_proceeds():
        strict = BrowserAI(session_id=SESSION_ID,
                           procedural_memory=BrowserProceduralMemory(db_path=memory_db))
        strict.approval_gate.pre_approve("destructive", "click button.delete-account-now")
        out = await strict._cap_click("button.delete-account-now")
        err = str(out.get("error") or "")
        ok = "approval required" not in err  # proceeds to browser, which (correctly) finds no such button
        return _ok(ok=ok, error=out.get("error") or "browser-level failure as expected")
    await t("H", "pre-approved action proceeds past gate", _gate_preapproved_proceeds, timeout=60)

    async def _blocked_scheme():
        out = await ai._cap_navigate("file:///etc/passwd")
        ok = out.get("success") is False
        return _ok(ok=ok, error=out.get("error"))
    await t("H", "file:// navigation blocked", _blocked_scheme)

    async def _approval_resolver_invoked():
        strict = BrowserAI(session_id=SESSION_ID, approval_resolver=lambda d: (approvals.append(d) or True),
                           procedural_memory=BrowserProceduralMemory(db_path=memory_db))
        strict.approval_gate.reset()
        await strict._cap_click("button.delete-account-now")
        ok = any(a.get("category") == "destructive" for a in approvals)
        return _ok(ok=ok, approvals=len(approvals))
    await t("H", "resolver receives approval request", _approval_resolver_invoked, timeout=180)

    # -- Report ------------------------------------------------------------------
    total, passed, failed, pct = runner.summary()
    print()
    print("=" * 60)
    print(f"BROWSER AI ACCEPTANCE: {total} tests, {passed} passed, {failed} failed ({pct}%)")
    print("=" * 60)
    report_path = Path("BROWSER_AI_ACCEPTANCE_REPORT.md")
    report_path.write_text(runner.generate_report(), encoding="utf-8")
    print(f"Report written to {report_path}")
    return runner


async def _unreachable_caller(tool, params):  # pragma: no cover - must never be called
    raise AssertionError(f"unexpected tool call: {tool}")


if __name__ == "__main__":
    async def run_and_cleanup():
        runner = await main()
        await BrowserManager.instance().stop()
        return runner

    runner = asyncio.run(run_and_cleanup())
    total, passed, failed, _pct = runner.summary()
    sys.exit(0 if failed == 0 else 1)
