"""The gap the second review flagged: grandchildren of a killed worker.

`killtree` was wired into the runner but untested — a code path claiming to
kill a whole tree that no test exercised is a claim, not a defense. These
tests spawn a real worker which spawns a real grandchild that appends to a
file forever; after `kill_tree` the file must stop growing. That is the only
evidence that survives a process inspector disagreeing with us: writes are
observable, process tables are racy.

POSIX kills the worker's process group (start_new_session); Windows kills the
job object (TerminateJobObject, with taskkill /T as fallback). Both are
covered by running the same test on both OSs in CI.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from mj.executor import killtree

#: A worker that spawns a grandchild writer and then idles. The grandchild is
#: what survives a naive worker-only kill.
_WORKER = r"""
import subprocess, sys, time

path = sys.argv[1]
child = (
    "import sys, time\n"
    "p = sys.argv[1]\n"
    "while True:\n"
    "    with open(p, 'a', encoding='utf-8') as fh:\n"
    "        fh.write('x' * 64)\n"
    "    time.sleep(0.02)\n"
)
subprocess.Popen([sys.executable, "-c", child, path])
while True:
    time.sleep(0.05)
"""


def _grew(path: Path, minimum: int = 256, deadline_s: float = 10.0) -> int:
    """Block until the file has grown past `minimum` bytes; return its size."""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        size = path.stat().st_size if path.exists() else 0
        if size > minimum:
            return size
        time.sleep(0.02)
    raise AssertionError(f"grandchild never wrote to {path} within {deadline_s}s")


def _spawn_worker(path: Path, tmp_path: Path) -> subprocess.Popen:
    out = (tmp_path / "worker.out").open("w", encoding="utf-8")
    err = (tmp_path / "worker.err").open("w", encoding="utf-8")
    try:
        return killtree.spawn(
            [sys.executable, "-c", _WORKER, str(path)],
            env={**os.environ},
            stdout=out,
            stderr=err,
        )
    finally:
        # killtree.spawn handed these to the child; the parent copy can close.
        out.close()
        err.close()


def test_killing_a_worker_stops_its_grandchild_writing(tmp_path: Path) -> None:
    heartbeat = tmp_path / "grandchild.heartbeat"
    proc = _spawn_worker(heartbeat, tmp_path)
    try:
        _grew(heartbeat)  # the grandchild is real and alive
        killtree.kill_tree(proc)
        killtree.reap(proc, grace_s=5.0)

        # Let any in-flight write land, then require silence.
        time.sleep(0.3)
        settled = heartbeat.stat().st_size
        time.sleep(0.6)
        assert heartbeat.stat().st_size == settled, (
            "grandchild kept writing after the worker tree was killed: "
            f"{settled} -> {heartbeat.stat().st_size} bytes"
        )
    finally:
        try:
            killtree.kill_tree(proc)
        except Exception:  # noqa: BLE001 - cleanup must never mask the verdict
            pass
        killtree.reap(proc, grace_s=2.0)


def test_killing_the_worker_actually_ends_the_worker(tmp_path: Path) -> None:
    """Belt: whatever the tree kill did, the worker itself must be gone."""
    heartbeat = tmp_path / "worker.heartbeat"
    proc = _spawn_worker(heartbeat, tmp_path)
    try:
        _grew(heartbeat, minimum=64)
        killtree.kill_tree(proc)
        killtree.reap(proc, grace_s=5.0)
        assert proc.poll() is not None, "worker still running after kill_tree"
    finally:
        killtree.kill_tree(proc)
        killtree.reap(proc, grace_s=2.0)
