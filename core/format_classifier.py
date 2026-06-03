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
