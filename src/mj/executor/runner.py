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
import threading
import time
import uuid
from typing import Any, Callable

from mj.brain import planner
from mj.core import audit, events, registry, settings, tasks
from mj.core.policy import ASK, DENY, PolicyGate
from mj.core.store import Store, canonical_json
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


def _run_with_timeout(
    store: Store,
    run_fn: Callable[[Store, dict[str, Any]], dict[str, Any]],
    inputs: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    """Run a worker under a wall-clock deadline (docs/08).

    The worker gets its *own* store connection (WAL allows concurrent
    connections; sqlite connections are not thread-safe), so an abandoned
    worker can never race the kernel's connection. On expiry we stop waiting:
    the step fails as timed out and the daemon thread is abandoned. Side
    effects it performs afterwards are invisible to the report — a timeout is
    an unknown outcome, never a success, and re-running the step requires a
    fresh approval if it was gated.
    """
    if timeout_s <= 0:
        return run_fn(store, dict(inputs))
    box: dict[str, Any] = {}

    def target() -> None:
        worker_store = Store(store.path)
        try:
            box["output"] = run_fn(worker_store, dict(inputs))
        except BaseException as exc:  # re-raised on the main thread below
            box["error"] = exc
        finally:
            worker_store.close()

    worker = threading.Thread(target=target, name="mj-step-worker", daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        raise TimeoutError(
            f"step timed out after {timeout_s:g}s (MJ_STEP_TIMEOUT_S); worker "
            "abandoned — side effects before expiry are unrecorded and must be "
            "re-observed"
        )
    if "error" in box:
        raise box["error"]
    if "output" in box:
        return box["output"]
    raise RuntimeError("step worker produced no result")


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
            output = _run_with_timeout(store, impl.run, step.inputs, timeout_s)
            evidence = impl.verify(store, dict(step.inputs), output)
            verified = bool(evidence.get("verified"))
        except Exception as exc:  # record the failure honestly, halt the DAG
            finished = time.time()
            store.conn.execute(
                "INSERT OR REPLACE INTO step_results "
                "(idempotency_key, task_id, step_id, output_json, verified, evidence_json, started_at, finished_at) "
                "VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
                (
                    key,
                    task_id,
                    step.step_id,
                    canonical_json({"error": str(exc)}),
                    canonical_json({"exception": str(exc)}),
                    started,
                    finished,
                ),
            )
            store.conn.execute(
                "UPDATE plan_steps SET status = 'failed' WHERE task_id = ? AND step_id = ?",
                (task_id, step.step_id),
            )
            events.append(
                store, "step.failed", {"step_id": step.step_id, "error": str(exc)}, task_id=task_id
            )
            failed = {"step_id": step.step_id, "error": str(exc)}
            break
        finished = time.time()
        store.conn.execute(
            "INSERT OR REPLACE INTO step_results "
            "(idempotency_key, task_id, step_id, output_json, verified, evidence_json, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                task_id,
                step.step_id,
                canonical_json(output),
                1 if verified else 0,
                canonical_json(evidence),
                started,
                finished,
            ),
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
