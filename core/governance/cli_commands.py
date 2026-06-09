# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""core/governance/cli_commands.py
CLI command handlers for governance subcommands.

  jarvis queue status
  jarvis queue list
  jarvis queue cancel <id>
  jarvis resources
  jarvis submit "task text"

These are imported by jarvis.py and registered as argparse sub-parsers.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

# ── helpers ───────────────────────────────────────────────────────────────────

def _colorize(text: str, color: str) -> str:
    codes = {"green": "32", "red": "31", "yellow": "33", "cyan": "36", "bold": "1"}
    code  = codes.get(color, "0")
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def _queue():
    from core.governance.work_queue import work_queue
    return work_queue


def _monitor():
    from core.governance.resource_monitor import resource_monitor
    return resource_monitor


def _router():
    from core.governance.task_router import task_router
    return task_router


# ── queue subcommands ─────────────────────────────────────────────────────────

def cmd_queue(args: argparse.Namespace) -> int:
    sub = getattr(args, "queue_command", None)

    if sub == "status":
        return _queue_status()
    if sub == "list":
        return _queue_list()
    if sub == "cancel":
        return _queue_cancel(args.task_id)

    # Default: show status
    return _queue_status()


def _queue_status() -> int:
    wq     = _queue()
    status = wq.get_status()
    print(_colorize("═" * 40, "bold"))
    print(_colorize(" JARVIS Work Queue Status", "bold"))
    print(_colorize("═" * 40, "bold"))
    for key, val in status.items():
        color = "green" if key == "done" else "yellow" if key == "pending" else "red" if key == "failed" else "cyan"
        print(f"  {key:<10}: {_colorize(str(val), color)}")
    return 0


def _queue_list() -> int:
    wq    = _queue()
    tasks = wq.list_tasks()
    if not tasks:
        print(_colorize("  Queue is empty.", "yellow"))
        return 0

    print(_colorize("═" * 80, "bold"))
    print(_colorize(f"  {'ID':<36}  {'P':>2}  {'STATUS':<12}  TASK", "bold"))
    print(_colorize("═" * 80, "bold"))
    for t in tasks:
        status = t.get("status", "?")
        color  = {
            "done": "green", "failed": "red",
            "running": "cyan", "pending": "yellow",
            "cancelled": "bold",
        }.get(status, "bold")
        task_preview = (t.get("task") or "")[:40]
        print(
            f"  {t['task_id']:<36}  {t['priority']:>2}  "
            f"{_colorize(f'{status:<12}', color)}  {task_preview}"
        )
    return 0


def _queue_cancel(task_id: str) -> int:
    wq        = _queue()
    cancelled = wq.cancel(task_id)
    if cancelled:
        print(_colorize(f"  ✓ Task {task_id} cancelled.", "green"))
    else:
        print(_colorize(f"  ✗ Could not cancel {task_id} (not found or already finished).", "red"))
    return 0 if cancelled else 1


# ── resources command ─────────────────────────────────────────────────────────

def cmd_resources(args: argparse.Namespace) -> int:
    mon  = _monitor()
    snap = mon.get_snapshot()

    def _bar(pct: float, width: int = 20) -> str:
        filled = int(pct / 100 * width)
        bar    = "█" * filled + "░" * (width - filled)
        color  = "green" if pct < 70 else "yellow" if pct < 85 else "red"
        return _colorize(f"[{bar}] {pct:5.1f}%", color)

    print(_colorize("═" * 50, "bold"))
    print(_colorize(" JARVIS System Resources", "bold"))
    print(_colorize("═" * 50, "bold"))
    print(f"  CPU   {_bar(snap.cpu_pct)}")
    print(f"  RAM   {_bar(snap.ram_pct)}")
    print(f"  DISK  {_bar(snap.disk_pct)}")
    print()
    print(f"  Active agents : {_colorize(str(snap.agent_count), 'cyan')}")
    print(f"  Active skills : {_colorize(', '.join(snap.active_skills) or 'none', 'cyan')}")
    print(f"  Concurrency   : {_colorize(str(mon.recommend_concurrency()), 'cyan')}")

    if mon.should_reject():
        print(_colorize("  ⚠  SYSTEM CRITICAL — new tasks will be rejected!", "red"))
    elif mon.should_throttle():
        print(_colorize("  ⚠  System load high — queue throttling active.", "yellow"))
    else:
        print(_colorize("  ✓  System healthy.", "green"))

    return 0


