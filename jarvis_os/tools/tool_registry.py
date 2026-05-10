from __future__ import annotations

from collections import OrderedDict
import re
from typing import Any, Callable

from ..contracts import ToolSpec

ToolHandler = Callable[..., dict[str, Any]]


class ToolRegistry:
    def __init__(self, *, config: Any, memory: Any, models: Any) -> None:
        self.config = config
        self.memory = memory
        self.models = models
        self._specs: OrderedDict[str, ToolSpec] = OrderedDict()
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        spec = self._normalized_spec(spec)
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def register_aliases(self, aliases: dict[str, str]) -> None:
        for alias, target in aliases.items():
            if target not in self._specs:
                continue
            spec = self._specs[target]
            self._specs[alias] = ToolSpec(
                name=alias,
                description=f"Alias for {target}: {spec.description}",
                arguments=list(spec.arguments),
                parameters=dict(spec.parameters),
                category=spec.category,
                permission=spec.permission,
                read_only=spec.read_only,
                keywords=list(spec.keywords),
                examples=list(spec.examples),
                metadata={"alias_for": target, **spec.metadata},
            )
            self._handlers[alias] = self._handlers[target]

    def invoke(self, tool_name: str, **kwargs) -> dict[str, Any]:
        if tool_name not in self._handlers:
            return self._structured_error(f"Unknown tool: {tool_name}")
        spec = self._specs[tool_name]
        normalized = self._validate_arguments(spec, kwargs)
        try:
            result = self._handlers[tool_name](**normalized)
            # Normalize output to standard format
            return self._normalize_output(result)
        except Exception as exc:
            return self._structured_error(str(exc))

    def _normalize_output(self, result: Any) -> dict[str, Any]:
        """Ensure all tool outputs follow: {"status": "success"/"error", "data": ...}"""
        if isinstance(result, dict):
            if "status" in result:
                return result  # Already normalized
            if "error" in result or "success" in result:
                # Convert old format
                success = result.get("success", not result.get("error"))
                status = "success" if success else "error"
                data = {k: v for k, v in result.items() if k not in {"success", "error"}}
                return {"status": status, "data": data, "error": result.get("error", "")}
            # Assume entire dict is data
            return {"status": "success", "data": result}
        # Wrap primitives
        return {"status": "success", "data": result}

    def _structured_error(self, error: str) -> dict[str, Any]:
        return {"status": "error", "data": {}, "error": error}

    def catalog(self) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in self._specs.values()]

    def recommend(self, prompt: str, intent_name: str) -> list[ToolSpec]:
        lowered = prompt.lower()
        ranked: list[tuple[int, ToolSpec]] = []
        for spec in self._specs.values():
            score = 0
            if spec.category == intent_name:
                score += 6
            if spec.metadata.get("alias_for"):
                score -= 1
            name_phrase = spec.name.replace("_", " ").replace(".", " ")
            if name_phrase in lowered:
                score += 5
            name_tokens = [token for token in re.split(r"[_\W]+", spec.name.lower()) if token]
            score += sum(2 for token in name_tokens if len(token) > 2 and token in lowered)
            score += sum(3 for token in spec.keywords if token.lower() in lowered)
            description_tokens = [token for token in re.split(r"[_\W]+", spec.description.lower()) if len(token) > 3]
            score += sum(1 for token in description_tokens[:8] if token in lowered)
            score += sum(1 for arg in spec.arguments if arg in lowered)
            score += sum(2 for example in spec.examples if example.lower() in lowered)
            if intent_name == "research" and any(token in lowered for token in ("latest", "news", "headline")) and "news" in spec.name:
                score += 4
            if intent_name == "filesystem" and any(token in lowered for token in ("file", "directory", "folder")) and spec.category == "filesystem":
                score += 2
            if score:
                ranked.append((score, spec))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [spec for _, spec in ranked[:6]]

    def get_spec(self, tool_name: str) -> ToolSpec:
        return self._specs[tool_name]

    def _normalized_spec(self, spec: ToolSpec) -> ToolSpec:
        parameters = dict(spec.parameters)
        for argument in spec.arguments:
            parameters.setdefault(argument, {"type": "string", "required": True})
        keywords = list(spec.keywords)
        if not keywords:
            auto_keywords = [token for token in re.split(r"[_\W]+", spec.name.lower()) if len(token) > 2]
            keywords = auto_keywords[:8]
        return ToolSpec(
            name=spec.name,
            description=spec.description,
            arguments=list(spec.arguments),
            parameters=parameters,
            category=spec.category,
            permission=spec.permission,
            read_only=spec.read_only,
            keywords=keywords,
            examples=list(spec.examples),
            metadata=dict(spec.metadata),
        )

    def _validate_arguments(self, spec: ToolSpec, kwargs: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(kwargs)
        for name, schema in spec.parameters.items():
            missing = name not in normalized
            empty = False
            if not missing:
                value = normalized[name]
                empty = value is None or value == ""
            if missing or empty:
                if "default" in schema:
                    normalized[name] = schema["default"]
                elif schema.get("required", False):
                    raise ValueError(f"tool `{spec.name}` requires argument `{name}`")
                else:
                    continue
            normalized[name] = self._coerce_value(normalized[name], schema)
        return normalized

    def _coerce_value(self, value: Any, schema: dict[str, Any]) -> Any:
        expected = schema.get("type", "string")
        if expected == "integer":
            if isinstance(value, int):
                return value
            return int(str(value).strip())
        if expected == "number":
            if isinstance(value, (int, float)):
                return float(value)
            return float(str(value).strip())
        if expected == "boolean":
            if isinstance(value, bool):
                return value
            lowered = str(value).strip().lower()
            return lowered in {"1", "true", "yes", "on"}
        if expected == "array":
            if isinstance(value, list):
                return value
            return [value]
        if expected == "object":
            if isinstance(value, dict):
                return value
            raise ValueError(f"expected object value, got {type(value).__name__}")
        if value is None:
            return ""
        return str(value) if expected == "string" and not isinstance(value, str) else value
