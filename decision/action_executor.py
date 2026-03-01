from __future__ import annotations

import json
from typing import Any


class ActionExecutor:
    """
    Executes planned actions by dispatching to JarvisTools.
    """

    async def execute(self, decision, tools) -> dict[str, Any]:
        action = getattr(decision, "action", "")
        tool = getattr(decision, "tool", "")
        params = dict(getattr(decision, "params", {}) or {})

        if not tool:
            return {"success": False, "error": "missing_tool"}

        try:
            if tool == "speak":
                text = str(params.get("text", "")).strip() or f"Executing action {action}"
                await tools.speak(text)
                return {"success": True, "output": text}

            if tool == "daily_briefing":
                briefing = await tools.get_daily_briefing()
                await tools.speak(briefing)
                return {"success": True, "output": briefing}

            if tool == "daily_summary":
                summary = await tools.get_daily_summary()
                await tools.speak(summary)
                return {"success": True, "output": summary}

            if tool == "list_reminders":
                reminders = await tools.list_reminders()
                return {"success": True, "output": json.dumps(reminders)}

            if tool == "task_list":
                tasks = await tools.get_task_list()
                return {"success": True, "output": json.dumps(tasks)}

            if tool == "media":
                mode = str(params.get("mode", "random"))
                result = await tools.play_music(mode=mode)
                return {"success": True, "output": json.dumps(result)}

            if tool == "notes":
                notes = await tools.list_recent_notes()
                return {"success": True, "output": json.dumps(notes)}

            if tool == "reminders":
                title = str(params.get("title", "")).strip() or str(params.get("text", "")).strip()
                when = str(params.get("time", "")).strip()
                ok = await tools.create_reminder(title, when)
                return {"success": bool(ok), "output": f"Reminder created: {title}" if ok else ""}

            if tool == "brain":
                query = str(params.get("query", "")).strip() or str(params.get("text", "")).strip() or str(action)
                out = await tools.ask_brain(query)
                return {"success": bool(out), "output": out}

            if tool == "web":
                url = str(params.get("url", "")).strip()
                if not url:
                    return {"success": False, "error": "missing_url"}
                await tools.open_url(url)
                return {"success": True, "output": f"Opened {url}"}

            # Generic fallback.
            result = await tools.call(tool, params)
            if isinstance(result, dict):
                success = bool(result.get("success", True))
                return {"success": success, "output": json.dumps(result)}
            return {"success": True, "output": str(result)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

