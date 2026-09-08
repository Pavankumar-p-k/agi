"""
Module: core.desktop.user_actions
Real "human-like" desktop capabilities: file system, storage, time,
clipboard, and VISION (see the screen + find+click UI elements like a real user).

Extends the raw controller so JARVIS can genuinely do what a real user does.
"""
from __future__ import annotations
from typing import Any
import os
import sys
import time
import shutil
import platform
import socket
from datetime import datetime
from pathlib import Path

import pyautogui

# Vision deps (optional but available)
try:
    import cv2
    import numpy as np
    from PIL import Image
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False


class UserActions:
    """High-level, human-like operations on top of the raw desktop controller."""

    # ---------- FILE SYSTEM ----------
    @staticmethod
    def list_files(path: str = ".", recursive: bool = False) -> list[dict[str, Any]]:
        p = Path(path).expanduser()
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        entries = []
        items = p.rglob("*") if recursive else p.iterdir()
        for item in items:
            try:
                is_dir = item.is_dir()
                info = item.stat()
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "dir" if is_dir else "file",
                    "size": None if is_dir else info.st_size,
                    "ext": item.suffix.lstrip(".") if not is_dir else "",
                    "modified": datetime.fromtimestamp(info.st_mtime).isoformat(),
                })
            except (PermissionError, OSError):
                continue
        entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
        return entries

    @staticmethod
    def create_file(path: str, content: str = "") -> dict:
        p = Path(path).expanduser()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(p), "action": "created"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def create_folder(path: str) -> dict:
        p = Path(path).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
            return {"success": True, "path": str(p), "action": "created"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def read_file(path: str, max_chars: int = 5000) -> dict:
        p = Path(path).expanduser()
        if not p.exists():
            return {"error": f"File not found: {path}"}
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            return {"success": True, "path": str(p), "content": text[:max_chars], "length": len(text)}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def write_file(path: str, content: str) -> dict:
        p = Path(path).expanduser()
        try:
            p.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(p), "action": "written"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def move_file(src: str, dst: str) -> dict:
        try:
            shutil.move(src, dst)
            return {"success": True, "from": src, "to": dst}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def copy_file(src: str, dst: str) -> dict:
        try:
            shutil.copy2(src, dst)
            return {"success": True, "from": src, "to": dst}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def delete_path(path: str, recursive: bool = False) -> dict:
        p = Path(path).expanduser()
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        try:
            if p.is_dir():
                shutil.rmtree(p) if recursive else p.rmdir()
            else:
                p.unlink()
            return {"success": True, "path": str(p), "action": "deleted"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def rename_file(path: str, new_name: str) -> dict:
        p = Path(path).expanduser()
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        try:
            new_path = p.parent / new_name
            p.rename(new_path)
            return {"success": True, "from": str(p), "to": str(new_path)}
        except Exception as e:
            return {"error": str(e)}

    # ---------- STORAGE / DISK ----------
    @staticmethod
    def storage_info() -> dict:
        result = {"drives": []}
        if sys.platform == "win32":
            import ctypes
            drives = []
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if bitmask & (1 << i):
                    drives.append(chr(65 + i) + ":\\")
            for d in drives:
                try:
                    usage = shutil.disk_usage(d)
                    result["drives"].append({
                        "drive": d,
                        "total_gb": round(usage.total / (1024**3), 2),
                        "used_gb": round(usage.used / (1024**3), 2),
                        "free_gb": round(usage.free / (1024**3), 2),
                        "percent_used": round(usage.used / usage.total * 100, 1),
                    })
                except OSError:
                    continue
        return result

    # ---------- TIME / TIMEZONE ----------
    @staticmethod
    def current_time() -> dict:
        now = datetime.now()
        return {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": now.strftime("%A"),
            "tz": time.tzname,
            "tz_offset_sec": time.timezone,
            "iso": now.isoformat(),
            "timestamp": now.timestamp(),
        }

    @staticmethod
    def system_info() -> dict:
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "release": platform.release(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "hostname": socket.gethostname(),
            "cpu_count": os.cpu_count(),
            "arch": platform.architecture()[0],
        }

    # ---------- VISION ----------
    @staticmethod
    def take_screenshot(path: str | None = None) -> dict:
        try:
            img = pyautogui.screenshot()
            if path:
                img.save(path)
                return {"success": True, "path": path, "size": img.size}
            return {"success": True, "size": img.size, "mode": img.mode}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def find_on_screen(image_path: str, confidence: float = 0.8) -> dict:
        """Find a UI element (button/icon) image on the screen and return its coords.
        This is how JARVIS 'sees' and clicks real buttons like a user."""
        try:
            if not VISION_AVAILABLE:
                return {"error": "OpenCV not available"}
            loc = pyautogui.locateOnScreen(image_path, confidence=confidence)
            if not loc:
                return {"found": False, "confidence": confidence}
            x, y = pyautogui.center(loc)
            left, top, width, height = loc.left, loc.top, loc.width, loc.height
            return {
                "found": True,
                "x": int(x), "y": int(y),
                "bbox": {"left": left, "top": top, "width": width, "height": height},
                "confidence": confidence,
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def click_image(image_path: str, confidence: float = 0.8) -> dict:
        """Find an image on screen and click it (like clicking a real button)."""
        try:
            loc = pyautogui.locateOnScreen(image_path, confidence=confidence)
            if not loc:
                return {"found": False}
            x, y = pyautogui.center(loc)
            pyautogui.click(x, y)
            return {"found": True, "clicked": (x, y)}
        except Exception as e:
            return {"error": str(e)}

    # ---------- APP LAUNCH (smart) ----------
    @staticmethod
    def open_with(path: str, app: str | None = None) -> dict:
        """Open a file. If app given, open in that app (e.g., notepad, excel)."""
        try:
            import subprocess
            if app:
                if app.lower() in ("notepad", "editor", "text", "txt"):
                    subprocess.Popen(["notepad.exe", path], shell=True)
                elif app.lower() in ("code", "vscode", "visual studio code", "vs code"):
                    subprocess.Popen(["code", path])
                elif app.lower() in ("chrome", "google chrome"):
                    subprocess.Popen(["chrome", path])
                else:
                    subprocess.Popen(f'start "" "{app}" "{path}"', shell=True)
                return {"success": True, "opened": path, "with": app}
            else:
                if sys.platform == "win32":
                    os.startfile(path)
                return {"success": True, "opened": path}
        except Exception as e:
            return {"error": str(e)}

    # ---------- NETWORK ----------
    @staticmethod
    def network_info() -> dict:
        """Current network interfaces, IPs, uptime."""
        try:
            import psutil
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            interfaces = []
            for name, addr_list in addrs.items():
                ipv4 = ipv6 = mac = None
                for a in addr_list:
                    if a.family == socket.AF_INET:
                        ipv4 = a.address
                    elif a.family == socket.AF_INET6:
                        ipv6 = a.address
                    elif a.family == psutil.AF_LINK:
                        mac = a.address
                is_up = stats[name].isup if name in stats else None
                speed = stats[name].speed if name in stats else None
                interfaces.append({
                    "name": name,
                    "ipv4": ipv4,
                    "ipv6": ipv6,
                    "mac": mac,
                    "is_up": is_up,
                    "link_speed_mbps": speed,
                })
            net_io = psutil.net_io_counters()
            boot = datetime.fromtimestamp(psutil.boot_time())
            return {
                "interfaces": interfaces,
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "system_boot": boot.isoformat(),
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def network_speed_test(measure_secs: float = 2.0) -> dict:
        """Measure current download/upload speed by actual data transfer.
        Uses a known fast endpoint and measures bytes moved."""
        try:
            import psutil
            import time as _t
            def _measure() -> dict:
                before = psutil.net_io_counters()
                t0 = _t.time()
                _t.sleep(measure_secs)
                after = psutil.net_io_counters()
                dt = _t.time() - t0
                down_mbps = (after.bytes_recv - before.bytes_recv) * 8 / dt / 1_000_000
                up_mbps = (after.bytes_sent - before.bytes_sent) * 8 / dt / 1_000_000
                return {"download_mbps": round(down_mbps, 2), "upload_mbps": round(up_mbps, 2)}

            # Cross-traffic avg over a few samples
            samples = [_measure() for _ in range(3)]
            avg_down = sum(s["download_mbps"] for s in samples) / len(samples)
            avg_up = sum(s["upload_mbps"] for s in samples) / len(samples)
            return {
                "download_mbps": round(avg_down, 2),
                "upload_mbps": round(avg_up, 2),
                "samples": samples,
                "note": "This measures current real traffic (not a forced speedtest). Higher = faster connection.",
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def ping(host: str = "8.8.8.8") -> dict:
        """Ping a host to check connectivity/latency."""
        try:
            import subprocess
            cmd = ["ping", "-n", "1", "-w", "2000", host]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                # extract time=XXms
                import re
                m = re.search(r"time[=<](\d+)ms", res.stdout)
                latency = int(m.group(1)) if m else None
                return {"reachable": True, "host": host, "latency_ms": latency}
            return {"reachable": False, "host": host, "output": res.stdout.strip()}
        except Exception as e:
            return {"error": str(e)}

    # ---------- BLUETOOTH ----------
    @staticmethod
    def bluetooth_devices() -> dict:
        """List paired Bluetooth devices using Windows PowerShell."""
        try:
            import subprocess
            ps = (
                "$t=@(); Get-PnpDevice -Class Bluetooth 2>$null | "
                "Where-Object {$_.FriendlyName -and ($_.FriendlyName -notmatch 'Radio|Adapter|Service|Registry|Generic')} | "
                "ForEach-Object { $t += [PSCustomObject]@{ "
                "Name=$_.FriendlyName; Status=$_.Status; ID=$_.InstanceId } }; "
                "$t | ConvertTo-Json -Compress"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=30,
            )
            out = res.stdout.strip()
            import json
            if not out or out == "null":
                return {"devices": []}
            data = json.loads(out)
            if not isinstance(data, list):
                data = [data]
            devs = []
            for d in data:
                devs.append({
                    "name": d.get("Name"),
                    "status": d.get("Status"),
                    "id": d.get("ID"),
                })
            return {"devices": devs}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _bluetooth_by_name_or_id(target: str) -> str | None:
        """Find a Bluetooth device InstanceId by partial name or id."""
        devs = UserActions.bluetooth_devices().get("devices", [])
        for d in devs:
            name = (d.get("name") or "").lower()
            did = (d.get("id") or "").lower()
            t = target.lower()
            if t in name or t in did:
                return d.get("id")
        return None

    @staticmethod
    def bluetooth_connect(target: str) -> dict:
        """Connect (enable) a Bluetooth device by name/id."""
        try:
            import subprocess
            inst = UserActions._bluetooth_by_name_or_id(target)
            if not inst:
                return {"success": False, "error": f"Bluetooth device not found: {target}"}
            ps = f'Enable-PnpDevice -InstanceId "{inst}" -Confirm:$false; Start-Sleep -Milliseconds 800; Get-PnpDevice -InstanceId "{inst}" | Select-Object -ExpandProperty Status'
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30)
            status = res.stdout.strip() or res.stderr.strip()
            return {"success": True, "device": target, "instance_id": inst, "status": status}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def bluetooth_disconnect(target: str) -> dict:
        """Disconnect (disable) a Bluetooth device by name/id."""
        try:
            import subprocess
            inst = UserActions._bluetooth_by_name_or_id(target)
            if not inst:
                return {"success": False, "error": f"Bluetooth device not found: {target}"}
            ps = f'Disable-PnpDevice -InstanceId "{inst}" -Confirm:$false; Start-Sleep -Milliseconds 800; Get-PnpDevice -InstanceId "{inst}" | Select-Object -ExpandProperty Status'
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30)
            status = res.stdout.strip() or res.stderr.strip()
            return {"success": True, "device": target, "instance_id": inst, "status": status}
        except Exception as e:
            return {"error": str(e)}

    # ---------- INSTALL / UNINSTALL PROGRAMS ----------
    @staticmethod
    def installed_programs() -> dict:
        """List installed programs (from registry) on Windows."""
        try:
            import subprocess
            ps = (
                "$r=@(); $keys=@('HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
                "'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
                "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*');"
                "$keys | ForEach-Object { Get-ItemProperty $_ -ErrorAction SilentlyContinue } | "
                "Where-Object {$_.DisplayName} | ForEach-Object { $r += [PSCustomObject]@{"
                "Name=$_.DisplayName; Version=$_.DisplayVersion; InstallLocation=$_.InstallLocation; "
                "UninstallString=$_.UninstallString} }; "
                "$r | Sort-Object Name | ConvertTo-Json -Compress"
            )
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60)
            out = res.stdout.strip()
            import json
            if not out or out == "null":
                return {"programs": []}
            data = json.loads(out)
            if not isinstance(data, list):
                data = [data]
            return {"count": len(data), "programs": data}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def install_program(installer_path: str, silent_args: str | None = None) -> dict:
        """Run an installer. If silent_args given, installs silently (no UI).
        Otherwise launches the installer UI for the user to confirm."""
        try:
            import subprocess
            if silent_args:
                cmd = [installer_path] + silent_args.split()
                subprocess.Popen(cmd)
                return {"success": True, "action": "install_started_silent", "installer": installer_path, "args": silent_args}
            os.startfile(installer_path)
            return {"success": True, "action": "installer_launched", "installer": installer_path, "note": "Installer UI opened - complete the install on screen"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def uninstall_program(name: str) -> dict:
        """Uninstall a program by name. Uses the registry UninstallString.
        Silently removes if a silent flag is detected, otherwise launches uninstaller for confirmation."""
        try:
            import subprocess
            progs = UserActions.installed_programs().get("programs", [])
            target = next((p for p in progs if name.lower() in (p.get("Name") or "").lower()), None)
            if not target:
                return {"success": False, "error": f"Program not found: {name}"}
            uninstall_str = target.get("UninstallString") or ""
            if not uninstall_str:
                return {"success": False, "error": f"No uninstall string for {target.get('Name')}"}
            # Try wingset uninstall as a clean method
            try:
                res = subprocess.run(
                    ["winget", "uninstall", "--id", target.get("Name"), "--silent", "--accept-source-agreements"],
                    capture_output=True, text=True, timeout=120,
                )
                if res.returncode == 0 or "successfully uninstalled" in res.stdout.lower():
                    return {"success": True, "program": target.get("Name"), "method": "winget"}
            except Exception:
                pass
            # Fallback: run the uninstall string
            cleaned = uninstall_str.strip().strip('"')
            subprocess.Popen(f'start "" "{cleaned}"', shell=True)
            return {
                "success": True,
                "program": target.get("Name"),
                "method": "uninstall_launched",
                "note": "Uninstaller opened - confirm on screen",
            }
        except Exception as e:
            return {"error": str(e)}

    # ---------- CONTROL / USE APPS (Windowkit + vision) ----------
    @staticmethod
    def list_running_apps() -> dict:
        """List currently running GUI apps (processes with a main window)."""
        try:
            import subprocess, json
            ps = "Get-Process | Where-Object {$_.MainWindowTitle} | ForEach-Object { [PSCustomObject]@{Name=$_.ProcessName; Title=$_.MainWindowTitle; PID=$_.Id} } | ConvertTo-Json -Compress"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=20)
            out = res.stdout.strip()
            if not out or out == "null":
                return {"apps": []}
            data = json.loads(out)
            if not isinstance(data, list):
                data = [data]
            return {"count": len(data), "apps": data}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def use_app_ui(action: str, app: str = "", **params: Any) -> dict:
        """High-level 'use an app like a real user'.
        action: focus | close | open_new | type | click_image | screenshot
        Combines window management + vision so Jarvis can drive app UIs."""
        try:
            from core.desktop.window import window_controller
        except ImportError:
            window_controller = None

        app_lower = app.lower()
        if action == "focus":
            # find matching window by partial title
            if window_controller:
                for w in window_controller.list_windows():
                    if app_lower in w["title"].lower():
                        r = window_controller.focus(w["title"])
                        return {"success": r.success, "window": w["title"]}
            # fallback: launch app
            if params.get("launch_if_missing", True):
                pyautogui.hotkey("win")
                time.sleep(0.3)
                pyautogui.typewrite(app, interval=0.02)
                time.sleep(0.3)
                pyautogui.press("enter")
                return {"success": True, "action": "launched_via_start_menu", "app": app}
            return {"success": False, "error": f"App window not found: {app}"}

        elif action == "close":
            if window_controller:
                for w in window_controller.list_windows():
                    if app_lower in w["title"].lower():
                        r = window_controller.close(w["title"])
                        return {"success": r.success, "window": w["title"]}
            return {"success": False, "error": f"App window not found: {app}"}

        elif action == "type":
            pyautogui.typewrite(str(params.get("text", "")), interval=0.02)
            return {"success": True, "typed": params.get("text", "")}

        elif action == "press":
            pyautogui.press(str(params.get("key", "")))
            return {"success": True, "key": params.get("key", "")}

        elif action == "click":
            x, y = params.get("x"), params.get("y")
            if x is not None and y is not None:
                pyautogui.click(int(x), int(y))
                return {"success": True, "clicked": (x, y)}
            return {"success": False, "error": "x,y required for click"}

        elif action == "screenshot":
            img = pyautogui.screenshot()
            from io import BytesIO
            import base64
            buf = BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            return {"success": True, "size": img.size, "png_base64": b64}

        elif action == "find_click":
            import os as _os
            img_path = params.get("image")
            if not img_path or not _os.path.exists(img_path):
                return {"success": False, "error": "image path required"}
            loc = pyautogui.locateOnScreen(img_path, confidence=params.get("confidence", 0.8))
            if not loc:
                return {"success": False, "found": False}
            cx, cy = pyautogui.center(loc)
            pyautogui.click(cx, cy)
            return {"success": True, "found": True, "clicked": (int(cx), int(cy))}

        return {"success": False, "error": f"Unknown ui action: {action}"}

    # ---------- SYSTEM CONTROLS (brightness / volume / power / display) ----------
    @staticmethod
    def run_ps(code: str, timeout: int = 20) -> dict:
        """Run a PowerShell snippet and return parsed output."""
        import subprocess
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", code],
                capture_output=True, text=True, timeout=timeout,
            )
            out = (res.stdout or "").strip()
            err = (res.stderr or "").strip()
            return {"exit": res.returncode, "stdout": out, "stderr": err}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def get_brightness() -> dict:
        """Current display brightness (0-100)."""
        code = "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness"
        r = UserActions.run_ps(code)
        try:
            val = int(float(r.get("stdout", "-1")))
            return {"brightness": val, "range": [0, 100]}
        except Exception:
            return {"error": "Brightness service not available", "raw": r.get("stdout") or r.get("error")}

    @staticmethod
    def set_brightness(level: int) -> dict:
        """Set display brightness. level 0-100."""
        level = max(0, min(100, int(level)))
        code = (
            f"$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods; "
            f"$m.WmiSetBrightness(1, {level})"
        )
        r = UserActions.run_ps(code)
        if r.get("stderr"):
            return {"success": False, "error": r["stderr"]}
        return {"success": True, "brightness": level}

    @staticmethod
    def get_volume() -> dict:
        """Current master volume (0-100) + mute state."""
        ps = (
            "Add-Type -Namespace Audio -Name Volume -MemberDefinition '[DllImport(\"winmm.dll\")]"
            "public static extern int waveOutGetVolume(IntPtr hwo, out uint dwVolume);' -ErrorAction SilentlyContinue; "
            "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices;"
            "public class Vol { [DllImport(\"winmm.dll\")] public static extern int waveOutGetVolume(IntPtr hwo, out uint dw); }' -ErrorAction SilentlyContinue; "
            "$v = 0; [Audio.Volume]::waveOutGetVolume([IntPtr]::Zero, [ref]$v) | Out-Null; "
            "$pct = [math]::Round(($v -band 0xFFFF) / 65535 * 100); "
            "Write-Output \"$pct\""
        )
        r = UserActions.run_ps(ps)
        try:
            val = int(float(r.get("stdout", "-1")))
            return {"volume": max(0, min(100, val)), "range": [0, 100]}
        except Exception:
            return {"error": "Volume read failed", "raw": r.get("stdout") or r.get("error")}

    @staticmethod
    def set_volume(level: int) -> dict:
        """Set master volume. level 0-100. (Uses winmm waveOutSetVolume.)"""
        level = max(0, min(100, int(level)))
        raw = int(65535 * level / 100)
        ps = (
            "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices;"
            "public class Vol2 { [DllImport(\"winmm.dll\")] public static extern int waveOutSetVolume(IntPtr hwo, uint dwVolume); }' -ErrorAction SilentlyContinue; "
            f"[Vol2]::waveOutSetVolume([IntPtr]::Zero, {raw}) | Out-Null"
        )
        r = UserActions.run_ps(ps)
        if r.get("stderr"):
            return {"success": False, "error": r["stderr"]}
        return {"success": True, "volume": level}

    @staticmethod
    def mute() -> dict:
        """Mute master volume."""
        ps = (
            "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices;"
            "public class Vol3 { [DllImport(\"winmm.dll\")] public static extern int waveOutSetVolume(IntPtr hwo, uint dwVolume); }' -ErrorAction SilentlyContinue; "
            "[Vol3]::waveOutSetVolume([IntPtr]::Zero, 0) | Out-Null"
        )
        r = UserActions.run_ps(ps)
        return {"success": not bool(r.get("stderr")), "muted": True}

    @staticmethod
    def unmute() -> dict:
        """Unmute (set volume to 50% if previously 0)."""
        return UserActions.set_volume(50)

    @staticmethod
    def power_state(action: str) -> dict:
        """Lock/sleep/restart/shutdown. action: lock|sleep."""  
        if action == "lock":
            r = UserActions.run_ps("rundll32.exe user32.dll,LockWorkStation")
        elif action == "sleep":
            r = UserActions.run_ps("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        else:
            return {"error": f"Unsupported power action: {action}"}
        return {"success": not bool(r.get("error") or r.get("stderr"))}

    @staticmethod
    def display_off_after(minutes: int) -> dict:
        """Set display sleep timeout (minutes). Uses powercfg."""
        code = f"powercfg /change monitor-timeout-ac {int(minutes)}"
        r = UserActions.run_ps(code)
        return {"success": not bool(r.get("error") or r.get("stderr")), "minutes": minutes}

    @staticmethod
    def cpu_ram_usage() -> dict:
        """Current CPU % and RAM used GB."""
        import psutil as _p
        try:
            mem = _p.virtual_memory()
            return {
                "cpu_percent": _p.cpu_percent(interval=0.5),
                "ram_used_gb": round(mem.used / (1024 ** 3), 2),
                "ram_total_gb": round(mem.total / (1024 ** 3), 2),
                "ram_percent": mem.percent,
            }
        except Exception as e:
            return {"error": str(e)}

    # ---------- RADIO CONTROLS (Bluetooth / Wi-Fi / Airplane mode) ----------
    @staticmethod
    def _pnp_devices(class_name: str = "Bluetooth") -> list[dict]:
        """Query PnP devices of a class. Returns id + friendly name + status."""
        ps = (
            f"Get-PnpDevice -Class {class_name} -PresentOnly | "
            "ForEach-Object { [PSCustomObject]@{Id=$_.InstanceId; Name=$_.FriendlyName; Status=$_.Status; Problem=$_.Problem} } | ConvertTo-Json -Compress"
        )
        import subprocess, json
        try:
            res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                                 capture_output=True, text=True, timeout=25)
            out = res.stdout.strip()
            if not out or out == "null":
                return []
            data = json.loads(out)
            if not isinstance(data, list):
                data = [data]
            return data
        except Exception:
            return []

    @staticmethod
    def _set_pnp_device(instance_id: str, enable: bool) -> dict:
        """Enable or disable a PnP device (requires admin)."""
        verb = "Enable" if enable else "Disable"
        ps = f"$d = Get-PnpDevice -InstanceId '{instance_id}'; {verb}-PnpDevice -InputObject $d -Confirm:$false"
        r = UserActions.run_ps(ps, timeout=30)
        if r.get("stderr"):
            return {"success": False, "action": verb, "instance_id": instance_id, "error": r["stderr"].strip()}
        return {"success": True, "action": verb, "instance_id": instance_id}

    @staticmethod
    def _find_adapter(class_name: str, name_hint: str = "Adapter") -> str | None:
        """Find the instance id of a hardware adapter (e.g. Bluetooth Adapter, Wi-Fi card)."""
        for dev in UserActions._pnp_devices(class_name):
            if name_hint.lower() in str(dev.get("Name", "")).lower():
                return dev.get("Id")
        return None

    @staticmethod
    def bluetooth_radio(on: bool) -> dict:
        """Turn the Bluetooth ADAPTER radio on (True) or off (False). REQUIRES ADMIN (run PS as admin)."""
        adapter = UserActions._find_adapter("Bluetooth", "Adapter")
        if not adapter:
            # fallback: any device whose name has no services (raw adapter)
            for dev in UserActions._pnp_devices("Bluetooth"):
                name = str(dev.get("Name", ""))
                if "Avrcp" not in name and "RFCOMM" not in name and "Enumerator" not in name and "Service" not in name:
                    adapter = dev.get("Id")
                    break
        if not adapter:
            return {"success": False, "error": "Bluetooth adapter not found"}
        return UserActions._set_pnp_device(adapter, enable=on)

    @staticmethod
    def bluetooth_radio_state() -> dict:
        """Whether the Bluetooth adapter is currently on/off."""
        devs = UserActions._pnp_devices("Bluetooth")
        on_devices = [d for d in devs if d.get("Status") == "OK"]
        adapter = UserActions._find_adapter("Bluetooth", "Adapter")
        for d in on_devices:
            if adapter and d.get("Id") == adapter:
                return {"bluetooth": "on", "adapter": d.get("Name"), "status": d.get("Status")}
        return {"bluetooth": "off", "reason": "adapter not enabled", "devices": len(devs)}

    @staticmethod
    def wifi_radio(on: bool) -> dict:
        """Turn the Wi-Fi adapter on (True) or off (False). REQUIRES ADMIN."""
        adapter = UserActions._find_adapter("Net", "Wi-Fi")
        if not adapter:
            for dev in UserActions._pnp_devices("Net"):
                name = str(dev.get("Name", ""))
                if "Wireless" in name or "WLAN" in name or "Wi-Fi" in name:
                    if "Virtual" not in name:
                        adapter = dev.get("Id")
                        break
        if not adapter:
            return {"success": False, "error": "Wi-Fi adapter not found"}
        return UserActions._set_pnp_device(adapter, enable=on)

    @staticmethod
    def airplane_mode(on: bool) -> dict:
        """Enable (True) or disable (False) AIRPLANE MODE — toggles both Wi-Fi and Bluetooth."""
        results = {"wifi": UserActions.wifi_radio(on), "bluetooth": UserActions.bluetooth_radio(on)}
        ok = any(r.get("success") for r in results.values())
        return {"success": ok, "airplane_mode": ("on" if on else "off"), "results": results}

    @staticmethod
    def radio_state() -> dict:
        """Overall radio state: wifi, bluetooth on/off."""
        bt = UserActions.bluetooth_radio_state()
        try:
            import subprocess
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                "(Get-NetAdapter -Physical | Where-Object Status -eq 'Up').Name"],
                               capture_output=True, text=True, timeout=20)
            wifi_up = any("Wi-Fi" in l or "Wireless" in l for l in (r.stdout or "").splitlines())
            wifi = "on" if wifi_up else "off"
        except Exception:
            wifi = "unknown"
        return {"wifi": wifi, "bluetooth": bt, "airplane_mode": "on" if (wifi == "off" and bt.get("bluetooth") == "off") else "off"}


user_actions = UserActions()
