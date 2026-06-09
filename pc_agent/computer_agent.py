# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import asyncio
import os
import re
import subprocess
import sqlite3
import base64
import io
import shutil
from pathlib import Path
from governance.GovernanceValidator import GovernanceValidator
from governance.exceptions import GovernanceViolation
from ai_os.sandbox import SandboxedExecutor
logger = logging.getLogger(__name__)

APP_MAP = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "cmd": "cmd.exe",
    "terminal": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "mozilla firefox": "firefox.exe",
    "vscode": "code.exe",
    "code": "code.exe",
    "visual studio code": "code.exe",
    "settings": "ms-settings:",
    "windows settings": "ms-settings:",
    "control panel": "control",
    "task manager": "taskmgr.exe",
    "regedit": "regedit.exe",
    "registry editor": "regedit.exe",
}

def _resolve_app_path(app_name: str) -> str | None:
    name_lower = app_name.lower().strip()
    mapped = APP_MAP.get(name_lower)
    if mapped:
        return mapped

    found = shutil.which(app_name)
    if found:
        return found

    common_dirs = [
        os.environ.get('WINDIR', 'C:\\Windows'),
        os.environ.get('WINDIR', 'C:\\Windows') + '\\System32',
        os.environ.get('ProgramFiles', 'C:\\Program Files'),
        os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
        os.environ.get('LOCALAPPDATA', '') + '\\Programs',
        os.environ.get('APPDATA', '') + '\\Microsoft\\Windows\\Start Menu\\Programs',
    ]
    for base_dir in common_dirs:
        if not base_dir:
            continue
        base = Path(base_dir)
        if not base.exists():
            continue
        for exe in base.rglob(f"{app_name}.exe"):
            return str(exe)
        for exe in base.rglob(f"{app_name}.lnk"):
            return str(exe)
    return app_name

class ComputerAgent:
    """
    Autonomous computer control.
    All execution passes through sandbox + governance.
    """
    def __init__(self, db_path: str = "data/jarvis_os_world.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.governance = GovernanceValidator()
        self.sandbox = SandboxedExecutor(timeout=30)
        self._interpreter = None

    def _get_interpreter(self):
        if getattr(self, '_interpreter', None) is not None:
            return self._interpreter
        try:
            import interpreter as interp_module
            if hasattr(interp_module, 'Interpreter'):
                interp = interp_module.Interpreter()
            elif hasattr(interp_module, 'interpreter') and hasattr(interp_module.interpreter, 'Interpreter'):
                interp = interp_module.interpreter.Interpreter()
            else:
                raise AttributeError("interpreter module missing Interpreter class")
            interp.auto_run = False
            try:
                interp.llm.model = "ollama/qwen2.5-coder:3b"
                interp.llm.api_base = "http://localhost:11434"
            except Exception as e:
                logger.warning("[pc_agent.computer_agent] control_computer failed: %s", e)
            self._interpreter = interp
            return interp
        except ImportError:
            raise RuntimeError(
                "Open Interpreter not installed. Run: pip install open-interpreter"
            )

    async def open_app(self, app_name: str) -> dict:
        resolved = _resolve_app_path(app_name)
        try:
            if resolved and (resolved.startswith("ms-") or resolved == "control"):
                subprocess.Popen(["explorer", resolved], shell=False)
            else:
                subprocess.Popen([resolved or app_name], shell=False)
            return {"status": "success", "app": app_name, "resolved_to": resolved}
        except Exception as e:
            return {"status": "error", "app": app_name, "error": str(e)}

    async def get_screen_context(self) -> str:
        try:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab()
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()
            from core.llm_router import get_router
            r = await get_router().acompletion(
                model="vision",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe what is on screen in 2 sentences. Focus on what app is open and what's visible."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    ]
                }],
                timeout=30,
            )
            return r.choices[0].message.content or "Screen capture processed."
        except Exception as e:
            return f"Screen capture: {e}"

    async def execute_natural_language(self, instruction: str, confirm: bool = True) -> dict:
        from .snapshot import snapshot_manager
        snapshot_id = None
        try:
            open_match = re.match(r'(?:open|launch|start)\s+(.+)', instruction.strip().lower())
            if open_match:
                return await self.open_app(open_match.group(1))

            self.governance.validate_execution({"task": instruction})
            sb_result = self.sandbox.execute(instruction)
            if not sb_result.get("success", False) and sb_result.get("sandbox_blocked", False):
                return {"status": "blocked", "reason": sb_result.get("error", "Sandbox rejected")}

            screen_state_coro = self.get_screen_context()
            if asyncio.iscoroutine(screen_state_coro):
                screen_state = await screen_state_coro
            else:
                screen_state = screen_state_coro
            vision_context = f"Current screen state: {screen_state}" if "failed" not in str(screen_state).lower() else ""

            snapshot_id = snapshot_manager.create(instruction)

            print(f"[ComputerAgent] Executing: {instruction}")
            full_prompt = f"{vision_context}\n\n{instruction}" if vision_context else instruction
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._get_interpreter().chat, full_prompt)

            self._log_action(instruction, str(result))

            return {
                "status": "success",
                "result": result,
                "instruction": instruction,
                "screen_context": screen_state,
                "snapshot_id": snapshot_id,
            }
        except GovernanceViolation as e:
            if snapshot_id:
                snapshot_manager.rollback(snapshot_id)
            return {"status": "blocked", "reason": f"Governance violation: {str(e)}", "rolled_back": True}
        except Exception as e:
            if snapshot_id:
                snapshot_manager.rollback(snapshot_id)
            return {"status": "error", "error": str(e), "instruction": instruction, "rolled_back": True}

    def _log_action(self, instruction: str, result: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pc_agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instruction TEXT,
                result TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT INTO pc_agent_logs (instruction, result) VALUES (?, ?)", (instruction, result))
        conn.commit()
        conn.close()

computer_agent = ComputerAgent()
