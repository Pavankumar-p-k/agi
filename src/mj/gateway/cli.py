"""The ``mj`` command-line gateway.

Every command tags the input with a trust level (localterminal here; chat
connectors would tag lower later). The CLI never implements capabilities
itself — it only talks to the store, the planner and the runner, so all side
effects go through the same policy gate, executor and verifiers.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Any

from mj import AUTONOMY_LEVEL, __version__
from mj.brain import model as model_adapter
from mj.brain import planner, reasoner
from mj.core import audit, events, registry, settings, tasks
from mj.core.store import Store
from mj.executor import broker
from mj.executor import capabilities as caps
from mj.executor import runner
from mj.world import model
from mj.world import probes as probes_mod


def _utc(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def _bootstrap(store: Store) -> None:
    caps.ensure_registered(store)


def _model_status_for_display(store: Store) -> dict[str, Any]:
    """Model readiness with one addition over the adapter's own report: a
    key held in the encrypted broker (``model_api_key``) counts as present.
    Only *presence* is reported — the token itself is never read to display,
    never printed, and never logged here."""
    info = dict(model_adapter.status())
    _token, origin = reasoner.resolve_api_key(store)
    if origin == "broker":
        info["api_key_set"] = True
        info.setdefault("key_origin", "broker")
    return info


# -- commands ----------------------------------------------------------------


def cmd_status(store: Store, args: argparse.Namespace) -> int:
    _bootstrap(store)
    ok, count, problem = audit.verify(store)
    status = {
        "package": "mjcore",
        "version": __version__,
        "autonomy_level": AUTONOMY_LEVEL,
        "store": str(store.path),
        "capabilities": registry.list_all(store),
        "audit_chain": {"ok": ok, "entries": count, "problem": problem or None},
        "limits": settings.snapshot(),
        # Readiness only: the env contract is reported, never a key (and no
        # request is made by `status` — it must work offline). A key stored
        # in the broker (model_api_key) counts as set; its value is not read
        # here for display, only its *presence*.
        "model": _model_status_for_display(store),
        "note": "L0: observe only. No autonomy above L0 until awareness acceptance tests pass.",
    }
    _print(status)
    return 0


def _ask_from_facts(store: Store, question: str) -> dict[str, Any]:
    """Answer awareness questions from labeled facts; refresh then read."""
    q = question.lower()
    out: dict[str, Any] = {"question": question, "answers": []}
    wants = {
        "disk": any(w in q for w in ("disk", "storage", "free space", "space")),
        "processes": any(w in q for w in ("running", "process")),
        "apps": any(w in q for w in ("installed", "app")),
        "tools": any(w in q for w in ("tool", "version")),
    }
    if not any(wants.values()):
        wants = {k: True for k in wants}
    scopes = [k for k, want in wants.items() if want]
    # always refresh what the question asks about: awareness answers must be
    # minted from a fresh observation, so no stale fact is presented as current
    probes_mod.run_probes(store, scopes)
    for scope in scopes:
        for f in model.list_all(store, scope=scope):
            out["answers"].append(
                {
                    "topic": scope,
                    "value": f.value,
                    "source": f.source,
                    "observed_at": _utc(f.observed_at or 0.0),
                    "label": f.label,
                    "ttl_seconds": f.ttl_seconds,
                }
            )
    return out


def cmd_ask(store: Store, args: argparse.Namespace) -> int:
    _bootstrap(store)
    out = _ask_from_facts(store, " ".join(args.question).strip())
    _print(out)
    return 0


def _print_unknown_goal(exc: "planner.UnknownGoalError") -> None:
    """One targeted question, plus why a configured model could not help.

    A model failure must never look like an unsupported goal: the reason is
    shown here (and already audited by the planner), so "unknown goal" is only
    printed when the goal really is unknown.
    """
    out: dict[str, Any] = {"error": "unknown goal", "goal": exc.goal, "question": exc.question}
    if exc.reasoner_note:
        out["reasoner"] = exc.reasoner_note
    _print(out)


def cmd_plan(store: Store, args: argparse.Namespace) -> int:
    _bootstrap(store)
    params: dict[str, Any] = {}
    if args.dir:
        params["dir"] = args.dir
    if args.commit:
        params["commit"] = True
    if getattr(args, "show_prompt", False):
        # Diagnostic decided 2026-10-28: print exactly what the model would
        # see for this goal — no contact with any endpoint, no audit entry,
        # no plan. Disclosure review happens *before* a key is configured.
        _print(reasoner.show_prompt(store, args.goal, params))
        return 0
    try:
        plan = planner.build_plan(store, args.goal, params)
    except planner.UnknownGoalError as exc:
        _print_unknown_goal(exc)
        return 3
    _print(plan.to_dict())
    return 0


def cmd_run(store: Store, args: argparse.Namespace) -> int:
    _bootstrap(store)
    params: dict[str, Any] = {}
    if args.dir:
        params["dir"] = args.dir
    if args.commit:
        params["commit"] = True
    try:
        plan = planner.build_plan(store, args.goal, params)
    except planner.UnknownGoalError as exc:
        _print_unknown_goal(exc)
        return 3

    resume = None
    for attempt in range(2):
        try:
            report = runner.run_plan(
                store, plan, auto_approve=args.yes, resume_task_id=resume
            )
        except runner.ApprovalRequired as exc:
            if args.yes:
                raise
            resume = exc.task_id
            for appr in exc.approvals:
                print(json.dumps({"action_required": "approval", **appr}, indent=2))
                try:
                    reply = input("approve this step? [y/N] ").strip().lower()
                except EOFError:
                    reply = "n"  # a non-interactive prompt is an explicit refusal
                if reply == "y":
                    runner.grant_pending(store, exc.task_id, decided_by="user")
                else:
                    runner.deny_pending(store, exc.task_id, decided_by="user")
                    print("denied: task stays blocked.")
                    return 4
            continue
        _print({k: report[k] for k in ("state", "task_id", "summary", "verified_steps", "unverified_steps", "steps")})
        return 0 if report["state"] == "done" else 5
    return 4


def cmd_events(store: Store, args: argparse.Namespace) -> int:
    if args.task_id:
        _print(events.for_task(store, args.task_id))
    else:
        rows = store.query(
            "SELECT seq, ts, task_id, kind, payload_json FROM events ORDER BY seq DESC LIMIT ?",
            (args.limit,),
        )
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d.pop("payload_json"))
            out.append(d)
        _print(out)
    return 0


def cmd_registry(store: Store, args: argparse.Namespace) -> int:
    _bootstrap(store)
    lst = registry.list_all(store, healthy_only=args.healthy)
    for row in lst:
        if row["last_verified"]:
            row["last_verified"] = _utc(row["last_verified"])
    _print(lst)
    return 0


def cmd_facts(store: Store, args: argparse.Namespace) -> int:
    if args.refresh_all or not model.list_all(store):
        probes_mod.run_probes(store)
    for f in model.list_all(store):
        out = {
            "scope": f.scope,
            "key": f.key,
            "value": f.value,
            "source": f.source,
            "observed_at": _utc(f.observed_at or 0.0),
            "ttl_seconds": f.ttl_seconds,
            "label": f.label,
        }
        _print(out)
    return 0


def cmd_undo(store: Store, args: argparse.Namespace) -> int:
    """Undo the side effects of one done task (currently: files.organize)."""
    report = tasks.get(store, args.task_id)
    if report is None:
        print(json.dumps({"error": f"unknown task {args.task_id}"}, indent=2))
        return 2
    row = store.one(
        "SELECT r.output_json, p.capability_id FROM step_results r "
        "JOIN plan_steps p ON p.task_id = r.task_id AND p.step_id = r.step_id "
        "WHERE r.task_id = ? AND p.status = 'done' AND p.capability_id = 'files.organize' "
        "ORDER BY r.finished_at DESC",
        (args.task_id,),
    )
    if row is None:
        print(json.dumps({"error": "no undoable (files.organize) step results found for that task"}, indent=2))
        return 2
    output = json.loads(row["output_json"])
    if row["capability_id"] == "files.organize":
        audit.append(store, "user", "task.undo", {"task_id": args.task_id})
        result = caps.undo_organize(store, output, output)
        _print({"task_id": args.task_id, "undone": result["undone"]})
        return 0
    print(json.dumps({"error": f"no undo plan for capability {row['capability_id']}"}, indent=2))
    return 5


def cmd_audit(store: Store, args: argparse.Namespace) -> int:
    """Verify the chain, and optionally show why recent decisions were made.

    The `--entries` view exists so a refusal (for example a reasoner declined
    plan, docs/11) is auditable by the person, not only recorded.
    """
    ok, count, problem = audit.verify(store)
    out: dict[str, Any] = {"ok": ok, "entries": count, "problem": problem or None}
    if args.entries:
        out["recent"] = [
            {
                "seq": row["seq"],
                "ts": _utc(row["ts"]),
                "actor": row["actor"],
                "action": row["action"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in audit.entries(store, limit=args.entries)
        ]
    _print(out)
    return 0 if ok else 6


def _local_terminal() -> bool:
    """True only for an interactive terminal the user is sitting at.

    A redirect, a pipe, or an agent capturing output is not a local terminal,
    so nothing that runs through them can ever trigger a secret reveal — the
    model must never see a value.
    """
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def cmd_secrets(store: Store, args: argparse.Namespace) -> int:
    """Manage encrypted secrets in the broker.

    ``get`` shows metadata only (name, created, last used). Printing the
    value itself takes an explicit ``--reveal`` *and* a local terminal, so a
    piped or agent-driven CLI can never read one back out.
    """
    try:
        if args.secret_action == "set":
            if not args.key:
                _print({"error": "usage: mj secrets set KEY"})
                return 2
            # A terminal gets the no-echo prompt. Anything else (a pipe, an
            # operator script feeding stdin) reads one line: getpass would
            # hang on a non-tty Windows stdin. Setting is not revealing — the
            # value goes in, and nothing prints it back out.
            if _local_terminal():
                import getpass

                value = getpass.getpass("Secret value: ")
            else:
                value = sys.stdin.readline().strip() if sys.stdin else ""
            broker.set_secret(store, args.key, value)
            _print({"action": "set", "key": args.key})
            return 0
        if args.secret_action == "list":
            _print({"secrets": broker.list_secrets(store)})
            return 0
        if args.secret_action == "get":
            if not args.key:
                _print({"error": "usage: mj secrets get KEY [--reveal]"})
                return 2
            meta = broker.secret_meta(store, args.key)
            if meta is None:
                _print({"error": f"secret {args.key} not found"})
                return 2
            meta["created"] = _utc(meta["created"]) if meta["created"] else None
            meta["last_used"] = _utc(meta["last_used"]) if meta["last_used"] else None
            if not args.reveal:
                meta["value"] = "<hidden: metadata only; --reveal needs the local terminal>"
                _print(meta)
                return 0
            if not _local_terminal():
                _print(
                    {
                        "error": "refused: revealing a secret needs the local terminal "
                        "(stdin and stdout must be a TTY)",
                        "key": args.key,
                    }
                )
                return 4
            print(broker.get_secret(store, args.key))
            return 0
        if args.secret_action == "delete":
            if not args.key:
                _print({"error": "usage: mj secrets delete KEY"})
                return 2
            broker.delete_secret(store, args.key)
            _print({"action": "deleted", "key": args.key})
            return 0
        return 1
    except broker.BrokerError as exc:
        _print({"error": str(exc)})
        return 2


# -- wiring -------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mj",
        description=(
            "MJ Core CLI (L0). Awareness questions, typed plans, "
            "policy-gated execution with verification."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("status", help="version, autonomy level, registry health, audit chain")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("ask", help="answer a machine-awareness question from labeled facts")
    sp.add_argument("question", nargs="+")
    sp.set_defaults(func=cmd_ask)

    sp = sub.add_parser(
        "plan", help="show the typed plan for a goal without running it"
    )
    sp.add_argument("goal")
    sp.add_argument("--dir", default=None)
    sp.add_argument("--commit", action="store_true", help="plan real moves instead of a dry run")
    sp.add_argument(
        "--show-prompt",
        action="store_true",
        help="print the exact model prompt (redacted) this goal would produce, and send nothing",
    )
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("run", help="build, policy-gate, execute and verify the plan for a goal")
    sp.add_argument("goal")
    sp.add_argument("--dir", default=None)
    sp.add_argument("--commit", action="store_true", help="move files for real (organize)")
    sp.add_argument("--yes", action="store_true", help="auto-approve policy 'ask' steps (R2)")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("events", help="task event log")
    sp.add_argument("--task-id", dest="task_id", default=None)
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(func=cmd_events)

    sp = sub.add_parser("registry", help="capability registry")
    sp.add_argument("--healthy", action="store_true")
    sp.set_defaults(func=cmd_registry)

    sp = sub.add_parser("facts", help="world-model facts (with honest labels)")
    sp.add_argument("--refresh", action="store_true", dest="refresh_all")
    sp.set_defaults(func=cmd_facts)

    sp = sub.add_parser("undo", help="undo the recorded side effects of a done task")
    sp.add_argument("task_id")
    sp.set_defaults(func=cmd_undo)

    sp = sub.add_parser("audit", help="verify the hash-chained audit log")
    sp.add_argument(
        "--entries",
        type=int,
        default=0,
        help="also print the N most recent audit entries (why decisions were made)",
    )
    sp.set_defaults(func=cmd_audit)

    sp = sub.add_parser("secrets", help="manage encrypted secrets (set/list/get/delete)")
    sp.add_argument("secret_action", choices=["set", "list", "get", "delete"])
    sp.add_argument("key", nargs="?", default=None)
    sp.add_argument(
        "--reveal",
        action="store_true",
        help="print a secret value — refused unless stdin and stdout are the local terminal",
    )
    sp.set_defaults(func=cmd_secrets)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    store = Store.open()
    try:
        return args.func(store, args)
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
