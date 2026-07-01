# Workflow Engine -- Durability Benchmark Report

**Date:** 2026-06-29 06:47 UTC
**Engine:** core/workflow/engine.py (v1)
**Storage:** SQLite (per-scenario isolated temp files in C:\Users\peter\AppData\Local\Temp\tmp94fgijbt)

## Summary

| Metric | Value |
|--------|-------|
| Scenarios | 8 |
| Passed | 8/8 (100%) |
| Duplicate executions | 0 |
| Data loss incidents | 0 |
| Avg recovery time | 43ms (n=4) |

## Per-Scenario Results

| # | Scenario | Result | Expected | Actual | Duplicate | Data Loss | Recovery |
|---|----------|--------|----------|--------|-----------|-----------|----------|
| 1 | Crash During Step | **PASS** | COMPLETED, step 1 resumed | COMPLETED, step 3/3 | no | no | 47ms |
| 2 | Crash Between Steps | **PASS** | COMPLETED, 4/4 steps | COMPLETED, 4/4 steps | no | no | 47ms |
| 3 | Cancel During Step | **PASS** | CANCELLED, no zombie | CANCELLED, zombie=no | no | no | N/A |
| 4 | Cancel During Retry | **PASS** | CANCELLED | CANCELLED | no | no | N/A |
| 5 | Concurrent Workflows (8) | **PASS** | 8/8 COMPLETED, no duplicates | 8/8 | no | no | N/A |
| 6 | Heartbeat Timeout Recovery | **PASS** | Live skipped, stale recovered | live_skipped=True stale_recovered=True | no | no | 47ms |
| 7 | Process Restart Recovery | **PASS** | COMPLETED, 3/3 steps | COMPLETED, step 3/3 | no | no | 31ms |
| 8 | External Side-Effect Recovery | **PASS** | COMPLETED, no duplicate step 0 | COMPLETED, duplicate=no | no | no | N/A |

## Detail

### Crash During Step

- **State:** expected `COMPLETED, step 1 resumed` -> actual `COMPLETED, step 3/3`
- **Duplicate:** NO
- **Data Loss:** NO
- **Recovery Time:** 47ms
- **Detail:** s0_ok=True

### Crash Between Steps

- **State:** expected `COMPLETED, 4/4 steps` -> actual `COMPLETED, 4/4 steps`
- **Duplicate:** NO
- **Data Loss:** NO
- **Recovery Time:** 47ms
- **Detail:** s0_completed=True completed=4/4

### Cancel During Step

- **State:** expected `CANCELLED, no zombie` -> actual `CANCELLED, zombie=no`
- **Duplicate:** NO
- **Data Loss:** NO
- **Detail:** 

### Cancel During Retry

- **State:** expected `CANCELLED` -> actual `CANCELLED`
- **Duplicate:** NO
- **Data Loss:** NO
- **Detail:** exec_calls=2

### Concurrent Workflows (8)

- **State:** expected `8/8 COMPLETED, no duplicates` -> actual `8/8`
- **Duplicate:** NO
- **Data Loss:** NO
- **Detail:** instances=8 steps=24 events=64

### Heartbeat Timeout Recovery

- **State:** expected `Live skipped, stale recovered` -> actual `live_skipped=True stale_recovered=True`
- **Duplicate:** NO
- **Data Loss:** NO
- **Recovery Time:** 47ms
- **Detail:** recovered=1

### Process Restart Recovery

- **State:** expected `COMPLETED, 3/3 steps` -> actual `COMPLETED, step 3/3`
- **Duplicate:** NO
- **Data Loss:** NO
- **Recovery Time:** 31ms
- **Detail:** completed=3/3

### External Side-Effect Recovery

- **State:** expected `COMPLETED, no duplicate step 0` -> actual `COMPLETED, duplicate=no`
- **Duplicate:** NO
- **Data Loss:** NO
- **Detail:** s0_calls=3 -> 3

## Failure Mode Coverage

| Category | Covered |
|----------|---------|
| Crash during step execution | Yes (Scenario 1) |
| Crash between step completions | Yes (Scenario 2) |
| Cancellation mid-execution | Yes (Scenario 3) |
| Cancellation during retry | Yes (Scenario 4) |
| Concurrent workflow isolation | Yes (Scenario 5) |
| Heartbeat-based stale detection | Yes (Scenario 6) |
| Full process restart survival | Yes (Scenario 7) |
| Side-effect idempotency | Yes (Scenario 8) |

### No Duplicate Execution

All scenarios showed zero step re-execution after recovery.
Completed steps were correctly skipped via idempotency key check.
### No Data Loss

All persisted workflow data survived crash, cancel, and restart cycles.

### Recovery Latency

Average recovery time: **43ms** (n=4).
This includes SQLite reload + state-machine transition overhead, excludes step execution.

## Verdict

**Workflow Engine v1 passes all 8 durability scenarios.**

- Crash mid-step: resumes from correct position, no step skipped or duplicated.
- Crash between steps: completed steps are not re-executed, remaining steps complete.
- Cancellation mid-execution: marks CANCELLED, no zombie tasks.
- Cancellation during retry: marks CANCELLED cleanly even while retrying.
- Concurrent execution (8 workflows): SQLite locks handle contention, all complete.
- Heartbeat staleness: live workflows skipped, stale workflows recovered.
- Process restart: workflow survives across independent engine instances.
- Side-effect idempotency: completed steps are never re-executed on recovery.

The engine is ready for production integration.
