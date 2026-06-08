from skills.utils import success_response, error_response, fetch_json

async def todoist(params: dict) -> dict:
    action = params.get("action", "list")
    token = params.get("token", "").strip()
    if not token:
        return error_response("token is required (Todoist API key)")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if action == "list":
        project = params.get("project")
        url = "https://api.todoist.com/rest/v2/tasks"
        req_params = {}
        if project:
            req_params["project_id"] = project
        data = await fetch_json(url, params=req_params, headers=headers)
        if data is None:
            return error_response("Failed to fetch tasks from Todoist")
        tasks = []
        for t in data:
            tasks.append({
                "id": t.get("id"),
                "content": t.get("content"),
                "priority": t.get("priority", 1),
                "due": t.get("due", {}).get("date") if t.get("due") else None,
                "project_id": t.get("project_id"),
                "url": t.get("url", ""),
            })
        return success_response({"tasks": tasks, "count": len(tasks)})

    elif action == "add":
        content = params.get("content", "").strip()
        if not content:
            return error_response("content is required")
        project_id = params.get("project")
        priority = int(params.get("priority", 1))
        body = {"content": content, "priority": max(1, min(4, priority))}
        if project_id:
            body["project_id"] = project_id
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.todoist.com/rest/v2/tasks",
                json=body,
                headers=headers,
            )
            if r.status_code in (200, 201):
                t = r.json()
                return success_response({
                    "id": t.get("id"),
                    "content": t.get("content"),
                    "priority": t.get("priority"),
                    "url": t.get("url", ""),
                })
            return error_response(f"Todoist API error {r.status_code}: {r.text}")

    elif action == "complete":
        task_id = params.get("task_id", "").strip()
        if not task_id:
            return error_response("task_id is required")
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.todoist.com/rest/v2/tasks/{task_id}/close",
                headers=headers,
            )
            if r.status_code == 204:
                return success_response({"task_id": task_id, "status": "completed"})
            return error_response(f"Todoist API error {r.status_code}: {r.text}")

    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest

    async def on_load(self):
        pass
