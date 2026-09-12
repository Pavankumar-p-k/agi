"""Outcome verification for Browser AI.

Never assume success from an action's return value alone: every meaningful
browser outcome is confirmed by observing page state (URL, visibility, text,
dialog/file evidence) and classified as SUCCESS / FAILED / UNCONFIRMED.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

SUCCESS = "SUCCESS"
FAILED = "FAILED"
UNCONFIRMED = "UNCONFIRMED"


@dataclass
class Check:
    kind: str          # url_host | url_contains | url_equals | text_present | element_visible | element_absent | title_contains | custom
    expected: str = ""
    negate: bool = False
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "expected": self.expected, "negate": self.negate, "description": self.description}


@dataclass
class VerificationOutcome:
    status: str                 # SUCCESS | FAILED | UNCONFIRMED
    checks: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": self.checks,
            "evidence": self.evidence,
            "reason": self.reason,
        }

    @property
    def ok(self) -> bool:
        return self.status == SUCCESS


ToolCaller = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def _host(url: str) -> str:
    from urllib.parse import urlparse
    value = str(url or "").strip().lower()
    if value and "://" not in value:
        value = "https://" + value  # scheme-less hosts (e.g. "github.com")
    parsed = urlparse(value)
    # hostname (not netloc): url_host comparisons must ignore the port
    # (http://127.0.0.1:8000/ is the same host as 127.0.0.1).
    host = parsed.hostname or parsed.netloc or parsed.path.split("/")[0]
    return host.removeprefix("www.")


async def verify_outcome(
    checks: list[Check],
    call: ToolCaller,
    session_id: str = "default",
) -> VerificationOutcome:
    """Run verification checks against live page state.

    Semantics:
    - every non-negated check must hold for SUCCESS;
    - any hard failing check means FAILED;
    - an error while *observing* (not a failed expectation) yields UNCONFIRMED,
      never a false SUCCESS.
    """
    if not checks:
        return VerificationOutcome(status=UNCONFIRMED, reason="no verification checks configured")

    results: list[dict[str, Any]] = []
    all_pass = True
    any_fail = False

    for check in checks:
        try:
            observed, note = await _observe(check, call, session_id)
            if observed is None:
                # Could not observe (tool error) — not evidence of failure or success.
                results.append({**check.to_dict(), "status": "unconfirmed", "note": note})
                all_pass = False
                continue
            passed = (not observed) if check.negate else observed
            results.append({**check.to_dict(), "status": "pass" if passed else "fail", "note": note})
            if passed:
                continue
            any_fail = True
            all_pass = False
        except Exception as exc:  # observation error → unconfirmed
            results.append({**check.to_dict(), "status": "unconfirmed", "note": f"{type(exc).__name__}: {exc}"})
            all_pass = False

    if all_pass:
        return VerificationOutcome(status=SUCCESS, checks=results, reason="all checks passed")
    if any_fail:
        return VerificationOutcome(status=FAILED, checks=results, reason="one or more checks failed")
    return VerificationOutcome(status=UNCONFIRMED, checks=results, reason="checks could not be observed")


async def _observe(check: Check, call: ToolCaller, session_id: str) -> tuple[bool | None, str]:
    """Return (observed_boolean_or_None, note).  None means 'could not observe'."""
    kind = check.kind
    if kind in ("url_host", "url_contains", "url_equals"):
        res = await call("browser_get_url", {"session_id": session_id})
        if res.get("status") != "ok":
            return None, res.get("error", "get_url failed")
        url = str(res.get("url") or res.get("result", {}).get("url") or "")
        if kind == "url_host":
            return _host(url) == _host(check.expected) or _host(url).endswith("." + _host(check.expected)), f"observed {url}"
        if kind == "url_contains":
            return check.expected.lower() in url.lower(), f"observed {url}"
        return url.rstrip("/") == check.expected.rstrip("/"), f"observed {url}"

    if kind == "text_present":
        res = await call("browser_find", {"text": check.expected, "session_id": session_id})
        return res.get("status") == "ok", res.get("error", "")

    if kind == "element_visible":
        res = await call("browser_is_visible", {"selector": check.expected, "session_id": session_id})
        if res.get("status") != "ok":
            return None, res.get("error", "is_visible failed")
        return bool(res.get("result", {}).get("visible")), ""

    if kind == "element_absent":
        res = await call("browser_is_visible", {"selector": check.expected, "session_id": session_id})
        if res.get("status") != "ok":
            return None, res.get("error", "is_visible failed")
        return not bool(res.get("result", {}).get("visible")), ""

    if kind == "title_contains":
        res = await call("browser_get_title", {"session_id": session_id})
        if res.get("status") != "ok":
            return None, res.get("error", "get_title failed")
        title = str(res.get("result", {}).get("title") or "")
        return check.expected.lower() in title.lower(), f"title={title[:120]}"

    raise ValueError(f"unknown check kind: {kind}")
