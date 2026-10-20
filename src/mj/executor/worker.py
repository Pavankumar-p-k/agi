"""Subprocess entry point for capability execution — one step, one process.

Why a process and not a thread: Python threads cannot be killed. A worker
that overruns its deadline and is merely "abandoned" keeps running and can
still cause side effects after MJ has marked the step failed (docs/09 §2).
A subprocess is something MJ owns: on expiry ``subprocess.run`` terminates it,
and anything it produced afterwards — including the result file — is
discarded by the parent, never written back.

Protocol: a single JSON document on stdin:

    {"store_path": ..., "capability_id": ..., "inputs": {...},
     "code": <override or null>, "out_path": ..., "pid_path": ...}

The result (or the error) is written as JSON to ``out_path``; the worker's
pid goes to ``pid_path`` immediately so an operator (or a test) can confirm
the process is really gone after a timeout. The worker opens its *own*
store connection — SQLite WAL supports concurrent connections across
processes, and the kernel's connection is never shared with a step.

``code`` is the dev/test-only override (MJ_WORKER_OVERRIDE_DEV), resolved and
passed in by the parent. It runs in exactly the place a real capability would
run, so injected tests exercise the real execution path, including its death
by timeout.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    payload = json.load(sys.stdin)
    out_path = Path(payload["out_path"])
    pid_path = Path(payload.get("pid_path") or out_path.with_suffix(".pid"))
    pid_path.write_text(str(os.getpid()), encoding="utf-8")

    from mj.core.store import Store
    from mj.executor.capabilities import BUILTINS

    store = Store(Path(payload["store_path"]))
    try:
        code = payload.get("code")
        if code:
            namespace: dict[str, object] = {}
            exec(code, namespace)  # dev/test override — operator-controlled, like MJ_POLICY
            run = namespace["run"]
        else:
            run = BUILTINS[payload["capability_id"]].run
        output = run(store, dict(payload["inputs"]))
        out_path.write_text(json.dumps({"ok": True, "output": output}), encoding="utf-8")
        return 0
    except BaseException as exc:  # noqa: BLE001 - report every failure honestly
        out_path.write_text(
            json.dumps({"ok": False, "error": str(exc), "type": type(exc).__name__}),
            encoding="utf-8",
        )
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
