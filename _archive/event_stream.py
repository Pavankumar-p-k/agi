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

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Generic, Optional, TypeVar

T = TypeVar("T")
R = TypeVar("R")


class EventStream(Generic[T, R]):
    """Async iterable that produces events and signals completion with a final result.

    Patterns borrowed from OpenClaw's EventStream implementation.
    """

    def __init__(self):
        self._queue: asyncio.Queue[T | _Sentinel] = asyncio.Queue()
        self._result: Optional[R] = None

    def push(self, event: T) -> None:
        self._queue.put_nowait(event)

    def end(self, result: R) -> None:
        self._result = result
        self._queue.put_nowait(_SENTINEL)

    @property
    def result(self) -> Optional[R]:
        return self._result

    def __aiter__(self) -> AsyncIterator[T]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[T]:
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                return
            yield item


class _Sentinel:
    pass


_SENTINEL = _Sentinel()


class AssistantMessageEventStream(EventStream[str, str]):
    """Event stream for assistant message chunks. Each push is a text delta."""

    def __init__(self):
        super().__init__()
        self._full_text: list[str] = []

    def push_delta(self, delta: str) -> None:
        self._full_text.append(delta)
        self.push(delta)

    def end_message(self) -> None:
        full = "".join(self._full_text)
        self.end(full)


def format_sse(data: Any, event: Optional[str] = None) -> str:
    """Format data as Server-Sent Event."""
    lines = []
    if event:
        lines.append(f"event: {event}")
    payload = json.dumps(data) if not isinstance(data, str) else data
    for line in payload.split("\n"):
        lines.append(f"data: {line}")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def sse_done() -> str:
    """Terminal SSE frame."""
    return "data: [DONE]\n\n"
