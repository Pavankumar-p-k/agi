from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import ctypes
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
import json


BACKEND_PORT = 8000
VISION_PORT = 8001
BACKEND_HEALTH = f"http://127.0.0.1:{BACKEND_PORT}/health"
VISION_HEALTH = f"http://127.0.0.1:{VISION_PORT}/health"


def _wait_health(url: str, timeout_sec: int = 35) -> bool:
    end = time.time() + timeout_sec
    while time.time() < end:
        try:
            with urlopen(url, timeout=2) as res:
                if res.status == 200:
                    return True
        except URLError:
            pass
        except Exception:
            pass
        time.sleep(1)
    return False


def _wait_until(check_fn, timeout_sec: int = 35) -> bool:
    end = time.time() + timeout_sec
    while time.time() < end:
        try:
            if bool(check_fn()):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _fetch_json(url: str, timeout_sec: float = 2.0) -> dict | None:
    try:
        with urlopen(url, timeout=timeout_sec) as res:
            if res.status != 200:
                return None
            data = res.read().decode("utf-8", errors="replace")
        payload = json.loads(data)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def _is_backend_ready() -> bool:
    capabilities = _fetch_json(
        f"http://127.0.0.1:{BACKEND_PORT}/api/automation/capabilities", timeout_sec=4.5
    )
    return isinstance(capabilities, dict) and "apps" in capabilities and "examples" in capabilities


def _is_vision_ready() -> bool:
    vision_health = _fetch_json(
        f"http://127.0.0.1:{VISION_PORT}/vision/health", timeout_sec=15.0
    )
    return isinstance(vision_health, dict) and str(vision_health.get("status", "")).lower() in {
        "healthy",
        "ok",
    }


