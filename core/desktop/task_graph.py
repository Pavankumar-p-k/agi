"""TaskGraph — deterministic multi-step action graphs with rollback.

A graph is `{"id": ..., "goal": ..., "steps": [{id, tool, args,
depends_on, rollback, rollback_capture, verify}]}`. Steps run in
dependency order; every step's outcome must be an *observable* success
(a structured "result:" payload) — unstructured text is treated as
failure, never as success. On failure the completed steps roll back in
reverse order (declared rollback action or captured pre-state).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional


class TaskGraphError(ValueError):
    """Raised for malformed graphs (missing/duplicate ids, bad deps)."""


def _parse_result_payload(text: str) -> dict:
    """Extract the structured payload from an execute() result string."""
    marker = "result:"
    text = str(text)
    if marker not in text:
        return {}
    payload = text.split(marker, 1)[1].strip()
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _step_succeeded(result_text: str) -> bool:
    """Only a structured `success: true` payload counts. Honesty rule."""
    payload = _parse_result_payload(result_text)
    if not payload:
        return False
    if payload.get("success") is True:
        return not payload.get("error")
    return False


class _Capture:
    """Pre-state captured before a step runs, restorable on rollback."""

    def __init__(self, spec: dict) -> None:
        self.kind = str(spec.get("kind", ""))
        self.path = str(spec.get("path", ""))
        self.existed = False
        self.content: Optional[str] = None
        self._captured = False

    def capture(self) -> None:
        if self.kind == "file" and self.path:
            target = Path(self.path)
            self.existed = target.exists()
            if self.existed:
                try:
                    self.content = target.read_text(encoding="utf-8",
                                                    errors="replace")
                except OSError:
                    self.content = None
            self._captured = True

    def restore(self) -> str:
        """Restore the captured state; returns 'restored'/'absent'/'failed'."""
        if not self._captured or self.kind != "file" or not self.path:
            return "failed"
        target = Path(self.path)
        try:
            if not self.existed:
                if target.exists():
                    target.unlink()
                return "restored"
            if self.content is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(self.content, encoding="utf-8")
                return "restored"
            return "failed"
        except OSError:
            return "failed"


class TaskGraph:
    """Validates, orders and executes a step graph through a callback."""

    def __init__(self, graph: Any) -> None:
        if isinstance(graph, str):
            try:
                graph = json.loads(graph)
            except json.JSONDecodeError as exc:
                raise TaskGraphError(f"graph must be valid JSON: {exc}") from exc
        if not isinstance(graph, dict):
            raise TaskGraphError("graph must be a dict with a 'steps' list")
        steps = graph.get("steps")
        if not isinstance(steps, list) or not steps:
            raise TaskGraphError("graph must contain a non-empty 'steps' list")

        self.graph_id = str(graph.get("id", ""))
        self.goal = str(graph.get("goal", ""))
        self.steps: list[dict] = []
        seen_ids: set = set()
        for index, raw in enumerate(steps, 1):
            if not isinstance(raw, dict):
                raise TaskGraphError(f"step {index} must be a dict")
            step = dict(raw)
            step_id = str(step.get("id") or f"step_{index}")
            if step_id in seen_ids:
                raise TaskGraphError(f"duplicate step id '{step_id}'")
            if not step.get("tool"):
                raise TaskGraphError(f"step '{step_id}' has no tool")
            seen_ids.add(step_id)
            step["id"] = step_id
            step.setdefault("args", {})
            self.steps.append(step)

        # Validate dependencies exist.
        for step in self.steps:
            for dep in step.get("depends_on", []) or []:
                if dep not in seen_ids:
                    raise TaskGraphError(
                        f"step '{step['id']}' depends on unknown step '{dep}'")

    # ── ordering ─────────────────────────────────────────────────────
    def _ordered_steps(self) -> list[dict]:
        """Topological order honouring depends_on (stable, cycle-checked)."""
        remaining = list(self.steps)
        done_ids = {s["id"] for s in ()}
        ordered: list[dict] = []
        while remaining:
            progress = False
            for step in list(remaining):
                deps = step.get("depends_on", []) or []
                if all(d in done_ids for d in deps):
                    ordered.append(step)
                    done_ids.add(step["id"])
                    remaining.remove(step)
                    progress = True
            if not progress:
                raise TaskGraphError("graph contains a dependency cycle")
        return ordered

    # ── execution ────────────────────────────────────────────────────
    def run(self, execute: Callable[[dict], Any]) -> dict:
        """Run the graph through `execute(action) -> (text, done)`.

        Returns a report dict: {status, success, steps, rollback, error}.
        Status is 'completed' only when every step reports structured
        success; otherwise completed steps roll back in reverse order.
        """
        report_steps: list[dict] = []
        completed: list[tuple[dict, Any]] = []  # (step, capture)

        for step in self._ordered_steps():
            capture = _Capture(step.get("rollback_capture") or {})
            if step.get("rollback_capture"):
                capture.capture()

            try:
                result_text, _done = execute({"tool": step["tool"],
                                              "args": dict(step.get("args", {}))})
            except Exception as exc:  # noqa: BLE001 — step errors are failures
                result_text = f"Tool '{step['tool']}' error: {exc}"

            ok = _step_succeeded(result_text)
            report_steps.append({
                "id": step["id"],
                "tool": step["tool"],
                "status": "completed" if ok else "failed",
                "result": str(result_text)[:500],
            })
            if ok:
                completed.append((step, capture))
                continue

            # Failure: roll back everything completed so far.
            rollback_report: list[dict] = []
            for done_step, done_capture in reversed(completed):
                declared = done_step.get("rollback")
                if declared:
                    try:
                        rb_text, _ = execute(declared if isinstance(declared, dict)
                                             else {"tool": str(declared), "args": {}})
                        rollback_report.append({
                            "step": done_step["id"],
                            "status": "restored" if _step_succeeded(rb_text) else "failed",
                        })
                        continue
                    except Exception as exc:  # noqa: BLE001
                        rollback_report.append({
                            "step": done_step["id"],
                            "status": "failed",
                            "error": str(exc),
                        })
                        continue
                if step.get("rollback_capture") or done_step.get("rollback_capture"):
                    status = done_capture.restore() if done_capture else "failed"
                    rollback_report.append({"step": done_step["id"],
                                            "status": status})
            return {
                "status": "rolled_back",
                "success": False,
                "steps": report_steps,
                "rollback": rollback_report,
                "failed_step": step["id"],
                "error": f"step '{step['id']}' failed: {report_steps[-1]['result'][:200]}",
            }

        return {
            "status": "completed",
            "success": True,
            "steps": report_steps,
            "rollback": [],
        }


__all__ = ["TaskGraph", "TaskGraphError"]
