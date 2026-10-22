"""Kill the whole process tree of a step: the worker AND what it spawned.

A worker may spawn processes — ``process`` is a declared effect that
``os.facts`` already uses (its probes shell out). Killing only the worker at
its deadline leaves its children running after MJ has marked the step
failed: a real zombie-maker, and the exact gap the second review flagged
("grandchildren of a killed worker survive").

Each worker therefore starts inside something MJ owns and can kill
wholesale (docs/10 §1):

* **POSIX** — its own session and process group (``start_new_session=True``).
  Descendants inherit the group at every depth, so one
  ``os.killpg(pgid, SIGKILL)`` reaches them all.
* **Windows** — a Job Object with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``.
  Processes spawned by a job member join the job automatically (nested jobs,
  Windows 8+), so ``TerminateJobObject`` kills every depth in one call; and
  because the job dies when its handle closes, MJ exiting cannot orphan a
  worker either.

Escape hatches that deliberately leave the group (``setsid``,
``CREATE_BREAKAWAY_FROM_JOB``) are a sandbox-level concern, out of scope
here — no builtin uses them (docs/10 §4).
"""

from __future__ import annotations

import os
import signal
import subprocess
from typing import IO, Any

# Between killing the tree and escalating to a direct kill of the worker.
REAP_GRACE_S = 5.0

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _JobObjectExtendedLimitInformation = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001

    # Handles are 64-bit on modern Windows: without explicit restypes ctypes
    # truncates them to 32 bits, so every signature below is declared.
    _kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL

    class _IO_COUNTERS(ctypes.Structure):
        # ULONGLONG = unsigned 64-bit; wintypes has no such alias on CPython
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


def spawn(
    argv: list[str],
    *,
    env: dict[str, str],
    stdout: IO[str],
    stderr: IO[str],
) -> subprocess.Popen:
    """Start a worker inside a killable group.

    stdout/stderr are caller-owned file objects (not pipes): a grandchild
    that inherits them and outlives the worker cannot wedge a pipe read, and
    the payload is written to the worker's stdin pipe as before.
    """
    common: dict[str, Any] = {
        "stdin": subprocess.PIPE,
        "stdout": stdout,
        "stderr": stderr,
        "env": env,
        "text": True,  # same locale-encoding stdin round-trip as before
    }
    if os.name == "nt":
        proc = subprocess.Popen(argv, **common)  # type: ignore[arg-type]
        _job_assign(proc)
        return proc
    # start_new_session: the worker's pgid == its pid, which is what
    # kill_tree() targets.
    proc = subprocess.Popen(argv, start_new_session=True, **common)  # type: ignore[arg-type]
    return proc


def _job_assign(proc: subprocess.Popen) -> None:
    """Windows: put the worker in a job MJ can kill wholesale.

    Best effort: if any step fails (e.g. a restrictive parent job on older
    Windows), the process runs unassigned and ``kill_tree`` falls back to
    ``taskkill /T`` — still a tree kill, one mechanism deeper.
    """
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        return
    info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = _kernel32.SetInformationJobObject(
        job, _JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
    )
    handle = _kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, proc.pid)
    if not ok or not handle or not _kernel32.AssignProcessToJobObject(job, handle):
        if handle:
            _kernel32.CloseHandle(handle)
        _kernel32.CloseHandle(job)
        return
    _kernel32.CloseHandle(handle)
    proc._mj_job = job  # type: ignore[attr-defined]


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill the worker and every process it spawned — best effort — then
    make sure the worker itself is dead either way."""
    if os.name == "nt":
        job = getattr(proc, "_mj_job", None)
        if job:
            _kernel32.TerminateJobObject(job, 1)  # every job member, any depth
        else:
            _taskkill_tree(proc.pid)
    else:
        # pgid == worker pid (start_new_session). killpg addresses a *group*,
        # not a process, so it also reaches stragglers that outlived the
        # worker; ESRCH simply means the group is already empty.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        proc.kill()  # belt: the worker dies even if the group kill failed
    except OSError:
        pass


def _taskkill_tree(pid: int) -> None:
    """Windows fallback when no job object could be attached: kill the tree
    by pid (``/T`` = child processes, ``/F`` = force)."""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        pass


def reap(proc: subprocess.Popen, grace_s: float = REAP_GRACE_S) -> None:
    """Reap the worker with a bound: close stdin, wait, escalate to kill."""
    if proc.stdin is not None:
        try:
            proc.stdin.close()
        except OSError:
            pass
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            pass  # unkillable even raw (POSIX D-state); nothing userland can do


def release(proc: subprocess.Popen) -> None:
    """Release the kill-handle after a finished step.

    On Windows the job was created with KILL_ON_JOB_CLOSE, so closing it
    also disposes of anything the worker left behind (and, if MJ itself
    crashes, kills the worker rather than orphaning it). On POSIX the
    worker's group dies with the worker unless it spawned stragglers
    (documented in docs/10 §4 — Windows is the stricter of the two here).
    """
    if os.name != "nt":
        return
    job = getattr(proc, "_mj_job", None)
    if job:
        _kernel32.CloseHandle(job)
        proc._mj_job = None  # type: ignore[attr-defined]
