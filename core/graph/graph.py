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

import json
import logging
from collections.abc import AsyncGenerator

from core.graph.state import AgentState

logger = logging.getLogger(__name__)


class StateGraph:
    def __init__(self):
        self.nodes: dict[str, callable] = {}
        self.edges: dict[str, str | tuple] = {}
        self._entry: str | None = None

    def add_node(self, name: str, fn: callable):
        self.nodes[name] = fn

    def add_edge(self, frm: str, to: str):
        self.edges[frm] = to

    def add_conditional_edges(self, frm: str, router: callable, path_map: dict[str, str]):
        self.edges[frm] = (router, path_map)

    def set_entry_point(self, name: str):
        self._entry = name

    async def execute(self, state: AgentState) -> AsyncGenerator[str, None]:
        current = self._entry
        while current and current != "__end__":
            if current == "__pause__":
                yield 'data: ' + json.dumps({
                    "type": "paused",
                    "run_id": state.run_id,
                    "round": state.round_num,
                }) + '\n\n'
                return

            fn = self.nodes.get(current)
            if not fn:
                logger.error("Graph missing node: %s", current)
                break

            state = await fn(state)

            for event in state.events:
                yield event
            state.events.clear()

            edge = self.edges.get(current)
            if isinstance(edge, str):
                current = edge
            elif isinstance(edge, tuple):
                router, path_map = edge
                decision = router(state)
                current = path_map.get(decision, "__end__")
            else:
                current = "__end__"

        if state.error:
            yield f'data: {json.dumps({"type": "error", "error": state.error})}\n\n'
        yield "data: [DONE]\n\n"
