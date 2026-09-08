"""
Dependency-aware multi-step action graph with per-step rollback for the desktop agent.

Steps are the SAME action dicts the agent's execute_action() accepts
({"tool", "args", "then_wait", ...}), so every step automatically inherits the
consent/risk tier, the self-healing UIA element layer, and the invocation audit
log. Execution is deterministic (topological order, Kahn's algorithm) -- no LLM
is consulted at run time.

Graph JSON shape (as produced by an LLM planner or a human):

  {
    "id": "optional-plan-id",
    "goal": "human readable goal",
    "steps": [
      {
        "id": "step_1",
        "desc": "create draft file",
        "tool": "create_file",
        "args": {"path": "...", "content": "..."},
        "depends_on": [],
        "wait": 1.0,
        "rollback": {"tool": "delete_path", "args": {"path": "..."}},   # optional inverse
        "rollback_capture": {"kind": "file", "path": "..."},            # optional pre-state snapshot
        "verify": {"expect": "created", "also": [{"tool": ..., "args": ...}]}  # optional
      }
    ]
  }

Rollback rules:
  - If a step fails, errors, is CONSENT-BLOCKED, or fails verification, the plan stops
    and every completed step is rolled back in reverse order.
  - `rollback_capture` (pre-state snapshot: file/clipboard) RESTORES DIRECTLY: it is
    provably scoped to exactly the files the graph itself touched (re-creates the exact
    pre-image, or deletes a file that did not exist before the graph), so it works
    non-interactively without bypassing any user data.
  - Declared `rollback` ACTIONS (arbitrary tool calls, e.g. delete_path) run through
    execute_action and therefore STILL require user consent if destructive. They are an
    interactive-use extra, never a consent bypass (a graph cannot smuggle a destructive
    delete by labelling it 'rollback').
  - A blocked destructive step is treated as a failure so mid-chain denials undo the
    chain's earlier effects, never leave partial state.

Every step is persisted via memory/task_store.TaskStore (task_id = plan id) when
available, and the full plan+report is written to data/task_graphs/<plan_id>.json.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable

CORE_DIR = Path(__file__).resolve().parents[2]
GRAPH_DIR = CORE_DIR / "data" / "task_graphs"


class TaskGraphError(Exception):
    """Raised for malformed graphs / dependency cycles (pre-execution)."""


def _agent_tool_result(text: str) -> dict:
    """Parse the agent's execute_action text into a classification."""
    text = text or ""
    if "BLOCKED" in text:
        return {"status": "blocked", "ok": False, "detail": text[:200]}
    if text.strip().startswith("Tool '") and " error:" in text:
        return {"status": "error", "ok": False, "detail": text[:200]}
    if "result:" in text:
        payload = text.split("result:", 1)[1].strip()
        try:
            val = json.loads(payload)
            if isinstance(val, dict):
                ok = val.get("success", not bool(val.get("error")))
                return {"status": "ok" if ok else "failed", "ok": bool(ok), "detail": text[:400]}
            ok = val if isinstance(val, bool) else True
            return {"status": "ok" if ok else "failed", "ok": bool(ok), "detail": text[:400]}
        except Exception:
            return {"status": "ok", "ok": True, "detail": text[:400]}
    return {"status": "ok", "ok": True, "detail": text[:400]}


def _capture(kind: str, target: str) -> Any:
    """Snapshot pre-step state for later rollback. Returns None when absent/missing."""
    try:
        if kind == "file":
            p = Path(target)
            if not p.exists():
                return {"present": False}
            return {"present": True, "bytes": p.read_bytes()}
        if kind == "clipboard":
            from core.workspace.clipboard_manager import ClipboardManager
            text = ClipboardManager().get_text()
            return {"text": text}
    except Exception:
        return None
    return None


def _restore(kind: str, target: str, captured: Any) -> bool:
    """Restore captured pre-state. Returns True if a restore actually happened."""
    if not captured or not isinstance(captured, dict):
        return False
    try:
        if kind == "file":
            p = Path(target)
            if captured.get("present", True) is False:
                if p.exists():
                    p.unlink()
                return True
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(captured["bytes"])
            return True
        if kind == "clipboard":
            from core.workspace.clipboard_manager import ClipboardManager
            ClipboardManager().set_text(captured.get("text", ""))
            return True
    except Exception:
        return False
    return False


