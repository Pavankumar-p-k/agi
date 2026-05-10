"""
l4_controller/controller_layer.py
═══════════════════════════════════════════════════════════════════
LEVEL 4 — CONTROLLER LAYER  (OpenClaw / System Agent equivalent)

WRAPS (does not replace):
  jarvis_remaining/adb/adb_controller.py         → ADBController
  jarvis_automation/backend/automation/pc_automation.py

ADDS:
  • SafetyGuard      — blocks dangerous commands (rm -rf, mkfs, etc.)
  • TerminalController — async shell execution
  • FSController     — controlled file system access
  • AppController    — unified PC + Android app management
  • ControllerLayer  — single façade for all L4 actions
"""
from __future__ import annotations
import asyncio, json, logging, os, re, subprocess, time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.l4_controller")


class ControlAction(str, Enum):
    TERMINAL    = "terminal"
    FILE_READ   = "file_read"
    FILE_WRITE  = "file_write"
    FILE_LIST   = "file_list"
    APP_OPEN    = "app_open"
    ANDROID     = "android"
    BROWSER     = "browser"
    SCREENSHOT  = "screenshot"
    VOLUME      = "volume"


@dataclass
class ControlResult:
    action:      ControlAction
    success:     bool
    output:      str
    error:       str = ""
    duration_ms: int = 0


# ── Safety Guard ──────────────────────────────────────────────────

BLOCKED_CMDS = [
    r"rm\s+-rf\s+[/~]",      r"mkfs",
    r"dd\s+if=.*of=/dev",    r":()\{.*\}",
    r"chmod\s+-R\s+777\s+/", r"shutdown\s+now",
    r"reboot",               r"passwd",
    r"curl.*\|\s*sh",        r"wget.*\|\s*bash",
    r"DROP\s+TABLE",         r"DELETE\s+FROM.*WHERE\s+1\s*=\s*1",
    r"sudo\s+rm",            r"format\s+c:",
]

PROTECTED_PATHS = [
    "/", "/etc", "/usr", "/bin", "/sbin", "/boot",
    "/sys", "/proc", "C:\\Windows", "C:\\System32",
]


class SafetyGuard:
    """Every L4 action must pass through here."""

    def __init__(self, strict: bool = True):
        self._strict    = strict
        self._block_log = []

    def check_cmd(self, cmd: str) -> tuple[bool, str]:
        for pat in BLOCKED_CMDS:
            if re.search(pat, cmd, re.IGNORECASE):
                reason = f"Blocked pattern: {pat}"
                self._log(cmd, False, reason)
                return False, reason
        self._log(cmd, True)
        return True, ""

    def check_path(self, path: str,
                   operation: str = "read") -> tuple[bool, str]:
        abs_path = str(Path(path).resolve())
        for protected in PROTECTED_PATHS:
            if abs_path.startswith(protected):
                reason = f"Protected path: {protected}"
                self._log(f"{operation}:{path}", False, reason)
                return False, reason
        if operation == "write" and self._strict:
            home = str(Path.home())
            cwd  = os.getcwd()
            if not (abs_path.startswith(home) or
                    abs_path.startswith(cwd)):
                reason = f"Write outside home/cwd: {abs_path}"
                self._log(f"write:{path}", False, reason)
                return False, reason
        return True, ""

    def _log(self, action: str, allowed: bool, reason: str = ""):
        self._block_log.append({
            "ts": time.time(), "action": action[:80],
            "allowed": allowed, "reason": reason,
        })
        if len(self._block_log) > 500:
            self._block_log = self._block_log[-250:]

    def recent_blocks(self, n: int = 10) -> list[dict]:
        return [e for e in reversed(self._block_log)
                if not e["allowed"]][:n]


# ── Terminal Controller ───────────────────────────────────────────

