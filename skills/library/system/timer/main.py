import asyncio
import time
import threading
from skills.utils import success_response, error_response

_timers = {}

async def timer(params: dict) -> dict:
    """Set, list, or cancel timers."""
    action = params.get("action", "set")
    duration = params.get("duration", params.get("seconds", 0))
    label = params.get("label", params.get("name", "Timer"))
    
    if action == "list":
        active = []
        for tid, tdata in list(_timers.items()):
            remaining = max(0, tdata["end"] - time.time())
            active.append({"id": tid, "label": tdata["label"], "remaining_seconds": int(remaining), "duration": tdata["duration"]})
        return success_response({"timers": active, "count": len(active)})
    
    if action == "cancel":
        tid = params.get("id", "")
        if tid in _timers:
            _timers[tid]["cancelled"] = True
            del _timers[tid]
            return success_response({"action": "cancelled", "timer": label})
        return error_response(f"Timer not found: {tid}")
    
    if action == "stop_all":
        count = len(_timers)
        _timers.clear()
        return success_response({"action": "stopped_all", "count": count})
    
    if action == "set" or action == "start":
        seconds = 0
        if isinstance(duration, (int, float)):
            seconds = int(duration)
        elif isinstance(duration, str):
            import re
            parts = re.findall(r'(\d+)\s*(s|sec|seconds?|m|min|minutes?|h|hr|hours?)', duration.lower())
            for val, unit in parts:
                val = int(val)
                if unit.startswith('h'):
                    seconds += val * 3600
                elif unit.startswith('m'):
                    seconds += val * 60
                else:
                    seconds += val
        
        if seconds <= 0:
            seconds = 60
        
        import uuid
        tid = uuid.uuid4().hex[:8]
        _timers[tid] = {
            "label": label,
            "duration": seconds,
            "start": time.time(),
            "end": time.time() + seconds,
            "cancelled": False,
        }
        
        def _run_timer(tid, seconds, label):
            import time as t
            t.sleep(seconds)
            if tid in _timers and not _timers[tid]["cancelled"]:
                import threading
                def _notify():
                    print(f"\nâ° Timer: {label} ({seconds}s) completed!")
                threading.Thread(target=_notify, daemon=True).start()
                del _timers[tid]
        
        t = threading.Thread(target=_run_timer, args=(tid, seconds, label), daemon=True)
        t.start()
        
        return success_response({
            "action": "started",
            "id": tid,
            "label": label,
            "seconds": seconds,
            "formatted": f"{seconds//60}m {seconds%60}s" if seconds >= 60 else f"{seconds}s",
        })
    
    return error_response(f"Unknown timer action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        pass
