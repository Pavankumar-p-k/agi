"""core/goal_processor.py
Takes a user goal, researches it, generates a plan with interactive setup,
handles GitHub repo creation/connection, and asks the user for preferences.
"""

import os
import json
import logging
from typing import Optional, Any
from datetime import datetime

logger = logging.getLogger("goal_processor")


class GoalProcessor:
    def __init__(self):
        self._llm_client = None

    def _get_llm(self):
        if self._llm_client is None:
            from openai import OpenAI
            self._llm_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        return self._llm_client

    async def research_goal(self, goal: str) -> str:
        try:
            from tools.search_tool import search_engine
            results = search_engine.search(f"best practices architecture {goal}")
            scraped = await search_engine.scrape_top(results)
            return scraped or "No research results available"
        except Exception as e:
            logger.warning(f"[GOAL] Research failed: {e}")
            return "Research unavailable, proceeding with general knowledge"

    async def generate_plan(self, goal: str, research: str = "",
                            preferences: Optional[dict] = None) -> dict:
        prefs = preferences or {}
        tech_stack = prefs.get("tech_stack", "")
        ui_ideas = prefs.get("ui_ideas", "")
        dir_path = prefs.get("directory", "")
        github = prefs.get("github", "skip")
        repo_name = prefs.get("repo_name", "")
        repo_visibility = prefs.get("repo_visibility", "public")
        repo_description = prefs.get("repo_description", "")

        client = self._get_llm()
        system_prompt = f"""You are a senior software architect. Generate a JSON plan for the given goal.

RULES - MUST FOLLOW:
1. Each step agent MUST be one of: codex, aider, opencode, gemini, copilot, shell, gh
2. agent "user" is NOT ALLOWED. Every step must be executable by a tool.
3. codex = generate new files/project. aider = modify existing code. opencode = complex multi-step. gemini = research/tests/docs. copilot = suggestions/refactor. shell = npm/git/build/install/deploy. gh = github operations.
4. prompt must be a concrete instruction for that agent, not a question to the user.
5. verify must be a real shell command (file check, test run, etc), not a human question.
6. Max 8 steps.

Goal: {goal}
Tech stack: {tech_stack or 'decide based on goal'}

Example good step: {{"id":1,"agent":"shell","task_type":"scaffold","prompt":"npx create-next-app@latest . --typescript --tailwind","verify":"test -f package.json"}}
Example bad step: {{"id":1,"agent":"user","task_type":"ask","prompt":"What tech stack do you want?","verify":"wait for user response"}}

Output ONLY valid JSON: {{"goal":"...","tech_stack":"...","steps":[...]}}"""

        resp = client.chat.completions.create(
            model="qwen2.5:7b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Create a plan for: {goal}"},
            ],
            temperature=0.1,
            max_tokens=4096,
        )

        content = resp.choices[0].message.content
        # Extract JSON from markdown if needed
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        content = content.strip()

        try:
            plan = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON object from the response
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    plan = json.loads(match.group())
                except json.JSONDecodeError:
                    plan = {"goal": goal, "steps": [], "error": f"Failed to parse plan: {content[:200]}"}
            else:
                plan = {"goal": goal, "steps": [], "error": f"No JSON found in response: {content[:200]}"}

        plan["id"] = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        plan["status"] = "pending_approval"
        plan["github"] = github
        plan["repo_name"] = repo_name or os.path.basename(dir_path.strip("/\\")) or ""
        plan["repo_visibility"] = repo_visibility
        plan["repo_description"] = repo_description
        plan["directory"] = dir_path
        plan["created_at"] = datetime.now().isoformat()

        if github == "existing":
            clone_step = {
                "id": 0, "agent": "gh",
                "task_type": "clone",
                "prompt": f"Clone existing repo {repo_name} into {dir_path}",
                "verify": f"test -d {dir_path}",
            }
            plan["steps"].insert(0, clone_step)

        if github == "new":
            repo_step = {
                "id": 0, "agent": "gh",
                "task_type": "repo_create",
                "prompt": f"Create {repo_visibility} repo {repo_name}: {repo_description}",
                "verify": f"gh repo view --json name",
            }
            plan["steps"].insert(0, repo_step)

        return plan

    def build_setup_questions(self, goal: str) -> list[dict]:
        return [
            {
                "key": "directory",
                "question": "Where do you want to create the project?",
                "default": os.path.expanduser("~/Desktop/projects"),
                "type": "path",
            },
            {
                "key": "tech_stack",
                "question": "What tech stack / frameworks do you want to use?",
                "default": "",
                "type": "text",
                "hint": "e.g., Next.js + Tailwind + PostgreSQL",
            },
            {
                "key": "ui_ideas",
                "question": "Any UI ideas, design preferences, or existing mockups?",
                "default": "",
                "type": "text",
                "hint": "e.g., dark theme, minimal, mobile-first",
            },
            {
                "key": "future_plans",
                "question": "Any future plans or features you want to leave room for?",
                "default": "",
                "type": "text",
                "hint": "e.g., auth, payments, multiplayer",
            },
            {
                "key": "github",
                "question": "GitHub — create new repo, connect existing one, or skip?",
                "default": "skip",
                "type": "choice",
                "options": [
                    {"value": "new", "label": "Create new repo"},
                    {"value": "existing", "label": "Connect existing repo"},
                    {"value": "skip", "label": "Skip GitHub"},
                ],
            },
        ]

    async def execute_github_setup(self, plan: dict, github_token: Optional[str] = None) -> dict:
        github = plan.get("github", "skip")
        repo_name = plan.get("repo_name", "")
        dir_path = plan.get("directory", "")
        visibility = plan.get("repo_visibility", "public")
        description = plan.get("repo_description", "")

        if github == "skip":
            return {"status": "skipped", "message": "GitHub setup skipped"}

        if github == "existing":
            if not repo_name:
                return {"status": "error", "message": "No repo URL provided"}
            result = await self._run_gh_cli(f"gh repo clone {repo_name} \"{dir_path}\"")
            if result["returncode"] != 0 and github_token:
                result = await self._run_gh_api("clone", repo_name, dir_path, github_token)
            return result

        if github == "new":
            if not repo_name:
                repo_name = os.path.basename(dir_path.strip("/\\")) or "my-project"
                plan["repo_name"] = repo_name
            result = await self._run_gh_cli(
                f"gh repo create {repo_name} --{visibility} --description \"{description}\" --push --remote origin --source \"{dir_path}\""
            )
            if result["returncode"] != 0 and github_token:
                result = await self._run_gh_api("create", repo_name, dir_path, github_token, visibility, description)
            return result

        return {"status": "error", "message": "Invalid GitHub option"}

    async def _run_gh_cli(self, cmd: str) -> dict:
        try:
            import shlex
            cmd_args = shlex.split(cmd)
            proc = await asyncio.create_subprocess_exec(
                *cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return {
                "status": "ok" if proc.returncode == 0 else "error",
                "returncode": proc.returncode,
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else "",
            }
        except Exception as e:
            return {"status": "error", "returncode": -1, "message": str(e)}

    async def _run_gh_api(self, action: str, repo: str, dir_path: str,
                          token: str, visibility: str = "public",
                          description: str = "") -> dict:
        import httpx
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            async with httpx.AsyncClient() as http:
                if action == "create":
                    resp = await http.post(
                        "https://api.github.com/user/repos",
                        headers=headers,
                        json={
                            "name": repo,
                            "description": description,
                            "private": visibility == "private",
                        },
                    )
                    if resp.status_code in (200, 201):
                        clone_url = resp.json().get("clone_url", "")
                        os.makedirs(dir_path, exist_ok=True)
                        git_init = await asyncio.create_subprocess_exec(
                            "git", "init", dir_path,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        )
                        await git_init.communicate()
                        if git_init.returncode == 0:
                            git_remote = await asyncio.create_subprocess_exec(
                                "git", "-C", dir_path, "remote", "add", "origin", clone_url,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            )
                            await git_remote.communicate()
                        return {"status": "ok", "message": f"Repo created: {resp.json().get('html_url', repo)}"}
                    return {"status": "error", "message": f"API error: {resp.status_code} {resp.text}"}
                elif action == "clone":
                    resp = await http.get(f"https://api.github.com/repos/{repo}")
                    if resp.status_code == 200:
                        clone_url = resp.json().get("clone_url", f"https://github.com/{repo}.git")
                        proc = await asyncio.create_subprocess_exec(
                            "git", "clone", clone_url, dir_path,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        )
                        await proc.communicate()
                        return {"status": "ok", "message": f"Cloned {repo}"}
                    return {"status": "error", "message": f"Repo not found: {resp.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def push_to_github(self, plan: dict, github_token: Optional[str] = None) -> dict:
        dir_path = plan.get("directory", "")
        repo_name = plan.get("repo_name", "")
        if not dir_path or not repo_name:
            return {"status": "skipped", "message": "No directory or repo name"}

        result = await self._run_gh_cli(
            f"git -C \"{dir_path}\" add . && git -C \"{dir_path}\" commit -m \"JARVIS: initial project setup\" && git -C \"{dir_path}\" push -u origin main"
        )
        if result["returncode"] != 0 and github_token:
            result = await self._run_gh_cli(
                f"git -C \"{dir_path}\" add . && git -C \"{dir_path}\" commit -m \"JARVIS: initial project setup\" && git -C \"{dir_path}\" branch -M main && git -C \"{dir_path}\" push -u origin main"
            )
        return result


import asyncio
import subprocess
