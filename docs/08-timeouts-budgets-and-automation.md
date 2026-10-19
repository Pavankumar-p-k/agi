# Update 8 — Registration rule, automated mutations, timeouts & budgets

Date: 2026-10-19 · Implements the review's four tightening items, plus one
packaging bug it caught.

## 0. Independent verification (run from outside the report)

Executed by command, not asserted: `git ls-remote origin main` → `f5feb5f`
on the remote; a brand-new venv with a **non-editable** `pip install .` ran
`mj status` (exit 0) and `mj audit` (exit 0); `pytest --collect-only -q`
inside that venv collected exactly **79** tests (20 adversarial + 19 executor
+ 15 kernel + 13 CLI + 11 world + 1 integration).

**Packaging bug found by that fresh environment** (the earlier report skipped
it): `pyproject.toml` declared no `dependencies`, so `pip install .` did not
install psutil and the process probe degraded to `stale` — the fresh-env suite
failed 2 tests that passed on the host only because psutil happened to be
installed there. Fixed at the cause: `dependencies = ["psutil>=6.1,<7"]` now
lives in `[project]`, matching `requirements.txt`. Fresh-env world tests: 11/11
green after the fix.

## 1. Registration rule — the URL/shell guarantee now holds automatically

`mj/core/registry.py`: `validate_manifest()` computes `declared_powers()` from
the manifest's **id segments, capability type, and required scopes** (word-level
tokens — `files.shellpaper` is not shell; `agent.web-worker` is web) and
rejects any manifest declaring `web` / `browser` / `shell` unless it is **R2 or
above** (so the policy gate asks before it runs) **and** carries
`has_verifier=True`.

- Enforced in `validate_manifest`, which every registration path calls —
  builtins, vetted adapters, BrowserOS, expansion-engine output, generated
  adapters. A future web worker cannot arrive silent or unverified.
- Unit test `test_sensitive_powers_require_risk_class_and_verifier` covers the
  four rejection shapes plus the conforming-registration path.
- End-to-end adversarial test `test_registered_web_capability_still_hits_the_gate`:
  a *properly registered* `browser.open` (R2+verifier) still asks from the
  terminal with the exact payload, and is blocked outright from `external`
  trust even under auto-approve — nothing opened either time.
- The mutation harness (§2) kill-tests this rule too.

## 2. Mutation testing is now a script, not a story

`tools/mutation_check.py` — no dependencies beyond pytest. For each defense it
applies a source mutation, runs the matching tests **requiring them to fail**,
restores from a byte-exact backup (marker-checked), and requires green again.
Exits nonzero if a defense survives, if the baseline was already red, if an
anchor no longer matches the source shape (forcing the harness to be updated
with the defense), or if restore integrity fails.

Current defenses under kill-test:

| Mutation | Matching tests |
|---|---|
| approval payload-hash → constant | approval-reuse-after-change |
| verifier bypassed (trust worker output) | both fake-success tests |
| `_escapes_base` → always False | both path-traversal tests |
| registry sensitive-power rule disabled | registry rule + no-URL-capability tests |

Last run: `python tools/mutation_check.py` → `OK: all 4 defenses are
load-bearing`, exit 0. In CI: run it beside pytest; a green suite plus a
surviving mutation still fails the build.

## 3. Worker timeouts and budgets (built ahead of the reasoner)

New `mj/core/settings.py`, env-tunable, read on every call; surfaced in
`mj status` under `limits`:

| Setting | Default | Semantics |
|---|---|---|
| `MJ_STEP_TIMEOUT_S` | 60 | Per-step deadline on `run()`. At expiry the runner stops waiting, the step **fails as timed out**, the daemon worker is abandoned on its **own store connection** (WAL) so it can never race the kernel's. A timeout is an unknown outcome, never a success. `<= 0` disables (documented, discouraged). |
| `MJ_TASK_BUDGET_S` | 600 | Per-task wall-clock, checked **before each step starts**. Exhausted → current step skipped, remaining steps not started, task fails with a budget error; **completed steps keep their verified results**. `<= 0` = exhausted immediately. |
| `MJ_MAX_STEPS` | 25 | Plan step cap enforced in `validate_plan` — oversized plans are refused **before any execution**. `<= 0` disables. |

**Expiry × undo:** limits bound execution, never recorded history. Undo reads
`step_results`, which expiry does not mutate — `test_timeouts_do_not_poison_undo_of_completed_tasks`
proves a later task dying to a timeout leaves a completed task's undo fully
usable. Conversely, a step that never ran (budget) left no moves, so there is
nothing for undo to reverse — asserted too.

Tests (`tests/unit/test_limits.py`, 7): deadline fails fast without hanging the
kernel; a timed-out step records `verified=0` + error, never success; zero
budget never touches the world; mid-plan expiry keeps the completed step
verified and refuses the next before it starts; cap refusal + `<=0` bypass;
undo-after-timeout; settings garbage falls back to defaults.

These bounds exist **before** any LLM joins the loop, so the reasoner inherits
them: a looping model hits the same deadline, budget and cap that a scripted
worker does.

## 4. Permanently unverified: everything MJ did not do

Reaffirmed as a standing rule: MJ reports only what happens **through MJ**.
The YouTube window opened from the developer's terminal outside MJ and remains
**unverified forever** — no future MJ report may cite it as an MJ result. The
registration rule (§1) ensures that when a web capability exists inside MJ,
its results are attributable precisely because they are gated, audited and
verified.

## 5. Order from here (unchanged)

1. ~~Timeouts and budgets~~ **done this update** (spec + implementation + tests).
2. **Credential broker** — next.
3. **Reasoner, typed plans only** — blocked on two decisions: **model provider**
   and **risk stance** (which action classes may run without asking).
4. **Expansion engine.**
5. Daemon/API — deferred.

Open decisions for the operator: model provider, risk stance, OS, first real
tasks, existing agents inventory (drafts remain in `docs/05`, editable).
