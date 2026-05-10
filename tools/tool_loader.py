from __future__ import annotations

from typing import Any, Callable, Dict, Iterable

from .base_tool import ToolDefinition
from .registry import ToolRegistry, new_registry


def _delegate(router: Any, base_tool: str, defaults: Dict[str, Any] | None = None, builder: Callable[[dict], dict] | None = None):
    defaults = defaults or {}

    async def _handler(**kwargs):
        payload = {**defaults, **kwargs}
        if builder is not None:
            payload = builder(payload)
        return await router.invoke(base_tool, **payload)

    return _handler


def _prompt_builder(template: str, field: str = "query"):
    def _builder(payload: dict) -> dict:
        value = payload.get(field) or payload.get("prompt") or payload.get("text") or ""
        payload["prompt"] = template.format(value=value)
        return payload

    return _builder


def _definitions(router: Any) -> Iterable[ToolDefinition]:
    browser_sites = ["google", "amazon", "flipkart", "github", "instagram", "whatsapp", "youtube", "gmail", "slack", "telegram", "discord"]
    search_sites = ["google", "amazon", "flipkart", "github", "youtube"]
    shell_commands = {
        "system.run_terminal_command": "",
        "system.git_status": "git status",
        "system.git_diff": "git diff --stat",
        "system.list_processes": "Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 ProcessName,CPU,Id",
        "system.python_version": "python --version",
        "system.pip_list": "pip list",
        "system.cwd": "Get-Location",
        "devops.pytest": "pytest",
        "devops.ruff": "ruff check .",
        "devops.format_check": "python -m compileall backend",
    }
    file_actions = {
        "files.read_file": {"action": "read"},
        "files.list_directory": {"action": "list"},
        "files.inspect_workspace": {"action": "list"},
    }

    defs: list[ToolDefinition] = []
    for site in browser_sites:
        defs.append(
            ToolDefinition(
                name=f"browser.open_{site}",
                description=f"Open {site} in the local browser controller.",
                category="browser",
                permission="desktop",
                input_schema={"target": {"type": "string", "default": site}},
                capabilities=["browser", "navigation"],
                risk_tags=["browser_control"],
                handler=_delegate(router, "browser", {"target": site}),
            )
        )
        defs.append(
            ToolDefinition(
                name=f"browser.login_{site}",
                description=f"Open {site} login flow using the browser controller.",
                category="browser",
                permission="interactive",
                input_schema={"command": {"type": "string", "default": f"login {site}"}},
                capabilities=["browser", "auth"],
                risk_tags=["browser_control", "credentials"],
                handler=_delegate(router, "browser", {"command": f"login {site}"}),
            )
        )
    for site in search_sites:
        defs.append(
            ToolDefinition(
                name=f"browser.search_{site}",
                description=f"Search {site} for a query.",
                category="browser",
                permission="desktop",
                input_schema={"query": {"type": "string", "required": True}},
                capabilities=["browser", "search"],
                risk_tags=["browser_control"],
                handler=_delegate(router, "browser", builder=lambda payload, site=site: {**payload, "command": f"in {site} search {payload.get('query', '')}".strip()}),
            )
        )
    defs.extend(
        [
            ToolDefinition(
                name="browser.open_url",
                description="Open an arbitrary URL in the browser controller.",
                category="browser",
                permission="desktop",
                input_schema={"target": {"type": "string", "required": True}},
                capabilities=["browser", "navigation"],
                risk_tags=["browser_control"],
                handler=_delegate(router, "browser"),
            ),
            ToolDefinition(
                name="browser.search_news",
                description="Search the web for news on a topic.",
                category="browser",
                permission="desktop",
                input_schema={"query": {"type": "string", "required": True}},
                capabilities=["browser", "news"],
                risk_tags=["browser_control"],
                handler=_delegate(router, "browser", builder=lambda payload: {**payload, "command": f"search latest news {payload.get('query', '')}".strip()}),
            ),
            ToolDefinition(
                name="browser.scrape_page",
                description="Extract readable content from the current page or a provided URL.",
                category="browser",
                permission="desktop",
                input_schema={"target": {"type": "string", "default": ""}, "max_chars": {"type": "integer", "default": 4000}},
                capabilities=["browser", "scrape", "content"],
                risk_tags=["browser_control"],
                read_only=True,
                handler=_delegate(router, "browser", {"action": "scrape_page"}),
            ),
            ToolDefinition(
                name="browser.summarize_page",
                description="Summarize the current page or a provided URL.",
                category="browser",
                permission="desktop",
                input_schema={"target": {"type": "string", "default": ""}, "max_chars": {"type": "integer", "default": 4000}},
                capabilities=["browser", "summary", "content"],
                risk_tags=["browser_control"],
                read_only=True,
                handler=_delegate(router, "browser", {"action": "summarize_page"}),
            ),
            ToolDefinition(
                name="browser.add_to_cart",
                description="Attempt add-to-cart on the active shopping page.",
                category="browser",
                permission="approval_required",
                input_schema={"command": {"type": "string", "default": "add to cart"}},
                capabilities=["browser", "shopping"],
                risk_tags=["browser_control", "commerce"],
                handler=_delegate(router, "browser", {"command": "add to cart"}),
            ),
            ToolDefinition(
                name="browser.click_text",
                description="Click visible text on the active page when DOM control is available.",
                category="browser",
                permission="interactive",
                input_schema={"command": {"type": "string", "required": True}},
                capabilities=["browser", "dom"],
                risk_tags=["browser_control"],
                handler=_delegate(router, "browser", builder=lambda payload: {**payload, "command": f"click {payload.get('command', '')}".strip()}),
            ),
        ]
    )

    for name, defaults in file_actions.items():
        defs.append(
            ToolDefinition(
                name=name,
                description=f"Filesystem helper for {defaults['action']} operations.",
                category="filesystem",
                permission="workspace",
                input_schema={"path": {"type": "string", "required": True}},
                capabilities=["files", defaults["action"]],
                risk_tags=["io"],
                handler=_delegate(router, "filesystem", defaults),
            )
        )
    defs.extend(
        [
            ToolDefinition(
                name="filesystem.workspace_summary",
                description="Summarize the current workspace for coding tasks.",
                category="filesystem",
                permission="workspace",
                input_schema={"path": {"type": "string", "default": "."}, "query": {"type": "string", "default": "workspace summary"}},
                capabilities=["workspace", "review"],
                risk_tags=["io"],
                read_only=True,
                handler=_delegate(router, "workspace"),
            ),
            ToolDefinition(
                name="filesystem.project_review",
                description="Review a project or repository structure.",
                category="filesystem",
                permission="workspace",
                input_schema={"path": {"type": "string", "default": "."}, "query": {"type": "string", "required": True}},
                capabilities=["workspace", "review"],
                risk_tags=["io"],
                read_only=True,
                handler=_delegate(router, "workspace"),
            ),
        ]
    )

    for name, command in shell_commands.items():
        defs.append(
            ToolDefinition(
                name=name,
                description=f"Shell helper for `{command or 'custom command'}`.",
                category="system" if name.startswith("system.") else "devops",
                permission="approval_required",
                input_schema={"command": {"type": "string", "default": command}, "cwd": {"type": "string", "default": "."}},
                capabilities=["shell", "terminal"],
                risk_tags=["shell_execution"],
                handler=_delegate(router, "shell", {"command": command} if command else {}),
            )
        )

    defs.extend(
        [
            ToolDefinition(
                name="internet.fetch_url",
                description="Fetch a URL or fact through the realtime tool.",
                category="internet",
                permission="read_only",
                input_schema={"query": {"type": "string", "required": True}},
                capabilities=["web_lookup", "facts"],
                read_only=True,
                handler=_delegate(router, "realtime"),
            ),
            ToolDefinition(
                name="internet.search_news",
                description="Fetch latest news headlines for a topic.",
                category="internet",
                permission="read_only",
                input_schema={"query": {"type": "string", "required": True}},
                capabilities=["news", "rss"],
                read_only=True,
                handler=_delegate(router, "realtime", builder=lambda payload: {**payload, "query": f"latest news {payload.get('query', '')}".strip()}),
            ),
            ToolDefinition(
                name="internet.current_time",
                description="Return the current local time.",
                category="internet",
                permission="read_only",
                input_schema={},
                capabilities=["time"],
                read_only=True,
                handler=_delegate(router, "realtime", {"query": "current time"}),
            ),
            ToolDefinition(
                name="internet.current_date",
                description="Return the current local date.",
                category="internet",
                permission="read_only",
                input_schema={},
                capabilities=["date"],
                read_only=True,
                handler=_delegate(router, "realtime", {"query": "today's date"}),
            ),
        ]
    )

    ai_templates = {
        "ai.summarize_text": "Summarize this text clearly: {value}",
        "ai.explain_text": "Explain this clearly: {value}",
        "ai.classify_text": "Classify the following content and explain the label briefly: {value}",
        "ai.extract_entities": "Extract key entities, names, and topics from: {value}",
        "ai.generate_documentation": "Generate concise technical documentation for: {value}",
        "ai.analyze_code": "Analyze this code and report issues, strengths, and next steps: {value}",
        "ai.debug_code": "Debug this code or error report and suggest the most likely fix: {value}",
        "ai.reason_about_task": "Reason step by step about this task and propose the next actions: {value}",
    }
    for name, template in ai_templates.items():
        defs.append(
            ToolDefinition(
                name=name,
                description=f"AI helper for {name.split('.', 1)[1].replace('_', ' ')}.",
                category="ai",
                permission="read_only",
                input_schema={"query": {"type": "string", "required": True}},
                capabilities=["ai", "language"],
                read_only=True,
                handler=_delegate(router, "assistant_chat", builder=_prompt_builder(template)),
            )
        )

    model_actions = {
        "models.status": {"action": "status"},
        "models.list": {"action": "status"},
        "models.generate_chat": {"action": "generate", "task": "chat"},
        "models.generate_code": {"action": "generate", "task": "coding"},
        "models.generate_reasoning": {"action": "generate", "task": "reasoning"},
    }
    for name, defaults in model_actions.items():
        defs.append(
            ToolDefinition(
                name=name,
                description=f"Model gateway action `{defaults['action']}`.",
                category="models",
                permission="read_only" if defaults["action"] == "status" else "standard",
                input_schema={"prompt": {"type": "string", "required": defaults['action'] == 'generate'}},
                capabilities=["models", "ollama"],
                read_only=defaults["action"] == "status",
                handler=_delegate(router, "models", defaults),
            )
        )

    gateway_channels = ["whatsapp", "instagram", "slack", "discord", "local"]
    for channel in gateway_channels:
        defs.append(
            ToolDefinition(
                name=f"communication.send_{channel}",
                description=f"Send a message through the {channel} gateway.",
                category="communication",
                permission="approval_required",
                input_schema={"message": {"type": "string", "required": True}, "recipient": {"type": "string", "default": ""}},
                capabilities=["messaging", channel],
                risk_tags=["message_send"],
                handler=_delegate(router, "gateway", {"action": "send", "channel": channel}),
            )
        )
    defs.extend(
        [
            ToolDefinition(
                name="communication.gateway_status",
                description="Inspect gateway status and recent channels.",
                category="communication",
                permission="read_only",
                input_schema={},
                capabilities=["messaging", "status"],
                read_only=True,
                handler=_delegate(router, "gateway", {"action": "status"}),
            ),
            ToolDefinition(
                name="mobile.scan_devices",
                description="Scan for connected mobile devices.",
                category="mobile",
                permission="read_only",
                input_schema={},
                capabilities=["mobile", "scan"],
                read_only=True,
                handler=_delegate(router, "mobile", {"action": "scan"}),
            ),
            ToolDefinition(
                name="mobile.queue_sync",
                description="Queue a mobile sync job.",
                category="mobile",
                permission="approval_required",
                input_schema={"target": {"type": "string", "default": "android"}, "scope": {"type": "string", "default": "messages"}},
                capabilities=["mobile", "sync"],
                handler=_delegate(router, "mobile", {"action": "queue_sync"}),
            ),
            ToolDefinition(
                name="scheduler.status",
                description="Get scheduler heartbeat and job status.",
                category="automation",
                permission="read_only",
                input_schema={},
                capabilities=["schedule", "status"],
                read_only=True,
                handler=_delegate(router, "scheduler", {"action": "status"}),
            ),
            ToolDefinition(
                name="scheduler.add_job",
                description="Add a recurring autonomous scheduler job.",
                category="automation",
                permission="approval_required",
                input_schema={"job_name": {"type": "string", "required": True}, "prompt": {"type": "string", "required": True}, "interval_s": {"type": "integer", "default": 3600}},
                capabilities=["schedule", "automation"],
                handler=_delegate(router, "scheduler", {"action": "add"}),
            ),
            ToolDefinition(
                name="access.status",
                description="Inspect approval and access state.",
                category="security",
                permission="read_only",
                input_schema={},
                capabilities=["permissions", "approval"],
                read_only=True,
                handler=_delegate(router, "access", {"action": "status"}),
            ),
            ToolDefinition(
                name="access.request_scope",
                description="Request approval for an access scope.",
                category="security",
                permission="approval_required",
                input_schema={"scope": {"type": "string", "required": True}, "reason": {"type": "string", "default": ""}},
                capabilities=["permissions", "approval"],
                handler=_delegate(router, "access", {"action": "request"}),
            ),
            ToolDefinition(
                name="memory.search",
                description="Search semantic memory for related experiences.",
                category="memory",
                permission="read_only",
                input_schema={"query": {"type": "string", "required": True}},
                capabilities=["memory", "search"],
                read_only=True,
                handler=_delegate(router, "memory"),
            ),
            ToolDefinition(
                name="learning.status",
                description="Inspect learning engine status.",
                category="learning",
                permission="read_only",
                input_schema={},
                capabilities=["learning", "status"],
                read_only=True,
                handler=_delegate(router, "learning"),
            ),
            ToolDefinition(
                name="vision.describe_image",
                description="Bridge to the vision subsystem for image analysis.",
                category="vision",
                permission="sensor",
                input_schema={"image_b64": {"type": "string", "default": ""}},
                capabilities=["vision", "image"],
                risk_tags=["sensor"],
                handler=_delegate(router, "vision"),
            ),
            ToolDefinition(
                name="android.run_adb",
                description="Execute an Android bridge command.",
                category="automation",
                permission="approval_required",
                input_schema={"command": {"type": "string", "required": True}},
                capabilities=["adb", "android"],
                risk_tags=["device_control"],
                handler=_delegate(router, "adb"),
            ),
            ToolDefinition(
                name="skills.list",
                description="List locally available JARVIS skills.",
                category="skills",
                permission="read_only",
                input_schema={},
                capabilities=["skills", "plugins"],
                read_only=True,
                handler=_delegate(router, "skills", {"action": "list"}),
            ),
        ]
    )

    # Reach 100+ working tools with safe semantic aliases around the live runtime.
    alias_templates = {
        "browser": ["open_workspace_docs", "open_project_readme", "open_latest_results", "search_support_docs", "search_release_notes", "search_error_message", "search_local_models", "search_python_fastapi", "search_flutter_windows", "search_ollama_models"],
        "filesystem": ["list_root", "list_backend", "list_apps", "list_docs", "review_backend", "review_flutter", "review_services", "review_memory", "review_autonomy", "review_tools"],
        "ai": ["summarize_workspace", "summarize_backend", "summarize_frontend", "summarize_logs", "explain_architecture", "write_release_notes", "draft_fix_plan", "draft_refactor_plan", "classify_issue", "extract_action_items"],
        "internet": ["latest_headlines", "latest_ai_news", "latest_python_news", "latest_flutter_news", "latest_ollama_news", "check_current_date", "check_current_time", "who_is_lookup", "what_is_lookup", "fact_lookup"],
        "communication": ["notify_local", "notify_whatsapp", "notify_instagram", "notify_slack", "notify_discord"],
    }
    for alias in alias_templates["browser"]:
        defs.append(ToolDefinition(name=f"browser.{alias}", description=f"Semantic browser alias `{alias}`.", category="browser", permission="desktop", input_schema={"query": {"type": "string", "default": alias.replace('_', ' ')}}, capabilities=["browser"], risk_tags=["browser_control"], handler=_delegate(router, "browser", builder=lambda payload, alias=alias: {**payload, "command": payload.get('query') or alias.replace('_', ' ')})))
    for alias in alias_templates["filesystem"]:
        defs.append(ToolDefinition(name=f"filesystem.{alias}", description=f"Semantic filesystem alias `{alias}`.", category="filesystem", permission="workspace", input_schema={"path": {"type": "string", "default": "."}, "query": {"type": "string", "default": alias.replace('_', ' ')}}, capabilities=["workspace"], read_only=True, handler=_delegate(router, "workspace", builder=lambda payload, alias=alias: {**payload, "query": payload.get('query') or alias.replace('_', ' ')})))
    for alias in alias_templates["ai"]:
        defs.append(ToolDefinition(name=f"ai.{alias}", description=f"Semantic AI alias `{alias}`.", category="ai", permission="read_only", input_schema={"query": {"type": "string", "required": True}}, capabilities=["ai"], read_only=True, handler=_delegate(router, "assistant_chat", builder=_prompt_builder(f"{alias.replace('_', ' ')}: {{value}}"))))
    for alias in alias_templates["internet"]:
        defs.append(ToolDefinition(name=f"internet.{alias}", description=f"Semantic internet alias `{alias}`.", category="internet", permission="read_only", input_schema={"query": {"type": "string", "default": alias.replace('_', ' ')}}, capabilities=["web_lookup"], read_only=True, handler=_delegate(router, "realtime", builder=lambda payload, alias=alias: {**payload, "query": payload.get('query') or alias.replace('_', ' ')})))
    for alias in alias_templates["communication"]:
        channel = alias.split('_', 1)[-1]
        defs.append(ToolDefinition(name=f"communication.{alias}", description=f"Semantic communication alias `{alias}`.", category="communication", permission="approval_required", input_schema={"message": {"type": "string", "required": True}}, capabilities=["messaging"], risk_tags=["message_send"], handler=_delegate(router, "gateway", {"action": "send", "channel": channel})))

    return defs


def load_router_tools(router: Any, registry: ToolRegistry | None = None) -> ToolRegistry:
    registry = registry or new_registry()
    for definition in _definitions(router):
        if registry.has(definition.name):
            continue
        registry.register(definition)
        router.register_tool(definition.to_router_spec(), definition.handler)
    return registry
