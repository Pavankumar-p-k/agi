"""Focused Phase 5 reliability regressions."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_ollama_embeddings_preserve_requested_model_and_batches():
    from core.model_providers.ollama import OllamaProvider

    provider = OllamaProvider.__new__(OllamaProvider)
    provider._base_url = "http://ollama.test"
    response = MagicMock()
    response.json.return_value = {"embeddings": [[1.0], [2.0]]}
    response.raise_for_status = MagicMock()
    client = AsyncMock()
    client.__aenter__.return_value.post.return_value = response

    with patch("httpx.AsyncClient", return_value=client):
        result = await provider.embeddings("custom-embed", ["one", "two"])

    assert result == [[1.0], [2.0]]
    assert client.__aenter__.return_value.post.call_args.kwargs["json"]["model"] == "custom-embed"


@pytest.mark.asyncio
async def test_service_health_uses_configured_ollama_url_and_embedding_probe():
    from monitors.services import ServiceHealthChecker

    tags = MagicMock(status_code=200)
    embed = MagicMock(status_code=200)
    client = AsyncMock()
    client.__aenter__.return_value.get.return_value = tags
    client.__aenter__.return_value.post.return_value = embed
    with patch("core.configuration.configuration.get", return_value="http://configured:1234"), \
         patch("httpx.AsyncClient", return_value=client):
        result = await ServiceHealthChecker._check_ollama()

    assert result.status == "healthy"
    assert client.__aenter__.return_value.get.call_args.args[0] == "http://configured:1234/api/tags"
    assert client.__aenter__.return_value.post.call_args.kwargs["json"]["model"] == "nomic-embed-text"


def test_wake_health_does_not_create_detector():
    from assistant import wake_word

    with patch.object(wake_word, "_watchdog_instance", None), \
         patch("assistant.wake_word.get_detector") as lazy:
        assert wake_word.get_existing_detector() is None
        lazy.assert_not_called()
