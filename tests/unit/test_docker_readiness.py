import asyncio
from types import SimpleNamespace

import numpy as np


def test_ollama_provider_prefers_container_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://ollama:11434/")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    from core.model_providers.ollama import OllamaProvider

    assert OllamaProvider()._base_url == "http://ollama:11434"


def test_embedding_client_uses_ollama_embed_endpoint(monkeypatch):
    monkeypatch.delenv("EMBEDDING_URL", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://ollama:11434")

    from core.embeddings import EmbeddingClient

    client = EmbeddingClient()
    assert client.url == "http://ollama:11434/api/embed"


def test_embedding_client_accepts_ollama_response(monkeypatch):
    from core.embeddings import EmbeddingClient

    client = EmbeddingClient(url="http://ollama:11434/api/embed")
    client._client.post = lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"embeddings": [[3.0, 4.0]]},
    )
    result = client.encode(["hello"])
    assert np.allclose(result, [[0.6, 0.8]])


def test_prompt_optimizer_handles_empty_mapping():
    from brain.prompt_optimizer import PromptOptimizer

    optimizer = object.__new__(PromptOptimizer)
    optimizer.AGENT_OUTPUT_TYPE = None
    assert asyncio.run(optimizer.run_cycle()) == []


def test_scheduler_executors_import_without_result_module():
    import core.scheduler.executors as executors

    assert executors.default_executor is not None


def test_workflow_recovery_records_trace_without_awaiting_sync_method():
    import inspect
    from core.workflow.recovery import recover_active_workflows

    assert "await em.record_trace" not in inspect.getsource(recover_active_workflows)
