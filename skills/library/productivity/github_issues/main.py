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

from skills.utils import success_response, error_response, fetch_json

async def github_issues(params: dict) -> dict:
    action = params.get("action", "search")
    repo = params.get("repo", "").strip()
    if not repo:
        return error_response("repo is required (format: owner/repo)")
    if "/" not in repo:
        return error_response("repo must be in format owner/repo")
    token = params.get("token", "")

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    if action == "search":
        query = params.get("query", "").strip()
        state = params.get("state", "open")
        url = f"https://api.github.com/search/issues"
        q = f"repo:{repo} state:{state}"
        if query:
            q += f" {query}"
        data = await fetch_json(url, params={"q": q, "per_page": 20}, headers=headers)
        if data is None:
            return error_response("Failed to search GitHub issues")
        issues = []
        for item in data.get("items", []):
            issues.append({
                "number": item["number"],
                "title": item["title"],
                "state": item["state"],
                "url": item["html_url"],
                "created_at": item["created_at"],
                "updated_at": item["updated_at"],
                "labels": [l["name"] for l in item.get("labels", [])],
            })
        return success_response({
            "repo": repo,
            "total_count": data.get("total_count", 0),
            "issues": issues,
        })

    elif action == "create":
        title = params.get("title", "").strip()
        body = params.get("body", "").strip()
        if not title:
            return error_response("title is required to create an issue")
        if not token:
            return error_response("token is required to create an issue")
        import httpx
        url = f"https://api.github.com/repos/{repo}/issues"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                url,
                json={"title": title, "body": body or ""},
                headers=headers,
            )
            if r.status_code in (201, 200):
                item = r.json()
                return success_response({
                    "number": item["number"],
                    "title": item["title"],
                    "state": item["state"],
                    "url": item["html_url"],
                })
            return error_response(f"GitHub API error {r.status_code}: {r.text}")

    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest

    async def on_load(self):
        pass
