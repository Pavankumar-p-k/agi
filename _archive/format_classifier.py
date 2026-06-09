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

"""Fast output format detection. Rule-based fast path covers 80% of cases."""

from __future__ import annotations


class FormatClassifier:
    RULES = [
        ({"3d", "scene", "render", "blender", "three.js",
          "threejs", "visualize 3d", "3d model", "3d scene"}, "scene"),
        ({"write code", "function", "script", "implement", "def ", "class "}, "code"),
        ({"build website", "create page", "design ui", "make component"}, "artifact"),
        ({"list", "give me", "show me", "what are", "enumerate"}, "list"),
        ({"table", "compare", "vs", "versus", "difference between"}, "table"),
        ({"json", "structured", "as json", "return json"}, "json"),
        ({"diagram", "flowchart", "draw", "visualize", "chart"}, "artifact"),
    ]
    FORMATS = ["code", "json", "prose", "list", "table", "artifact", "voice", "scene"]

    async def classify(self, query: str) -> str:
        q = query.lower()
        for keywords, fmt in self.RULES:
            if any(kw in q for kw in keywords):
                return fmt
        return "prose"
