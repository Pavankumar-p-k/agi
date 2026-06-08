from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional, Union


class ProviderFormat(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


@dataclass
class TextPart:
    text: str

    def to_provider_format(self, provider: ProviderFormat) -> dict:
        if provider == ProviderFormat.ANTHROPIC:
            return {"type": "text", "text": self.text}
        return {"type": "text", "text": self.text}

    @classmethod
    def from_dict(cls, data: dict) -> TextPart:
        return cls(text=data.get("text", data.get("TextPart", {}).get("text", "")))


@dataclass
class ImagePart:
    data: str  # base64-encoded image data
    mime: str = "image/png"

    def to_provider_format(self, provider: ProviderFormat) -> dict:
        if provider == ProviderFormat.ANTHROPIC:
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self.mime,
                    "data": self.data,
                },
            }
        if provider == ProviderFormat.OLLAMA:
            return {"type": "image", "data": self.data}
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{self.mime};base64,{self.data}",
                "detail": "auto",
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> ImagePart:
        d = data.get("ImagePart", data)
        return cls(data=d.get("data", ""), mime=d.get("mime", "image/png"))


@dataclass
class AudioPart:
    data: str  # base64-encoded audio data
    mime: str = "audio/wav"

    def to_provider_format(self, provider: ProviderFormat) -> dict:
        if provider == ProviderFormat.ANTHROPIC:
            return {
                "type": "image",  # Anthropic doesn't support audio natively
                "source": {"type": "base64", "media_type": self.mime, "data": self.data},
            }
        if provider == ProviderFormat.OLLAMA:
            return {"type": "text", "text": "[Audio input not supported by this model]"}
        return {
            "type": "input_audio",
            "input_audio": {"data": self.data, "format": self.mime.split("/")[-1]},
        }

    @classmethod
    def from_dict(cls, data: dict) -> AudioPart:
        d = data.get("AudioPart", data)
        return cls(data=d.get("data", ""), mime=d.get("mime", "audio/wav"))


@dataclass
class ToolCallPart:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_provider_format(self, provider: ProviderFormat) -> dict:
        return {
            "type": "tool_use" if provider == ProviderFormat.ANTHROPIC else "function",
            "id": self.id,
            "function" if provider != ProviderFormat.ANTHROPIC else "name": self.name,
            "input" if provider == ProviderFormat.ANTHROPIC else "arguments": self.arguments,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ToolCallPart:
        d = data.get("ToolCallPart", data)
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            arguments=d.get("arguments", {}),
        )


@dataclass
class ToolResultPart:
    id: str
    content: str
    is_error: bool = False

    def to_provider_format(self, provider: ProviderFormat) -> dict:
        if provider == ProviderFormat.ANTHROPIC:
            return {
                "type": "tool_result",
                "tool_use_id": self.id,
                "content": self.content,
                "is_error": self.is_error,
            }
        return {
            "role": "tool",
            "tool_call_id": self.id,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ToolResultPart:
        d = data.get("ToolResultPart", data)
        return cls(
            id=d.get("id", ""),
            content=d.get("content", ""),
            is_error=d.get("is_error", False),
        )


MultiModalPart = Union[TextPart, ImagePart, AudioPart, ToolCallPart, ToolResultPart]


@dataclass
class MultiModalMessage:
    role: str  # "user", "assistant", "system", "tool"
    parts: list[MultiModalPart] = field(default_factory=list)

    def to_openai_dict(self) -> dict:
        content = []
        for part in self.parts:
            content.append(part.to_provider_format(ProviderFormat.OPENAI))
        return {"role": self.role, "content": content}

    def to_anthropic_dict(self) -> dict:
        content = []
        for part in self.parts:
            content.append(part.to_provider_format(ProviderFormat.ANTHROPIC))
        return {"role": self.role, "content": content}

    def to_ollama_dict(self) -> dict:
        content = []
        images = []
        for part in self.parts:
            if isinstance(part, ImagePart):
                images.append(part.data)
            content.append(part.to_provider_format(ProviderFormat.OLLAMA))
        result = {"role": self.role, "content": content}
        if images:
            result["images"] = images
        return result

    def to_provider_format(self, provider: ProviderFormat) -> dict:
        if provider == ProviderFormat.ANTHROPIC:
            return self.to_anthropic_dict()
        if provider == ProviderFormat.OLLAMA:
            return self.to_ollama_dict()
        return self.to_openai_dict()

    @classmethod
    def from_text(cls, role: str, text: str) -> MultiModalMessage:
        return cls(role=role, parts=[TextPart(text=text)])

    @classmethod
    def from_dict(cls, data: dict) -> MultiModalMessage:
        role = data.get("role", "user")
        parts: list[MultiModalPart] = []
        raw_parts = data.get("parts", data.get("content", []))
        if isinstance(raw_parts, str):
            parts.append(TextPart(text=raw_parts))
        elif isinstance(raw_parts, list):
            for p in raw_parts:
                if isinstance(p, dict):
                    ptype = p.get("type", "")
                    if ptype in ("text",):
                        parts.append(TextPart(text=p.get("text", "")))
                    elif ptype in ("image_url", "image"):
                        img_data = p.get("image_url", {}).get("url", p.get("data", ""))
                        if img_data.startswith("data:"):
                            _, b64 = img_data.split(",", 1)
                            parts.append(ImagePart(data=b64))
                        else:
                            parts.append(ImagePart(data=img_data))
                    elif ptype in ("input_audio", "audio"):
                        parts.append(AudioPart(
                            data=p.get("input_audio", {}).get("data", p.get("data", "")),
                            mime=p.get("input_audio", {}).get("format", "wav"),
                        ))
                    elif ptype in ("function", "tool_use"):
                        parts.append(ToolCallPart(
                            id=p.get("id", ""),
                            name=p.get("function", {}).get("name", p.get("name", "")),
                            arguments=p.get("function", {}).get("arguments", p.get("input", {})),
                        ))
                    elif ptype == "tool_result":
                        parts.append(ToolResultPart(
                            id=p.get("tool_use_id", p.get("tool_call_id", "")),
                            content=p.get("content", ""),
                            is_error=p.get("is_error", False),
                        ))
        return cls(role=role, parts=parts)