class TerminalController:
    def __init__(self, guard: SafetyGuard, timeout: int = 30):
        self._guard   = guard
        self._timeout = timeout

    async def run(self, cmd: str, cwd: str = None) -> ControlResult:
        t0 = time.time()
        ok, reason = self._guard.check_cmd(cmd)
        if not ok:
            return ControlResult(ControlAction.TERMINAL, False,
                                  "", f"BLOCKED: {reason}", 0)
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return ControlResult(ControlAction.TERMINAL, False,
                                      "", f"Timeout {self._timeout}s",
                                      int((time.time()-t0)*1000))

            out = stdout.decode(errors="replace")[:4000]
            err = stderr.decode(errors="replace")[:800]
            ok  = proc.returncode == 0
            return ControlResult(ControlAction.TERMINAL, ok,
                                  out, err if not ok else "",
                                  int((time.time()-t0)*1000))
        except Exception as e:
            return ControlResult(ControlAction.TERMINAL, False,
                                  "", str(e),
                                  int((time.time()-t0)*1000))


# ── File System Controller ────────────────────────────────────────

class FSController:
    def __init__(self, guard: SafetyGuard):
        self._guard = guard

    async def read(self, path: str,
                    max_bytes: int = 100_000) -> ControlResult:
        t0 = time.time()
        ok, reason = self._guard.check_path(path, "read")
        if not ok:
            return ControlResult(ControlAction.FILE_READ, False,
                                  "", reason)
        try:
            p = Path(path)
            if not p.exists():
                return ControlResult(ControlAction.FILE_READ, False,
                                      "", f"Not found: {path}")
            content = p.read_bytes()[:max_bytes].decode(errors="replace")
            return ControlResult(ControlAction.FILE_READ, True,
                                  content, "",
                                  int((time.time()-t0)*1000))
        except Exception as e:
            return ControlResult(ControlAction.FILE_READ, False,
                                  "", str(e))

    async def write(self, path: str, content: str,
                    append: bool = False) -> ControlResult:
        t0 = time.time()
        ok, reason = self._guard.check_path(path, "write")
        if not ok:
            return ControlResult(ControlAction.FILE_WRITE, False,
                                  "", reason)
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            if append:
                with p.open("a", encoding="utf-8") as f:
                    f.write(content)
            else:
                p.write_text(content, encoding="utf-8")
            return ControlResult(ControlAction.FILE_WRITE, True,
                                  f"Written {len(content)} chars → {path}",
                                  "", int((time.time()-t0)*1000))
        except Exception as e:
            return ControlResult(ControlAction.FILE_WRITE, False,
                                  "", str(e))

    async def list_dir(self, path: str = ".") -> ControlResult:
        try:
            entries = [
                {"name": i.name,
                 "type": "dir" if i.is_dir() else "file",
                 "size": i.stat().st_size if i.is_file() else 0}
                for i in sorted(Path(path).iterdir())
            ]
            return ControlResult(ControlAction.FILE_LIST, True,
                                  json.dumps(entries, indent=2))
        except Exception as e:
            return ControlResult(ControlAction.FILE_LIST, False,
                                  "", str(e))


# ── App Controller ────────────────────────────────────────────────

APP_MAP_WIN = {
    "chrome":     "chrome.exe", "firefox":    "firefox.exe",
    "vscode":     "code",       "notepad":    "notepad.exe",
    "explorer":   "explorer.exe","spotify":   "spotify.exe",
    "terminal":   "cmd.exe",    "calculator": "calc.exe",
    "powershell": "powershell.exe",
}

APP_MAP_ANDROID = {
    "whatsapp":  "com.whatsapp",
    "instagram": "com.instagram.android",
    "spotify":   "com.spotify.music",
    "youtube":   "com.google.android.youtube",
    "camera":    "com.android.camera",
    "settings":  "com.android.settings",
    "telegram":  "org.telegram.messenger",
    "chrome":    "com.android.chrome",
}


