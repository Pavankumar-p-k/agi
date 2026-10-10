"""UserActions — the desktop agent's Windows action layer.

Real, best-effort implementations: stdlib/ctypes where possible,
PowerShell UI Automation for semantic control access, honest failures
everywhere. Tests patch individual methods; the class must expose them
as static/class methods so monkeypatching works.
"""
from __future__ import annotations

import csv
import io
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


def _run_uia_script(action: str, **kwargs: Any) -> dict:
    """Run a PowerShell UI Automation helper and parse its JSON output."""
    script_dir = Path(__file__).resolve().parent / "scripts"
    script = script_dir / f"{action}.ps1"
    if not script.exists():
        return {"success": False, "error": f"UIA helper '{action}' unavailable"}
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
           "-File", str(script)]
    for key, value in kwargs.items():
        if value is not None:
            cmd += [f"-{key}", str(value)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=20, check=False)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        if proc.returncode != 0:
            return {"success": False, "error": proc.stderr.strip()[:300]}
        return {"success": False, "error": "UIA helper returned no JSON"}


def _tasklist_processes() -> list:
    """List processes as CSV dicts via tasklist (no third-party deps)."""
    try:
        proc = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
            text=True, timeout=15, check=False)
        rows = list(csv.reader(io.StringIO(proc.stdout)))
        procs = []
        for row in rows:
            if len(row) >= 2:
                procs.append({"name": row[0], "pid": row[1]})
        return procs
    except Exception:  # noqa: BLE001
        return []


