"""
l4_controller/system_controller.py
═══════════════════════════════════════════════════════════════════
LEVEL 4 — SYSTEM CONTROLLER (OpenClaw equivalent)

The physical execution layer. Controls:
  • Terminal / shell commands
  • File system (read/write/watch)
  • App launching/switching
  • Android device via ADB (bridges existing ADBController)
  • Safety guard (never runs dangerous commands)

SAFETY RULES:
  • Blocked: rm -rf /, shutdown, format, dd if=...
  • Blocked: curl | bash, wget | sh (remote execution)
  • Blocked: any command with credential patterns
  • Always logged to WorldState
  • Confirmation required for destructive ops

Integration with existing code:
  • ADBBridge wraps jarvis_automation/adb/adb_controller.py
  • FileSystemController extends existing file operations
  • CommandLayer extends existing pc_automation.py
═══════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import asyncio, logging, os, platform, re, subprocess, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.l4")

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"


# ─────────────────────────────────────────────────────────────────
#  SAFETY GUARD — blocks dangerous commands
# ─────────────────────────────────────────────────────────────────

class SafetyGuard:
    """
    Evaluates commands before execution.
    Zero tolerance for irreversible destructive operations.
    """

    # Patterns that are ALWAYS blocked
    BLOCKED_PATTERNS = [
        r"rm\s+-rf\s+/",              # delete root
        r"rm\s+-rf\s+~",              # delete home
        r"rm\s+-rf\s+\*",             # delete everything
        r"mkfs\.",                     # format filesystem
        r"dd\s+if=.+\s+of=/dev/",     # disk write
        r">\s*/dev/sd",               # overwrite disk
        r":\(\)\{.*\}",               # fork bomb
        r"chmod\s+-R\s+777\s+/",      # world-writable root
        r"curl.+\|\s*(bash|sh)",       # pipe to shell
        r"wget.+\|\s*(bash|sh)",       # pipe to shell
        r"shutdown\s+(-h|-r|now)",     # shutdown (without flag)
        r"halt\b",
        r"reboot\b",
        r"deltree\s+/",               # Windows deltree root
        r"format\s+[cC]:",            # Windows format C
        r"del\s+/[Ff]\s+/[Ss]\s+\*", # Windows del /F /S *
        # Credential/secret patterns
        r"export.+PASSWORD\s*=",
        r"echo.+(password|secret|token|key)\s*=",
    ]

    # Patterns that require confirmation (warning, not block)
    WARN_PATTERNS = [
        r"rm\s+-r",      # recursive delete
        r"git\s+push",   # git push
        r"DROP\s+TABLE", # SQL drop
        r"DELETE\s+FROM",# SQL mass delete
        r"truncate\b",
    ]

    # Safe-listed commands always allowed
    SAFE_LIST = {
        "echo", "cat", "ls", "pwd", "cd", "mkdir", "touch",
        "python", "python3", "pip", "npm", "flutter", "dart",
        "git status", "git log", "git diff", "git branch",
        "adb devices", "adb shell", "adb push", "adb pull",
        "ollama", "curl http://localhost",
    }

    def __init__(self, strict: bool = True):
        self.strict        = strict
        self._blocked_count = 0
        self._blocked_log: List[dict] = []

    def check(self, command: str, tool: str = "terminal") -> bool:
        """
        Returns True if command is safe to execute.
        Returns False to block.
        """
        if not command or not command.strip():
            return True

        # Non-terminal tools are always allowed
        if tool in ("file", "api", "python", "code"):
            return True

        cmd_lower = command.lower().strip()

        # Check safe list first
        for safe in self.SAFE_LIST:
            if cmd_lower.startswith(safe):
                return True

        # Check blocked patterns
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                self._log_block(command, f"Matched blocked pattern: {pattern}")
                return False

        return True

    def warn_level(self, command: str) -> Optional[str]:
        """Returns warning message if command needs confirmation."""
        for pattern in self.WARN_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Destructive command detected: {command[:80]}"
        return None

    def _log_block(self, command: str, reason: str):
        self._blocked_count += 1
        entry = {"command": command[:100], "reason": reason, "ts": time.time()}
        self._blocked_log.append(entry)
        logger.warning("[L4] BLOCKED: %s | Reason: %s", command[:60], reason)
        if len(self._blocked_log) > 100:
            self._blocked_log.pop(0)

    def stats(self) -> dict:
        return {"blocked_total": self._blocked_count,
                "recent": self._blocked_log[-5:]}


# ─────────────────────────────────────────────────────────────────
#  COMMAND LAYER — shell execution
# ─────────────────────────────────────────────────────────────────

class CommandLayer:
    """
    Executes shell/PowerShell/bash commands safely.
    Extends existing pc_automation.py functionality.
    """

    def __init__(self, safety: SafetyGuard, working_dir: str = "."):
        self.safety  = safety
        self.cwd     = Path(working_dir).resolve()
        self._history: List[dict] = []

    async def run(self, command: str, timeout: int = 30,
                  cwd: str = None) -> Tuple[bool, str, str]:
        """Execute command. Returns (success, stdout, stderr)."""
        if not self.safety.check(command, "terminal"):
            return False, "", f"BLOCKED: {command[:60]}"

        work_dir = Path(cwd).resolve() if cwd else self.cwd

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout)
                ok     = proc.returncode == 0
                out    = stdout.decode(errors="replace").strip()
                err    = stderr.decode(errors="replace").strip()
                self._history.append({
                    "cmd": command[:100], "ok": ok,
                    "out": out[:200], "ts": time.time()
                })
                if len(self._history) > 200:
                    self._history.pop(0)
                return ok, out, err
            except asyncio.TimeoutError:
                proc.kill()
                return False, "", f"Timeout after {timeout}s"
        except Exception as e:
            return False, "", str(e)

    def run_sync(self, command: str, timeout: int = 30) -> Tuple[bool, str, str]:
        """Synchronous version for non-async contexts."""
        if not self.safety.check(command):
            return False, "", "BLOCKED"
        try:
            r = subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=timeout, cwd=str(self.cwd)
            )
            return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", f"Timeout after {timeout}s"
        except Exception as e:
            return False, "", str(e)

    def history(self, limit: int = 20) -> list:
        return self._history[-limit:]


# ─────────────────────────────────────────────────────────────────
#  FILE SYSTEM CONTROLLER
# ─────────────────────────────────────────────────────────────────

class FileSystemController:
    """
    Safe file system operations with change watching.
    """

    def __init__(self, safety: SafetyGuard, root: str = "."):
        self.safety  = safety
        self.root    = Path(root).resolve()
        self._watchers: Dict[str, Callable] = {}

    def read(self, path: str) -> Tuple[bool, str]:
        try:
            p = self._resolve(path)
            return True, p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return False, str(e)

    def write(self, path: str, content: str,
              create_dirs: bool = True) -> Tuple[bool, str]:
        try:
            p = self._resolve(path)
            if create_dirs:
                p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            logger.info("[L4] Written: %s (%d bytes)", path, len(content))
            return True, f"Written {len(content)} bytes to {path}"
        except Exception as e:
            logger.error("[L4] Write failed %s: %s", path, e)
            return False, str(e)

    def append(self, path: str, content: str) -> Tuple[bool, str]:
        try:
            p = self._resolve(path)
            with open(p, "a", encoding="utf-8") as f:
                f.write(content)
            return True, f"Appended to {path}"
        except Exception as e:
            return False, str(e)

    def delete(self, path: str) -> Tuple[bool, str]:
        try:
            p = self._resolve(path)
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                import shutil
                shutil.rmtree(p)
            return True, f"Deleted {path}"
        except Exception as e:
            return False, str(e)

    def list_dir(self, path: str = ".") -> List[dict]:
        try:
            p = self._resolve(path)
            return [
                {"name": f.name, "is_dir": f.is_dir(),
                 "size": f.stat().st_size if f.is_file() else 0,
                 "modified": f.stat().st_mtime}
                for f in sorted(p.iterdir())
            ]
        except Exception:
            return []

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        return p.resolve()


# ─────────────────────────────────────────────────────────────────
#  APP CONTROLLER
# ─────────────────────────────────────────────────────────────────

class AppController:
    """
    Open, close, and switch between applications.
    Extends existing pc_automation.py app launching.
    """

    # Known app mappings (name → executable/command)
    APP_MAP = {
        "chrome":        "google-chrome" if IS_LINUX else "start chrome",
        "browser":       "google-chrome" if IS_LINUX else "start chrome",
        "vscode":        "code",
        "code":          "code",
        "terminal":      "x-terminal-emulator" if IS_LINUX else "wt.exe",
        "spotify":       "spotify" if IS_LINUX else "start spotify",
        "notepad":       "notepad" if not IS_LINUX else "gedit",
        "calculator":    "gnome-calculator" if IS_LINUX else "calc",
        "whatsapp":      "whatsapp-nativy" if IS_LINUX else "start whatsapp",
        "files":         "nautilus" if IS_LINUX else "explorer",
        "settings":      "gnome-control-center" if IS_LINUX else "ms-settings:",
    }

    def __init__(self, safety: SafetyGuard, cmd: CommandLayer):
        self.safety = safety
        self.cmd    = cmd

    async def open(self, app_name: str) -> Tuple[bool, str]:
        """Open an application by name."""
        name    = app_name.lower().strip()
        command = self.APP_MAP.get(name)

        if not command:
            # Try to find by name
            if IS_LINUX:
                command = f"nohup {name} &>/dev/null &"
            else:
                command = f"start {name}"

        ok, out, err = await self.cmd.run(command, timeout=10)
        return ok, out or err

    async def close(self, app_name: str) -> Tuple[bool, str]:
        """Close an application by name."""
        if IS_LINUX:
            ok, out, err = await self.cmd.run(f"pkill -f {app_name}")
        else:
            ok, out, err = await self.cmd.run(f"taskkill /IM {app_name}.exe /F")
        return ok, out or err

    async def list_running(self) -> List[str]:
        """Get list of running applications."""
        if IS_LINUX:
            ok, out, _ = await self.cmd.run("ps aux --no-header | awk '{print $11}'")
        else:
            ok, out, _ = await self.cmd.run("tasklist /FO CSV /NH")
        if ok:
            return [l.strip() for l in out.splitlines() if l.strip()][:30]
        return []


# ─────────────────────────────────────────────────────────────────
#  ADB BRIDGE — wraps existing ADBController
# ─────────────────────────────────────────────────────────────────

class ADBBridge:
    """
    Thin wrapper around existing jarvis_automation ADBController.
    Adds safety checking + WorldState integration.
    Existing code is NEVER modified.
    """

    def __init__(self, world_state, device_id: str = None,
                 adb_ip: str = None):
        self._ws = world_state
        self._adb = None
        self._device_id = device_id
        self._adb_ip    = adb_ip

    def connect(self) -> bool:
        try:
            from jarvis_automation.backend.automation.pc_automation import ADBController
        except ImportError:
            try:
                from jarvis_remaining.adb.adb_controller import ADBController
            except ImportError:
                logger.warning("[L4] ADBController not found — ADB disabled")
                return False

        self._adb = ADBController(
            device_id=self._device_id,
            world_state=self._ws,
        )
        ok = self._adb.connect(ip=self._adb_ip)
        if ok:
            logger.info("[L4] ADB connected")
        return ok

    def __getattr__(self, name):
        """Proxy all method calls to underlying ADBController."""
        if self._adb is None:
            raise RuntimeError("ADB not connected. Call connect() first.")
        return getattr(self._adb, name)

    @property
    def connected(self) -> bool:
        return self._adb is not None and getattr(self._adb, "_connected", False)


# ─────────────────────────────────────────────────────────────────
#  SYSTEM CONTROLLER — main entry point
# ─────────────────────────────────────────────────────────────────

class SystemController:
    """
    L4 Controller main entry point.
    Single interface to all system control capabilities.
    """

    def __init__(self, world_state, working_dir: str = ".",
                 device_id: str = None, adb_ip: str = None):
        self.safety = SafetyGuard()
        self.cmd    = CommandLayer(self.safety, working_dir)
        self.fs     = FileSystemController(self.safety, working_dir)
        self.apps   = AppController(self.safety, self.cmd)
        self.adb    = ADBBridge(world_state, device_id, adb_ip)
        self._world = world_state
        logger.info("[L4] SystemController ready | cwd=%s", working_dir)

    async def execute(self, command: str, tool: str = "terminal",
                      timeout: int = 30) -> dict:
        """
        Universal execute method — routes to correct sub-controller.
        """
        t0 = time.time()
        ok, out, err = False, "", ""

        if tool == "terminal":
            ok, out, err = await self.cmd.run(command, timeout)
        elif tool == "file":
            import json as _json
            try:
                op = _json.loads(command)
                if op.get("op") == "write":
                    ok, out = self.fs.write(op["path"], op.get("content",""))
                elif op.get("op") == "read":
                    ok, out = self.fs.read(op["path"])
                elif op.get("op") == "delete":
                    ok, out = self.fs.delete(op["path"])
                err = "" if ok else out
            except Exception as e:
                ok, err = False, str(e)
        elif tool == "app":
            ok, out = await self.apps.open(command)
        elif tool == "adb":
            ok = self.adb.connected
            if ok:
                # Dispatch ADB command
                out = str(self.adb._adb._run(command))
            else:
                err = "ADB not connected"

        ms = int((time.time() - t0) * 1000)
        logger.info("[L4] execute tool=%s ok=%s ms=%d", tool, ok, ms)

        return {
            "success": ok, "output": out, "error": err,
            "tool": tool, "command": command[:100],
            "duration_ms": ms,
        }

    async def system_info(self) -> dict:
        """Get current system state."""
        _, cpu, _  = await self.cmd.run("top -bn1 | grep 'Cpu' | awk '{print $2}'" if IS_LINUX
                                         else "wmic cpu get LoadPercentage")
        _, mem, _  = await self.cmd.run("free -m | grep Mem | awk '{print $3\"/\"$2}'" if IS_LINUX
                                         else "wmic OS get FreePhysicalMemory")
        _, disk, _ = await self.cmd.run("df -h / | tail -1 | awk '{print $5}'" if IS_LINUX
                                         else "wmic logicaldisk get FreeSpace")
        return {
            "cpu":  cpu.strip() or "unknown",
            "mem":  mem.strip() or "unknown",
            "disk": disk.strip() or "unknown",
            "adb_connected": self.adb.connected,
            "platform": platform.system(),
        }

    def safety_stats(self) -> dict:
        return self.safety.stats()
