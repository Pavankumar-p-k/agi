# Update 7 — Verification audit: counting slips, the YouTube incident, mutation tests

Date: 2026-10-19 · Triggered by a review that caught a counting slip and an
architectural bypass in the previous report. Both were real; both are fixed or
explicitly labeled below.

## 1. The test count did not add up — reconciled with `--collect-only`

The previous report claimed "71 passed: 58 core + 13 CLI + 12 adversarial"
(= 83 ≠ 71). `python -m pytest tests --collect-only -q` per-file counts:

| File | Tests |
|---|---|
| `tests/unit/test_brain_executor.py` | 19 |
| `tests/unit/test_kernel.py` | 15 |
| `tests/unit/test_cli.py` | 13 |
| `tests/adversarial/test_adversarial.py` | 12 (now 20) |
| `tests/unit/test_world.py` | 11 |
| `tests/integration/test_clean_install.py` | 1 |
| **Total (at the time)** | **71** |

**The slip:** the "58 core" figure already contained the 13 CLI tests
(45 core unit + 13 CLI = 58); the breakdown then listed the CLI tests a second
time and omitted the integration test. 45 + 13 + 12 + 1 = 71. The total was
right; the breakdown was double-counted. Verified total after this update:
**79** (45 core + 13 CLI + 20 adversarial + 1 integration).

## 2. The "open YouTube" incident — labeled unverified, and the hole closed

What actually happened: the request was served by `cmd //c start <url>` from
the **developer's own terminal** — the coding agent's shell, which is outside
MJ entirely. It did **not** pass through MJ's policy gate and left **no audit
record**, because MJ was not involved. And it proved less than it claimed: a
window opening is not evidence that a video played. Correct label: **unverified
side effect, outside the architecture**.

Why it cannot happen *inside* MJ: there is no registered capability that opens
URLs or runs shell commands. New adversarial proof (5-parametrized-case test
`test_no_registered_capability_can_open_a_url_or_run_a_shell`): any plan
naming `web.open`, `browser.open`, `browser.navigate`, `browseros.open` or
`shell.exec` fails plan validation as *unregistered* — before the gate, before
execution. A task phrased "play this" cannot take an ungated path through MJ.

**Standing rule adopted:** a browser/web worker (e.g. BrowserOS) is treated
like any new capability: registered with a manifest, given least-privilege
scopes only, and required to pass its own sandbox tests before it may handle
web tasks. Until then, any web action done by the coding agent's terminal is
reported as unverified, never as "done".

## 3. Missing adversarial coverage from the review's checklist — now added

| Reviewer's required case | Test | Status |
|---|---|---|
| Instructions hidden in a tool result | `test_injected_filename_stays_quoted_data_and_moves_nothing` | was covered |
| Worker claiming success without evidence | `test_worker_claims_success_verifier_refutes`, `test_organize_reports_moves_that_never_happened` | was covered |
| Approval reused after the payload changed | `test_granted_approval_does_not_authorize_a_changed_payload` | **added** |
| Path-traversal / out-of-scope file target | `test_lying_worker_cannot_move_files_out_of_the_sandbox`, `test_undo_refuses_to_pull_files_in_from_outside_the_sandbox` | **added** |

New defenses added with them:

- `_escapes_base()` in `mj/executor/capabilities.py`: both `verify_organize`
  and `undo_organize` refuse any move whose src or dst resolves outside the
  approved base directory. The verifier reports it as a problem (step
  unverified, capability degraded); undo refuses and lists it under `refused`.
- Approval binding was already hash-based (failure 25); it now has a test that
  proves a grant authorizes exactly the payload shown, and nothing else.

## 4. Mutation testing — do the adversarial tests actually test anything?

Each defense was disabled on purpose; the matching tests had to go red.

| Defense disabled (mutation) | Matching test(s) | Result with defense OFF | After restore |
|---|---|---|---|
| `_payload_hash` → constant (kills approval↔payload binding) | approval-reuse test | **RED** — `DID NOT RAISE ApprovalRequired`; changed payload would have run under the old grant | GREEN |
| Runner trusts worker output, verifier never called | both fake-success tests | **RED** — lying worker reported `verified: 1`, fabricated moves list passed | GREEN |
| `_escapes_base` → `return False` (no escape check) | both traversal tests | **RED** — escaped move verified as true; undo dragged an outside file inward | GREEN |

Source integrity: both mutated files were restored from backups and
`diff -q`-verified byte-identical before the final suite run. No mutation code
remains in the tree.

## 5. Updated build order (per review: pull timeouts/budgets forward)

1. **Credential broker** — no raw token ever reaches planner or model.
2. **Worker timeouts and budgets** — moved ahead of the reasoner: an LLM that
   can loop will need a kill switch and a spend cap from day one.
3. **Reasoner, restricted to emitting typed plans** that the existing executor
   and policy gate validate (no new execution paths).
4. **Expansion engine** — after quarantine/sandbox/rollback pieces exist.
5. Daemon/API — still explicitly deferred.

## 6. Open items (reported, not verified)

- No credential broker yet, so no secrets-handling attacks are testable.
- No LLM is wired anywhere; model-context injection remains untestable until
  the reasoner phase.
- BrowserOS (or any web worker) is not registered; the standing rule in §2
  governs its eventual onboarding.
- Worker timeouts/budgets not implemented yet (next in order).
