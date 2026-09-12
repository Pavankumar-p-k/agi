"""Unit tests for core.browser.verification and core.browser.recovery (mocked tools)."""
from __future__ import annotations

import pytest

from core.browser.recovery import RecoveryContext, RecoveryEngine
from core.browser.verification import FAILED, SUCCESS, UNCONFIRMED, Check, verify_outcome


class FakeCaller:
    """Scripted tool caller: maps (tool) -> list of responses in order."""

    def __init__(self, script: dict[str, list[dict]] | None = None, default_ok: bool = True):
        self.script = script or {}
        self.default_ok = default_ok
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, tool: str, params: dict):
        self.calls.append((tool, params))
        seq = self.script.get(tool)
        if seq:
            return seq.pop(0)
        return {"status": "ok"} if self.default_ok else {"status": "error", "error": "no script"}


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

class TestVerifyOutcome:
    @pytest.mark.asyncio
    async def test_no_checks_is_unconfirmed(self):
        outcome = await verify_outcome([], FakeCaller())
        assert outcome.status == UNCONFIRMED

    @pytest.mark.asyncio
    async def test_url_host_success(self):
        caller = FakeCaller({"browser_get_url": [{"status": "ok", "url": "https://github.com/peter/repo"}]})
        outcome = await verify_outcome([Check(kind="url_host", expected="github.com")], caller)
        assert outcome.status == SUCCESS

    @pytest.mark.asyncio
    async def test_url_host_subdomain_failure(self):
        caller = FakeCaller({"browser_get_url": [{"status": "ok", "url": "https://gitlab.com/x"}]})
        outcome = await verify_outcome([Check(kind="url_host", expected="github.com")], caller)
        assert outcome.status == FAILED

    @pytest.mark.asyncio
    async def test_text_present_pass_and_fail(self):
        caller = FakeCaller({"browser_find": [{"status": "ok"}]})
        outcome = await verify_outcome([Check(kind="text_present", expected="Deployed")], caller)
        assert outcome.status == SUCCESS

        caller = FakeCaller({"browser_find": [{"status": "error", "error": "not found"}]})
        outcome = await verify_outcome([Check(kind="text_present", expected="Deployed")], caller)
        assert outcome.status == FAILED

    @pytest.mark.asyncio
    async def test_negated_check(self):
        caller = FakeCaller({"browser_is_visible": [{"status": "ok", "result": {"visible": False}}]})
        outcome = await verify_outcome([Check(kind="element_visible", expected=".error-banner", negate=True)], caller)
        assert outcome.status == SUCCESS

    @pytest.mark.asyncio
    async def test_observation_error_yields_unconfirmed_never_false_success(self):
        caller = FakeCaller({"browser_get_url": [{"status": "error", "error": "page closed"}]})
        outcome = await verify_outcome([Check(kind="url_host", expected="github.com")], caller)
        assert outcome.status == UNCONFIRMED

    @pytest.mark.asyncio
    async def test_unknown_check_kind_yields_unconfirmed(self):
        outcome = await verify_outcome([Check(kind="magic", expected="x")], FakeCaller())
        assert outcome.status == UNCONFIRMED

    @pytest.mark.asyncio
    async def test_mixed_fail_and_unconfirmed_is_failed(self):
        caller = FakeCaller({
            "browser_get_url": [{"status": "error", "error": "x"}],
            "browser_find": [{"status": "error", "error": "text missing"}],
        })
        outcome = await verify_outcome(
            [Check(kind="url_host", expected="a.com"), Check(kind="text_present", expected="hi")],
            caller,
        )
        assert outcome.status == FAILED

    @pytest.mark.asyncio
    async def test_title_contains(self):
        caller = FakeCaller({"browser_get_title": [{"status": "ok", "result": {"title": "Settings - GitHub"}}]})
        outcome = await verify_outcome([Check(kind="title_contains", expected="settings")], caller)
        assert outcome.status == SUCCESS


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------

