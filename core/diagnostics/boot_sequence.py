from __future__ import annotations

import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

StepHandler = Callable[[], Any]


@dataclass
class BootStep:
    label: str
    status: str = "pending"  # pending | running | passed | failed | skipped
    duration_ms: float = 0.0
    error: str | None = None
    detail: str | None = None
    suggestion: str | None = None


_SUGGESTION_MAP: list[tuple[list[str], str]] = [
    (["ModuleNotFoundError", "ImportError"], "Missing dependency. Run: pip install <package>"),
    (["Port already in use", "Address already in use", "WinError 10048"],
     "Port is occupied. Use --port to pick a different port, or stop the other process."),
    (["Permission denied", "Access denied", "WinError 5"],
     "Permission issue. Try running as Administrator."),
    (["No such file", "FileNotFoundError", "The system cannot find"],
     "File or directory not found. Check the path."),
    (["Connection refused", "WinError 10061"],
     "The target service is not running or not reachable."),
    (["Timeout", "timed out"],
     "Operation timed out. Check network or increase timeout."),
    (["No module named", "cannot import"],
     "A required Python module is missing. Run: pip install -r requirements.txt"),
    (["uvicorn", "No module named 'uvicorn'"],
     "FastAPI webserver not installed. Run: pip install uvicorn"),
    (["sqlite3", "SQLite"],
     "Database error. Try deleting data/*.db and restarting."),
    (["[Errno 13]", "chmod", "chown"],
     "File permission error. Check file ownership."),
]


def _detect_suggestion(error_text: str) -> str | None:
    for patterns, suggestion in _SUGGESTION_MAP:
        for p in patterns:
            if p.lower() in error_text.lower():
                return suggestion
    return None


class BootSequence:
    def __init__(self, title: str = "Boot Sequence", verbose: bool = True) -> None:
        self.title = title
        self.verbose = verbose
        self.steps: list[BootStep] = []
        self._step_index: int = 0
        self._max_label: int = 30
        self._header_printed = False

    def _print_header(self, file) -> None:
        if self._header_printed:
            return
        self._header_printed = True
        print(f"\n{'=' * 60}", file=file)
        print(f"  {self.title}", file=file)
        print(f"{'=' * 60}", file=file)

    def _emit_step(self, s: BootStep, file) -> None:
        """Live-print a step result line immediately."""
        self._max_label = max(self._max_label, len(s.label))
        icon = _status_icon(s.status)
        dur = f"({s.duration_ms:.0f}ms)" if s.duration_ms else ""
        print(f"  {icon} {s.label.ljust(self._max_label)} {dur}", file=file)
        if s.status == "failed":
            if s.error:
                print(f"     Error: {s.error}", file=file)
            if s.detail:
                print(f"     Detail:\n{s.detail}", file=file)
            if s.suggestion:
                print(f"     Fix: {s.suggestion}", file=file)

    def step(self, label: str) -> _StepContext:
        ctx = _StepContext(self, label)
        self.steps.append(ctx.step_data)
        self._step_index += 1
        return ctx

    def run_step(self, label: str, handler: StepHandler) -> BootStep:
        bs = BootStep(label=label, status="running")
        self.steps.append(bs)
        if self.verbose:
            self._print_header(sys.stdout)
            print(f"  > {label}...", file=sys.stdout, end="", flush=True)
        t0 = time.monotonic()
        try:
            result = handler()
            bs.status = "passed"
            bs.duration_ms = (time.monotonic() - t0) * 1000
            if self.verbose:
                dur = f"({bs.duration_ms:.0f}ms)"
                print(f" OK {dur}", file=sys.stdout, flush=True)
            bs.detail = str(result)[:120] if result is not None else None
        except Exception as e:
            bs.status = "failed"
            bs.duration_ms = (time.monotonic() - t0) * 1000
            tb = traceback.format_exc()
            bs.error = f"{type(e).__name__}: {e}"
            bs.detail = tb[:600]
            bs.suggestion = _detect_suggestion(tb) or _detect_suggestion(str(e))
            if self.verbose:
                print(f" FAILED", file=sys.stdout, flush=True)
                self._emit_step(bs, sys.stdout)
        return bs

    def print_report(self, file=sys.stdout) -> None:
        self._print_header(file)
        total = sum(s.duration_ms for s in self.steps if s.status != "skipped")
        failed = sum(1 for s in self.steps if s.status == "failed")
        if failed:
            print(f"  Result: FAILED ({failed}/{len(self.steps)} steps failed)  Total: {total:.0f}ms", file=file)
        else:
            print(f"  Result: PASSED ({len(self.steps)}/{len(self.steps)} steps passed)  Total: {total:.0f}ms", file=file)
        print(f"{'=' * 60}\n", file=file)

    def ok(self) -> bool:
        return all(s.status == "passed" for s in self.steps)


class _StepContext:
    def __init__(self, seq: BootSequence, label: str) -> None:
        self._seq = seq
        self._file = sys.stdout
        self.step_data = BootStep(label=label)

    def __enter__(self) -> BootStep:
        self.step_data.status = "running"
        self._t0 = time.monotonic()
        if self._seq.verbose:
            self._seq._print_header(self._file)
            print(f"  > {self.step_data.label}...", file=self._file, end="", flush=True)
        return self.step_data

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        dur = (time.monotonic() - self._t0) * 1000
        self.step_data.duration_ms = dur
        if exc_type is not None:
            self.step_data.status = "failed"
            self.step_data.error = f"{exc_type.__name__}: {exc_val}"
            tb = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
            self.step_data.detail = tb[:600]
            self.step_data.suggestion = _detect_suggestion(tb) or _detect_suggestion(str(exc_val))
            if self._seq.verbose:
                print(f" FAILED", file=self._file, flush=True)
                self._seq._emit_step(self.step_data, self._file)
            return True  # suppress exception
        if self.step_data.status == "pending" or self.step_data.status == "running":
            self.step_data.status = "passed"
        if self._seq.verbose:
            tag = " FAILED" if self.step_data.status == "failed" else f" OK ({dur:.0f}ms)"
            print(tag, file=self._file, flush=True)
            if self.step_data.status == "failed":
                self._seq._emit_step(self.step_data, self._file)
        return False


def _status_icon(status: str) -> str:
    return {
        "pending": " ",
        "running": ">",
        "passed": "OK",
        "failed": "XX",
        "skipped": "--",
    }.get(status, "??")
