from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


class MessagingController:
    def __init__(self) -> None:
        self.started = False
        self.last_error: str = ""
        self._script = Path(__file__).resolve().parent / "playwright_messenger.mjs"
        self.signature = "I am Pavan sir personal assistant."

    def _parse_last_json_line(self, text: str) -> dict[str, Any]:
        for line in reversed([ln.strip() for ln in (text or "").splitlines() if ln.strip()]):
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except Exception:
                    continue
        return {}

    def _run_playwright(self, platform: str, mode: str, target: str = "", message: str = "") -> bool:
        self.started = True
        self.last_error = ""

        node_bin = shutil.which("node.exe") or shutil.which("node")
        if not node_bin:
            self.last_error = "node not found. Install Node.js and ensure node is in PATH."
            return False
        if not self._script.exists():
            self.last_error = f"messenger script not found: {self._script}"
            return False
        # Playwright package is expected to be installed in this folder.
        local_pkg = self._script.parent / "node_modules" / "playwright"
        if not local_pkg.exists():
            self.last_error = f"playwright not installed at: {local_pkg}"
            return False

        cmd = [
            node_bin,
            str(self._script),
            "--platform",
            platform,
            "--mode",
            mode,
            "--browser",
            os.getenv("AUTOMATION_BROWSER", "chromium").strip().lower() or "chromium",
            "--timeout_ms",
            "90000",
        ]
        if target:
            cmd.extend(["--target", target])
        if message:
            cmd.extend(["--message", message])

        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self._script.parent),
            )
        except Exception as exc:
            self.last_error = str(exc)
            return False

        payload = self._parse_last_json_line(result.stdout)
        ok = bool(payload.get("success"))
        if ok:
            return True

        self.last_error = str(payload.get("error") or result.stderr.strip() or result.stdout.strip() or "unknown_error")
        return False

    def _with_signature(self, message: str) -> str:
        base = (message or "").strip()
        sig = self.signature.strip()
        if not sig:
            return base
        if sig.lower() in base.lower():
            return base
        if base:
            return f"{base}\n\n{sig}"
        return sig

    def login(self, platform: str) -> bool:
        return self._run_playwright(platform=platform, mode="login")

    def send_whatsapp(self, contact: str, message: str) -> bool:
        return self._run_playwright(
            platform="whatsapp",
            mode="send",
            target=contact.strip(),
            message=self._with_signature(message),
        )

    def send_instagram_dm(self, username: str, message: str) -> bool:
        return self._run_playwright(
            platform="instagram",
            mode="send",
            target=username.strip().lstrip("@"),
            message=self._with_signature(message),
        )

    def shutdown(self) -> None:
        if self.started:
            print("[Messaging] Shutdown complete")


messaging = MessagingController()