class TestRecoveryEngine:
    @pytest.mark.asyncio
    async def test_simple_retry_recovers(self):
        caller = FakeCaller({
            "browser_click": [
                {"status": "error", "error": "timeout"},
                {"status": "ok", "result": {"clicked": "#btn"}},
            ],
        })
        engine = RecoveryEngine(caller, wait_seconds=0)
        outcome = await engine.recover(RecoveryContext(action_name="browser_click", params={"selector": "#btn"}))
        assert outcome.recovered
        assert outcome.attempts[0].rung == "retry"

    @pytest.mark.asyncio
    async def test_alt_selector_rung(self):
        caller = FakeCaller({
            "browser_click": [
                {"status": "error", "error": "timeout"},   # retry
                {"status": "error", "error": "timeout"},   # alt selector
                {"status": "ok", "result": {"clicked": "text=Submit"}},
            ],
            "browser_snapshot": [{"status": "ok", "result": {}}],
        })
        engine = RecoveryEngine(caller, wait_seconds=0)
        outcome = await engine.recover(RecoveryContext(
            action_name="browser_click", params={"selector": "#submit"}, alt_selectors=["text=Submit"],
        ))
        assert outcome.recovered
        rungs = [a.rung for a in outcome.attempts]
        assert "alt_selector" in rungs

    @pytest.mark.asyncio
    async def test_ladder_exhaustion_is_bounded(self):
        # everything always fails
        caller = FakeCaller(default_ok=False)
        engine = RecoveryEngine(caller, wait_seconds=0)
        outcome = await engine.recover(RecoveryContext(
            action_name="browser_click", params={"selector": "#x"},
            alt_selectors=[".a", ".b"],
        ))
        assert not outcome.recovered
        assert outcome.exhausted
        # bounded: retry(1) + alt(2) + snapshot + text-click(1) + refresh(2) per pass, 2 passes
        max_clicks = 2 * (1 + 2 + 1 + 2)
        click_calls = sum(1 for tool, _ in caller.calls if tool == "browser_click")
        assert click_calls <= max_clicks

    @pytest.mark.asyncio
    async def test_loop_detection_short_circuits(self):
        caller = FakeCaller(default_ok=False)
        engine = RecoveryEngine(caller, wait_seconds=0)
        ctx = RecoveryContext(action_name="browser_click", params={"selector": "#x"})
        for _ in range(4):
            await engine.recover(ctx)
        outcome = await engine.recover(ctx)
        assert outcome.loop_detected
        assert not outcome.attempts  # short-circuited before any attempt

    @pytest.mark.asyncio
    async def test_alternative_workflow_rung(self):
        caller = FakeCaller(default_ok=False)
        engine = RecoveryEngine(caller, wait_seconds=0)
        outcome = await engine.recover(RecoveryContext(
            action_name="browser_navigate",
            params={"url": "https://down.example"},
            alternative_workflows=[("browser_search", {"query": "down.example mirror"})],
        ))
        assert not outcome.recovered
        rungs = [a.rung for a in outcome.attempts]
        assert "alternative_workflow" in rungs

    @pytest.mark.asyncio
    async def test_navigation_failure_reopens_new_tab(self):
        caller = FakeCaller({
            "browser_navigate": [
                {"status": "error", "error": "timeout"},       # retry
                {"status": "error", "error": "timeout"},       # refresh-rung retry
                {"status": "ok", "result": {"url": "https://x.com"}},  # new tab nav
            ],
            "browser_new_tab": [{"status": "ok", "result": {"url": "https://x.com"}}],
        })
        engine = RecoveryEngine(caller, wait_seconds=0)
        outcome = await engine.recover(RecoveryContext(action_name="browser_navigate", params={"url": "https://x.com"}))
        assert outcome.recovered
        tools = [t for t, _ in caller.calls]
        assert "browser_new_tab" in tools