def _is_port_busy(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _resolve_workspace() -> tuple[Path, Path, Path, Path]:
    launcher_path = Path(
        sys.executable if getattr(sys, "frozen", False) else __file__
    ).resolve()
    launcher_dir = launcher_path.parent
    search_root = launcher_dir
    for _ in range(8):
        candidate = search_root / "jarvis-project" / "backend"
        if candidate.exists():
            backend_dir = candidate
            workspace_root = search_root
            logs_dir = search_root / "jarvis-project" / "run_logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            return workspace_root, backend_dir, launcher_dir, logs_dir
        if search_root.parent == search_root:
            break
        search_root = search_root.parent
    raise RuntimeError("Could not locate workspace root containing jarvis-project/backend")


def _python_exists_or_cmd(cmd: str) -> bool:
    if cmd.lower() in {"python", "py"}:
        return True
    return Path(cmd).exists()


def _python_supports(cmd: str, modules: list[str]) -> bool:
    if not _python_exists_or_cmd(cmd):
        return False
    script = (
        "import importlib.util,sys;"
        f"mods={modules!r};"
        "missing=[m for m in mods if importlib.util.find_spec(m) is None];"
        "sys.exit(0 if not missing else 1)"
    )
    try:
        result = subprocess.run(
            [cmd, "-c", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _pick_backend_python(workspace_root: Path, backend_dir: Path) -> str:
    candidates = [
        str(backend_dir / "venv" / "Scripts" / "python.exe"),
        str(workspace_root / ".venv" / "Scripts" / "python.exe"),
        str(Path(sys.executable)),
        "python",
    ]
    for candidate in candidates:
        if _python_supports(candidate, ["fastapi", "uvicorn"]):
            return candidate
    return "python"


def _pick_vision_python(workspace_root: Path, backend_dir: Path) -> str:
    configured = os.environ.get("JARVIS_VISION_PYTHON", "").strip()
    candidates = [
        configured,
        str(Path(sys.executable)),
        "python",
        str(backend_dir / "venv" / "Scripts" / "python.exe"),
        str(workspace_root / ".venv" / "Scripts" / "python.exe"),
    ]
    for candidate in candidates:
        if candidate and _python_supports(
            candidate, ["fastapi", "uvicorn", "mss", "pyautogui"]
        ):
            return candidate
    return "python"


def _pid_file(logs_dir: Path, name: str) -> Path:
    return logs_dir / f"{name}.pid"


def _read_pid(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _write_pid(path: Path, pid: int) -> None:
    path.write_text(str(pid), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        if not ok:
            return False
        return int(exit_code.value) == STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _start_process(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    out_log: Path,
    err_log: Path,
) -> subprocess.Popen[bytes]:
    out_handle = out_log.open("ab")
    err_handle = err_log.open("ab")
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=out_handle,
        stderr=err_handle,
        creationflags=flags,
    )


def _ensure_backend(workspace_root: Path, backend_dir: Path, logs_dir: Path) -> bool:
    if _is_backend_ready():
        print(f"[Launcher] Backend already healthy at {BACKEND_HEALTH}")
        return True
    if _is_port_busy("127.0.0.1", BACKEND_PORT):
        print("[Launcher] Port 8000 is in use by another process. Backend identity check failed.")
        return False

    py = _pick_backend_python(workspace_root, backend_dir)
    env = os.environ.copy()
    env.setdefault("JARVIS_VISION_SERVER_URL", f"http://127.0.0.1:{VISION_PORT}")
    proc = _start_process(
        [py, "-u", "-m", "core.main"],
        cwd=backend_dir,
        env=env,
        out_log=logs_dir / "backend-launcher.out.log",
        err_log=logs_dir / "backend-launcher.err.log",
    )
    _write_pid(_pid_file(logs_dir, "backend"), proc.pid)
    return _wait_until(_is_backend_ready, timeout_sec=120)


def _ensure_vision(workspace_root: Path, backend_dir: Path, logs_dir: Path) -> bool:
    if _is_vision_ready():
        print(f"[Launcher] Vision server already healthy at {VISION_HEALTH}")
        return True
    if _is_port_busy("127.0.0.1", VISION_PORT):
        print("[Launcher] Port 8001 is in use by another process. Vision identity check failed.")
        return False

    py = _pick_vision_python(workspace_root, backend_dir)
    env = os.environ.copy()
    env["JARVIS_VISION_PORT"] = str(VISION_PORT)
    env.setdefault("JARVIS_HOST", "127.0.0.1")
    proc = _start_process(
        [py, "-u", "main_server.py"],
        cwd=workspace_root,
        env=env,
        out_log=logs_dir / "vision-launcher.out.log",
        err_log=logs_dir / "vision-launcher.err.log",
    )
    _write_pid(_pid_file(logs_dir, "vision"), proc.pid)
    return _wait_until(_is_vision_ready, timeout_sec=90)


def _ensure_windows_assistant(backend_dir: Path, logs_dir: Path) -> bool:
    pid_path = _pid_file(logs_dir, "windows-assistant")
    existing_pid = _read_pid(pid_path)
    if _pid_alive(existing_pid):
        print(f"[Launcher] Windows assistant already running (PID {existing_pid})")
        return True

    script = backend_dir / "windows_assistant_daemon.ps1"
    if not script.exists():
        print(f"[Launcher] Assistant script missing: {script}")
        return False

    env = os.environ.copy()
    proc = _start_process(
        [
            "powershell",
            "-NoProfile",
            "-Sta",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ServerHost",
            "127.0.0.1",
            "-ServerPort",
            str(BACKEND_PORT),
        ],
        cwd=backend_dir,
        env=env,
        out_log=logs_dir / "windows-assistant.out.log",
        err_log=logs_dir / "windows-assistant.err.log",
    )
    _write_pid(pid_path, proc.pid)
    time.sleep(2)
    return proc.poll() is None


def main() -> int:
    try:
        workspace_root, backend_dir, _, logs_dir = _resolve_workspace()
    except Exception as exc:
        print(f"[Launcher] {exc}")
        return 1

    print("=" * 68)
    print("JARVIS Launcher (Brain + Reminders + Vision + Assistant)")
    print("=" * 68)
    print(f"Workspace: {workspace_root}")
    print(f"Backend:   {backend_dir}")
    print(f"Logs:      {logs_dir}")
    print("=" * 68)

    backend_ok = _ensure_backend(workspace_root, backend_dir, logs_dir)
    if not backend_ok:
        print(f"[Launcher] Backend failed health check: {BACKEND_HEALTH}")
        return 1
    print(f"[Launcher] Backend ready: {BACKEND_HEALTH}")

    vision_ok = _ensure_vision(workspace_root, backend_dir, logs_dir)
    if not vision_ok:
        print(f"[Launcher] Vision server not ready at {VISION_HEALTH}. Continuing with core backend.")
    else:
        print(f"[Launcher] Vision ready:  {VISION_HEALTH}")

    assistant_ok = _ensure_windows_assistant(backend_dir, logs_dir)
    if not assistant_ok:
        print("[Launcher] Windows assistant did not stay running. Core servers are still ready.")
    else:
        print("[Launcher] Windows assistant ready.")

    print("=" * 68)
    print("JARVIS full stack is running.")
    print(f"API docs:   http://127.0.0.1:{BACKEND_PORT}/docs")
    print(f"Vision docs: http://127.0.0.1:{VISION_PORT}/docs")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
