"""The deterministic executor: the only thing allowed to touch the world.

The brain emits a typed plan; this runner walks it. The LLM (when it exists)
never runs steps itself, never holds credentials, and never edits policy
(invariants 1, 2, 8). Every step:
  * is checked by the policy gate (allow/ask/deny decided outside the model),
  * carries an idempotency key, so a retry or a resumed run reuses the
    recorded result instead of duplicating a side effect (failure mode 7),
  * is graded by an independent verifier, which may disagree with the
    worker — the report separates verified from unverified (failures 3, 30).

Resumability: an approval binds to the exact step payload hash (failure 25),
and plan ids are deterministic, so granting an approval and re-running the
same goal reuses recorded step results and never double-executes a side
effect. A task waiting approval is resumed with ``resume_task_id``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from mj.brain import planner
from mj.core import audit, events, registry, settings, tasks
from mj.core.effects import SENSITIVE_EFFECTS
from mj.core.policy import ASK, DENY, Decision, PolicyGate
from mj.core.store import Store, canonical_json
from mj.executor import broker, killtree
from mj.executor.capabilities import BUILTINS, Impl


class ApprovalRequired(Exception):
    """Raised when the policy says 'ask' and no grant has been recorded yet."""

    def __init__(self, approvals: list[dict[str, Any]], task_id: str):
        self.approvals = approvals
        self.task_id = task_id
        super().__init__(
            f"{len(approvals)} step(s) require approval; the exact payload is shown, not a summary"
        )


def _payload_hash(step: planner.Step) -> str:
    return hashlib.sha256(canonical_json(step.to_dict()).encode("utf-8")).hexdigest()


def _dev_override(capability_id: str) -> str | None:
    """Test/dev-only worker code override (MJ_WORKER_OVERRIDE_DEV).

    The env var names a JSON file ``{"capability": ..., "code": ...}`` where
    ``code`` defines ``run(store, inputs)``. Like MJ_POLICY, it is
    operator-controlled input to a local tool, not an attack surface: it can
    only affect the step it names, in the worker subprocess where that step
    would run anyway.
    """
    path = os.environ.get("MJ_WORKER_OVERRIDE_DEV")
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("capability") != capability_id:
        return None
    return data["code"]


# A just-terminated worker can keep its inherited stdout/stderr handles for
# a short window on Windows (handle teardown lags the process object being
# signaled), so removing scratch files right after a kill can hit
# ERROR_SHARING_VIOLATION. Retry briefly instead of failing the step.
_UNLINK_ATTEMPTS = 20
_UNLINK_RETRY_S = 0.05


def _cleanup_files(*paths: Path) -> None:
    """Remove a step's scratch files — best effort, never raises.

    Cleanup must never shadow the step's real outcome: an unlink OSError in
    a `finally` used to *replace* the TimeoutError this function's callers
    raise. A file that stays locked past the retries is left behind (scratch,
    not state) rather than turned into a fake step failure.
    """
    for path in paths:
        for _ in range(_UNLINK_ATTEMPTS):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                time.sleep(_UNLINK_RETRY_S)
            else:
                break


def _run_step(
    store: Store,
    capability_id: str,
    inputs: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    """Execute one step in its own subprocess — a process MJ can kill.

    Python threads cannot be killed; an "abandoned" thread keeps running and
    can cause side effects after the step is marked failed. One subprocess
    per step makes the deadline real (docs/09 §2, docs/10 §1): on expiry the
    worker's whole process group/job is killed — including processes the
    worker itself spawned — before raising, and the result file it may have
    written is discarded — a late result is never written back. The worker
    opens its own store connection (WAL), so it can never race the kernel's.
    """
    code = _dev_override(capability_id)
    if os.environ.get("MJ_WORKER_MODE") == "inline" or timeout_s <= 0:
        # inline mode (debugging) or no deadline: run in this process
        if code:
            namespace: dict[str, Any] = {}
            exec(code, namespace)  # dev/test only — see _dev_override
            run_fn = namespace["run"]
        else:
            run_fn = BUILTINS[capability_id].run
        return run_fn(store, dict(inputs))

    token = uuid.uuid4().hex
    out_path = store.path.parent / f"worker-{token}.json"
    pid_path = store.path.parent / f"worker-{token}.pid"
    payload = canonical_json(
        {
            "store_path": str(store.path),
            "capability_id": capability_id,
            "inputs": dict(inputs),
            "code": code,
            "out_path": str(out_path),
            "pid_path": str(pid_path),
        }
    )
    env = dict(os.environ)
    # The master key unlocks every stored credential; a worker never needs it
    # (values arrive in its stdin payload), so it must not be inherited. The
    # model API key is the reasoner's alone (docs/11): a capability worker has
    # no reason to hold it, so it does not see it either.
    env.pop("MJ_BROKER_KEY", None)
    env.pop("MJ_MODEL_API_KEY", None)
    src_root = str(Path(__file__).resolve().parents[2])  # .../src
    env["PYTHONPATH"] = src_root + os.pathsep + env.get("PYTHONPATH", "")
    stdout_path = store.path.parent / f"worker-{token}.stdout"
    stderr_path = store.path.parent / f"worker-{token}.stderr"
    try:
        timed_out = False
        try:
            # stdout/stderr go to files, not pipes: a stray grandchild
            # inheriting the handles can never wedge a pipe read below.
            with open(stdout_path, "w", encoding="utf-8", errors="replace") as out_log, open(
                stderr_path, "w", encoding="utf-8", errors="replace"
            ) as err_log:
                proc = killtree.spawn(
                    [sys.executable, "-m", "mj.executor.worker"],
                    env=env,
                    stdout=out_log,
                    stderr=err_log,
                )
                try:
                    proc.communicate(input=payload, timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    # The deadline kills the worker *and its whole process
                    # group/job* (docs/10 §1): a process the worker spawned
                    # must not outlive the step and keep acting after MJ
                    # marked it failed.
                    killtree.kill_tree(proc)
                finally:
                    killtree.reap(proc)
        except OSError as exc:
            raise RuntimeError(f"could not start worker: {exc}") from exc
        if timed_out:
            # Whatever the worker was still doing — alone or in its
            # children — is over. Its half-written result (if any) is
            # discarded below: a timeout is an unknown outcome, never a
            # success.
            raise TimeoutError(
                f"step timed out after {timeout_s:g}s (MJ_STEP_TIMEOUT_S); worker "
                "process tree killed — side effects before expiry are unrecorded and "
                "must be re-observed; a late result is discarded, never written back"
            ) from None
        try:
            if not out_path.is_file():
                tail = stderr_path.read_text(encoding="utf-8", errors="replace").strip()[-500:]
                raise RuntimeError(
                    f"worker produced no result (exit {proc.returncode}): {tail}"
                )
            result = json.loads(out_path.read_text(encoding="utf-8"))
        finally:
            killtree.release(proc)
    finally:
        _cleanup_files(out_path, pid_path, stdout_path, stderr_path)
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "worker failed"))
    return result["output"]


def _record_step_result(
    store: Store,
    idempotency_key: str,
    task_id: str,
    step_id: str,
    output_json: str,
    verified: int,
    evidence_json: str | None,
    started_at: float,
    finished_at: float,
) -> bool:
    """Persist a step result — write-once (docs/09 §2).

    step_results keyed by idempotency_key is the record of *the* result of an
    exact step execution. ON CONFLICT DO NOTHING makes a late or duplicate
    write (e.g. a worker that finished after its deadline was declared) lose
    against the recorded truth, and the discard is audited so nothing vanishes
    without a trace. The final state, once recorded, is final.
    """
    cur = store.conn.execute(
        "INSERT INTO step_results "
        "(idempotency_key, task_id, step_id, output_json, verified, evidence_json, started_at, finished_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(idempotency_key) DO NOTHING",
        (idempotency_key, task_id, step_id, output_json, verified, evidence_json, started_at, finished_at),
    )
    if cur.rowcount == 0:
        audit.append(
            store,
            "executor",
            "step.result.discarded",
            {
                "task_id": task_id,
                "step_id": step_id,
                "idempotency_key": idempotency_key,
                "reason": "a result is already recorded for this key; late/duplicate write discarded",
            },
        )
        return False
    return True


def _existing_approval(
    store: Store, task_id: str, step_id: str, payload_hash: str
) -> dict[str, Any] | None:
    row = store.one(
        "SELECT * FROM approvals WHERE task_id = ? AND step_id = ? AND payload_hash = ? "
        "ORDER BY requested_at DESC LIMIT 1",
        (task_id, step_id, payload_hash),
    )
    return dict(row) if row else None


def _grant(store: Store, approval_id: str, decided_by: str) -> None:
    row = store.one("SELECT state FROM approvals WHERE id = ?", (approval_id,))
    if row is None or row["state"] == "granted":
        return
    store.conn.execute(
        "UPDATE approvals SET state = 'granted', decided_at = ?, decided_by = ?, "
        "decision = 'grant' WHERE id = ?",
        (time.time(), decided_by, approval_id),
    )
    events.append(
        store, "approval.granted", {"approval_id": approval_id, "decided_by": decided_by}
    )


def _deny(store: Store, approval_id: str, decided_by: str) -> None:
    store.conn.execute(
        "UPDATE approvals SET state = 'denied', decided_at = ?, decided_by = ?, "
        "decision = 'deny' WHERE id = ?",
        (time.time(), decided_by, approval_id),
    )
    events.append(store, "approval.denied", {"approval_id": approval_id})


def grant_pending(store: Store, task_id: str, decided_by: str = "user") -> int:
    """Grant every pending approval of a task; the payload hash was bound at request time."""
    pending = store.query(
        "SELECT id FROM approvals WHERE task_id = ? AND state = 'pending'", (task_id,)
    )
    for row in pending:
        _grant(store, row["id"], decided_by)
    return len(pending)


def deny_pending(store: Store, task_id: str, decided_by: str = "user") -> int:
    pending = store.query(
        "SELECT id FROM approvals WHERE task_id = ? AND state = 'pending'", (task_id,)
    )
    for row in pending:
        _deny(store, row["id"], decided_by)
    return len(pending)


def run_plan(
    store: Store,
    plan: planner.Plan,
    trust_level: str = "local-terminal",
    auto_approve: bool = False,
    resume_task_id: str | None = None,
) -> dict[str, Any]:
    """Execute a validated plan. New runs create a task; resumes reuse one.

    Resumable and idempotent: identical goals/params -> identical plan_id ->
    identical idempotency keys; recorded step results are reused verbatim.
    """
    gate = PolicyGate.load()
    timeout_s = settings.step_timeout_s()
    budget_s = settings.task_budget_s()
    resuming = resume_task_id is not None
    if resuming:
        task = tasks.get(store, resume_task_id or "")
        if task is None:
            raise ValueError(f"cannot resume unknown task {resume_task_id!r}")
        if task["state"] != "awaiting_approval":
            raise ValueError(
                f"task {task['id']} is {task['state']!r}; only an awaiting_approval task can be resumed"
            )
        task_id = task["id"]
    else:
        task = tasks.create(store, plan.goal, trust_level)
        task_id = task["id"]

    steps_order = planner.validate_plan(plan, store)
    if not resuming:
        planner.persist_plan(store, plan, task_id)
        tasks.transition(
            store, task_id, "planned", {"plan_id": plan.plan_id, "steps": len(plan.steps)}
        )

    # -- policy gate on every step before any execution (plan workflow A, step 6)
    decisions: dict[str, dict[str, Any]] = {}
    needs_approval: list[dict[str, Any]] = []
    denied: list[str] = []
    for step in steps_order:
        manifest, _ = registry.get(store, step.capability_id)
        d = gate.decide(store, "user", manifest.risk_class, trust_level)
        # Effects floor (docs/09 §3): sensitive effects (network, process,
        # secrets) run on the local terminal only. Registration enforces the
        # declaration; this enforces it at runtime too, so a legacy or
        # compromised row that skipped validation still cannot act.
        sensitive = SENSITIVE_EFFECTS & set(manifest.effects)
        if sensitive and trust_level != "local-terminal":
            d = Decision(
                DENY,
                d.rule,
                f"effect(s) {', '.join(sorted(sensitive))} are local-terminal only; "
                f"trust {trust_level!r} cannot run them",
            )
        decisions[step.step_id] = d.to_dict()
        p_hash = _payload_hash(step)
        if d.action == DENY:
            denied.append(step.step_id)
            continue
        if d.action != ASK:
            continue
        approval = _existing_approval(store, task_id, step.step_id, p_hash)
        if approval is None:
            approval_id = f"a-{uuid.uuid4().hex[:10]}"
            store.conn.execute(
                "INSERT INTO approvals (id, task_id, step_id, payload_json, payload_hash, "
                "risk_class, state, requested_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    approval_id,
                    task_id,
                    step.step_id,
                    canonical_json(step.to_dict()),
                    p_hash,
                    manifest.risk_class,
                    time.time(),
                ),
            )
        elif approval["state"] == "granted":
            continue  # standing grant bound to the same payload hash
        if auto_approve and approval is None:
            row = _existing_approval(store, task_id, step.step_id, p_hash)
            assert row is not None
            _grant(store, row["id"], "auto-approve")
            continue
        if auto_approve and approval["state"] != "granted":
            _grant(store, approval["id"], "auto-approve")
            continue
        approval = _existing_approval(store, task_id, step.step_id, p_hash)
        needs_approval.append(
            {
                "approval_id": approval["id"],
                "step_id": step.step_id,
                "risk_class": manifest.risk_class,
                "payload": step.to_dict(),
                "payload_hash": p_hash,
                "reason": d.reason,
            }
        )

    audit.append(
        store,
        "executor",
        "policy.gate",
        {"task_id": task_id, "actions": {k: v["action"] for k, v in decisions.items()}},
    )

    if denied:
        if resuming:
            tasks.transition(store, task_id, "blocked", {"denied_steps": denied})
        else:
            tasks.transition(store, task_id, "policy_checked", {"decisions": decisions})
            tasks.transition(store, task_id, "blocked", {"denied_steps": denied})
        report = _report(store, task_id, plan, decisions, denied=denied)
        tasks.set_report(store, task_id, report)
        report["state"] = "blocked"
        report["task_id"] = task_id
        return report

    if needs_approval:
        if not resuming:
            tasks.transition(store, task_id, "policy_checked", {"decisions": decisions})
            tasks.transition(store, task_id, "awaiting_approval", {"count": len(needs_approval)})
        raise ApprovalRequired(needs_approval, task_id)

    if resuming:
        tasks.transition(store, task_id, "executing", {"resumed": True})
    else:
        tasks.transition(store, task_id, "policy_checked", {"decisions": decisions})
        tasks.transition(store, task_id, "executing", {"plan_id": plan.plan_id})

    # -- execute the DAG in topological order ---------------------------------
    exec_started = time.time()
    failed: dict[str, Any] | None = None
    results: list[dict[str, Any]] = []
    for step in steps_order:
        if failed is not None:
            store.conn.execute(
                "UPDATE plan_steps SET status = 'skipped' WHERE task_id = ? AND step_id = ?",
                (task_id, step.step_id),
            )
            continue

        manifest, _ = registry.get(store, step.capability_id)
        key = planner.key_for(plan, step)
        planner.set_step_key(store, task_id, step.step_id, key)
        prior = store.one(
            "SELECT output_json, verified, evidence_json FROM step_results WHERE idempotency_key = ?",
            (key,),
        )
        if prior is not None:
            # A previous run already executed this exact step: reuse the
            # recorded result, never re-trigger the side effect.
            evidence = json.loads(prior["evidence_json"] or "null")
            verified = bool(prior["verified"])
            store.conn.execute(
                "UPDATE plan_steps SET status = 'reused' WHERE task_id = ? AND step_id = ?",
                (task_id, step.step_id),
            )
            events.append(
                store, "step.reused", {"step_id": step.step_id, "key": key}, task_id=task_id
            )
            results.append(
                {
                    "step_id": step.step_id,
                    "status": "reused",
                    "capability": step.capability_id,
                    "risk_class": manifest.risk_class,
                    "verified": verified,
                    "evidence": evidence,
                    "duration_s": 0.0,
                }
            )
            continue

        # -- per-task budget: refuse to start work this run cannot afford ---
        if (time.time() - exec_started) >= budget_s:
            store.conn.execute(
                "UPDATE plan_steps SET status = 'skipped' WHERE task_id = ? AND step_id = ?",
                (task_id, step.step_id),
            )
            events.append(
                store,
                "step.skipped",
                {"step_id": step.step_id, "reason": "task budget exhausted"},
                task_id=task_id,
            )
            failed = {
                "step_id": step.step_id,
                "error": f"task budget exhausted: {time.time() - exec_started:.1f}s used "
                f"of {budget_s:g}s (MJ_TASK_BUDGET_S); step not started",
            }
            break

        impl: Impl = BUILTINS[step.capability_id]
        store.conn.execute(
            "UPDATE plan_steps SET status = 'executing' WHERE task_id = ? AND step_id = ?",
            (task_id, step.step_id),
        )
        events.append(store, "step.start", {"step_id": step.step_id}, task_id=task_id)
        started = time.time()
        try:
            # Credential broker: resolve secret *names* to values here, at
            # execution time only, right before the worker subprocess spawns.
            # The manifest declares its allowed names in requires_scopes; the
            # broker refuses anything outside it. The resolved copy is handed
            # to the worker and dropped afterwards — the plan payload, audit
            # trail, and reports keep names only.
            exec_inputs = step.inputs
            exec_manifest, _ = registry.get(store, step.capability_id)
            if "secrets" in (exec_manifest.effects or []):
                exec_inputs = broker.inject_secrets(
                    store, dict(step.inputs), exec_manifest.requires_scopes
                )
            # Everything a worker hands back is scrubbed of every stored
            # secret before it can be verified, recorded, reported or
            # printed: output, raised error text, and the stderr tail of a
            # worker that died without a result all pass through here.
            known = broker.known_secrets(store)
            output = _run_step(store, step.capability_id, exec_inputs, timeout_s)
            output = broker.redact(output, known)
            evidence = impl.verify(store, dict(step.inputs), output)
            verified = bool(evidence.get("verified"))
        except Exception as exc:  # record the failure honestly, halt the DAG
            finished = time.time()
            error = broker.redact(str(exc), broker.known_secrets(store))
            _record_step_result(
                store,
                key,
                task_id,
                step.step_id,
                canonical_json({"error": error}),
                0,
                canonical_json({"exception": error}),
                started,
                finished,
            )
            store.conn.execute(
                "UPDATE plan_steps SET status = 'failed' WHERE task_id = ? AND step_id = ?",
                (task_id, step.step_id),
            )
            events.append(
                store, "step.failed", {"step_id": step.step_id, "error": error}, task_id=task_id
            )
            failed = {"step_id": step.step_id, "error": error}
            break
        finished = time.time()
        _record_step_result(
            store,
            key,
            task_id,
            step.step_id,
            canonical_json(output),
            1 if verified else 0,
            canonical_json(evidence),
            started,
            finished,
        )
        store.conn.execute(
            "UPDATE plan_steps SET status = 'done' WHERE task_id = ? AND step_id = ?",
            (task_id, step.step_id),
        )
        events.append(
            store, "step.result", {"step_id": step.step_id, "verified": verified}, task_id=task_id
        )
        audit.append(
            store,
            "executor",
            "step.verified" if verified else "step.unverified",
            {"task_id": task_id, "step_id": step.step_id, "capability": step.capability_id},
        )
        if verified:
            registry.mark_verified(store, step.capability_id)
        else:
            registry.set_status(store, step.capability_id, "degraded")
        results.append(
            {
                "step_id": step.step_id,
                "status": "executed",
                "capability": step.capability_id,
                "risk_class": manifest.risk_class,
                "verified": verified,
                "evidence": evidence,
                "duration_s": round(finished - started, 3),
            }
        )

    # -- verifying -> done | failed -------------------------------------------
    tasks.transition(store, task_id, "verifying", {})
    report = _report(store, task_id, plan, decisions, results=results, failed=failed)
    tasks.set_report(store, task_id, report)
    report["task_id"] = task_id
    if failed is not None:
        tasks.transition(store, task_id, "failed", failed)
        report["state"] = "failed"
        return report

    tasks.transition(
        store,
        task_id,
        "done",
        {"verified": report["verified_steps"], "unverified": report["unverified_steps"]},
    )
    audit.append(
        store,
        "executor",
        "task.complete",
        {
            "task_id": task_id,
            "verified": report["verified_steps"],
            "unverified": report["unverified_steps"],
        },
    )
    report["state"] = "done"
    return report


def _report(
    store: Store,
    task_id: str,
    plan: planner.Plan,
    decisions: dict[str, dict[str, Any]],
    results: list[dict[str, Any]] | None = None,
    failed: dict[str, Any] | None = None,
    denied: list[str] | None = None,
) -> dict[str, Any]:
    results = results or []
    if results and all(r["verified"] for r in results):
        summary = "every step verified"
    elif denied:
        summary = "blocked at policy gate: " + ",".join(denied)
    elif failed is not None:
        summary = f"failed at step {failed['step_id']}: {failed['error']}"
    else:
        summary = "some steps unverified"
    return {
        "goal": plan.goal,
        "plan_id": plan.plan_id,
        "decisions": decisions,
        "denied_steps": denied or [],
        "failed_step": failed,
        "steps": results,
        "verified_steps": sum(1 for r in results if r["verified"]),
        "unverified_steps": sum(1 for r in results if not r["verified"]),
        "summary": summary,
    }
