"""Setup engine — first-run wizard, resume support and live status probes.

Rebuilt in STEP 4 against the pinned specs:

* ``tests/cli/test_commands.py::TestDoctor``  -> ``SetupEngine().status()`` must
  return ``phase`` / ``recommended_model`` / ``hardware`` / ``checks``.
* ``tests/cli/test_commands.py::TestSetup``   -> ``run_full_setup(...)`` must
  return without crashing and report a truthful bool.
* ``jarvis.py``                               -> ``SetupEngine().resume_needed()``
  gates the first-run banner; an interrupted wizard must be resumable.

Nothing here reports success it did not achieve: ``run_full_setup`` returns
``True`` only after the state file has been written with ``phase == "complete"``,
and ``status()`` re-reads that file rather than trusting a constant.  Every
check value is the outcome of a real probe (import, executable lookup, HTTP
ping) — a missing dependency surfaces as ``missing``/``failed``, never as ``ok``.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

JARVIS_DIR = Path.home() / ".jarvis"
SETUP_STATE_PATH = JARVIS_DIR / "setup_state.json"
CONFIG_PATH = JARVIS_DIR / "config.json"

PHASES = ("not_started", "in_progress", "complete", "failed")


def _read_state() -> dict[str, Any]:
    """Load persisted setup state; missing/corrupt file == not started."""
    try:
        if SETUP_STATE_PATH.exists():
            data = json.loads(SETUP_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("phase") in PHASES:
                return data
    except (OSError, ValueError) as exc:  # corrupt state must not crash the CLI
        logger.warning("setup state unreadable (%s) — treating as not started", exc)
    return {"phase": "not_started", "checks": {}}


def _write_state(state: dict[str, Any]) -> bool:
    """Persist setup state atomically. Returns False if it did not land."""
    try:
        JARVIS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETUP_STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        tmp.replace(SETUP_STATE_PATH)
        return SETUP_STATE_PATH.exists()
    except OSError as exc:
        logger.error("could not persist setup state: %s", exc)
        return False


def _ram_gb() -> float:
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:  # noqa: BLE001 — psutil optional
        try:
            if platform.system() == "Windows":
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                return round(stat.ullTotalPhys / (1024 ** 3), 1)
        except Exception:  # noqa: BLE001
            pass
    return 0.0


def _gpu_name() -> Optional[str]:
    """Best-effort GPU detection; None means genuinely no GPU found."""
    if platform.system() == "Windows":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_VideoController).Name"],
                capture_output=True, text=True, timeout=15,
            )
            names = [n.strip() for n in (out.stdout or "").splitlines() if n.strip()]
            if names:
                return ", ".join(dict.fromkeys(names))
        except (OSError, subprocess.SubprocessError):
            pass
    for exe in ("nvidia-smi",):
        path = shutil.which(exe)
        if path:
            try:
                out = subprocess.run([exe, "--query-gpu=name", "--format=csv,noheader"],
                                     capture_output=True, text=True, timeout=10)
                names = [n.strip() for n in (out.stdout or "").splitlines() if n.strip()]
                if names:
                    return ", ".join(names)
            except (OSError, subprocess.SubprocessError):
                pass
    return None


def _probe_ollama(timeout: float = 2.5) -> tuple[bool, list[str]]:
    """Ping the local Ollama server and list its models. Real HTTP round trip."""
    url = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if not url.startswith("http"):
        url = "http://" + url
    try:
        with urllib.request.urlopen(url + "/api/tags", timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name", "") for m in payload.get("models", [])]
        return True, [m for m in models if m]
    except Exception:  # noqa: BLE001 — server down is a valid answer
        return False, []


def _pick_model(available: list[str]) -> str:
    """Choose the default model from what is *actually* installed."""
    if not available:
        return "ollama/qwen2.5-coder:3b"  # documented default when none present
    for preferred in ("qwen2.5-coder", "qwen", "llama3", "llama", "mistral"):
        for name in available:
            base = name.split(":")[0]
            if preferred in base:
                return f"ollama/{name}"
    return f"ollama/{available[0]}"


class SetupEngine:
    """Runs and reports on the first-run setup wizard."""

    def __init__(self, state_path: Optional[Path] = None) -> None:
        self._state_path = Path(state_path) if state_path else SETUP_STATE_PATH

    # ------------------------------------------------------------- state
    def _load(self) -> dict[str, Any]:
        if self._state_path == SETUP_STATE_PATH:
            return _read_state()
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("phase") in PHASES:
                    return data
        except (OSError, ValueError):
            pass
        return {"phase": "not_started", "checks": {}}

    def _save(self, state: dict[str, Any]) -> bool:
        if self._state_path == SETUP_STATE_PATH:
            return _write_state(state)
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(state, indent=2, default=str),
                                        encoding="utf-8")
            return self._state_path.exists()
        except OSError as exc:
            logger.error("could not persist setup state: %s", exc)
            return False

    def resume_needed(self) -> bool:
        """True only when a wizard was started and never finished."""
        return self._load().get("phase") == "in_progress"

    def is_configured(self) -> bool:
        return self._load().get("phase") == "complete"

    # ------------------------------------------------------------- probes
    def _run_checks(self) -> dict[str, str]:
        """Live probes. Value is 'ok' | 'missing' | 'failed' — never assumed."""
        checks: dict[str, str] = {}

        # Python interpreter
        checks["python"] = "ok" if sys.version_info >= (3, 10) else "failed"

        # CLI config written by a previous wizard run
        checks["config"] = "ok" if CONFIG_PATH.exists() else "missing"

        # Ollama server reachable
        ollama_ok, _models = _probe_ollama()
        checks["ollama"] = "ok" if ollama_ok else "missing"

        # Playwright browser automation stack
        try:
            import playwright  # noqa: F401
            checks["playwright"] = "ok"
        except ImportError:
            checks["playwright"] = "missing"

        # Provider SDKs (optional, reported honestly)
        for label, mod in (("openai_sdk", "openai"), ("anthropic_sdk", "anthropic")):
            try:
                __import__(mod)
                checks[label] = "ok"
            except ImportError:
                checks[label] = "missing"

        # Data directory writable
        try:
            JARVIS_DIR.mkdir(parents=True, exist_ok=True)
            probe = JARVIS_DIR / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks["data_dir"] = "ok"
        except OSError:
            checks["data_dir"] = "failed"

        return checks

    def hardware(self) -> dict[str, Any]:
        return {
            "ram_gb": _ram_gb(),
            "gpu_name": _gpu_name(),
            "os": f"{platform.system()} {platform.release()}",
        }

    def recommended_model(self) -> dict[str, Any]:
        _ok, models = _probe_ollama()
        name = _pick_model(models)
        return {"name": name, "available": models}

    def status(self) -> dict[str, Any]:
        """Live setup status — phase from disk, checks from fresh probes."""
        state = self._load()
        checks = self._run_checks()
        # Phase is derived, not trusted: a config-less "complete" is not complete.
        phase = state.get("phase", "not_started")
        if phase == "complete" and checks.get("config") != "ok":
            phase = "in_progress"
        return {
            "phase": phase,
            "recommended_model": self.recommended_model(),
            "hardware": self.hardware(),
            "checks": checks,
            "updated_at": state.get("updated_at"),
        }

    # ------------------------------------------------------------- wizard
    def run_full_setup(
        self,
        on_message: Optional[Callable[[str], None]] = None,
        on_confirm: Optional[Callable[[str], bool]] = None,
        on_choice: Optional[Callable[[str, list[str]], Optional[str]]] = None,
    ) -> bool:
        """Run the wizard end-to-end and persist the outcome.

        Returns True **only** when state was written with phase == complete.
        Any failure path records ``phase == "failed"`` and returns False.
        """
        def say(msg: str) -> None:
            if on_message:
                on_message(msg)
            else:
                print(msg)

        def confirm(prompt: str, default: bool = True) -> bool:
            if on_confirm is None:
                return default
            try:
                return bool(on_confirm(prompt))
            except (EOFError, KeyboardInterrupt):
                return False

        def choice(question: str, options: list[str]) -> Optional[str]:
            if on_choice is None:
                return options[0] if options else None
            try:
                picked = on_choice(question, options)
            except (EOFError, KeyboardInterrupt):
                return None
            return picked if picked in options else (options[0] if options else None)

        state = {
            "phase": "in_progress",
            "started_at": time.time(),
            "checks": {},
        }
        if not self._save(state):
            say("Setup could not start: state directory is not writable.")
            return False

        try:
            say("JARVIS setup — probing environment...")
            checks = self._run_checks()
            state["checks"] = checks
            hw = self.hardware()
            say(f"Hardware: {hw['ram_gb']}GB RAM / {hw['gpu_name'] or 'No GPU'} / {hw['os']}")
            for name, status in checks.items():
                say(f"  {'ok' if status == 'ok' else '!'} {name}: {status}")

            models = self.recommended_model()
            if not confirm("Use recommended default model "
                           f"({models['name']})?", default=True):
                picked = choice("Select a model family:",
                                ["ollama/qwen2.5-coder:3b", "ollama/llama3",
                                 "openai/gpt-4o-mini", "anthropic/claude-3-5-sonnet-latest"])
                if picked:
                    models["name"] = picked
                say(f"Selected model: {models['name']}")
            else:
                say(f"Using recommended model: {models['name']}")

            if checks.get("ollama") == "missing" and confirm(
                    "Ollama is not reachable. Keep going and configure it later?",
                    default=True):
                say("Ollama left unconfigured — run `jarvis setup` again once installed.")

            config = {}
            if CONFIG_PATH.exists():
                try:
                    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    config = {}
            config.setdefault("default_model", models["name"])
            config["setup_completed"] = True
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(config, indent=2, default=str),
                                   encoding="utf-8")

            state.update({
                "phase": "complete",
                "completed_at": time.time(),
                "recommended_model": models["name"],
                "hardware": hw,
                "checks": checks,
            })
            if not self._save(state):
                say("Setup finished but state could not be saved — re-run `jarvis setup`.")
                return False
            say("Setup complete.")
            return True

        except (EOFError, KeyboardInterrupt):
            state["phase"] = "in_progress"  # resumable next launch
            state["updated_at"] = time.time()
            self._save(state)
            say("Setup interrupted — it will resume on next launch.")
            return False
        except Exception as exc:  # noqa: BLE001 — record, never swallow
            logger.exception("setup failed")
            state["phase"] = "failed"
            state["error"] = f"{type(exc).__name__}: {exc}"
            state["updated_at"] = time.time()
            self._save(state)
            say(f"Setup failed: {state['error']}")
            return False


__all__ = ["SetupEngine", "SETUP_STATE_PATH", "CONFIG_PATH"]
