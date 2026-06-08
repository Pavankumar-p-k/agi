from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from core.multimodal import (
    TextPart, ImagePart, AudioPart, ToolCallPart, ToolResultPart,
    MultiModalMessage, ProviderFormat, MultiModalPipeline,
)


# ════════════════════════════════════════════════════════════════════════
# Phase 6a: MultiModalMessage Schema
# ════════════════════════════════════════════════════════════════════════

class TestMultiModalParts:
    def test_text_part(self):
        tp = TextPart(text="hello")
        assert tp.text == "hello"
        o = tp.to_provider_format(ProviderFormat.OPENAI)
        assert o["type"] == "text"
        assert o["text"] == "hello"
        a = tp.to_provider_format(ProviderFormat.ANTHROPIC)
        assert a["type"] == "text"

    def test_text_part_from_dict(self):
        tp = TextPart.from_dict({"text": "world"})
        assert tp.text == "world"

    def test_image_part_openai(self):
        ip = ImagePart(data="abc123", mime="image/png")
        o = ip.to_provider_format(ProviderFormat.OPENAI)
        assert o["type"] == "image_url"
        assert "data:image/png;base64,abc123" in o["image_url"]["url"]

    def test_image_part_anthropic(self):
        ip = ImagePart(data="abc123", mime="image/png")
        a = ip.to_provider_format(ProviderFormat.ANTHROPIC)
        assert a["type"] == "image"
        assert a["source"]["type"] == "base64"
        assert a["source"]["data"] == "abc123"

    def test_image_part_ollama(self):
        ip = ImagePart(data="abc123")
        o = ip.to_provider_format(ProviderFormat.OLLAMA)
        assert o["type"] == "image"
        assert o["data"] == "abc123"

    def test_image_part_from_dict(self):
        ip = ImagePart.from_dict({"data": "xyz", "mime": "image/jpeg"})
        assert ip.data == "xyz"
        assert ip.mime == "image/jpeg"

    def test_audio_part_openai(self):
        ap = AudioPart(data="audiodata", mime="audio/wav")
        o = ap.to_provider_format(ProviderFormat.OPENAI)
        assert o["type"] == "input_audio"
        assert o["input_audio"]["data"] == "audiodata"

    def test_audio_part_anthropic(self):
        ap = AudioPart(data="audiodata")
        a = ap.to_provider_format(ProviderFormat.ANTHROPIC)
        assert a["type"] == "image"

    def test_audio_part_ollama(self):
        ap = AudioPart(data="audiodata")
        o = ap.to_provider_format(ProviderFormat.OLLAMA)
        assert o["type"] == "text"

    def test_tool_call_part(self):
        tc = ToolCallPart(id="call1", name="get_weather", arguments={"city": "NYC"})
        o = tc.to_provider_format(ProviderFormat.OPENAI)
        assert o["type"] == "function"

    def test_tool_result_part(self):
        tr = ToolResultPart(id="call1", content='{"temp": 72}')
        o = tr.to_provider_format(ProviderFormat.OPENAI)
        assert o["role"] == "tool"
        assert o["tool_call_id"] == "call1"


class TestMultiModalMessage:
    def test_from_text(self):
        msg = MultiModalMessage.from_text("user", "hello")
        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert isinstance(msg.parts[0], TextPart)

    def test_to_openai_dict(self):
        msg = MultiModalMessage(
            role="user",
            parts=[TextPart(text="hi"), ImagePart(data="imgdata")],
        )
        d = msg.to_openai_dict()
        assert d["role"] == "user"
        assert len(d["content"]) == 2
        assert d["content"][0]["type"] == "text"
        assert d["content"][1]["type"] == "image_url"

    def test_to_anthropic_dict(self):
        msg = MultiModalMessage(
            role="user",
            parts=[TextPart(text="hi")],
        )
        d = msg.to_anthropic_dict()
        assert d["role"] == "user"
        assert d["content"][0]["type"] == "text"

    def test_to_ollama_dict(self):
        msg = MultiModalMessage(
            role="user",
            parts=[TextPart(text="desc"), ImagePart(data="img")],
        )
        d = msg.to_ollama_dict()
        assert d["role"] == "user"
        assert "images" in d
        assert d["images"] == ["img"]

    def test_from_dict_text_string(self):
        msg = MultiModalMessage.from_dict({"role": "user", "content": "hello"})
        assert msg.role == "user"
        assert isinstance(msg.parts[0], TextPart)

    def test_from_dict_openai_format(self):
        data = {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        }
        msg = MultiModalMessage.from_dict(data)
        assert len(msg.parts) == 2
        assert isinstance(msg.parts[1], ImagePart)

    def test_provider_format_openai(self):
        msg = MultiModalMessage.from_text("user", "test")
        d = msg.to_provider_format(ProviderFormat.OPENAI)
        assert d["role"] == "user"

    def test_provider_format_anthropic(self):
        msg = MultiModalMessage.from_text("user", "test")
        d = msg.to_provider_format(ProviderFormat.ANTHROPIC)
        assert d["content"][0]["type"] == "text"

    def test_provider_format_ollama(self):
        msg = MultiModalMessage.from_text("user", "test")
        d = msg.to_provider_format(ProviderFormat.OLLAMA)
        assert "images" not in d


