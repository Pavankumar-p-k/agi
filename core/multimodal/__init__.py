"""Multi-modal message schema and completion pipeline."""
from __future__ import annotations

from core.multimodal.pipeline import (
    MultiModalPipeline,
    MultiModalResult,
    multimodal_pipeline,
)
from core.multimodal.schema import (
    AudioPart,
    ImagePart,
    MultiModalMessage,
    MultiModalPart,
    ProviderFormat,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)

__all__ = [
    "AudioPart",
    "ImagePart",
    "MultiModalMessage",
    "MultiModalPart",
    "MultiModalPipeline",
    "MultiModalResult",
    "ProviderFormat",
    "TextPart",
    "ToolCallPart",
    "ToolResultPart",
    "multimodal_pipeline",
]
