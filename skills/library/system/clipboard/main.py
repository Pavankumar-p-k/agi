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

import asyncio
from skills.utils import success_response, error_response

async def clipboard(params: dict) -> dict:
    action = params.get("action", "read")
    try:
        import pyperclip
    except ImportError:
        return error_response("pyperclip is not installed. Install with: pip install pyperclip")
    try:
        if action == "read":
            text = await asyncio.to_thread(pyperclip.paste)
            return success_response({"text": text, "action": "read"})
        elif action == "write":
            text = params.get("text", "")
            await asyncio.to_thread(pyperclip.copy, text)
            return success_response({"text": text, "action": "written"})
        elif action == "clear":
            await asyncio.to_thread(pyperclip.copy, "")
            return success_response({"action": "cleared"})
        else:
            return error_response(f"Unknown action '{action}'. Use read/write/clear.")
    except Exception as e:
        return error_response(f"Clipboard operation failed: {e}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
