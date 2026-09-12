# BROWSER_AI_STATUS — Production-Ready (PHASE 12)

**Date:** 2026-09-12
**Status:** ✅ PRODUCTION_READY (specialist boundary + verified outcomes + security)
**Plan:** Built per the approved Browser-AI-first development order (PHASE 1–12).

## What Browser AI is

The web specialist of the JARVIS specialist architecture. It conforms to the
standard `SpecialistModule` contract (`core/specialist.py`) so the future
Super-Brain discovers capabilities (`browser.navigate`, `browser.search`,
`browser.extract`, `browser.form_fill`, `browser.verify`, `browser.recover`, …)
without understanding browser internals. **No parallel architecture was
created** — every layer reuses existing infrastructure.

## Reuse map (nothing duplicated)

| Requirement | Reused component |
|---|---|
| Browser control | `core/browser_manager` (existing) |
| Reliable primitives | `core/tools/browser_tools.py` (extended, same `do_*` signatures) |
| Capability registration | `tools/registry` + `core/capability/discovery` (ADR-013 authoritative registry) |
| Multi-step workflows | `core/desktop/task_graph` action-dict shape (`execute_workflow`) |
| Procedural memory | `memory/` sqlite infrastructure via `BrowserProceduralMemory` |
| Safety/authz | `core/tools/security.is_authorized_to_execute` + `core/tools/policy` + risk tiers |
| Search | `do_browser_search` (existing engine backends) |

## Module map

| File | Role |
|---|---|
| `core/browser/browser_ai.py` | The specialist: identity / capabilities / requirements / `health()` / `observe()` / `execute_capability()` / `verify()` / `recover()` / `report()` |
| `core/browser/registration.py` | Idempotent registration into the authoritative registry (15 capabilities, risk tiers, verification specs) |
| `core/browser/verification.py` | `Check` kinds: url_host / url_contains / url_equals / text_present / element_visible / element_absent / title_contains → **SUCCESS / FAILED / UNCONFIRMED** (observation errors are never a false SUCCESS) |
| `core/browser/recovery.py` | Bounded ladder: retry → alt_selector → DOM re-evaluate → refresh/reopen → alternative workflow. Per-rung once, max passes, loop detection, truthful exhaustion report |
| `core/browser/procedural_memory.py` | Site/task procedures with selectors, conditions, failure modes, **last_verified, confidence, TTL expiry** |
| `core/browser/page_security.py` | Page content is **UNTRUSTED DATA**: wrapping markers, injection-pattern scan, fail-closed `ApprovalGate` (payment / account_deletion / publishing / messaging / destructive / credential_access / sensitive_upload) |
| `core/tools/browser_research.py` | Bounded research flow: search → open → extract → compare → conflict detection → evidence-backed report (never launches a browser itself) |

## Verification semantics (the critical part)

No action reports success from its return value alone:
click Deploy → wait → inspect result → check URL/status/message →
verify expected state → `SUCCESS / FAILED / UNCONFIRMED`.
Workflows report `SUCCESS` **only** when verification checks pass on live page state.

## Security

- All page-derived text is wrapped in `<<<UNTRUSTED_PAGE_CONTENT>>>` markers; injection patterns are flagged and reported, never obeyed.
- Gated actions are **fail-closed**: without an explicit resolver approval or `pre_approve`, the action is denied.
- `file://`, `chrome://`, `javascript:` navigations remain blocked (existing hardening preserved).

## Test evidence

| Suite | Result |
|---|---|
| Unit (`tests/unit/test_browser_{page_security,verification_recovery,procedural_memory,ai_specialist,research,planner}.py`) | **102 passed** |
| Real-browser acceptance (`tests/acceptance/test_browser_ai_acceptance.py`) | **28/28 PASS (100%)** → `BROWSER_AI_ACCEPTANCE_REPORT.md`, classification **PRODUCTION_READY** |
| Pre-existing tool acceptance (`tests/acceptance/test_browser_acceptance.py`) | unchanged; categories A/C–H already 100% (Category B site-nav drift is pre-existing, tracked in the old report) |

Run: `python tests/acceptance/test_browser_ai_acceptance.py`

## Wiring for callers

```python
from core.browser.registration import register_browser_ai
register_browser_ai()   # startup / discovery pass, idempotent

from core.browser.browser_ai import get_browser_ai
ai = get_browser_ai()
result = ai.execute_capability("browser.navigate", {"url": "https://example.com"})
# SpecialistResult(success=..., verified=..., verification_reason=...)
```

## Known limitations / next steps

1. **Approval resolver wiring** — `ApprovalGate` defaults to fail-closed deny; wire a UI/CLI prompt into `approval_resolver` (interactive MCP variant already exists in `jarvis_mcp`).
2. **Recovery latency** — bounded but not fast: each rung click can wait up to 15s at the Playwright layer; consider a shorter default timeout for interactive use.
3. **Research depth** — bounded to `max_pages` sources; conflict detection is textual (no claim-level NLP yet).
4. **Pre-existing suite failures** — unrelated modules (`test_opportunity.py`, `test_long_horizon_fsm.py`, desktop bridge/agent-reuse) fail on `main` independent of this work (e.g. `Opportunity.__getattr__` returns a lambda default); not addressed here.
