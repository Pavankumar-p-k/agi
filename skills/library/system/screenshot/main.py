import asyncio
import base64
import io
import os
import tempfile
from datetime import datetime
from skills.utils import success_response, error_response

async def screenshot(params: dict) -> dict:
    region = params.get("region", "full")
    fmt = params.get("format", "png").lower()
    filename = params.get("filename")
    try:
        import pyautogui
    except ImportError:
        try:
            from PIL import ImageGrab
        except ImportError:
            return error_response(
                "No screenshot library available. Install with: pip install pyautogui"
            )
        screenshot_func = ImageGrab.grab
    else:
        screenshot_func = pyautogui.screenshot
    try:
        if region == "selection":
            return error_response("Selection region is not supported programmatically. Use 'full' instead.")
        img = await _run_screenshot(screenshot_func)
        if fmt == "jpg":
            img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            ext = "jpg"
        else:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            ext = "png"
        b64 = base64.b64encode(buf.getvalue()).decode()
        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        img.save(filepath)
        return success_response({
            "data_url": f"data:image/{ext};base64,{b64}",
            "file_path": filepath,
            "format": ext,
            "region": region,
        })
    except Exception as e:
        return error_response(f"Screenshot failed: {e}")

async def _run_screenshot(func):
    return await asyncio.to_thread(func)

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