# ════════════════════════════════════════════════════════════════════════
# Phase 6b: MultiModalPipeline
# ════════════════════════════════════════════════════════════════════════

class TestMultiModalPipeline:
    @pytest.mark.asyncio
    async def test_text_complete_default(self):
        """Text-only messages route through default _default_complete."""
        pipeline = MultiModalPipeline()
        msg = MultiModalMessage.from_text("user", "hello")

        with patch.object(pipeline, "_default_complete", new=AsyncMock()) as mock_default:
            mock_default.return_value.text = "Hi there!"
            mock_default.return_value.error = ""
            result = await pipeline.complete([msg])
            assert result.text == "Hi there!"

    @pytest.mark.asyncio
    async def test_vision_routes_to_vision_providers(self):
        """Messages with images use vision providers."""
        pipeline = MultiModalPipeline()
        msg = MultiModalMessage(
            role="user",
            parts=[TextPart(text="describe"), ImagePart(data="img")],
        )

        mock_vision = AsyncMock(return_value=MagicMock(text="A picture", error=""))
        pipeline.register_vision(mock_vision)

        result = await pipeline.complete([msg])
        assert result.text == "A picture"
        mock_vision.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_chain(self):
        """When first vision provider fails, the second is tried."""
        pipeline = MultiModalPipeline()
        msg = MultiModalMessage(
            role="user",
            parts=[ImagePart(data="img")],
        )

        failing = AsyncMock(side_effect=Exception("provider down"))
        succeeding = AsyncMock(return_value=MagicMock(text="Success", error=""))
        pipeline.register_vision(failing)
        pipeline.register_vision(succeeding)

        result = await pipeline.complete([msg])
        assert result.text == "Success"
        failing.assert_called_once()
        succeeding.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        pipeline = MultiModalPipeline()
        msg = MultiModalMessage.from_text("user", "test")

        failing = AsyncMock(side_effect=Exception("fail"))
        pipeline.register_text(failing)

        result = await pipeline.complete([msg])
        assert result.error
        assert "All providers failed" in result.error

    @pytest.mark.asyncio
    async def test_transcribe_no_providers(self):
        pipeline = MultiModalPipeline()
        text = await pipeline.transcribe(b"audio_bytes")
        assert text == "[Audio transcription not available]"

    @pytest.mark.asyncio
    async def test_transcribe_with_provider(self):
        pipeline = MultiModalPipeline()
        mock_stt = AsyncMock(return_value="hello world")
        pipeline.register_audio_stt(mock_stt)

        text = await pipeline.transcribe(b"audio_bytes")
        assert text == "hello world"
        mock_stt.assert_called_once_with(b"audio_bytes")

    @pytest.mark.asyncio
    async def test_transcribe_fallback(self):
        pipeline = MultiModalPipeline()
        failing = AsyncMock(side_effect=Exception("stt failed"))
        succeeding = AsyncMock(return_value="fallback text")
        pipeline.register_audio_stt(failing)
        pipeline.register_audio_stt(succeeding)

        text = await pipeline.transcribe(b"audio")
        assert text == "fallback text"

    @pytest.mark.asyncio
    async def test_stream_complete(self):
        pipeline = MultiModalPipeline()
        msg = MultiModalMessage.from_text("user", "hello")

        with patch.object(pipeline, "_default_complete", new=AsyncMock()) as mock_default:
            mock_default.return_value.text = "streamed"
            mock_default.return_value.error = ""
            mock_default.return_value.chunks = ["streamed"]

            chunks = []
            async for chunk in pipeline.stream_complete([msg]):
                chunks.append(chunk)
            assert "".join(chunks) == "streamed"

    @pytest.mark.asyncio
    async def test_default_complete_vision(self):
        """_default_complete detects images and routes to complete_vision."""
        pipeline = MultiModalPipeline()
        msg = MultiModalMessage(role="user", parts=[ImagePart(data="img")])

        mock_vision_result = MagicMock()
        mock_vision_result.is_ok.return_value = True
        mock_vision_result.unwrap.return_value = "vision result"

        with patch("core.llm_router.complete_vision", new=AsyncMock(return_value=mock_vision_result)) as mock_cv, \
             patch("core.llm_router.complete", new=AsyncMock()) as mock_c:

            result = await pipeline._default_complete([msg])
            assert result.text == "vision result"
            mock_cv.assert_called_once()
            mock_c.assert_not_called()

    def test_provider_format_constant_values(self):
        assert ProviderFormat.OPENAI == "openai"
        assert ProviderFormat.ANTHROPIC == "anthropic"
        assert ProviderFormat.OLLAMA == "ollama"
