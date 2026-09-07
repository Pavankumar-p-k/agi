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

from datetime import datetime, date

from skills.utils import success_response, error_response

_habits = {}
_logs = {}

def _streak(habit_name):
    logs = _logs.get(habit_name, set())
    if not logs:
        return 0
    today = date.today()
    streak = 0
    d = today
    while d.isoformat() in logs:
        streak += 1
        from datetime import timedelta
        d -= timedelta(days=1)
    return streak

async def habit_tracker(params: dict) -> dict:
    action = params.get("action", "list")
    habit_name = params.get("habit", "").strip()
    date_str = params.get("date")

    if action == "list":
        if not _habits:
            return success_response({"habits": []})
        result = []
        for name, desc in _habits.items():
            result.append({
                "name": name,
                "description": desc,
                "streak": _streak(name),
                "total_logs": len(_logs.get(name, set())),
            })
        return success_response({"habits": result})

    elif action == "add":
        if not habit_name:
            return error_response("habit name is required")
        _habits[habit_name] = habit_name
        if habit_name not in _logs:
            _logs[habit_name] = set()
        return success_response({"habit": habit_name, "message": f"Habit '{habit_name}' added"})

    elif action == "log":
        if not habit_name:
            return error_response("habit name is required")
        if habit_name not in _habits:
            return error_response(f"Habit '{habit_name}' not found")
        log_date = date_str if date_str else date.today().isoformat()
        if habit_name not in _logs:
            _logs[habit_name] = set()
        _logs[habit_name].add(log_date)
        return success_response({
            "habit": habit_name,
            "date": log_date,
            "streak": _streak(habit_name),
        })

    elif action == "stats":
        if not habit_name:
            return error_response("habit name is required for stats")
        if habit_name not in _habits:
            return error_response(f"Habit '{habit_name}' not found")
        logs = sorted(_logs.get(habit_name, set()))
        return success_response({
            "habit": habit_name,
            "total_logs": len(logs),
            "streak": _streak(habit_name),
            "logs": logs,
        })

    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest

    async def on_load(self):
        pass
