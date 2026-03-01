from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def _add_adb_to_path() -> str:
    candidates = [
        Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools",
        Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools",
        Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools",
    ]
    for folder in candidates:
        if folder and folder.exists() and (folder / "adb.exe").exists():
            os.environ["Path"] = f"{folder};{os.environ.get('Path', '')}"
            return str(folder)
    return ""


def _detect_android_serial() -> str:
    try:
        out = subprocess.check_output(
            ["adb", "devices"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices attached"):
            continue
        if "\tdevice" in line:
            return line.split("\t", 1)[0].strip()
    return ""


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


def _is_port_busy(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _resolve_workspace() -> tuple[Path, Path, Path]:
    # launcher location: ...\apk\agi\JarvisLauncher.exe
    launcher_dir = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    apk_root = launcher_dir.parent
    backend_dir = apk_root / "jarvis-project" / "backend"
    agi_dir = launcher_dir
    return apk_root, backend_dir, agi_dir


def _pick_backend_python(backend_dir: Path) -> str:
    venv_py = backend_dir / "venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return str(venv_py)
    return "python"


def _start_full_backend(backend_dir: Path) -> subprocess.Popen[bytes]:
    py = _pick_backend_python(backend_dir)
    env = os.environ.copy()
    # Keep old features, but ensure bridge settings are available too.
    env.setdefault("JARVIS_BRIDGE_MODE", "adb")
    return subprocess.Popen(
        [py, "-m", "core.main"],
        cwd=str(backend_dir),
        env=env,
    )


def main() -> int:
    _, backend_dir, _ = _resolve_workspace()
    if not backend_dir.exists():
        print(f"[Launcher] Full backend path not found: {backend_dir}")
        return 1

    adb_dir = _add_adb_to_path()
    serial = _detect_android_serial()
    if serial:
        os.environ["ANDROID_SERIAL"] = os.environ.get("ANDROID_SERIAL", serial)
        os.environ["JARVIS_BRIDGE_MODE"] = os.environ.get("JARVIS_BRIDGE_MODE", "adb")
    else:
        os.environ["JARVIS_BRIDGE_MODE"] = os.environ.get("JARVIS_BRIDGE_MODE", "mock")

    if _is_port_busy("127.0.0.1", 8000):
        print("[Launcher] Port 8000 already in use. Reusing existing backend.")
        if _wait_health("http://127.0.0.1:8000/health", timeout_sec=8):
            print("[Launcher] Backend healthy at http://127.0.0.1:8000")
            return 0
        print("[Launcher] Port is busy but health check failed.")
        return 1

    print("=" * 68)
    print("JARVIS Launcher (Full Stack)")
    print("=" * 68)
    print(f"Backend dir: {backend_dir}")
    print(f"Bridge mode: {os.environ.get('JARVIS_BRIDGE_MODE', 'mock')}")
    print(f"Android serial: {os.environ.get('ANDROID_SERIAL', '(none)')}")
    print(f"ADB path added: {adb_dir or '(not found)'}")
    print("Starting full backend: core.main ...")
    print("=" * 68)

    proc = _start_full_backend(backend_dir)
    ok = _wait_health("http://127.0.0.1:8000/health", timeout_sec=40)
    if ok:
        print("[Launcher] Backend is ready at http://127.0.0.1:8000")
        print("[Launcher] Keep this window open. Press Ctrl+C to stop.")
    else:
        print("[Launcher] Backend did not become healthy in time.")
        try:
            proc.terminate()
        except Exception:
            pass
        return 1

    try:
        return proc.wait()
    except KeyboardInterrupt:
        try:
            proc.terminate()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
