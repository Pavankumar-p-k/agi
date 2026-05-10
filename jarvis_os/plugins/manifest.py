from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..contracts import PluginManifestRecord, PluginWorkflowRecord


@dataclass(slots=True)
class PluginToolDefinition:
    name: str
    description: str
    category: str = "plugin"
    permission: str = "safe"
    read_only: bool = False
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    execution: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "permission": self.permission,
            "read_only": self.read_only,
            "parameters": dict(self.parameters),
            "keywords": list(self.keywords),
            "examples": list(self.examples),
            "execution": dict(self.execution),
        }


@dataclass(slots=True)
class PluginManifest:
    name: str
    version: str
    description: str
    root: Path
    tools: list[PluginToolDefinition] = field(default_factory=list)
    workflows: list[PluginWorkflowRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def plugin_id(self) -> str:
        return self.name.strip().lower().replace(" ", "_")

    def to_record(self) -> PluginManifestRecord:
        return PluginManifestRecord(
            name=self.name,
            version=self.version,
            description=self.description,
            path=str(self.root),
            tools=[tool.to_dict() for tool in self.tools],
            workflows=list(self.workflows),
            metadata=dict(self.metadata),
        )


def load_manifest(path: Path) -> PluginManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    name = str(payload.get("name", "")).strip()
    version = str(payload.get("version", "0.1.0")).strip()
    description = str(payload.get("description", "")).strip()
    if not name:
        raise ValueError(f"plugin manifest `{path}` is missing `name`")
    tools = [_tool_from_payload(item) for item in payload.get("tools", [])]
    workflows = [_workflow_from_payload(item) for item in payload.get("workflows", [])]
    return PluginManifest(
        name=name,
        version=version or "0.1.0",
        description=description or name,
        root=path.parent,
        tools=tools,
        workflows=workflows,
        metadata=dict(payload.get("metadata", {})),
    )


def _tool_from_payload(payload: dict[str, Any]) -> PluginToolDefinition:
    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip()
    execution = dict(payload.get("execution", {}))
    if not name:
        raise ValueError("plugin tool is missing `name`")
    if not execution or "type" not in execution:
        raise ValueError(f"plugin tool `{name}` is missing execution type")
    return PluginToolDefinition(
        name=name,
        description=description or name,
        category=str(payload.get("category", "plugin")),
        permission=str(payload.get("permission", "safe")),
        read_only=bool(payload.get("read_only", False)),
        parameters=dict(payload.get("parameters", {})),
        keywords=[str(item) for item in payload.get("keywords", [])],
        examples=[str(item) for item in payload.get("examples", [])],
        execution=execution,
    )


def _workflow_from_payload(payload: dict[str, Any]) -> PluginWorkflowRecord:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("plugin workflow is missing `name`")
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError(f"plugin workflow `{name}` must define a list of steps")
    return PluginWorkflowRecord(
        name=name,
        description=str(payload.get("description", name)),
        steps=[dict(step) for step in steps],
    )
