import os
from unittest.mock import Mock, patch

import pytest

from jarvis_provider import GroqLLM, OpenRouterLLM, get_provider


def test_openrouter_uses_native_endpoint_and_headers():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

    with patch("jarvis_provider.requests.post", return_value=response) as post:
        result = OpenRouterLLM(
            api_key="test-key",
            model="anthropic/claude-3.5-sonnet",
        ).chat("hello", max_tokens=100)

    assert result == "ok"
    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["headers"]["X-Title"] == "JARVIS"
    assert kwargs["json"]["max_tokens"] == 100


def test_groq_remains_available_with_its_native_endpoint():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

    with patch("jarvis_provider.requests.post", return_value=response) as post:
        assert GroqLLM(api_key="test-key").chat("hello") == "ok"

    assert post.call_args.args[0] == "https://api.groq.com/openai/v1/chat/completions"


def test_explicit_cloud_reasoning_does_not_silently_fallback_without_key():
    with patch.dict(
        os.environ,
        {"REASONING_MODEL": "openrouter/anthropic/claude-3.5-sonnet"},
        clear=False,
    ):
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            get_provider("reasoning")
