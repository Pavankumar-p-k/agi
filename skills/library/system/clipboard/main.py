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