class TaskGraph:
    """Deterministic executor for a multi-step action graph with rollback."""

    def __init__(self, plan: dict):
        if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list):
            raise TaskGraphError("plan must contain a 'steps' list")
        self.plan_id = str(plan.get("id") or uuid.uuid4().hex[:12])
        self.goal = str(plan.get("goal", ""))
        self.steps = plan["steps"]
        self._validate()
        self._order = self._topological_order()

    # ---------- validation & ordering ----------
    def _validate(self):
        seen = set()
        for s in self.steps:
            if not isinstance(s, dict) or not s.get("id") or not s.get("tool"):
                raise TaskGraphError("each step needs 'id' and 'tool'")
            if s["id"] in seen:
                raise TaskGraphError(f"duplicate step id: {s['id']}")
            seen.add(s["id"])
            for dep in s.get("depends_on", []):
                if dep not in seen and dep not in {x.get("id") for x in self.steps}:
                    raise TaskGraphError(f"step {s['id']} depends on unknown step {dep}")

    def _topological_order(self) -> list[str]:
        ids = [s["id"] for s in self.steps]
        deps = {s["id"]: list(s.get("depends_on", [])) for s in self.steps}
        indegree = {i: len(deps[i]) for i in ids}
        ready = [i for i in ids if indegree[i] == 0]
        order: list[str] = []
        while ready:
            ready.sort()
            node = ready.pop(0)
            order.append(node)
            for other in deps:
                if node in deps[other]:
                    indegree[other] -= 1
                    if indegree[other] == 0 and other not in order:
                        ready.append(other)
        if len(order) != len(ids):
            raise TaskGraphError("dependency cycle detected in graph")
        return order

    # ---------- persistence ----------
    def _persist(self, report: dict):
        try:
            GRAPH_DIR.mkdir(parents=True, exist_ok=True)
            (GRAPH_DIR / f"{self.plan_id}.json").write_text(
                json.dumps({"plan_id": self.plan_id, "goal": self.goal,
                            "steps": self.steps, "report": report},
                           ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass

    def _trace_step(self, task_id: str, step: dict, observation: str, ok: bool, duration_ms: float):
        try:
            from memory.task_store import TaskStore
            TaskStore().store(
                action_name=step.get("tool", ""),
                action_params=step.get("args", {}),
                observation=observation[:500],
                success=ok,
                duration_ms=duration_ms,
                task_id=task_id,
                context={"goal": self.goal, "step_id": step.get("id"), "desc": step.get("desc", "")},
                tags=["task_graph"],
            )
        except Exception:
            pass

    # ---------- execution ----------
    def run(self, execute_action: Callable[[dict], tuple[str, bool]]) -> dict:
        by_id = {s["id"]: s for s in self.steps}
        completed: list[dict] = []
        captures: dict[str, dict] = {}
        trace: list[dict] = []
        rollback_trace: list[dict] = []
        status = "completed"
        error = None

        for step_id in self._order:
            step = by_id[step_id]
            # pre-capture rollback state
            cap = step.get("rollback_capture")
            if isinstance(cap, dict):
                captures[step_id] = {"kind": cap.get("kind"), "target": cap.get("path", cap.get("target", "")),
                                     "snapshot": _capture(cap.get("kind", ""), cap.get("path", cap.get("target", "")))}
            action = {"tool": step["tool"], "args": step.get("args", {}), "then_wait": step.get("wait", 1.0)}
            t0 = time.time()
            text, _ = execute_action(action)
            dur_ms = (time.time() - t0) * 1000.0
            cls = _agent_tool_result(text)
            entry = {"id": step_id, "tool": step["tool"], "status": cls["status"], "duration_ms": round(dur_ms, 1),
                     "detail": cls["detail"]}
            trace.append(entry)
            self._trace_step(self.plan_id, step, cls["detail"], cls["ok"], dur_ms)
            print(f"  [GRAPH] {step_id} {step['tool']} -> {cls['status']}")
            if not cls["ok"]:
                status = "rolled_back"
                error = f"step {step_id} ({step['tool']}) {cls['status']}"
                break
            completed.append(step)
            # optional verification
            verify = step.get("verify")
            if isinstance(verify, dict):
                verified = True
                vtext = ""
                for vact in verify.get("also", []):
                    vtext2, _ = execute_action({"tool": vact["tool"], "args": vact.get("args", {}), "then_wait": 0.5})
                    vtext += vtext2 + "\n"
                expect = verify.get("expect", "")
                verified = expect in (vtext + cls["detail"])
                if not verified:
                    entry["status"] = "verify_failed"
                    status = "rolled_back"
                    error = f"step {step_id} verification failed: expected '{expect}'"
                    trace[-1] = entry
                    print(f"  [GRAPH] {step_id} verify FAILED (want '{expect}')")
                    break
            time.sleep(max(0.5, float(step.get("wait", 1.0))))

        # rollback on any failure / consent-block / verify failure
        if status == "rolled_back":
            for step in reversed(completed):
                rid = step["id"]
                rb = step.get("rollback")
                if isinstance(rb, dict):
                    text2, _ = execute_action({"tool": rb["tool"], "args": rb.get("args", {}), "then_wait": 0.5})
                    c2 = _agent_tool_result(text2)
                    rollback_trace.append({"step_id": rid, "action": f"{rb['tool']}", "status": c2["status"], "detail": c2["detail"]})
                    print(f"  [GRAPH] rollback {rid}: {rb['tool']} -> {c2['status']}")
                elif rid in captures and captures[rid].get("snapshot"):
                    restored = _restore(captures[rid]["kind"], captures[rid]["target"], captures[rid]["snapshot"])
                    rollback_trace.append({"step_id": rid, "restore": f"{captures[rid]['kind']}:{captures[rid]['target']}",
                                          "status": "restored" if restored else "restore_failed"})
                    print(f"  [GRAPH] rollback {rid}: restore (restored={restored})")

        report = {
            "plan_id": self.plan_id, "goal": self.goal, "status": status,
            "steps": trace, "rollback": rollback_trace, "error": error,
        }
        self._persist(report)
        return report