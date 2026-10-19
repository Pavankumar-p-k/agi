# Update 6 — Adversarial suite: the policy gate under pressure

Date: 2026-10-19 · Built before any LLM joins the loop, per the review's ordering.

## Attack classes covered — `tests/adversarial/test_adversarial.py` (12 tests)

| Attack | Test | Outcome |
|---|---|---|
| Injection string planted in tool output (an "IGNORE PRIOR INSTRUCTIONS" filename) | `test_injected_filename_stays_quoted_data_and_moves_nothing` | Appears **verbatim as data** in the listing/proposals; nothing acted on it; file untouched |
| Shell-metacharacter payload in `--dir` (`; format c: & del .`) | `test_shell_metacharacters_are_literal_paths_not_commands` | Treated as one nonexistent literal path; task `failed` honestly; no side effects anywhere |
| JSON-hostile filename (braces, semicolons, unicode) | `test_json_hostile_filename_roundtrips_through_store` | Round-trips exactly through the store; audit chain stays intact |
| Worker claims glorious success | `test_worker_claims_success_verifier_refutes` | Independent verifier refutes it; step flagged `unverified`; capability demoted to `degraded` |
| Worker fabricates a moves list | `test_organize_reports_moves_that_never_happened` | Verifier stats real files, refutes the list; the file is untouched; capability `degraded` |
| Gate bypass via an unregistered capability (`shell.exec`, R4 semantically) | `test_bypass_with_unregistered_capability_rejected` | `PlanValidationError` — the planner may only name registered capabilities |
| Gate bypass via a degraded (retreated) capability | `test_bypass_with_retired_capability_rejected` | Refused until it is healthy again |
| **R4 capability with auto-approve** | `test_r4_capability_denied_before_execution_never_runs` | Denied at the gate even with `--yes`; the destructive impl is booby-trapped and **never runs** (proven by a sentinel) |
| Confused deputy: `chat-connector` / `external` trusts R2 actions | `test_low_trust_channel_cannot_run_r2_even_with_auto_approve` | Blocked at the gate; files untouched |
| Low-trust privilege ceiling | `test_low_trust_channel_cannot_pull_r0_facts_silently` | R1/R2 denied from `external`; R0 reads remain the only documented standing rule |
| Ambiguity never becomes invention | `test_partial_keyword_will_not_infer_dangerous_action` | `clean up my pc` (no dir) asks one question instead of choosing a directory itself |

## What this says about the gate

- Deny happens **before** execution: destructive code never runs even under auto-approve.
- The verifier, not the worker, decides success; reports separate verified from unverified and lied-to runs degrade the capability.
- Injection payloads survive as quoted data end-to-end; nothing in the deterministic pipeline executes content.

## Honest gaps this suite does not cover

- No LLM exists yet, so prompt-injection *into a model context* is untestable at this layer — the injection tests cover the tool-output side that an LLM would later consume.
- No worker timeouts/budgets yet (a hung worker stalls a task rather than being killed) — needed before any external worker adapter.
- No secrets exist in the system yet, so exfiltration attacks target a future credential broker.
