"""Dynamic tool router for the JARVIS AI Operating System."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Dict, List, Optional
from urllib import parse, request
import webbrowser
import xml.etree.ElementTree as ET

from ..cache import TTLCache, fingerprint
from ..contracts import ToolSelection, ToolSpec
from tools.tool_loader import load_router_tools

logger = logging.getLogger("jarvis.os.tool_router")


class ToolInvocationError(Exception):
    pass


class ToolRouter:
    def __init__(
        self,
        world_model: Any | None = None,
        observability: Any | None = None,
        config: Optional[dict] = None,
        model_gateway: Any | None = None,
        browser: Any | None = None,
        skill_registry: Any | None = None,
        supervisor: Any | None = None,
        access_manager: Any | None = None,
        mobile_sync: Any | None = None,
        scheduler: Any | None = None,
        gateway: Any | None = None,
    ):
        self.world_model = world_model
        self.observability = observability
        self.config = config or {}
        self.model_gateway = model_gateway
        self.browser = browser
        self.skill_registry = skill_registry
        self.supervisor = supervisor
        self.access_manager = access_manager
        self.mobile_sync = mobile_sync
        self.scheduler = scheduler
        self.gateway = gateway
        self._tools: Dict[str, Callable[..., Any]] = {}
        self._specs: Dict[str, ToolSpec] = {}
        self._cache = TTLCache(
            ttl_s=int(self.config.get("cache_ttl_s", 120)),
            max_entries=int(self.config.get("cache_max_entries", 512)),
        )

    async def initialize(self):
        self.register_tool(
            ToolSpec(
                name="assistant_chat",
                description="Conversational assistant for natural language tasks.",
                capabilities=["chat", "reasoning", "conversation"],
                read_only=True,
            ),
            self._assistant_tool,
        )
        self.register_tool(
            ToolSpec(
                name="brain",
                description="Legacy autonomy orchestrator bridge.",
                capabilities=["analysis", "planning", "conversation"],
                read_only=True,
            ),
            self._brain_tool,
        )
        self.register_tool(
            ToolSpec(
                name="memory",
                description="Semantic memory and world model retrieval.",
                capabilities=["memory", "search", "state"],
                read_only=True,
            ),
            self._memory_tool,
        )
        self.register_tool(
            ToolSpec(
                name="filesystem",
                description="Repository-safe file inspection and controlled writes.",
                capabilities=["files", "storage", "artifacts"],
                risk_tags=["io"],
            ),
            self._filesystem_tool,
        )
        self.register_tool(
            ToolSpec(
                name="automation",
                description="PC automation and app/web control.",
                capabilities=["automation", "desktop", "browser"],
                risk_tags=["desktop_control"],
            ),
            self._automation_tool,
        )
        self.register_tool(
            ToolSpec(
                name="browser",
                description="Local browser controller with DOM-aware upgrade path.",
                capabilities=["browser", "navigation", "search"],
                risk_tags=["browser_control"],
            ),
            self._browser_tool,
        )
        self.register_tool(
            ToolSpec(
                name="vision",
                description="Vision and image interpretation bridge.",
                capabilities=["vision", "camera", "screen"],
                risk_tags=["sensor"],
                read_only=True,
            ),
            self._vision_tool,
        )
        self.register_tool(
            ToolSpec(
                name="adb",
                description="Android device bridge.",
                capabilities=["adb", "android", "device"],
                risk_tags=["device_control"],
            ),
            self._adb_tool,
        )
        self.register_tool(
            ToolSpec(
                name="learning",
                description="Learning and student AGI bridge.",
                capabilities=["learning", "teaching", "reflection"],
                read_only=True,
            ),
            self._learning_tool,
        )
        self.register_tool(
            ToolSpec(
                name="realtime",
                description="Current date/time, live news, and lightweight factual web lookup.",
                capabilities=["time", "date", "news", "web_lookup"],
                read_only=True,
            ),
            self._realtime_tool,
        )
        self.register_tool(
            ToolSpec(
                name="workspace",
                description="Workspace-aware project and codebase inspection.",
                capabilities=["project", "repo", "codebase", "review"],
                read_only=True,
            ),
            self._workspace_tool,
        )
        self.register_tool(
            ToolSpec(
                name="shell",
                description="Local shell execution within the approved workspace.",
                capabilities=["shell", "terminal", "commands"],
                risk_tags=["shell_execution"],
            ),
            self._shell_tool,
        )
        self.register_tool(
            ToolSpec(
                name="skills",
                description="Local skill registry discovery and lookup.",
                capabilities=["skills", "plugins", "extensions"],
                read_only=True,
            ),
            self._skills_tool,
        )
        self.register_tool(
            ToolSpec(
                name="models",
                description="Local Ollama model gateway and routing.",
                capabilities=["models", "ollama", "routing"],
                read_only=True,
            ),
            self._models_tool,
        )
        self.register_tool(
            ToolSpec(
                name="gateway",
                description="Local channel gateway for CLI, desktop, and messaging connectors.",
                capabilities=["channels", "messaging", "gateway"],
            ),
            self._gateway_tool,
        )
        self.register_tool(
            ToolSpec(
                name="mobile",
                description="Device pairing and Android sync bridge.",
                capabilities=["mobile", "sync", "adb"],
            ),
            self._mobile_tool,
        )
        self.register_tool(
            ToolSpec(
                name="scheduler",
                description="Heartbeat and scheduled autonomous task management.",
                capabilities=["schedule", "heartbeat", "cron"],
            ),
            self._scheduler_tool,
        )
        self.register_tool(
            ToolSpec(
                name="access",
                description="Scoped host access and approval workflow management.",
                capabilities=["permissions", "approval", "security"],
            ),
            self._access_tool,
        )
        self._semantic_registry = load_router_tools(self)
        logger.info("[ToolRouter] Registered tools: %s", list(self._tools.keys()))

    async def shutdown(self):
        return None

    def register_tool(self, spec: ToolSpec, handler: Callable[..., Any]):
        self._specs[spec.name] = spec
        self._tools[spec.name] = handler

    def get_tool(self, name: str) -> Callable[..., Any]:
        if name not in self._tools:
            raise ToolInvocationError(f"Tool not registered: {name}")
        return self._tools[name]

    def get_spec(self, name: str) -> ToolSpec:
        if name not in self._specs:
            raise ToolInvocationError(f"Tool spec not registered: {name}")
        return self._specs[name]

    def catalog(self) -> List[Dict[str, Any]]:
        return [spec.to_dict() for spec in self._specs.values()]

    # NOTE: recommend_tools REMOVED - keyword-only routing replaced by
    # sovereign_router.py which uses classification-based routing.
    # Use sovereign_router.classify() and build_plan() instead.

    async def invoke(self, name: str, **kwargs) -> Any:
        handler = self.get_tool(name)
        spec = self.get_spec(name)
        cache_key = ""
        if spec.read_only:
            cache_key = fingerprint(name, kwargs)
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return cached
        try:
            result = await handler(**kwargs) if asyncio.iscoroutinefunction(handler) else handler(**kwargs)
            if cache_key:
                await self._cache.set(cache_key, result)
            if self.observability:
                self.observability.record_event("tool_router.invoke", {"tool": name})
            return result
        except Exception as exc:
            logger.exception("Tool '%s' failed", name)
            raise ToolInvocationError(str(exc)) from exc

    async def _assistant_tool(self, prompt: str = "", context: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        direct = self._direct_response(prompt)
        if direct:
            return {"response": direct, "intent": "direct_answer"}
        local_only = bool((context or {}).get("local_only", os.getenv("JARVIS_LOCAL_ONLY", "1") not in {"0", "false", "no"}))
        if local_only and self.model_gateway:
            response = self.model_gateway.generate(
                prompt=prompt,
                task="chat",
                system="You are JARVIS, a concise local-first AI operating system assistant.",
            )
            if response.get("ok") and response.get("response"):
                return {"response": response["response"], "intent": "local_model"}
        from assistant.engine import jarvis

        user_id = kwargs.get("user_id")
        return await jarvis.process_text(prompt, user_id=user_id)

    async def _brain_tool(self, prompt: str = "", **kwargs) -> Dict[str, Any]:
        try:
            from autonomy import get_orchestrator

            orchestrator = get_orchestrator()
            if not orchestrator:
                raise RuntimeError("autonomy orchestrator unavailable")
            result = await orchestrator.process(prompt, platform=kwargs.get("platform", "os"), session=kwargs.get("session_id", ""))
            return {
                "reply": result.reply,
                "intent": result.intent,
                "emotion": result.emotion,
                "route": result.route,
                "plan": result.plan,
                "model_used": result.model_used,
            }
        except Exception:
            return await self._assistant_tool(prompt=prompt, context=kwargs.get("context"))

    async def _memory_tool(self, query: str = "", top_k: int = 5, **kwargs) -> Dict[str, Any]:
        if not self.world_model:
            return {"results": [], "count": 0}
        results = await self.world_model.query(query, top_k=top_k)
        return {"results": results, "count": len(results)}

    async def _filesystem_tool(
        self,
        path: str = ".",
        action: str = "read",
        content: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        target = Path(path).expanduser().resolve()
        if action == "read":
            if not target.exists():
                return {"content": "", "exists": False}
            return {"content": target.read_text(encoding="utf-8"), "exists": True, "path": str(target)}
        if action == "list":
            if not target.exists():
                return {"entries": [], "exists": False}
            return {
                "entries": [
                    {"name": entry.name, "is_dir": entry.is_dir(), "path": str(entry)}
                    for entry in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
                ],
                "exists": True,
                "path": str(target),
            }
        if action == "write":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"written": True, "path": str(target), "bytes": len(content.encode("utf-8"))}
        return {"error": f"Unsupported filesystem action: {action}"}

    async def _automation_tool(self, command: str = "", **kwargs) -> Dict[str, Any]:
        normalized = self._normalize_automation_command(command)
        if self._looks_browser_native(normalized):
            browser_result = await self._browser_tool(command=normalized, context=kwargs.get("context"))
            if browser_result.get("success") or browser_result.get("error") != "Unsupported browser action.":
                return browser_result
        try:
            from automation.pc_automation import execute_command

            return execute_command(normalized)
        except Exception as exc:
            fallback = self._fallback_automation(normalized)
            if fallback:
                fallback["warning"] = str(exc)
                return fallback
            return {"success": False, "error": str(exc), "command": command}

    async def _vision_tool(self, prompt: str = "", image_b64: str = "", **kwargs) -> Dict[str, Any]:
        if image_b64:
            return {"status": "accepted", "prompt": prompt, "image_supplied": True}
        try:
            from vision.face_recognition import face_recognizer

            return {"status": "ready", "known_faces": getattr(face_recognizer, "known_faces", None)}
        except Exception as exc:
            return {"status": "unavailable", "error": str(exc), "prompt": prompt}

    async def _adb_tool(self, command: str = "", **kwargs) -> Dict[str, Any]:
        try:
            from automation.adb_controller import ADBController

            controller = ADBController()
            return {"result": controller.run(command), "command": command}
        except Exception as exc:
            return {"error": str(exc), "command": command}

    async def _learning_tool(self, prompt: str = "", topic: str = "", **kwargs) -> Dict[str, Any]:
        if not self.world_model:
            return {"status": "unavailable"}
        memories = await self.world_model.query(topic or prompt, top_k=5)
        return {
            "status": "ready",
            "topic": topic or prompt,
            "supporting_memories": memories,
        }

    async def _workspace_tool(self, query: str = "", path: str = ".", **kwargs) -> Dict[str, Any]:
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return {"error": f"Workspace path not found: {root}"}
        summary = self._workspace_summary(root)
        return {
            "summary": summary,
            "workspace_root": str(root),
            "query": query,
        }

    async def _browser_tool(
        self,
        command: str = "",
        target: str = "",
        query: str = "",
        action: str = "",
        max_chars: int = 4000,
        **kwargs,
    ) -> Dict[str, Any]:
        if not self.browser:
            return {"success": False, "error": "Browser controller is unavailable."}
        context = kwargs.get("context") or {}
        normalized = self._normalize_automation_command(command or query or target)
        lowered = normalized.lower().strip()
        site = self._extract_site_name(lowered) or self._site_from_context(context)

        if action == "scrape_page" or lowered in {"scrape page", "read page", "extract page"}:
            result = self.browser.scrape_page(target=target, max_chars=max_chars)
            if "site" not in result:
                result["site"] = site
            return result
        if action == "summarize_page" or lowered in {"summarize page", "summarise page"}:
            snapshot = self.browser.scrape_page(target=target, max_chars=max_chars)
            if not snapshot.get("success"):
                return snapshot
            summary = self._summarize_browser_snapshot(snapshot)
            return {
                **snapshot,
                "action": "summarize_page",
                "summary": summary,
                "speech": summary,
            }

        if lowered.startswith("open chrome"):
            remainder = re.sub(r"^open chrome\b", "", normalized, flags=re.IGNORECASE).strip()
            target = target or remainder or "google"
            result = self.browser.open(target)
            result.setdefault("site", self._extract_site_name(target) or site or "google")
            return result
        if target:
            result = self.browser.open(target)
            result["site"] = self._extract_site_name(target) or site
            return result
        if lowered.startswith(("search ", "google ")):
            effective_query = re.sub(r"^(search|google)\s+", "", normalized, flags=re.IGNORECASE).strip()
            if self._extract_site_name(effective_query):
                result = self.browser.open(self._extract_site_name(effective_query))
                result["site"] = self._extract_site_name(effective_query)
                return result
        result = self.browser.perform(normalized, context=context)
        if "site" not in result:
            result["site"] = site
        return result

    def _summarize_browser_snapshot(self, snapshot: Dict[str, Any]) -> str:
        title = (snapshot.get("title") or "").strip()
        text = (snapshot.get("text") or "").strip()
        url = (snapshot.get("url") or "").strip()
        if self.model_gateway and text:
            generated = self.model_gateway.generate(
                prompt=(
                    "Summarize the following browser page in 3 concise bullet-style sentences. "
                    f"Title: {title or 'Untitled'}. URL: {url}. Content: {text[:3500]}"
                ),
                task="reasoning",
            )
            if generated.get("ok") and generated.get("response"):
                return generated["response"].strip()
        if not text:
            return f"No readable content was captured from {url or 'the current page'}."
        sentences = re.split(r"(?<=[.!?])\s+", text)
        excerpt = " ".join(sentence for sentence in sentences[:3] if sentence).strip()
        if title:
            return f"{title}: {excerpt[:420]}".strip()
        return excerpt[:420] or f"Captured content from {url or 'the current page'}."

    async def _shell_tool(self, command: str = "", cwd: str = ".", timeout_s: int = 30, **kwargs) -> Dict[str, Any]:
        workdir = Path(cwd or ".").expanduser().resolve()
        if not workdir.exists():
            return {"success": False, "error": f"Shell cwd not found: {workdir}"}
        if os.name == "nt":
            cmd = ["powershell", "-NoProfile", "-Command", command]
        else:
            cmd = ["/bin/sh", "-lc", command]
        completed = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return {
            "success": completed.returncode == 0,
            "command": command,
            "cwd": str(workdir),
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "speech": completed.stdout.strip()[:280] or completed.stderr.strip()[:280] or f"Command finished with code {completed.returncode}.",
        }

    async def _skills_tool(self, action: str = "list", skill_name: str = "", **kwargs) -> Dict[str, Any]:
        if not self.skill_registry:
            return {"skills": [], "count": 0}
        if action == "get" and skill_name:
            skill = self.skill_registry.get_skill(skill_name)
            return {"skill": skill, "found": bool(skill)}
        skills = self.skill_registry.list_skills()
        return {"skills": skills, "count": len(skills)}

    async def _models_tool(self, action: str = "status", prompt: str = "", task: str = "chat", **kwargs) -> Dict[str, Any]:
        if not self.model_gateway:
            return {"ready": False, "error": "Model gateway unavailable."}
        if action == "generate" and prompt:
            return self.model_gateway.generate(prompt=prompt, task=task)
        return self.model_gateway.status()

    async def _gateway_tool(self, action: str = "status", channel: str = "", recipient: str = "", message: str = "", **kwargs) -> Dict[str, Any]:
        if not self.gateway:
            return {"error": "Gateway unavailable."}
        if action == "send" and channel and message:
            lowered = channel.lower()
            transport_result: Dict[str, Any] = {"success": True}
            if lowered in {"whatsapp", "instagram"}:
                try:
                    from automation.messaging import messaging

                    target = recipient or kwargs.get("recipient") or kwargs.get("target") or ""
                    if lowered == "whatsapp":
                        success = messaging.send_whatsapp(target, message) if target else False
                    else:
                        success = messaging.send_instagram_dm(target, message) if target else False
                    transport_result = {"success": bool(success), "recipient": target, "channel": lowered}
                except Exception as exc:
                    transport_result = {"success": False, "error": str(exc), "channel": lowered}
            self.gateway.record_message(channel=channel, direction="outbound", content=message, metadata={**kwargs, **transport_result})
            return {"channel": channel, "message": message[:200], **transport_result}
        return self.gateway.status()

    async def _mobile_tool(self, action: str = "status", target: str = "", scope: str = "messages", **kwargs) -> Dict[str, Any]:
        if not self.mobile_sync:
            return {"error": "Mobile sync unavailable."}
        if action == "scan":
            return {"devices": self.mobile_sync.scan_devices()}
        if action == "queue_sync":
            return self.mobile_sync.queue_sync(target=target or "android", scope=scope)
        return self.mobile_sync.status()

    async def _scheduler_tool(self, action: str = "status", job_name: str = "", prompt: str = "", interval_s: int = 3600, channel: str = "local", **kwargs) -> Dict[str, Any]:
        if not self.scheduler:
            return {"error": "Scheduler unavailable."}
        if action == "add" and job_name and prompt:
            return self.scheduler.add_job(name=job_name, prompt=prompt, interval_s=interval_s, channel=channel)
        return self.scheduler.status()

    async def _access_tool(self, action: str = "status", profile: str = "", scope: str = "", ticket_id: str = "", reason: str = "", **kwargs) -> Dict[str, Any]:
        if not self.access_manager:
            return {"error": "Access manager unavailable."}
        if action == "grant" and profile:
            return self.access_manager.grant_profile(profile)
        if action == "request" and scope:
            return self.access_manager.request_approval(action=kwargs.get("requested_action", scope), scope=scope, reason=reason)
        if action == "approve" and ticket_id:
            return self.access_manager.approve(ticket_id)
        if action == "reject" and ticket_id:
            return self.access_manager.reject(ticket_id)
        return self.access_manager.status()

    async def _realtime_tool(self, query: str = "", **kwargs) -> Dict[str, Any]:
        lowered = query.lower().strip()
        now = dt.datetime.now().astimezone()
        if any(token in lowered for token in ["date today", "today's date", "what is date today", "what is the date", "date today"]):
            return {"response": f"Today's date is {now.strftime('%B %d, %Y')}."}
        if any(token in lowered for token in ["time now", "current time", "what time", "time today"]):
            return {"response": f"The current time is {now.strftime('%I:%M %p %Z')}."}
        if "news" in lowered or "latest" in lowered:
            return {"response": self._fetch_news(query), "source": "google_news_rss"}
        if lowered.startswith("who is ") or lowered.startswith("what is ") or lowered.startswith("tell me about "):
            return {"response": self._fetch_fact(query), "source": "duckduckgo"}
        return {"response": f"Current local date and time: {now.strftime('%B %d, %Y, %I:%M %p %Z')}."}

    def _direct_response(self, prompt: str) -> str:
        lowered = prompt.lower().strip()
        now = dt.datetime.now().astimezone()
        if lowered in {"hi", "hello", "hey", "yo", "hi jarvis", "hello jarvis", "hey jarvis"}:
            return "Hello. What do you want me to do?"
        if lowered in {"who are you", "who r u", "who are u"}:
            return "I'm JARVIS, your personal AI assistant."
        if any(token in lowered for token in ["date today", "today's date", "what is date today", "what is the date"]):
            return f"Today's date is {now.strftime('%B %d, %Y')}."
        if any(token in lowered for token in ["what time is it", "current time", "time now"]):
            return f"The current time is {now.strftime('%I:%M %p %Z')}."
        return ""

    def _normalize_automation_command(self, command: str) -> str:
        normalized = command.strip()
        replacements = {
            "whatapp": "whatsapp",
            "watsapp": "whatsapp",
            "serch": "search",
            "amzon": "amazon",
            "amazone": "amazon",
            "amaozn": "amazon",
            "msg ": "message ",
        }
        for source, target in replacements.items():
            normalized = re.sub(source, target, normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^\s*search for\b", "google ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^\s*search github\b", "google github", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\binto cart\b", "add to cart", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bin to cart\b", "add to cart", normalized, flags=re.IGNORECASE)
        return normalized

    def _fetch_news(self, query: str) -> str:
        topic = "India" if "india" in query.lower() else query
        rss_url = "https://news.google.com/rss/search?q=" + parse.quote(topic)
        rss_url += "&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            with request.urlopen(rss_url, timeout=10) as response:
                xml_bytes = response.read()
            root = ET.fromstring(xml_bytes)
            items = root.findall(".//item")[:3]
            headlines = []
            for item in items:
                title = (item.findtext("title") or "").strip()
                if title:
                    headlines.append(title)
            if headlines:
                return "Top live headlines: " + " | ".join(headlines)
        except Exception as exc:
            logger.debug("News fetch failed: %s", exc)
        return "I couldn't fetch live news right now."

    def _fetch_fact(self, query: str) -> str:
        try:
            url = "https://api.duckduckgo.com/?" + parse.urlencode(
                {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
            )
            with request.urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            abstract = (payload.get("AbstractText") or "").strip()
            heading = (payload.get("Heading") or "").strip()
            if abstract:
                return f"{heading}: {abstract}" if heading else abstract
            related = payload.get("RelatedTopics") or []
            for item in related:
                text = (item.get("Text") if isinstance(item, dict) else "") or ""
                if text:
                    return text
        except Exception as exc:
            logger.debug("Fact lookup failed: %s", exc)
        return "I couldn't verify that from a live source right now."

    def _workspace_summary(self, root: Path) -> str:
        manifest_names = [
            "pyproject.toml",
            "requirements.txt",
            "package.json",
            "pubspec.yaml",
            "README.md",
            "setup.py",
        ]
        manifests = [name for name in manifest_names if (root / name).exists()]
        top_entries = []
        try:
            entries = sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            for entry in entries[:12]:
                top_entries.append(entry.name + ("/" if entry.is_dir() else ""))
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")
        readme_excerpt = ""
        readme = root / "README.md"
        if readme.exists():
            try:
                readme_excerpt = readme.read_text(encoding="utf-8", errors="replace")[:500].replace("\n", " ").strip()
            except Exception:
                readme_excerpt = ""
        return (
            f"Workspace: {root}. "
            f"Top-level entries: {', '.join(top_entries) or 'none'}. "
            f"Detected manifests: {', '.join(manifests) or 'none'}. "
            f"README summary: {readme_excerpt or 'not available'}"
        )

    def _fallback_automation(self, command: str) -> Dict[str, Any]:
        lowered = command.lower().strip()
        website_map = {
            "instagram": "https://www.instagram.com/",
            "whatsapp": "https://web.whatsapp.com/",
            "github": "https://github.com/",
            "gmail": "https://mail.google.com/",
            "youtube": "https://www.youtube.com/",
        }
        if any(token in lowered for token in ("login as", "log in as", "sign in as")) or lowered.startswith(("login ", "log in ", "sign in ")):
            return {
                "success": False,
                "error": "Login automation is not configured yet. I can open the app or site, but sign-in needs a browser controller.",
                "action": "login",
            }
        if lowered.startswith("open chrome"):
            return self._open_app_fallback("chrome")
        if lowered.startswith("open "):
            target = lowered[5:].strip()
            target = re.sub(r"\bin chrome\b", "", target, flags=re.IGNORECASE).strip()
            target = re.sub(r"\band.*$", "", target, flags=re.IGNORECASE).strip()
            if target in website_map:
                webbrowser.open(website_map[target])
                return {"success": True, "speech": f"Opening {target}.", "action": "open_url", "url": website_map[target]}
            if "." in target and " " not in target:
                url = target if target.startswith(("http://", "https://")) else f"https://{target}"
                webbrowser.open(url)
                return {"success": True, "speech": f"Opening {url}.", "action": "open_url"}
            return self._open_app_fallback(target)
        if lowered.startswith("google ") or lowered.startswith("search "):
            query = re.sub(r"^(google|search)\s+", "", command, flags=re.IGNORECASE).strip()
            url = "https://www.google.com/search?q=" + parse.quote_plus(query)
            webbrowser.open(url)
            return {"success": True, "speech": f"Searching Google for {query}.", "action": "google"}
        return {}

    def _looks_browser_native(self, command: str) -> bool:
        lowered = command.lower()
        return any(
            token in lowered
            for token in (
                "chrome",
                "search ",
                "google ",
                "website",
                "amazon",
                "flipkart",
                "cart",
                "checkout",
                "in chrome",
                "instagram",
                "whatsapp",
                "github",
            )
        )

    def _extract_site_name(self, text: str) -> str:
        lowered = text.lower()
        for site in ("amazon", "flipkart", "instagram", "whatsapp", "github", "google", "youtube"):
            if site in lowered:
                return site
        return ""

    def _site_from_context(self, context: Dict[str, Any]) -> str:
        last_output = context.get("last_step_output")
        if isinstance(last_output, dict):
            for key in ("site", "target", "url", "speech"):
                value = str(last_output.get(key, "")).lower()
                site = self._extract_site_name(value)
                if site:
                    return site
        for step in reversed(context.get("completed_steps", [])):
            output = step.get("output", {})
            if isinstance(output, dict):
                for key in ("site", "target", "url", "speech"):
                    value = str(output.get(key, "")).lower()
                    site = self._extract_site_name(value)
                    if site:
                        return site
            site = self._extract_site_name(step.get("action", ""))
            if site:
                return site
        return ""

    def _extract_search_query(self, text: str, site: str = "") -> str:
        normalized = re.sub(rf"^in\s+{re.escape(site)}\s+", "", text, flags=re.IGNORECASE).strip() if site else text.strip()
        normalized = re.sub(r"^(search|google)\s+", "", normalized, flags=re.IGNORECASE).strip()
        normalized = re.sub(r"^for\s+", "", normalized, flags=re.IGNORECASE).strip()
        return normalized or site

    def _browser_site_search(self, site: str, search_query: str) -> Dict[str, Any]:
        urls = {
            "amazon": "https://www.amazon.in/s?k=" + parse.quote_plus(search_query),
            "flipkart": "https://www.flipkart.com/search?q=" + parse.quote_plus(search_query),
            "youtube": "https://www.youtube.com/results?search_query=" + parse.quote_plus(search_query),
            "github": "https://github.com/search?q=" + parse.quote_plus(search_query),
        }
        url = urls.get(site)
        if not url:
            return self.browser.search(search_query)
        webbrowser.open(url)
        return {
            "success": True,
            "site": site,
            "query": search_query,
            "url": url,
            "speech": f"Searching {site} for {search_query}.",
        }

    def _is_cart_action(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in ("add to cart", "cart", "checkout", "buy now"))


    def _open_app_fallback(self, app: str) -> Dict[str, Any]:
        try:
            if os.name == "nt":
                subprocess.Popen(["cmd", "/c", "start", "", app], shell=False)
            else:
                webbrowser.open(app)
            return {"success": True, "speech": f"Opening {app}.", "action": "open_app"}
        except Exception as exc:
            return {"success": False, "error": str(exc), "action": "open_app"}
