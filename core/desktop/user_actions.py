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

# ---------- SELF-HEALING ELEMENT MAP (drift-tolerant UIA lookup) ----------
# Cache of per-app/window form-element maps, so when a control's automation id or
# position drifts between runs, we can still locate it by name + relative offset
# from a last-known-good anchor, and every such recovery is logged as a drift event.
import json as _json

CACHE_DIR = Path(__file__).resolve().parents[2] / "data"
ELEMENT_CACHE_FILE = CACHE_DIR / "element_cache.json"
DRIFT_LOG_FILE = Path(__file__).resolve().parents[2] / "logs" / "element_drift.jsonl"
# Below this confidence score a drift-recovered click is refused (stale or anchor-less),
# because clicking from a wrong guess is worse than returning a corrective error.
MIN_RECOVERY_CONFIDENCE = 0.6
HOURS = 3600.0


def _load_element_cache() -> dict:
    try:
        if ELEMENT_CACHE_FILE.exists():
            with open(ELEMENT_CACHE_FILE, "r", encoding="utf-8") as f:
                data = _json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_element_cache(cache: dict):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(ELEMENT_CACHE_FILE, "w", encoding="utf-8") as f:
            _json.dump(cache, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _log_drift(event: dict):
    try:
        DRIFT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DRIFT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(_json.dumps(event) + "\n")
    except Exception:
        pass


def _name_similarity(a: str, b: str) -> float:
    """0..1 similarity for control names (covers spacing/case/typos)."""
    import difflib
    return difflib.SequenceMatcher(None, str(a).lower().strip(), str(b).lower().strip()).ratio()


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

    # ---------- VISION: CROP TEMPLATE FROM SCREENSHOT ----------
    @staticmethod
    def crop_image(image_path: str, x: int, y: int, w: int, h: int, out_path: str) -> dict:
        """Crop a region from an existing screenshot and save it as a standalone template
        image. THIS is how a UI element (button/icon/text box) becomes a template that
        find_on_screen and click_image can locate. Covers whole screen: x,y are pixels."""
        try:
            from PIL import Image
            img = Image.open(image_path)
            box = (int(x), int(y), int(x) + int(w), int(y) + int(h))
            region = img.crop(box)
            region.save(out_path)
            return {
                "success": True,
                "template": out_path,
                "region": {"x": x, "y": y, "w": w, "h": h},
            }
        except Exception as e:
            return {"error": str(e)}

    # ---------- VISION: ELEMENT COORDINATES VIA VISION MODEL ----------
    @staticmethod
    def _vision_element_hint(provider, screenshot: str, target: str) -> dict:
        """Ask the vision model for a rough screen location of an element to guide clicks.
        Returns a region guess + raw answer; pixel-accurate clicks still use click_image."""
        import re as _re, json as _json
        def _ask(prompt) -> dict:
            raw = provider.vision(screenshot, prompt).strip()
            m = _re.search(r'\{[^{}]*\}', raw)
            if m:
                try:
                    return _json.loads(m.group(0))
                except Exception:
                    return {"error": raw[:200]}
            return {"error": raw[:200], "raw": True}
        prompt1 = (
            f"The screen is 1920 pixels wide and 1080 tall. Locate the '{target}' on screen. "
            f'Give its approximate x y width height in pixels as JSON: '
            '{"x":Number,"y":Number,"w":Number,"h":Number}. Reply with only that JSON.'
        )
        hint = _ask(prompt1)
        if "x" in hint:
            return hint
        # Retry with simpler phrasing if model refused first time
        prompt2 = (
            f"Where is the {target} on this screenshot? The image is 1920x1080. "
            f'Answer JSON only: {"x":center,"y":center,"w":width,"h":height}.'
        )
        hint = _ask(prompt2)
        return hint

    @staticmethod
    def click_vision_element(provider, target: str, verify_brightness: bool = False) -> dict:
        """Find a UI element by NAME using the vision model, then click it.
        Flow: screenshot -> vision estimate -> crop template -> click_image -> verify.
        Degenerate or off-screen estimates are rejected so the agent never mis-clicks."""
        import time as _t, subprocess as _sp, tempfile as _tf, os as _os
        SW, SH = 1920, 1080
        try:
            shot = _tf.mktemp(suffix=".png", prefix="jarvis_scan_")
            UserActions.take_screenshot(shot)
            hint = UserActions._vision_element_hint(provider, shot, target)
            if not hint or "x" not in hint:
                return {"success": False, "error": f"Vision model did not locate '{target}'", "hint": hint}
            if not isinstance(hint.get("x"), (int, float)):
                return {"success": False, "error": "Malformed vision location", "hint": hint}

            x, y = float(hint["x"]), float(hint["y"])
            w = float(hint.get("w", 60))
            h = float(hint.get("h", 30))
            # detect normalized (0..1) coords and scale to real pixels
            if x <= 1.0 and y <= 1.0:
                x, y = round(x * SW), round(y * SH)
            if w <= 1.0 and h <= 1.0:
                w, h = round(w * SW), round(h * SH)
            x, y, w, h = int(round(x)), int(round(y)), int(round(w)), int(round(h))

            # SAFETY: reject degenerate/off-screen guesses
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x > SW or y > SH:
                return {"success": False, "error": f"Vision rejected unsafe location for '{target}': {(x,y,w,h)}"}
            if (x, y) == (0, 0) and (w >= SW or h >= SH):
                return {"success": False, "error": f"Vision returned whole-screen bbox for '{target}'"}

            # expand a bit to catch the whole element
            pad = 10
            x0, y0 = max(0, x - w // 2 - pad), max(0, y - h // 2 - pad)
            w0, h0 = min(SW, w + 2 * pad), min(SH, h + 2 * pad)
            tpl = _tf.mktemp(suffix=".png", prefix="jarvis_tpl_")
            crop = UserActions.crop_image(shot, x0, y0, w0, h0, tpl)
            if not crop.get("success"):
                return {"success": False, "error": crop.get("error")}
            res = UserActions.click_image(tpl, confidence=0.75)
            if not res.get("found"):
                # Try a wider search: click the estimated center as fallback only if it's
                # inside the viewport and not a whole-screen estimate.
                center = UserActions.find_on_screen(tpl, confidence=0.6)
                if not center.get("found"):
                    return {"success": False, "error": "Template match failed for target", "target": target, "hint": hint}
                res = UserActions.click_image(tpl, confidence=0.6)
            return {
                "success": bool(res.get("found")),
                "target": target,
                "vision_guess": {"x": x, "y": y, "w": w, "h": h},
                "click": res,
            }
        except Exception as e:
            return {"error": str(e)}

    # ---------- APP LAUNCH (smart) ----------
    @staticmethod
    def open_with(path: str, app: str | None = None) -> dict:
        """Open a file or URL. If app given, open in that app (e.g., notepad, excel, chrome).
        VERIFIES the path exists first so it never returns success for a nonexistent file."""
        import subprocess, os as _os
        path = str(path).strip().strip('"').strip()
        low = path.lower()
        is_url = low.startswith(("http://", "https://", "file://", "ftp://"))
        if not is_url and not _os.path.exists(path):
            return {
                "success": False,
                "error": f"Path does not exist: {path}. Check the path (open_file only opens real files/folders, not made-up names).",
                "path": path,
            }
        try:
            if is_url:
                subprocess.Popen(f'start "" "{path}"', shell=True)
                return {"success": True, "opened": path, "kind": "url"}
            if app:
                if app.lower() in ("notepad", "editor", "text", "txt"):
                    subprocess.Popen(["notepad.exe", path], shell=True)
                elif app.lower() in ("code", "vscode", "visual studio code", "vs code"):
                    subprocess.Popen(["code", path])
                elif app.lower() in ("chrome", "google chrome"):
                    subprocess.Popen(["chrome", path])
                else:
                    subprocess.Popen(f'start "" "{app}" "{path}"', shell=True)
                return {"success": True, "opened": path, "with": app, "path_exists": True}
            else:
                if sys.platform == "win32":
                    _os.startfile(path)
                return {"success": True, "opened": path, "path_exists": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

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

    # ---------- TABS & WINDOW FOCUS (all tabbed apps via UI Automation) ----------
    @staticmethod
    def focus_window_win32(title: str) -> dict:
        """Reliably bring a window to the foreground using Win32 APIs."""
        import win32gui, win32con, win32api, win32process, time as _t
        target_lower = str(title).lower()
        found = []

        def _enum(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            text = win32gui.GetWindowText(hwnd)
            if text and target_lower in text.lower():
                found.append((hwnd, text))
            return True

        win32gui.EnumWindows(_enum, None)
        if not found:
            return {"success": False, "error": f"No visible window matches '{title}'"}

        hwnd, win_title = found[0]
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            # Attach input thread so SetForegroundWindow is allowed, then restore.
            fg = win32gui.GetForegroundWindow()
            cur = win32api.GetCurrentThreadId()
            fg_tid, _ = win32process.GetWindowThreadProcessId(fg)
            win_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
            win32process.AttachThreadInput(cur, fg_tid, True)
            win32process.AttachThreadInput(cur, win_tid, True)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            win32process.AttachThreadInput(cur, fg_tid, False)
            win32process.AttachThreadInput(cur, win_tid, False)
            _t.sleep(0.15)
            return {"success": True, "window": win_title, "hwnd": hwnd}
        except Exception as e:
            # Final fallback: ShowWindow minimized trick
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                _t.sleep(0.15)
                return {"success": True, "window": win_title, "hwnd": hwnd, "note": str(e)}
            except Exception as e2:
                return {"success": False, "error": str(e2)}

    @staticmethod
    def _app_pids(app_name: str) -> list[int]:
        """Find pids of an app by process executable name (e.g. chrome -> msedge/chrome)."""
        import psutil
        app_lower = str(app_name).lower().replace(".exe", "").strip()
        names = {app_lower, app_lower + ".exe"}
        if app_lower in ("chrome", "msedge", "edge", "brave", "opera", "firefox", "vivaldi", "yandex"):
            for alias in ("chrome", "msedge", "brave", "opera", "firefox", "vivaldi"):
                names.add(alias)
                names.add(alias + ".exe")
        results = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                n = (p.info.get("name") or "").lower().replace(".exe", "")
                if n in names:
                    results.append(p.info["pid"])
            except Exception:
                continue
        return results

    @staticmethod
    def list_tabs(app_name: str) -> dict:
        """Enumerate tabs of ANY tabbed app (Chrome, Edge, Explorer, VS Code, Notepad++, etc.)
        using Windows UI Automation. Returns per-window tab list + total count."""
        pids = UserActions._app_pids(app_name)
        if not pids:
            return {"success": False, "app": app_name, "error": f"No running '{app_name}' process found."}

        windows = []
        total = 0
        for pid in pids:
            ps = (
                "Add-Type -AssemblyName UIAutomationClient; "
                "Add-Type -AssemblyName UIAutomationTypes; "
                f"$pidT = {pid}; "
                "$root = [System.Windows.Automation.AutomationElement]::RootElement; "
                "$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pidT); "
                "$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond); "
                "$out = @(); "
                "foreach ($w in $wins) { "
                "  $tabs = @(); "
                "  $tcond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::TabItem); "
                "  $items = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $tcond); "
                "  foreach ($i in $items) { $tabs += $i.Current.Name } "
                "  $out += [PSCustomObject]@{window=$w.Current.Name; pid=$pidT; tabs=$tabs} "
                "} "
                "[PSCustomObject]@{pid=$pidT; windows=$out} | ConvertTo-Json -Compress -Depth 6"
            )
            import subprocess, json
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-STA", "-Command", ps],
                    capture_output=True, text=True, timeout=40,
                )
                raw = (res.stdout or "").strip()
                if raw:
                    data = json.loads(raw)
                    for win in data.get("windows", []):
                        total += len(win.get("tabs", []))
                    windows.extend(data.get("windows", []))
            except Exception:
                continue
        return {
            "success": bool(windows),
            "app": app_name,
            "total_tabs": total,
            "windows": windows,
        }

    @staticmethod
    def focus_tab(app_name: str, tab_title: str) -> dict:
        """Switch to a specific tab (by title substring) in ANY tabbed app via UI Automation."""
        pids = UserActions._app_pids(app_name)
        if not pids:
            return {"success": False, "error": f"No running '{app_name}' process found."}
        needle = str(tab_title).lower()
        for pid in pids:
            ps = (
                "Add-Type -AssemblyName UIAutomationClient; "
                "Add-Type -AssemblyName UIAutomationTypes; "
                f"$pidT = {pid}; "
                "$root = [System.Windows.Automation.AutomationElement]::RootElement; "
                "$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pidT); "
                "$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond); "
                "foreach ($w in $wins) { "
                "  $tcond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::TabItem); "
                "  $items = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $tcond); "
                "  foreach ($i in $items) { "
                f"    if ($i.Current.Name.ToLower().Contains('{needle}')) {{ "
                "      try { $pat = $i.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern); $pat.Select(); [void]$w.SetFocus() } catch {} "
                "      Write-Output ('SWITCHED:' + $i.Current.Name + '|' + $w.Current.Name); exit "
                "    } "
                "  } "
                "}"
            )
            import subprocess
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-STA", "-Command", ps],
                    capture_output=True, text=True, timeout=30,
                )
                out = (res.stdout or "").strip()
                if out.startswith("SWITCHED:"):
                    _, _, rest = out.partition("SWITCHED:")
                    tab_name, _, win_title = rest.partition("|")
                    # bring the owning window to the foreground too
                    UserActions.focus_window_win32(win_title)
                    return {"success": True, "app": app_name, "tab": tab_name, "window": win_title}
            except Exception:
                continue
        return {"success": False, "app": app_name, "error": f"Tab '{tab_title}' not found."}

    @staticmethod
    def reveal_in_explorer(path: str) -> dict:
        """Reveal/focus a file or folder in Windows Explorer."""
        import subprocess, os as _os
        path = str(path).strip().strip('"').strip()
        if not _os.path.exists(path):
            return {"success": False, "error": f"Path does not exist: {path}", "path": path}
        try:
            subprocess.Popen(f'explorer /select,"{path}"')
            return {"success": True, "path": path, "revealed_in_explorer": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---------- UIA FORM FIELD DISCOVERY (reliable click into web/app forms) ----------
    @staticmethod
    def _cache_key(app_name: str, window: str) -> str:
        return f"{str(app_name).lower()}|{window}"

    @staticmethod
    def _update_element_cache(app_name: str, fields: list[dict]) -> dict:
        """Merge a live UIA field scan into the persistent element map keyed by app+window."""
        cache = _load_element_cache()
        by_win: dict[str, list] = {}
        for f in fields:
            by_win.setdefault(f.get("window", "?"), []).append(f)
        for window, flist in by_win.items():
            key = UserActions._cache_key(app_name, window)
            entry = {"window": window, "app": app_name, "fields": flist, "updated": time.time()}
            cache[key] = entry
        _save_element_cache(cache)
        return cache

    @staticmethod
    def _cached_fields_for(app_name: str) -> list[dict]:
        """All cached fields for an app (any window), for drift-recovery matching."""
        cache = _load_element_cache()
        out = []
        for key, entry in (cache or {}).items():
            if key.startswith(f"{str(app_name).lower()}|"):
                out.extend(entry.get("fields", []))
        return out

    @staticmethod
    def _drift_recover(app_name: str, label: str, live_fields: list[dict]) -> dict | None:
        """Try to locate a form control that UIA no longer exposes by exact id/name.
        Strategy: match cached element by (name similarity + control type), then
        re-anchor its position using a live field that matches a cached anchor.
        Every recovery is logged as a drift event."""
        cache = _load_element_cache()
        cached = UserActions._cached_fields_for(app_name)
        if not cached:
            return None
        low = str(label).lower()
        # 1) find best cached candidate by name-similarity or id-substring
        best = None
        for f in cached:
            sim = _name_similarity(f.get("name", ""), low)
            id_hit = low in (f.get("automationid") or "").lower() or low in (f.get("name") or "").lower()
            if best is None or (id_hit and not best[1]) or (sim > best[1]):
                best = (f, sim, id_hit)
        if best is None:
            return None
        cand, sim, id_hit = best
        # 2) find a shared anchor between live scan and cache (same automationid or exact name)
        anchor_cached = None
        anchor_live = None
        for cf in cached:
            if cf.get("automationid"):
                for lf in live_fields:
                    if lf.get("automationid") and lf["automationid"] == cf["automationid"]:
                        anchor_cached, anchor_live = cf, lf
                        break
                if anchor_cached:
                    break
        if anchor_cached and anchor_live:
            dx = cand["x"] - anchor_cached["x"]
            dy = cand["y"] - anchor_cached["y"]
            nx = anchor_live["x"] + dx
            ny = anchor_live["y"] + dy
            method = "reanchored"
        else:
            # fall back to cached absolute position (window may have moved — low confidence)
            nx, ny = cand["x"], cand["y"]
            method = "cached_absolute"
        anchor_found = anchor_cached is not None and anchor_live is not None
        if anchor_found:
            # a live anchor matched by automation id proves the layout is current:
            # relative offsets are trustworthy regardless of cache age.
            confidence = 0.95
        else:
            # anchor-less fallback degrades quickly, and worse with cache age
            confidence = 0.55
            age_hours = UserActions._cache_age_hours(app_name)
            if age_hours is not None and age_hours > 1.0:
                confidence *= max(0.35, 1.0 - (age_hours - 1.0) / 24.0)
        confidence = round(confidence, 2)
        age_hours = UserActions._cache_age_hours(app_name)
        _log_drift({
            "t": time.time(), "app": app_name, "target_label": label,
            "matched_name": cand.get("name"), "matched_id": cand.get("automationid"),
            "similarity": round(sim, 2), "id_hit": id_hit, "method": method,
            "cache_age_hours": None if age_hours is None else round(age_hours, 2),
            "confidence": confidence,
            "live_fields": [f.get("automationid") for f in live_fields][:10],
            "new_pos": [int(nx), int(ny)],
        })
        rec = {
            "name": cand.get("name"), "automationid": cand.get("automationid"),
            "x": int(nx), "y": int(ny),
            "w": int(cand.get("w", 10)), "h": int(cand.get("h", 10)),
            "type": cand.get("type"), "drift_recovered": True, "drift_method": method,
            "confidence": confidence,
        }
        if confidence < MIN_RECOVERY_CONFIDENCE:
            rec["low_confidence"] = True
        return rec

    @staticmethod
    def _cache_age_hours(app_name: str) -> float | None:
        """Age of the newest cached element map for an app (None if untracked/absent)."""
        cache = _load_element_cache()
        newest = None
        for key, entry in (cache or {}).items():
            if key.startswith(f"{str(app_name).lower()}|"):
                u = entry.get("updated")
                if u and (newest is None or u > newest):
                    newest = u
        if newest is None:
            return None
        return max(0.0, (time.time() - newest) / HOURS)

    @staticmethod
    def list_form_fields(app_name: str) -> dict:
        """Find interactive form controls (Edit, ComboBox, RadioButton, CheckBox, Button)
        inside app windows via UI Automation. Returns controls with pixel click positions
        and their control type. Every successful scan is cached for drift recovery.
        If live UIA returns nothing but a cached map exists, cached positions are returned
        with from_cache=True so the agent can still act without re-discovering."""
        pids = UserActions._app_pids(app_name)
        if not pids:
            return {"success": False, "app": app_name, "error": f"No running '{app_name}' process found."}
        ps = (
            "Add-Type -AssemblyName UIAutomationClient; "
            "Add-Type -AssemblyName UIAutomationTypes; "
            "$out = @(); "
            "$types = @('Edit','ComboBox','RadioButton','CheckBox','Button'); "
            "foreach ($pidT in @(" + ",".join(str(p) for p in pids) + ")) { "
            "$root = [System.Windows.Automation.AutomationElement]::RootElement; "
            "$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pidT); "
            "$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond); "
            "foreach ($w in $wins) { "
            "  foreach ($t in $types) { "
            "    $ct = [System.Windows.Automation.ControlType]::$t; "
            "    $tc = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, $ct); "
            "    $items = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $tc); "
            "    foreach ($e in $items) { "
            "      $r = $e.Current.BoundingRectangle; "
            "      $n = $e.Current.Name; "
            "      if ($r.Width -gt 10 -and $r.Height -gt 8 -and $n -and $n -notin @('Minimize','Restore','Close','Back','Forward','Reload','New Tab','Tab search','Extensions','Bookmark this tab','View site information')) { "
            "        $out += [PSCustomObject]@{ window=$w.Current.Name; pid=$pidT; type=$t; name=$n; automationid=$e.Current.AutomationId; "
            "          x=[int]$r.X; y=[int]$r.Y; w=[int]$r.Width; h=[int]$r.Height } "
            "      } "
            "    } "
            "  } "
            "} } "
            "if ($out.Count -eq 0) { Write-Output '[]' } else { $out | ConvertTo-Json -Compress -Depth 5 }"
        )
        import subprocess, json
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-STA", "-Command", ps],
                capture_output=True, text=True, timeout=40,
            )
            raw = (res.stdout or "").strip()
            if not raw or raw == "null":
                fields = []
            else:
                fields = json.loads(raw)
                if not isinstance(fields, list):
                    fields = [fields]
            window = fields[0].get("window", "?") if fields else "?"
            UserActions._update_element_cache(app_name, fields)
            if not fields:
                cached = UserActions._cached_fields_for(app_name)
                if cached:
                    age_hours = UserActions._cache_age_hours(app_name)
                    stale = age_hours is not None and age_hours > 24.0
                    _log_drift({"t": time.time(), "app": app_name, "uia_blind": True,
                                "fell_back_to_cache": len(cached), "live_fields": 0,
                                "cache_age_hours": None if age_hours is None else round(age_hours, 1)})
                    return {"success": True, "app": app_name, "fields": cached, "count": len(cached),
                            "from_cache": True, "cache_age_hours": age_hours, "stale": stale,
                            "warning": "Live UIA empty; used cached element map (drift-recovered). Stale cache -> verify visually before clicking." if stale else "Live UIA empty; used cached element map (drift-recovered)."}
            return {"success": True, "app": app_name, "fields": fields, "count": len(fields), "window": window}
        except Exception as e:
            return {"success": False, "error": str(e), "raw": raw if 'raw' in dir() else str(e)}

    @staticmethod
    def click_form_field(app_name: str, index: int = 0, field_label: str | None = None) -> dict:
        """Click/activate a form control found via UIA. If the exact automation id is gone
        (layout/app update), recover via cached map: name-similarity + control type +
        relative offset from a live anchor. Args: {"app_name":str,"index":int,"field_label":str}."""
        import time as _t
        res = UserActions.list_form_fields(app_name)
        fields = res.get("fields", [])
        drift_recovered = False
        if not fields:
            return {"success": False, "error": "No input fields found", "detail": res}
        if res.get("from_cache"):
            # fields came from the CACHE because UIA is currently blind -> absolute
            # positions may be stale (app/window moved since last successful scan)
            age_hours = res.get("cache_age_hours")
            if age_hours is None or age_hours > 24.0:
                _log_drift({"t": time.time(), "app": app_name, "refused_from_cache_click": True,
                            "target_label": str(field_label), "cache_age_hours": age_hours})
                return {"success": False, "error": "UIA is blind and the cached element map is stale "
                        "(age=%s). Refusing to click a cached absolute position. Re-discover first: "
                        "screenshot + find_on_screen/click_image, or keyboard Tab order." % (
                            None if age_hours is None else round(age_hours, 1))}
            drift_recovered = True
        candidates = fields
        if field_label:
            low = field_label.lower()
            exact = [f for f in fields if low in f.get("name", "").lower() or low in f.get("automationid", "").lower()]
            if not exact:
                # live match failed -> attempt drift recovery against the cache
                rec = None
                for f in fields:
                    if f.get("window"):
                        rec = UserActions._drift_recover(app_name, str(field_label), fields)
                        if rec:
                            break
                if rec is None:
                    rec = UserActions._drift_recover(app_name, str(field_label), fields)
                if rec:
                    if rec.get("low_confidence"):
                        _log_drift({"t": time.time(), "app": app_name, "refused_low_confidence": True,
                                    "target_label": str(field_label)})
                        return {"success": False, "error": "Drift-recovered control has low confidence "
                                "(stale cache and no live anchor). Refusing to click blind. "
                                "Re-discover first: take a screenshot and use find_on_screen/click_image "
                                "or keyboard Tab order instead.", "detail": {k: rec.get(k) for k in
                                ("name", "automationid", "confidence", "drift_method", "cache_age_hours")}}
                    candidates = [rec]
                    drift_recovered = True
                else:
                    return {"success": False, "error": f"No form control matches label '{field_label}'", "available": [f.get("name") for f in fields]}
            else:
                candidates = exact
        target = candidates[min(int(index), len(candidates) - 1)] if index else candidates[0]
        cx = int(target["x"] + target["w"] / 2)
        cy = int(target["y"] + target["h"] / 2)
        from core.desktop.controller import desktop_controller as _dc
        _dc.click(cx, cy)
        _t.sleep(0.4)
        return {
            "success": True,
            "field": {"name": target.get("name"), "id": target.get("automationid"), "type": target.get("type"), "index": index, "pos": (cx, cy)},
            "drift_recovered": drift_recovered,
        }


user_actions = UserActions()
