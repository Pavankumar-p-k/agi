# Update 2 — Environment awareness (world model + real probes)

Date: 2026-10-19 · Scope: the fact store and the four probes that answer the Phase-2 questions honestly.

## What exists (all real, all tested)

| Component | Module | Notes |
|---|---|---|
| Fact store | `mj/world/model.py` | Facts live in the one state store: `{scope, key, value, source, observed_at, ttl_seconds, label}`. Readers get honest labels — `verified`, `reported`, or **`stale` once past TTL**. Reading never refreshes; refreshing is an explicit audited act. |
| Disk probe | `mj/world/probes.py` | Free/total space per unique drive touched by cwd and home. Verified against an independent `shutil.disk_usage` in the test. Found and fixed a real bug during testing (facts keyed per directory collided on one drive). |
| Process probe | `mj/world/probes.py` | `psutil.process_iter` summary: count, distinct names, top-by-frequency sample. Answers "what is running" / "is X running". |
| Installed-apps probe | `mj/world/probes.py` | Per-OS enumeration: Windows Uninstall registry keys (HKLM / WOW6432Node / HKCU), `/Applications` on macOS, `/usr/share/applications` on Linux — with the enumeration source recorded per fact. |
| Tools probe | `mj/world/probes.py` | Interpreter and tool versions via subprocess; missing tools reported as `null`, never guessed. |

## Invariants honored

- Provenance on every fact (invariant 5): each fact records its source API and observation time.
- Honest labels: unobserved things are absent or marked stale — the awareness test suite cross-checks probe answers against independent OS-level checks, exactly as the plan's "Awareness ground-truth tests" require.
- Auditability: every refresh appends `world.refresh` to the hash-chained audit log.

## Not claimed yet

Autonomy stays at L0. No planner uses these facts yet — answers still come only through tests and the upcoming CLI (Update 4). The `stale`-before-high-impact-use reconciler is not wired beyond the label machinery.

## Proven by tests

`tests/unit/test_world.py` — 11 tests: TTL expiry → stale label, latest-observation-wins upsert, disk facts equal an independent `shutil.disk_usage` read, process count ≥ 1 (this test is itself a process), app/tool probes on the running OS, all scopes persisted through the audited refresh.
