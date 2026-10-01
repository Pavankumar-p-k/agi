"""Multi-modal message schema — text/image/audio/tool parts per provider.

One canonical ``MultiModalMessage`` serialises to OpenAI, Anthropic and Ollama
shapes, so the rest of the system never branches on the vendor format.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ProviderFormat(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


@dataclass
class MultiModalPart:
    """Base class for message parts."""

    def to_provider_format(self, fmt: ProviderFormat) -> dict:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> "MultiModalPart":
        raise NotImplementedError


@dataclass
class TextPart(MultiModalPart):
    text: str = ""

    def to_provider_format(self, fmt: ProviderFormat) -> dict:
        return {"type": "text", "text": self.text}

    @classmethod
    def from_dict(cls, data: dict) -> "TextPart":
        return cls(text=str(data.get("text", "")))


@dataclass
class ImagePart(MultiModalPart):
    data: str = ""
    mime: str = "image/png"

    def to_provider_format(self, fmt: ProviderFormat) -> dict:
        if fmt == ProviderFormat.OPENAI:
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{self.mime};base64,{self.data}"},
            }
        if fmt == ProviderFormat.ANTHROPIC:
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self.mime,
                    "data": self.data,
                },
            }
        # Ollama takes the raw base64 payload under ``images``.
        return {"type": "image", "data": self.data}

    @classmethod
    def from_dict(cls, data: dict) -> "ImagePart":
        mime = str(data.get("mime") or "")
        payload = data.get("data")
        if payload is None and isinstance(data.get("image_url"), dict):
            url = str(data["image_url"].get("url", ""))
            payload, mime = _split_data_url(url, mime)
        if payload is None and isinstance(data.get("source"), dict):
            source = data["source"]
            payload = source.get("data", "")
            mime = str(source.get("media_type") or mime)
        return cls(data=str(payload or ""), mime=mime or "image/png")


@dataclass
class AudioPart(MultiModalPart):
    data: str = ""
    mime: str = "audio/wav"

    def to_provider_format(self, fmt: ProviderFormat) -> dict:
        if fmt == ProviderFormat.OPENAI:
            return {
                "type": "input_audio",
                "input_audio": {"data": self.data, "format": self.mime.split("/")[-1]},
            }
        if fmt == ProviderFormat.ANTHROPIC:
            # Anthropic has no audio channel: carry it as an inline image block.
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": self.mime, "data": self.data},
            }
        return {"type": "text", "text": ""}

    @classmethod
    def from_dict(cls, data: dict) -> "AudioPart":
        return cls(data=str(data.get("data", "")), mime=str(data.get("mime") or "audio/wav"))


@dataclass
class ToolCallPart(MultiModalPart):
    id: str = ""
    name: str = ""
    arguments: dict = field(default_factory=dict)

    def to_provider_format(self, fmt: ProviderFormat) -> dict:
        args = self.arguments
        if not isinstance(args, str):
            args = json.dumps(args)
        return {
            "type": "function",
            "id": self.id,
            "function": {"name": self.name, "arguments": args},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolCallPart":
        fn = data.get("function") or {}
        return cls(
            id=str(data.get("id", "")),
            name=str(fn.get("name") or data.get("name", "")),
            arguments=fn.get("arguments") or data.get("arguments") or {},
        )


@dataclass
class ToolResultPart(MultiModalPart):
    id: str = ""
    content: str = ""

    def to_provider_format(self, fmt: ProviderFormat) -> dict:
        return {"role": "tool", "tool_call_id": self.id, "content": self.content}

    @classmethod
    def from_dict(cls, data: dict) -> "ToolResultPart":
        return cls(id=str(data.get("tool_call_id") or data.get("id", "")),
                   content=str(data.get("content", "")))


def _split_data_url(url: str, fallback_mime: str = "") -> tuple[str, str]:
    if url.startswith("data:") and ";base64," in url:
        header, _, payload = url.partition(";base64,")
        return payload, header[len("data:"):] or fallback_mime
    return url, fallback_mime


@dataclass
class MultiModalMessage:
    role: str = "user"
    parts: list = field(default_factory=list)

    # ── constructors ─────────────────────────────────────────────────
    @classmethod
    def from_text(cls, role: str, text: str) -> "MultiModalMessage":
        return cls(role=role, parts=[TextPart(text=text)])

    @classmethod
    def from_dict(cls, data: dict) -> "MultiModalMessage":
        role = str(data.get("role", "user"))
        content = data.get("content")
        parts: list = []
        if isinstance(content, str):
            parts.append(TextPart(text=content))
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    parts.append(TextPart(text=str(item)))
                    continue
                parts.append(_part_from_block(item))
        return cls(role=role, parts=parts)

    # ── capability queries ───────────────────────────────────────────
    def has_images(self) -> bool:
        return any(isinstance(p, ImagePart) for p in self.parts)

    def has_audio(self) -> bool:
        return any(isinstance(p, AudioPart) for p in self.parts)

    def text(self) -> str:
        return "\n".join(p.text for p in self.parts if isinstance(p, TextPart))

    # ── serialisation ────────────────────────────────────────────────
    def to_openai_dict(self) -> dict:
        return {"role": self.role,
                "content": [p.to_provider_format(ProviderFormat.OPENAI)
                            for p in self.parts]}

    def to_anthropic_dict(self) -> dict:
        return {"role": self.role,
                "content": [p.to_provider_format(ProviderFormat.ANTHROPIC)
                            for p in self.parts]}

    def to_ollama_dict(self) -> dict:
        out: dict[str, Any] = {"role": self.role, "content": self.text()}
        images = [p.data for p in self.parts if isinstance(p, ImagePart)]
        if images:
            out["images"] = images
        return out

    def to_provider_format(self, fmt: ProviderFormat) -> dict:
        if fmt == ProviderFormat.ANTHROPIC:
            return self.to_anthropic_dict()
        if fmt == ProviderFormat.OLLAMA:
            return self.to_ollama_dict()
        return self.to_openai_dict()


def _part_from_block(block: dict) -> MultiModalPart:
    kind = str(block.get("type", "text"))
    if kind in ("text", "input_text"):
        return TextPart.from_dict(block)
    if kind in ("image_url", "image"):
        return ImagePart.from_dict(block)
    if kind in ("input_audio", "audio"):
        return AudioPart.from_dict(block)
    if kind in ("function", "tool_call"):
        return ToolCallPart.from_dict(block)
    if kind == "tool_result":
        return ToolResultPart.from_dict(block)
    return TextPart(text=str(block.get("text", "")))


__all__ = [
    "AudioPart",
    "ImagePart",
    "MultiModalMessage",
    "MultiModalPart",
    "ProviderFormat",
    "TextPart",
    "ToolCallPart",
    "ToolResultPart",
]
