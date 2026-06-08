import time

from skills.utils import success_response, error_response

_state = {
    "active": False,
    "phase": None,
    "end_time": 0,
    "work_minutes": 25,
    "break_minutes": 5,
}

async def pomodoro(params: dict) -> dict:
    action = params.get("action", "status")
    if action == "start":
        work = int(params.get("work_minutes", 25))
        brk = int(params.get("break_minutes", 5))
        _state["work_minutes"] = work
        _state["break_minutes"] = brk
        _state["phase"] = "work"
        _state["end_time"] = time.time() + work * 60
        _state["active"] = True
        return success_response({
            "phase": "work",
            "work_minutes": work,
            "break_minutes": brk,
            "remaining_seconds": work * 60,
        })
    elif action == "stop":
        _state["active"] = False
        _state["phase"] = None
        _state["end_time"] = 0
        return success_response({"phase": "stopped"})
    else:
        if not _state["active"]:
            return success_response({"phase": "idle", "remaining_seconds": 0})
        remaining = max(0, int(_state["end_time"] - time.time()))
        if remaining <= 0 and _state["phase"] == "work":
            _state["phase"] = "break"
            _state["end_time"] = time.time() + _state["break_minutes"] * 60
            remaining = _state["break_minutes"] * 60
        elif remaining <= 0 and _state["phase"] == "break":
            _state["active"] = False
            return success_response({"phase": "complete", "remaining_seconds": 0})
        return success_response({
            "phase": _state["phase"],
            "remaining_seconds": remaining,
            "work_minutes": _state["work_minutes"],
            "break_minutes": _state["break_minutes"],
        })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest

    async def on_load(self):
        pass
