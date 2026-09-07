# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""tests/test_image_gen.py — Tests for tools/image_gen.py ImageGenerator."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestImageGenerator:
    def test_no_provider(self):
        with patch.dict("os.environ", {}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            assert gen._provider is None

    def test_detect_openai(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            assert gen._provider == "openai"

    def test_detect_stability(self):
        with patch.dict("os.environ", {"STABILITY_API_KEY": "st-test"}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            assert gen._provider == "stability"

    def test_detect_replicate(self):
        with patch.dict("os.environ", {"REPLICATE_API_TOKEN": "rp-test"}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            assert gen._provider == "replicate"

    def test_detect_together(self):
        with patch.dict("os.environ", {"TOGETHER_API_KEY": "tg-test"}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            assert gen._provider == "together"

    @pytest.mark.asyncio
    async def test_generate_no_provider(self):
        with patch.dict("os.environ", {}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            gen._provider = None
            result = await gen.generate("test prompt")
            assert result == []

    @pytest.mark.asyncio
    async def test_generate_openai(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            with patch("openai.AsyncOpenAI") as mock_openai:
                mock_instance = AsyncMock()
                mock_instance.images.generate = AsyncMock(
                    return_value=MagicMock(
                        data=[MagicMock(url="https://example.com/img.png")]
                    )
                )
                mock_openai.return_value = mock_instance
                result = await gen.generate("test")
                assert len(result) == 1
                assert result[0] == "https://example.com/img.png"

    @pytest.mark.asyncio
    async def test_generate_openai_failure(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            with patch("openai.AsyncOpenAI") as mock_openai:
                mock_openai.side_effect = Exception("API error")
                result = await gen.generate("test")
                assert result == []

    @pytest.mark.asyncio
    async def test_generate_stability(self):
        with patch.dict("os.environ", {"STABILITY_API_KEY": "st-test"}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"artifacts": [{"base64": "aaaa"}]}
                mock_instance.post.return_value = mock_resp
                mock_client.return_value.__aenter__.return_value = mock_instance
                result = await gen.generate("test", size="1024x1024")
                assert len(result) == 1

    @pytest.mark.asyncio
    async def test_generate_replicate(self):
        with patch.dict("os.environ", {"REPLICATE_API_TOKEN": "rp-test"}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"urls": {"get": "https://example.com/result"}}
                mock_instance.post.return_value = mock_resp
                mock_client.return_value.__aenter__.return_value = mock_instance
                result = await gen.generate("test")
                assert len(result) == 1

    @pytest.mark.asyncio
    async def test_generate_together(self):
        with patch.dict("os.environ", {"TOGETHER_API_KEY": "tg-test"}, clear=True):
            from tools.image_gen import ImageGenerator
            gen = ImageGenerator()
            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"data": [{"url": ["https://example.com/img"]}]}
                mock_instance.post.return_value = mock_resp
                mock_client.return_value.__aenter__.return_value = mock_instance
                result = await gen.generate("test")
                assert len(result) == 1
