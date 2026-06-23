"""Vision + browser automation tool using pyautogui + Ollama vision models."""
from __future__ import annotations
import asyncio
import logging

logger = logging.getLogger(__name__)

_agent_instance = None


async def _get_agent():
    global _agent_instance
    if _agent_instance is None:
        from core.vision_agent import VisionAgent
        _agent_instance = VisionAgent()
    return _agent_instance


async def do_vision_browser(content: str, owner: str | None = None) -> dict:
    """Execute a vision-based browser/desktop automation task.

    Uses screen capture + Ollama vision model + pyautogui to
    autonomously perform multi-step browser tasks:
      - Open apps (Chrome, Notepad, etc.)
      - Navigate to websites
      - Click UI elements (located via vision)
      - Fill forms and type text
      - Search and extract information

    Args:
        content: Natural language instruction (e.g. "open chrome, go to
                 google.com, search for python, take screenshot")
        owner: Optional user identifier

    Returns:
        dict with status, result, steps, error (if any)
    """
    if not content or not content.strip():
        return {"status": "error", "result": "", "error": "No instruction provided"}

    try:
        agent = await _get_agent()
        task = await agent.run(content)
        steps_data = [
            {
                "num": s.get("step_num"),
                "desc": s.get("desc"),
                "status": s.get("_status", "unknown"),
                "output": s.get("_output", ""),
            }
            for s in task.steps
        ]
        done = sum(1 for s in task.steps if s.get("_status") == "done")
        return {
            "status": task.status,
            "result": task.result,
            "steps": steps_data,
            "done": done,
            "total": len(task.steps),
            "error": task.error or "",
        }
    except Exception as e:
        logger.exception("[VisionTool] error")
        return {"status": "failed", "result": "", "error": str(e)}