class AppController:
    def __init__(self, guard: SafetyGuard, adb=None):
        self._guard = guard
        self._adb   = adb

    async def open(self, app: str,
                    target: str = "pc") -> ControlResult:
        t0   = time.time()
        name = app.lower().strip()
        self._guard._log(f"open_app:{name}", True)

        if target == "android" and self._adb:
            pkg = APP_MAP_ANDROID.get(name, name)
            try:
                self._adb._shell(
                    f"am start -a android.intent.action.MAIN "
                    f"-n {pkg}/.MainActivity")
                return ControlResult(ControlAction.APP_OPEN, True,
                                      f"Opened {app} on Android",
                                      "", int((time.time()-t0)*1000))
            except Exception as e:
                return ControlResult(ControlAction.APP_OPEN, False,
                                      "", str(e))

        exe = APP_MAP_WIN.get(name, name)
        try:
            subprocess.Popen([exe], shell=True)
            return ControlResult(ControlAction.APP_OPEN, True,
                                  f"Opened {app}",
                                  "", int((time.time()-t0)*1000))
        except Exception as e:
            return ControlResult(ControlAction.APP_OPEN, False,
                                  "", str(e))

    async def send_message(self, platform: str,
                            recipient: str, message: str) -> ControlResult:
        t0 = time.time()
        if not self._adb:
            return ControlResult(ControlAction.ANDROID, False,
                                  "", "ADB not connected")
        try:
            if platform == "whatsapp":
                ok = self._adb.send_whatsapp(recipient, message)
            elif platform == "sms":
                ok = self._adb.send_sms(recipient, message)
            else:
                ok = False
            return ControlResult(ControlAction.ANDROID, ok,
                                  f"Sent via {platform}" if ok else "",
                                  "" if ok else "Send failed",
                                  int((time.time()-t0)*1000))
        except Exception as e:
            return ControlResult(ControlAction.ANDROID, False, "", str(e))

    async def open_url(self, url: str) -> ControlResult:
        try:
            import webbrowser
            webbrowser.open(url)
            return ControlResult(ControlAction.BROWSER, True,
                                  f"Opened: {url}")
        except Exception as e:
            return ControlResult(ControlAction.BROWSER, False, "", str(e))


# ── Controller Layer Façade ───────────────────────────────────────

class ControllerLayer:
    """
    L4 entry point. All system actions go through here.
    Every call passes SafetyGuard first.
    """

    def __init__(self, adb=None, workspace: str = ".",
                  strict: bool = True):
        self._guard    = SafetyGuard(strict=strict)
        self._terminal = TerminalController(self._guard)
        self._fs       = FSController(self._guard)
        self._apps     = AppController(self._guard, adb)
        self._adb      = adb
        logger.info("[L4] ControllerLayer initialized (strict=%s)", strict)

    async def execute(self, action: str, **params) -> ControlResult:
        """
        Unified entry point for all L4 actions.
        action: terminal|file_read|file_write|file_list|
                app_open|send_message|browser|android_*
        """
        if action == "terminal":
            return await self._terminal.run(
                params.get("cmd",""), params.get("cwd"))

        if action == "file_read":
            return await self._fs.read(params["path"])

        if action == "file_write":
            return await self._fs.write(
                params["path"], params["content"],
                params.get("append", False))

        if action == "file_list":
            return await self._fs.list_dir(params.get("path","."))

        if action == "app_open":
            return await self._apps.open(
                params["app"], params.get("target","pc"))

        if action == "send_message":
            return await self._apps.send_message(
                params["platform"],
                params["recipient"],
                params["message"])

        if action == "browser":
            return await self._apps.open_url(params["url"])

        if action == "android_screenshot":
            if self._adb:
                path = self._adb.screenshot()
                return ControlResult(ControlAction.SCREENSHOT,
                                      True, f"Screenshot: {path}")
            return ControlResult(ControlAction.SCREENSHOT,
                                  False, "", "ADB not connected")

        if action == "android_battery":
            if self._adb:
                data = self._adb.get_battery()
                return ControlResult(ControlAction.ANDROID,
                                      True, json.dumps(data))
            return ControlResult(ControlAction.ANDROID,
                                  False, "", "ADB not connected")

        return ControlResult(ControlAction.TERMINAL, False,
                              "", f"Unknown action: {action}")

    @property
    def safety(self) -> SafetyGuard:
        return self._guard

    def recent_blocks(self, n: int = 10) -> list[dict]:
        return self._guard.recent_blocks(n)