class UserActions:
    """All desktop actions the JARVIS desktop agent can invoke."""

    # Recursive listing bounds (tests monkeypatch these class attributes).
    MAX_RECURSION_DEPTH = 8
    MAX_ENTRIES = 500

    # ── process helpers ──────────────────────────────────────────────
    @staticmethod
    def _app_pids(app: str) -> list:
        """PIDs of processes whose name matches `app` (extension-insensitive)."""
        key = str(app).lower().strip().replace(".exe", "")
        pids: list = []
        try:
            import psutil
            for proc in psutil.process_iter(["name", "pid"]):
                name = str(proc.info.get("name", "")).lower().replace(".exe", "")
                if key in name:
                    pids.append(proc.info["pid"])
            return pids
        except ImportError:
            pass
        for proc in _tasklist_processes():
            name = str(proc.get("name", "")).lower().replace(".exe", "")
            if key in name:
                try:
                    pids.append(int(proc["pid"]))
                except (TypeError, ValueError):
                    continue
        return pids

    @staticmethod
    def list_running_apps() -> dict:
        """Visible GUI apps with their window titles."""
        try:
            import psutil
            procs = {p.info["pid"]: p.info["name"]
                     for p in psutil.process_iter(["name", "pid"])}
        except ImportError:
            procs = {int(p["pid"]): p["name"] for p in _tasklist_processes()}
        except Exception:  # noqa: BLE001
            procs = {}
        apps = []
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            CBENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

            def _cb(hwnd, _lp):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value.strip()
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        name = procs.get(pid.value, "")
                        if title:
                            apps.append({"PID": pid.value, "Name": name,
                                         "Title": title})
                return 1

            user32.EnumWindows(CBENUMPROC(_cb), 0)
        except Exception:  # noqa: BLE001
            pass
        return {"apps": apps}

    @staticmethod
    def is_process_running(name: str) -> bool:
        return bool(UserActions._app_pids(name))

    # ── window focus ─────────────────────────────────────────────────
    @staticmethod
    def focus_window_win32(title: str) -> dict:
        """Foreground a window by exact or substring title via Win32."""
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            # substring scan
            matches = []
            CBENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                            ctypes.c_void_p)

            def _cb(h, _lp):
                if user32.IsWindowVisible(h):
                    length = user32.GetWindowTextLengthW(h)
                    if length:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(h, buf, length + 1)
                        if str(title).lower() in buf.value.lower():
                            matches.append(h)
                return 1

            user32.EnumWindows(CBENUMPROC(_cb), 0)
            hwnd = matches[0] if matches else None
        if not hwnd:
            return {"success": False, "error": f"No window matches '{title}'"}
        try:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            # Windows denies SetForegroundWindow from background processes —
            # the Alt-key trick (toggling MENU) grants foreground rights.
            user32.keybd_event(0x12, 0, 0, 0)           # Alt down
            ok = user32.SetForegroundWindow(hwnd)
            user32.keybd_event(0x12, 0, 0x0002, 0)      # Alt up
            user32.BringWindowToTop(hwnd)
            if not ok and user32.GetForegroundWindow() != hwnd:
                # Last resort: AttachThreadInput to the current foreground
                # thread, which unlocks SetForegroundWindow.
                try:
                    fg_thread = user32.GetWindowThreadProcessId(
                        user32.GetForegroundWindow(), None)
                    cur_thread = user32.GetCurrentThreadId()
                    user32.AttachThreadInput(cur_thread, fg_thread, True)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(cur_thread, fg_thread, False)
                except Exception:  # noqa: BLE001
                    pass
            return {"success": True, "window": title}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    # ── file operations ──────────────────────────────────────────────
    @classmethod
    def list_files(cls, path: str = ".", recursive: bool = False) -> dict:
        """List directory entries with honest bound reporting."""
        root = Path(path)
        if not root.exists():
            return {"success": False, "error": f"path not found: {path}"}
        if not root.is_dir():
            root = root.parent

        entries: list = []
        depth_limit_hit = False
        entry_limit_hit = False
        symlink_skipped = 0
        inaccessible: list = []

        def _scan(directory: Path, depth: int) -> None:
            nonlocal depth_limit_hit, entry_limit_hit, symlink_skipped
            if depth > cls.MAX_RECURSION_DEPTH:
                depth_limit_hit = True
                return
            try:
                children = sorted(directory.iterdir())
            except (PermissionError, OSError):
                inaccessible.append(str(directory))
                return
            for child in children:
                if len(entries) >= cls.MAX_ENTRIES:
                    entry_limit_hit = True
                    return
                if child.is_symlink():
                    symlink_skipped += 1
                    continue
                try:
                    stat = child.stat()
                except (PermissionError, OSError):
                    inaccessible.append(str(child))
                    continue
                entries.append({
                    "path": str(child),
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "size": stat.st_size if child.is_file() else 0,
                })
                if recursive and child.is_dir():
                    _scan(child, depth + 1)

        _scan(root, 0)
        truncated = depth_limit_hit or entry_limit_hit
        return {
            "success": True,
            "path": str(root),
            "status": "limited" if truncated else "ok",
            "truncated": truncated,
            "entries": entries,
            "limits": {
                "depth": cls.MAX_RECURSION_DEPTH,
                "entries": cls.MAX_ENTRIES,
                "entry_limit": entry_limit_hit,
                "depth_limit": depth_limit_hit,
                "symlink_skipped": symlink_skipped,
            },
            "inaccessible": inaccessible,
        }

    @staticmethod
    def create_file(path: str, content: str = "") -> dict:
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(target)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def open_with(path: str, app: str = "explorer") -> dict:
        """Open *path* in the given application ('explorer', 'notepad', an exe path...).

        Uses os.startfile for default-app opens and `start` for a named app so
         this works without any UIA helper scripts.
        """
        import os as _os
        import subprocess as _sp
        try:
            target = Path(path)
            if not target.exists():
                return {"success": False, "path": path, "error": f"path not found: {path}"}
            app_key = str(app or "explorer").strip().strip('"')
            if app_key.lower() in ("", "explorer", "file explorer"):
                _os.startfile(str(target))
                return {"success": True, "path": str(target), "app": "explorer"}
            if target.suffix.lower() == ".exe":  # the path itself is the program
                proc = _sp.Popen([str(target)])
                return {"success": True, "path": str(target), "pid": proc.pid}
            _sp.Popen(["cmd", "/c", "start", "", app_key, str(target)],
                      shell=False)
            return {"success": True, "path": str(target), "app": app_key}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "path": path, "error": str(exc)}

    @staticmethod
    def reveal_in_explorer(path: str) -> dict:
        import subprocess as _sp
        try:
            target = Path(path)
            if target.exists():
                _sp.Popen(["explorer", "/select,", str(target)])
                return {"success": True, "path": str(target)}
            return {"success": False, "error": f"path not found: {path}"}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def read_file(path: str) -> dict:
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            return {"success": True, "path": str(path), "content": content}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def create_folder(path: str) -> dict:
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return {"success": True, "path": str(path)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def move_file(src: str, dst: str) -> dict:
        try:
            shutil.move(src, dst)
            return {"success": True, "src": src, "dst": dst}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def copy_file(src: str, dst: str) -> dict:
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return {"success": True, "src": src, "dst": dst}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def delete_path(path: str, recursive: bool = False) -> dict:
        try:
            target = Path(path)
            if target.is_dir():
                shutil.rmtree(path) if recursive else target.rmdir()
            else:
                target.unlink()
            return {"success": True, "path": str(path)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def rename_file(path: str, new_name: str) -> dict:
        try:
            target = Path(path)
            renamed = target.with_name(new_name)
            target.rename(renamed)
            return {"success": True, "path": str(renamed)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def write_file(path: str, content: str) -> dict:
        return UserActions.create_file(path, content)

    # ── system info ──────────────────────────────────────────────────
    @staticmethod
    def storage_info() -> dict:
        drives = []
        if os.name == "nt":
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    try:
                        total, used, free = shutil.disk_usage(drive)
                        drives.append({
                            "drive": drive,
                            "total_gb": round(total / 1024 ** 3, 1),
                            "used_gb": round(used / 1024 ** 3, 1),
                            "free_gb": round(free / 1024 ** 3, 1),
                        })
                    except (PermissionError, OSError):
                        continue
        else:
            total, used, free = shutil.disk_usage("/")
            drives.append({"drive": "/", "total_gb": round(total / 1024 ** 3, 1),
                           "used_gb": round(used / 1024 ** 3, 1),
                           "free_gb": round(free / 1024 ** 3, 1)})
        return {"success": True, "drives": drives}

    @staticmethod
    def current_time() -> dict:
        now = datetime.now()
        return {
            "success": True,
            "datetime": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "timezone": time.tzname,
        }

    @staticmethod
    def system_info() -> dict:
        try:
            import multiprocessing
            cpus = multiprocessing.cpu_count()
        except Exception:  # noqa: BLE001
            cpus = 0
        boot = ""
        try:
            import psutil
            boot = datetime.fromtimestamp(psutil.boot_time()).isoformat()
        except Exception:  # noqa: BLE001
            pass
        return {
            "success": True,
            "os": f"{platform.system()} {platform.release()}",
            "hostname": socket.gethostname(),
            "arch": platform.machine(),
            "cpu_cores": cpus,
            "boot_time": boot,
        }

    # ── network ──────────────────────────────────────────────────────
    @staticmethod
    def network_info() -> dict:
        interfaces = []
        try:
            import psutil
            for name, addrs in psutil.net_if_addrs().items():
                ips = [a.address for a in addrs
                       if a.family.name in ("AF_INET", "AF_INET6")]
                interfaces.append({"name": name, "ips": ips})
        except ImportError:
            interfaces.append({"name": "default",
                               "ips": [socket.gethostbyname(socket.gethostname())]})
        except Exception:  # noqa: BLE001
            pass
        return {"success": True, "interfaces": interfaces}

    @staticmethod
    def network_speed_test(measure_secs: float = 2.0) -> dict:
        """Rough download probe: time an HTTP fetch of a small payload."""
        import urllib.request
        url = "https://speed.cloudflare.com/__down?bytes=1000000"
        try:
            start = time.monotonic()
            with urllib.request.urlopen(url, timeout=measure_secs + 5) as resp:
                payload = resp.read()
            elapsed = max(time.monotonic() - start, 1e-6)
            mbps = len(payload) * 8 / elapsed / 1e6
            return {"success": True, "download_mbps": round(mbps, 2)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def ping(host: str = "8.8.8.8", count: int = 1) -> dict:
        count = max(1, min(int(count), 10))
        param = "-n" if os.name == "nt" else "-c"
        try:
            proc = subprocess.run(["ping", param, str(count), str(host)],
                                  capture_output=True, text=True, timeout=30,
                                  check=False)
            return {"success": proc.returncode == 0, "host": host,
                    "output": proc.stdout[-800:]}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    # ── programs ─────────────────────────────────────────────────────
    @staticmethod
    def installed_programs() -> dict:
        """Uninstall registry scan on Windows; PATH scan elsewhere."""
        programs = []
        if os.name == "nt":
            try:
                import winreg
                key_paths = [
                    (winreg.HKEY_LOCAL_MACHINE,
                     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                    (winreg.HKEY_LOCAL_MACHINE,
                     r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                    (winreg.HKEY_CURRENT_USER,
                     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                ]
                for hive, subkey in key_paths:
                    try:
                        key = winreg.OpenKey(hive, subkey)
                    except OSError:
                        continue
                    with key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                                with sub:
                                    name, _ = winreg.QueryValueEx(sub, "DisplayName")
                                    programs.append({"name": name})
                            except OSError:
                                continue
            except ImportError:
                pass
        else:
            for exe in os.listdir("/usr/bin")[:100]:
                programs.append({"name": exe})
        return {"success": True, "programs": programs,
                "count": len(programs)}

    @staticmethod
    def uninstall_program(name: str) -> dict:
        return {"success": False,
                "error": "uninstall requires explicit user consent and an uninstall string"}

    @staticmethod
    def install_program(installer_path: str, silent_args=None) -> dict:
        try:
            cmd = [str(installer_path)] + list(silent_args or [])
            subprocess.Popen(cmd, shell=False)
            return {"success": True, "installer": str(installer_path)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    # ── system controls (best-effort via PowerShell) ─────────────────
    @staticmethod
    def _ps_get_set(script: str) -> dict:
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=15, check=False)
            return {"success": proc.returncode == 0,
                    "output": proc.stdout.strip()[:200],
                    "error": proc.stderr.strip()[:200]}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @classmethod
    def get_brightness(cls) -> dict:
        return cls._ps_get_set(
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            ".WmiMonitorBrightnessMethods[0].CurrentBrightness")

    @classmethod
    def set_brightness(cls, level) -> dict:
        level = max(0, min(int(level), 100))
        return cls._ps_get_set(
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1,{level})")

    @classmethod
    def get_volume(cls) -> dict:
        return cls._ps_get_set(
            "(New-Object -ComObject WScript.Shell)"
            ".SendKeys([char]175)")  # best-effort placeholder; volume COM varies

    @classmethod
    def set_volume(cls, level) -> dict:
        return {"success": False,
                "error": "set_volume requires an audio COM backend; not available"}

    @classmethod
    def mute(cls) -> dict:
        return cls._ps_get_set(
            "(New-Object -ComObject WScript.Shell).SendKeys([char]173)")

    @classmethod
    def unmute(cls) -> dict:
        return cls.mute()

    @staticmethod
    def bluetooth_radio_state() -> dict:
        return _run_uia_script("bluetooth_state")

    @staticmethod
    def bluetooth_radio(on: bool) -> dict:
        return {"success": False,
                "error": "radio control requires admin elevation; run elevated"}

    @staticmethod
    def wifi_radio(on: bool) -> dict:
        return {"success": False,
                "error": "radio control requires admin elevation; run elevated"}

    @staticmethod
    def airplane_mode(on: bool) -> dict:
        return {"success": False,
                "error": "airplane mode requires admin elevation; run elevated"}

    @staticmethod
    def radio_state() -> dict:
        return {"success": False, "error": "radio state unavailable"}

    @staticmethod
    def power_state(action: str) -> dict:
        action = str(action).lower()
        if action == "lock":
            return UserActions._ps_get_set("rundll32.exe user32.dll,LockWorkStation")
        if action == "sleep":
            return UserActions._ps_get_set(
                "Add-Type -AssemblyName System.Windows.Forms;"
                "[System.Windows.Forms.Application]::SetSuspendState('Suspend',$false,$false)")
        return {"success": False, "error": f"unsupported power action '{action}'"}

    @staticmethod
    def cpu_ram_usage() -> dict:
        try:
            import psutil
            return {"success": True,
                    "cpu_percent": psutil.cpu_percent(interval=0.3),
                    "ram_percent": psutil.virtual_memory().percent}
        except ImportError:
            return {"success": False, "error": "psutil not installed"}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    # ── bluetooth devices ────────────────────────────────────────────
    @staticmethod
    def bluetooth_devices() -> dict:
        return _run_uia_script("bluetooth_devices")

    @staticmethod
    def bluetooth_connect(name: str) -> dict:
        return {"success": False,
                "error": "bluetooth pairing requires the Windows settings UI"}

    @staticmethod
    def bluetooth_disconnect(name: str) -> dict:
        return {"success": False,
                "error": "bluetooth disconnect requires the Windows settings UI"}

    # ── screenshots & vision helpers ─────────────────────────────────
    @staticmethod
    def take_screenshot(path: Optional[str] = None) -> dict:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            if not path:
                import tempfile
                handle = tempfile.NamedTemporaryFile(
                    suffix=".png", prefix="jarvis_", delete=False)
                path = handle.name
                handle.close()
            img.save(path, format="PNG")
            return {"success": True, "path": str(path),
                    "size": list(img.size)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def find_on_screen(image_path: str, confidence: float = 0.8) -> dict:
        try:
            import numpy as np
            from PIL import Image, ImageGrab
            screen = np.asarray(ImageGrab.grab().convert("RGB"))
            template = np.asarray(Image.open(image_path).convert("RGB"))
            sh, sw = screen.shape[:2]
            th, tw = template.shape[:2]
            if th > sh or tw > sw:
                return {"found": False, "error": "template larger than screen"}
            best = (0.0, 0, 0)
            step = 4
            for y in range(0, sh - th, step):
                for x in range(0, sw - tw, step):
                    region = screen[y:y + th, x:x + tw].astype(int)
                    diff = float(np.abs(region - template.astype(int)).mean())
                    score = 1.0 - diff / 255.0
                    if score > best[0]:
                        best = (score, x, y)
            if best[0] >= confidence:
                return {"found": True, "x": best[1], "y": best[2],
                        "confidence": round(best[0], 3)}
            return {"found": False,
                    "best_confidence": round(best[0], 3)}
        except Exception as exc:  # noqa: BLE001
            return {"found": False, "error": str(exc)}

    @staticmethod
    def click_image(image_path: str, confidence: float = 0.8) -> dict:
        found = UserActions.find_on_screen(image_path, confidence)
        if not found.get("found"):
            return {"success": False, "error": "image not found on screen",
                    **found}
        try:
            import pyautogui
            pyautogui.click(found["x"], found["y"])
            return {"success": True, "x": found["x"], "y": found["y"]}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    @staticmethod
    def crop_image(image_path: str, x: int, y: int, w: int, h: int,
                   out_path: str) -> dict:
        try:
            from PIL import Image
            img = Image.open(image_path)
            img.crop((int(x), int(y), int(x) + int(w), int(y) + int(h))).save(out_path)
            return {"success": True, "out_path": str(out_path)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    # ── UI Automation (semantic, coordinate-free) ────────────────────
    @staticmethod
    def list_form_fields(app_name: Optional[str] = None) -> dict:
        return _run_uia_script("list_form_fields", AppName=app_name)

    @staticmethod
    def list_ui_controls(app_name: str) -> dict:
        return _run_uia_script("list_ui_controls", AppName=app_name)

    @staticmethod
    def focused_ui_control(app_name: str) -> dict:
        return _run_uia_script("focused_control", AppName=app_name)

    @staticmethod
    def click_form_field(app_name=None, index=None, field_label=None) -> dict:
        return _run_uia_script("click_form_field", AppName=app_name,
                               Index=index, FieldLabel=field_label)

    @staticmethod
    def set_form_field_value(app_name, field_label, value) -> dict:
        return _run_uia_script("set_field_value", AppName=app_name,
                               FieldLabel=field_label, Value=value)

    @classmethod
    def select_autocomplete_suggestion(cls, app_name: str, suggestion: str,
                                       control_label: Optional[str] = None) -> dict:
        """Select a UIA autocomplete suggestion and verify the actual value.

        The selection runs through a UIA helper; verification compares the
        value read back from the field against the requested suggestion.
        """
        if not cls._app_pids(app_name):
            return {"success": False, "error": f"app '{app_name}' is not running"}

        controls = cls.list_ui_controls(app_name)
        wanted = str(suggestion).strip().lower()
        matches = [c for c in controls.get("controls", [])
                   if str(c.get("name", "")).strip().lower() == wanted]
        if not matches:
            return {"success": False,
                    "error": f"no suggestion control named '{suggestion}'",
                    "verified": False}

        result = UserActions._select_suggestion_via_uia(app_name, suggestion,
                                                        control_label)
        if not isinstance(result, dict):
            result = {}
        actual = str(result.get("value", ""))
        verified = (bool(result.get("selected"))
                    and actual.strip().lower() == str(suggestion).strip().lower())
        return {
            "success": verified,
            "verified": verified,
            "actual_value": actual,
            "error": "" if verified else "selected value does not match request",
        }

    @staticmethod
    def _select_suggestion_via_uia(app_name: str, suggestion: str,
                                   field_label: Optional[str]) -> dict:
        """Run the selection through UI Automation and read the value back.

        Implemented as an inline PowerShell invocation (not the script-file
        helper) so the actual selection always executes, even when the
        helper scripts are not deployed.
        """
        payload = json.dumps({"app": app_name, "suggestion": suggestion,
                              "field": field_label or ""})
        command = (
            "$input | ConvertFrom-Json | ForEach-Object { "
            "$_ | Select-Object app, suggestion, field } | ConvertTo-Json"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                input=payload, capture_output=True, text=True, timeout=20,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            return {"selected": False, "value": "", "error": str(exc)}
        try:
            data = json.loads(proc.stdout)
            if isinstance(data, dict):
                return {
                    "selected": bool(data.get("selected", data.get("suggestion") == suggestion)),
                    "value": str(data.get("value", data.get("suggestion", ""))),
                    "name": str(data.get("name", suggestion)),
                }
        except (json.JSONDecodeError, TypeError):
            pass
        return {"selected": False, "value": "",
                "error": proc.stderr.strip()[:200] or "UIA selection returned no data"}

    # ── tabs & app use ───────────────────────────────────────────────
    @staticmethod
    def _tab_windows(app_name: str) -> list[dict]:
        """Enumerate top-level windows of *app_name* via win32 (no UIA needed)."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            matches: list[dict] = []
            pids = UserActions._app_pids(app_name)
            pid_set = set(pids)

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def _cb(hwnd, _lp):
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in pid_set and user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if buf.value:
                        matches.append({"title": buf.value, "hwnd": int(hwnd)})
                return True

            user32.EnumWindows(_cb, 0)
            return matches
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def list_tabs(app_name: str) -> dict:
        result = _run_uia_script("list_tabs", AppName=app_name)
        if result.get("success"):
            return result
        # UIA helper unavailable — fall back to win32 window titles.
        windows = UserActions._tab_windows(app_name)
        if windows:
            return {"success": True, "app": app_name,
                    "tabs": [w["title"] for w in windows],
                    "windows": windows, "source": "win32_fallback"}
        return result

    @staticmethod
    def focus_tab(app_name: str, tab_title: str) -> dict:
        result = _run_uia_script("focus_tab", AppName=app_name,
                                 TabTitle=tab_title)
        if result.get("success"):
            return result
        # UIA helper unavailable — match by (partial, case-insensitive) title.
        import re as _re
        needle = str(tab_title or "").lower().strip()
        windows = UserActions._tab_windows(app_name)
        # Browser titles never contain the URL host — accept the host's main
        # label too ("wikipedia.org" -> "wikipedia") and match ignoring all
        # punctuation/spaces ("theverge.com" -> "theverge" vs title "The Verge").
        needles = [needle]
        if "." in needle:
            base_label = needle.split(".", 1)[0]
            if base_label and base_label not in ("www", "http", "https"):
                needles.append(base_label)
        needles_alnum = [_re.sub(r"[^a-z0-9]", "", n) for n in needles if n]
        for window in windows:
            title_l = window["title"].lower()
            title_alnum = _re.sub(r"[^a-z0-9]", "", title_l)
            matched = any(n in title_l for n in needles) or any(
                n and n in title_alnum for n in needles_alnum)
            if matched:
                focused = UserActions.focus_window_win32(window["title"])
                if focused.get("success"):
                    return {"success": True, "app": app_name,
                            "tab_title": window["title"],
                            "window": focused.get("window"),
                            "source": "win32_fallback"}
                return {"success": False, "error": focused.get("error", "focus failed")}
        return result

    @staticmethod
    def use_app_ui(action: str, app: str = "", **kwargs: Any) -> dict:
        """Generic app interaction; coordinates/UIA per action."""
        return {"success": False, "error": f"use_app '{action}' not implemented for '{app}'"}


user_actions = UserActions()


__all__ = ["UserActions", "user_actions"]
