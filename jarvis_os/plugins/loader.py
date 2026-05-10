from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..contracts import ToolSpec
from .manifest import PluginManifest, PluginWorkflowRecord, load_manifest


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _render_template(template: Any, variables: dict[str, Any]) -> Any:
    if isinstance(template, str):
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered
    if isinstance(template, list):
        return [_render_template(item, variables) for item in template]
    if isinstance(template, dict):
        return {key: _render_template(value, variables) for key, value in template.items()}
    return template


class PluginManager:
    def __init__(self, config: Any) -> None:
        self.config = config
        configured = [Path(path).expanduser().resolve() for path in getattr(config, "plugin_roots", [])]
        default_root = Path(config.workspace_root) / "plugins"
        repo_root = Path(__file__).resolve().parents[2] / "plugins"
        roots = configured or [default_root, repo_root]
        self.roots = list(dict.fromkeys(root for root in roots))
        self._plugins: dict[str, PluginManifest] = {}

    def discover(self) -> dict[str, PluginManifest]:
        found: dict[str, PluginManifest] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for manifest_path in root.rglob("manifest.json"):
                manifest = load_manifest(manifest_path)
                found[manifest.plugin_id] = manifest
        self._plugins = dict(sorted(found.items()))
        return self._plugins

    def register(self, registry: Any, models: Any) -> None:
        if not self._plugins:
            self.discover()
        for plugin in self._plugins.values():
            for tool in plugin.tools:
                name = f"plugin.{plugin.plugin_id}.{_slug(tool.name)}"
                spec = ToolSpec(
                    name=name,
                    description=tool.description,
                    arguments=list(tool.parameters.keys()),
                    parameters=dict(tool.parameters),
                    category=tool.category,
                    permission=tool.permission,
                    read_only=tool.read_only,
                    keywords=list(tool.keywords),
                    examples=list(tool.examples),
                    metadata={"plugin": plugin.plugin_id, "plugin_tool": tool.name},
                )
                registry.register(spec, self._build_handler(plugin, tool, registry, models))
            for workflow in plugin.workflows:
                workflow_name = f"plugin.{plugin.plugin_id}.workflow.{_slug(workflow.name)}"
                spec = ToolSpec(
                    name=workflow_name,
                    description=workflow.description,
                    arguments=["input"],
                    parameters={"input": {"type": "string", "required": False, "default": ""}},
                    category="automation",
                    permission="safe",
                    read_only=False,
                    keywords=[workflow.name.lower(), plugin.name.lower(), "workflow"],
                    metadata={"plugin": plugin.plugin_id, "workflow": workflow.name},
                )
                registry.register(spec, self._build_workflow_handler(plugin, workflow, registry))

    def list(self) -> list[dict[str, Any]]:
        return [plugin.to_record().to_dict() for plugin in self._plugins.values()]

    def get(self, name: str) -> dict[str, Any] | None:
        plugin = self._plugins.get(name) or next((item for item in self._plugins.values() if item.name == name), None)
        if plugin is None:
            return None
        return plugin.to_record().to_dict()

    def run_workflow(self, plugin_name: str, workflow_name: str, registry: Any, *, input_text: str = "") -> dict[str, Any]:
        plugin = self._plugins.get(plugin_name) or next((item for item in self._plugins.values() if item.name == plugin_name), None)
        if plugin is None:
            return {"error": "plugin not found", "name": plugin_name}
        workflow = next((item for item in plugin.workflows if item.name == workflow_name), None)
        if workflow is None:
            return {"error": "workflow not found", "plugin": plugin_name, "workflow": workflow_name}
        handler = self._build_workflow_handler(plugin, workflow, registry)
        return handler(input=input_text)

    def _build_handler(self, plugin: PluginManifest, tool: Any, registry: Any, models: Any):
        execution = dict(tool.execution)
        execution_type = str(execution.get("type", "")).lower()

        def _handler(**kwargs):
            variables = {**kwargs, "plugin": plugin.name, "plugin_id": plugin.plugin_id}
            if execution_type == "proxy":
                target = str(execution.get("tool", "")).strip()
                arguments = _render_template(execution.get("arguments", {}), variables)
                for key, value in kwargs.items():
                    arguments.setdefault(key, value)
                return registry.invoke(target, **arguments)
            if execution_type == "workflow":
                workflow = PluginWorkflowRecord(
                    name=tool.name,
                    description=tool.description,
                    steps=[dict(step) for step in execution.get("steps", [])],
                )
                return self._run_steps(plugin, workflow, registry, variables)
            if execution_type == "model_prompt":
                prompt_template = str(execution.get("prompt_template", "{{input}}"))
                prompt = _render_template(prompt_template, variables)
                system = _render_template(execution.get("system", ""), variables)
                task = str(execution.get("task", "analysis"))
                result = models.generate(prompt=prompt, task=task, system=system)
                return {
                    "success": bool(result.get("ok", False)),
                    "provider": result.get("provider", ""),
                    "model": result.get("model", ""),
                    "response": result.get("response", ""),
                    "error": result.get("error", ""),
                }
            raise ValueError(f"unsupported plugin execution type `{execution_type}`")

        return _handler

    def _build_workflow_handler(self, plugin: PluginManifest, workflow: PluginWorkflowRecord, registry: Any):
        def _handler(**kwargs):
            variables = {**kwargs, "plugin": plugin.name, "plugin_id": plugin.plugin_id}
            return self._run_steps(plugin, workflow, registry, variables)

        return _handler

    def _run_steps(self, plugin: PluginManifest, workflow: PluginWorkflowRecord, registry: Any, variables: dict[str, Any]) -> dict[str, Any]:
        results = []
        for step in workflow.steps:
            tool_name = str(step.get("tool", "")).strip()
            if not tool_name:
                raise ValueError(f"workflow `{workflow.name}` in plugin `{plugin.name}` has a step without `tool`")
            arguments = _render_template(step.get("arguments", {}), variables)
            result = registry.invoke(tool_name, **arguments)
            results.append({"tool": tool_name, "output": result})
            variables["last_output"] = result
        return {"success": True, "plugin": plugin.name, "workflow": workflow.name, "steps": len(results), "results": results}
