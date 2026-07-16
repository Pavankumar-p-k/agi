from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Capability:
    id: str
    version: int = 1
    category: str = ""
    description: str = ""
    risk: str = "medium"
    permissions: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches(self, goal: str) -> bool:
        goal_lower = goal.lower()
        if self.id in goal_lower:
            return True
        for tag in self.tags:
            if tag in goal_lower:
                return True
        for inp in self.inputs:
            if inp in goal_lower:
                return True
        for out in self.outputs:
            if out in goal_lower:
                return True
        return False

    def compatible_with(self, other: Capability) -> bool:
        my_outputs = set(self.outputs)
        their_inputs = set(other.inputs)
        return bool(my_outputs & their_inputs) if my_outputs and their_inputs else True


_BUILTIN_CAPABILITIES: dict[str, Capability] = {
    "coding": Capability(
        id="coding", version=1, category="development", risk="medium",
        description="Software development and code generation",
        permissions=("filesystem.read", "filesystem.write"),
        inputs=("requirement", "specification", "task"),
        outputs=("source_code", "patch"),
        tags=("code", "programming", "develop", "implement", "feature"),
    ),
    "browser": Capability(
        id="browser", version=1, category="automation", risk="high",
        description="Web browsing and page interaction",
        permissions=("network.http",),
        inputs=("url", "search_query", "selector"),
        outputs=("screenshot", "dom_snapshot", "page_text"),
        tags=("web", "browse", "navigate", "search", "scrape"),
    ),
    "vision": Capability(
        id="vision", version=1, category="perception", risk="medium",
        description="Image understanding and analysis",
        permissions=(),
        inputs=("image", "screenshot"),
        outputs=("description", "analysis", "ocr_text"),
        tags=("image", "see", "screen", "ocr", "read"),
    ),
    "deployment": Capability(
        id="deployment", version=1, category="operations", risk="critical",
        description="Application deployment and hosting",
        permissions=("network.http", "filesystem.read"),
        inputs=("build_artifact", "configuration"),
        outputs=("deployment_url", "deployment_status"),
        tags=("deploy", "publish", "host", "release"),
    ),
    "testing": Capability(
        id="testing", version=1, category="development", risk="low",
        description="Automated test execution and generation",
        permissions=("filesystem.read", "filesystem.write"),
        inputs=("source_code", "test_file"),
        outputs=("test_result", "coverage_report"),
        tags=("test", "assert", "verify", "validate", "coverage"),
    ),
    "documentation": Capability(
        id="documentation", version=1, category="development", risk="low",
        description="Documentation generation and management",
        permissions=("filesystem.read", "filesystem.write"),
        inputs=("source_code", "api_schema"),
        outputs=("documentation", "readme"),
        tags=("doc", "document", "readme", "wiki"),
    ),
    "security": Capability(
        id="security", version=1, category="analysis", risk="medium",
        description="Security analysis and auditing",
        permissions=("filesystem.read",),
        inputs=("source_code", "dependency_list"),
        outputs=("security_report", "vulnerability_list"),
        tags=("security", "audit", "vulnerability", "cve"),
    ),
    "research": Capability(
        id="research", version=1, category="knowledge", risk="low",
        description="Information gathering and analysis",
        permissions=("network.http",),
        inputs=("question", "topic", "query"),
        outputs=("research_report", "fact_list", "summary"),
        tags=("search", "research", "investigate", "learn", "gather"),
    ),
    "database": Capability(
        id="database", version=1, category="data", risk="high",
        description="Database operations and management",
        permissions=("network.http", "filesystem.read"),
        inputs=("query", "schema", "connection_string"),
        outputs=("query_result", "migration_script"),
        tags=("db", "sql", "database", "query", "migrate"),
    ),
    "notifications": Capability(
        id="notifications", version=1, category="communication", risk="medium",
        description="Push notifications and alerts",
        permissions=("network.http",),
        inputs=("message", "recipient", "channel"),
        outputs=("notification_status",),
        tags=("notify", "alert", "push"),
    ),
    "filesystem": Capability(
        id="filesystem", version=1, category="infrastructure", risk="high",
        description="File system operations",
        permissions=("filesystem.read", "filesystem.write"),
        inputs=("path", "pattern"),
        outputs=("file_content", "file_list"),
        tags=("file", "read", "write", "list", "search"),
    ),
    "desktop": Capability(
        id="desktop", version=1, category="automation", risk="critical",
        description="Desktop automation",
        permissions=(
            "desktop.window.read", "desktop.mouse.move",
            "desktop.mouse.click", "desktop.keyboard.type",
            "desktop.screen.capture",
        ),
        inputs=("window_title", "mouse_position", "key_sequence"),
        outputs=("screenshot", "window_list"),
        tags=("desktop", "automation", "window", "mouse", "keyboard", "screen"),
    ),
    "email": Capability(
        id="email", version=1, category="communication", risk="medium",
        description="Email sending and management",
        permissions=("network.smtp",),
        inputs=("to", "subject", "body", "attachment"),
        outputs=("email_status", "message_id"),
        tags=("email", "mail", "send", "inbox"),
    ),
    "messaging": Capability(
        id="messaging", version=1, category="communication", risk="medium",
        description="Messaging platform integration",
        permissions=("network.http",),
        inputs=("message", "recipient", "platform"),
        outputs=("message_status",),
        tags=("message", "chat", "slack", "discord", "whatsapp"),
    ),
    "terminal": Capability(
        id="terminal", version=1, category="infrastructure", risk="critical",
        description="Terminal and shell operations",
        permissions=("process.list", "process.control", "filesystem.read"),
        inputs=("command", "working_directory"),
        outputs=("stdout", "stderr", "exit_code"),
        tags=("terminal", "shell", "command", "exec", "run"),
    ),
    "voice": Capability(
        id="voice", version=1, category="perception", risk="low",
        description="Voice processing and synthesis",
        permissions=(),
        inputs=("text", "audio"),
        outputs=("audio", "transcription"),
        tags=("voice", "speak", "speech", "audio"),
    ),
    "speech": Capability(
        id="speech", version=1, category="perception", risk="low",
        description="Speech-to-text and text-to-speech",
        permissions=(),
        inputs=("audio", "text"),
        outputs=("text", "audio"),
        tags=("stt", "tts", "transcribe", "synthesize"),
    ),
    "translation": Capability(
        id="translation", version=1, category="knowledge", risk="low",
        description="Language translation",
        permissions=("network.http",),
        inputs=("text", "source_language", "target_language"),
        outputs=("translated_text",),
        tags=("translate", "lang"),
    ),
    "image_generation": Capability(
        id="image_generation", version=1, category="creative", risk="medium",
        description="AI image generation",
        permissions=("network.http",),
        inputs=("prompt", "style", "size"),
        outputs=("image",),
        tags=("generate", "create", "draw", "art"),
    ),
    "automation": Capability(
        id="automation", version=1, category="infrastructure", risk="high",
        description="General workflow automation",
        permissions=(
            "filesystem.read", "filesystem.write", "network.http",
        ),
        inputs=("workflow_definition", "trigger"),
        outputs=("workflow_result",),
        tags=("automate", "workflow", "pipeline", "schedule"),
    ),
}

BUILTIN_CAPABILITY_IDS = frozenset(_BUILTIN_CAPABILITIES.keys())
