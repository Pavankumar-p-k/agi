from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path


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


def _is_port_busy(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def main() -> int:
    port = 8000
    if _is_port_busy("127.0.0.1", port):
        print(f"[Launcher] Port {port} is already in use. Stop old backend first.")
        return 1

    adb_dir = _add_adb_to_path()
    serial = _detect_android_serial()

    if serial:
        os.environ["JARVIS_BRIDGE_MODE"] = os.environ.get("JARVIS_BRIDGE_MODE", "adb")
        os.environ["ANDROID_SERIAL"] = os.environ.get("ANDROID_SERIAL", serial)
    else:
        os.environ["JARVIS_BRIDGE_MODE"] = os.environ.get("JARVIS_BRIDGE_MODE", "mock")

    print("=" * 60)
    print("JARVIS Launcher")
    print("=" * 60)
    print(f"Bridge mode: {os.environ.get('JARVIS_BRIDGE_MODE', 'mock')}")
    print(f"Android serial: {os.environ.get('ANDROID_SERIAL', '(none)')}")
    print(f"ADB path added: {adb_dir or '(not found)'}")
    print(f"Backend: http://127.0.0.1:{port}")
    print("=" * 60)

    # Keep launcher process as backend process for one-click run.
    import uvicorn
    from main import app

    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
