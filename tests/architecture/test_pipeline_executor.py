from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.pipeline.messages import Request, Response
from core.scheduler.pipeline_executor import pipeline_executor


@pytest.fixture
def mock_process_message():
    with patch("core.scheduler.pipeline_executor.process_message") as mock:
        mock.return_value = Response(
            text="hello world",
            metadata={
                "activity_id": "act-new",
                "trace_id": "trace-1",
                "pipeline_version": "1.0",
            },
        )
        yield mock


class TestPipelineExecutor:
    async def test_returns_dict_with_success(self, mock_process_message):
        result = await pipeline_executor(
            activity_id="act-123",
            goal="do something",
        )

        assert result["success"] is True
        assert result["activity_id"] == "act-123"
        assert result["text"] == "hello world"
        assert result["error"] is None

    async def test_calls_process_message_with_correct_request(self, mock_process_message):
        await pipeline_executor(
            activity_id="act-123",
            goal="do something",
            metadata={"source": "test"},
        )

        mock_process_message.assert_awaited_once()
        request: Request = mock_process_message.call_args[0][0]
        assert isinstance(request, Request)
        assert request.text == "do something"
        assert request.transport == "scheduler"
        assert request.metadata["scheduler_activity_id"] == "act-123"
        assert request.metadata["source"] == "test"

    async def test_handles_process_message_error(self):
        with patch("core.scheduler.pipeline_executor.process_message", new=AsyncMock(side_effect=ValueError("boom"))):
            result = await pipeline_executor(
                activity_id="act-err",
                goal="fail",
            )

            assert result["success"] is False
            assert "boom" in result["error"]
            assert result["activity_id"] == "act-err"

    async def test_metadata_defaults_to_empty(self, mock_process_message):
        await pipeline_executor(activity_id="act-1", goal="test")
        request: Request = mock_process_message.call_args[0][0]
        assert request.metadata["scheduler_activity_id"] == "act-1"

    async def test_response_contains_full_metadata(self, mock_process_message):
        result = await pipeline_executor(activity_id="act-1", goal="test")
        assert "activity_id" in result["metadata"]
        assert "trace_id" in result["metadata"]
        assert "pipeline_version" in result["metadata"]