# ── submit command ────────────────────────────────────────────────────────────

def cmd_submit(args: argparse.Namespace) -> int:
    task     = " ".join(args.task)
    priority = getattr(args, "priority", 5)

    async def _do():
        from core.governance.work_queue import work_queue
        try:
            task_id = await work_queue.enqueue(task, priority=priority)
            print(_colorize(f"  ✓ Task submitted: {task_id}", "green"))
            print(f"    Priority : {priority}")
            print(f"    Task     : {task[:80]}")
        except RuntimeError as exc:
            print(_colorize(f"  ✗ {exc}", "red"))
            return 1
        return 0

    return asyncio.run(_do())


# ── route command (dry-run) ───────────────────────────────────────────────────

def cmd_route(args: argparse.Namespace) -> int:
    task = " ".join(args.task)

    async def _do():
        from core.governance.task_router import task_router
        decision = await task_router.route(task)
        print(_colorize("═" * 50, "bold"))
        print(_colorize(" Task Routing Decision (dry-run)", "bold"))
        print(_colorize("═" * 50, "bold"))
        print(f"  Task       : {task[:70]}")
        print(f"  Handler    : {_colorize(decision.handler, 'cyan')}")
        print(f"  Target     : {_colorize(decision.target, 'cyan')}")
        conf_color = "green" if decision.confidence >= 0.7 else "yellow" if decision.confidence >= 0.5 else "red"
        print(f"  Confidence : {_colorize(f'{decision.confidence:.0%}', conf_color)}")
        print(f"  Est. time  : {decision.estimated_duration_s:.1f}s")
        print(f"  Reasoning  : {decision.reasoning}")
        if decision.needs_clarification():
            print(_colorize("  ⚠  Confidence below 0.5 — clarification recommended.", "yellow"))
        return 0

    return asyncio.run(_do())


# ── argparse registration helper ──────────────────────────────────────────────

def register_governance_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register all governance CLI subcommands onto an argparse subparser group."""

    # queue
    queue_p = subparsers.add_parser("queue", help="Manage the JARVIS task queue.", prefix_chars="-/")
    queue_sub = queue_p.add_subparsers(dest="queue_command")

    queue_status = queue_sub.add_parser("status", help="Show pending/running/done counts.", prefix_chars="-/")
    queue_status.set_defaults(func=cmd_queue, queue_command="status")

    queue_list = queue_sub.add_parser("list", help="Show all tasks in the queue.", prefix_chars="-/")
    queue_list.set_defaults(func=cmd_queue, queue_command="list")

    queue_cancel = queue_sub.add_parser("cancel", help="Cancel a task by ID.", prefix_chars="-/")
    queue_cancel.add_argument("task_id", help="Task ID to cancel.")
    queue_cancel.set_defaults(func=cmd_queue, queue_command="cancel")

    queue_p.set_defaults(func=cmd_queue)

    # resources
    res_p = subparsers.add_parser("resources", help="Show CPU/RAM/agent resource usage.", prefix_chars="-/")
    res_p.set_defaults(func=cmd_resources)

    # submit
    submit_p = subparsers.add_parser("submit", help='Submit a task: jarvis submit "task description"', prefix_chars="-/")
    submit_p.add_argument("task", nargs=argparse.REMAINDER, help="Task description (quoted or unquoted).")
    submit_p.add_argument("--priority", "-p", type=int, default=5, help="Priority 1 (urgent) – 10 (background).")
    submit_p.set_defaults(func=cmd_submit)

    # route (dry-run)
    route_p = subparsers.add_parser("route", help='Dry-run route a task: jarvis route "task"', prefix_chars="-/")
    route_p.add_argument("task", nargs=argparse.REMAINDER, help="Task description.")
    route_p.set_defaults(func=cmd_route)
