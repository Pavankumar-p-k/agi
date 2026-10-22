# Update 10 — killable process trees, honest assertions, CI's first real run

Date: 2026-10-20 · Implements three items of the third review: the
grandchild kill, the never-fail assertions, and reading the first Actions
run on both platforms. Branch protection and the broker/reasoner remain.

## 1. Grandchildren die with the worker

Previous state: the deadline killed the worker process itself
(`subprocess.run` at expiry). A worker that had *spawned* processes — the
declared `process` effect `os.facts` already uses — left its children
running after MJ marked the step failed. A zombie that survives the fix
that was meant to remove zombies.

**`src/mj/executor/killtree.py`** — one step, one killable group:

- **POSIX**: the worker starts with `start_new_session=True`, so its pgid
  equals its pid and every descendant joins that group at any depth. On
  expiry one `os.killpg(pgid, SIGKILL)` kills the worker *and everything it
  spawned*.
- **Windows**: the worker is assigned to a **Job Object** created with
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Anything the worker spawns joins the
  job automatically (nested jobs, Win8+). On expiry `TerminateJobObject`
  kills every member in one call; and because the job dies with its handle,
  MJ itself crashing can no longer orphan a worker either. Fallback if
  assignment fails (restrictive parent job): `taskkill /T /F`, then a
  direct kill of the worker.
- stdout/stderr now go to **files, not pipes**: a surviving grandchild that
  inherits the handles can no longer wedge a pipe read, and stdin round-trips
  exactly as before (same locale-encoding semantics).

**Bug found by the new test, fixed at the cause:** immediately after a kill,
Windows can hold the inherited handles for a short window (~0.1–0.2 s
measured) — `ERROR_SHARING_VIOLATION` on the scratch-file unlink. That OSError
in a `finally` *replaced the TimeoutError*, so the step reported a file error
instead of "timed out". Cleanup is now a bounded-retry helper
(`_cleanup_files`, 20 × 50 ms, never raises): a transcript error can never
mask the step's real outcome, and a file that somehow stays locked is left
behind as scratch rather than faked into a step failure.

**Test** (`test_killed_worker_kills_its_grandchildren_too`): the injected
worker records its own pid, spawns a child, the child spawns a grandchild —
all three record their pids and sleep. The step times out; the test asserts
**all three processes are dead** afterwards, through the real execution path
(`MJ_WORKER_OVERRIDE_DEV`, `killtree`) on each platform.

**Carried limitation:** deliberate breakaway (`setsid`, a new session or
`CREATE_BREAKAWAY_FROM_JOB`) escapes both mechanisms. No builtin does this;
escaping by design is a sandbox-level concern, not an enumerator's. POSIX
stragglers of a *normally finished* worker also survive (Windows does not:
`KILL_ON_JOB_CLOSE` disposes of them at handle close). Both stay open until
the sandbox step.

## 2. Assertions that can never fail — gone, and banned

- `tests/unit/test_world.py`: `assert any(...) or True` replaced with real
  invariants (sample non-empty, counts consistent, sum ≤ total) plus the
  check it was standing in for: when the sample is not truncated, the
  interpreter running the test **must** appear in it; if truncated, that's
  stated, not smuggled past a `or True`. A second tautology in
  `test_probe_processes_count_in_range` was tightened to the aggregation
  invariant (`count >= distinct_names >= 1`), and the vacuous
  `os.getpid() > 0` removed.
- `tests/adversarial/test_adversarial.py`: the shell-metacharacter test's
  loop asserted `... or True` and could never fail; it now fails if **any**
  entry in the sandbox contains the "benign parent" marker string.
- **New lint** — `tests/lint/test_dead_asserts.py`: AST scan (not text) of
  `tests/`, `src/`, `tools/` fails the suite on any expression containing
  `or True`, with self-tests proving it catches both operand orders and
  stays quiet on legitimate `or`. The pattern cannot come back without a red
  suite.

## 3. First Actions run — Linux failed exactly where predicted

Run 39407941124 (push `ab25f12`): **windows-latest green, ubuntu-latest red**
at the suite — `ModuleNotFoundError: No module named 'msvcrt'` from a
vestigial `import msvcrt` in `tests/unit/test_cli.py` (Windows-only module,
explicitly unused — `# noqa: F401`; interactive input arrives through
`subprocess.run(input=...)`, which is cross-platform). 97 of 98 passed on
Linux; the import is removed with a comment saying why it must not return.
The reviewer's "first Linux run on Windows-developed code usually fails
somewhere" was right, and it took one line.

Observations from the run itself: the workflow's step structure executed as
designed on both OSes (venv + hash-locked install + smoke all green before
the suite), and the annotation about `ubuntu-latest` migrating to Ubuntu 26
is informational.

## 4. Verification record (this update)

| Check | Result |
|---|---|
| Host suite after each change batch | **101 passed, exit 0** (100 + the grandchild test) |
| `tools/mutation_check.py` | **all 6 defenses killed, exit 0** |
| Isolated reproductions of the WinError | lock measured transient (≤ ~0.2 s), fixed by bounded retry |
| Direct `run_plan` reproduction (no pytest) | confirmed the shadowed TimeoutError, then confirmed the fix |

New tests: `test_killed_worker_kills_its_grandchildren_too` plus the two lint
tests (98 → 101).

## 5. Order and what's next

Standing order: **branch protection → read both platforms' runs → grandchild
kill + no-op assertions → credential broker → the reasoner.** Items 3 and 4
of that list are done here; item 2 continues with the next push's runs, item
1 is the one-time GitHub setting (both check names are known:
`ubuntu-latest`, `windows-latest`), and the reasoner still waits on §5 of
docs/09 becoming your decision.