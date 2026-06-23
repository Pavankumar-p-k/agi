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

"""brain/epistemic_tagger.py
EpistemicTagger — classifies each response with [VERIFIED], [ASSUMED], or [UNCERTAIN]
based on the actual source of the information.

Usage:
    tagger = EpistemicTagger()
    tagged = tagger.tag_response(text, {"source": "web_search", "confidence": 0.9})
    cleaned = tagger.strip_tags(tagged)
"""

from __future__ import annotations

import re
from enum import Enum


class ResponseSource(str, Enum):
    WEB_SEARCH = "VERIFIED"
    MEMORY = "VERIFIED"
    TOOL_RESULT = "VERIFIED"
    INFERENCE = "ASSUMED"
    LOW_CONF_MEMORY = "ASSUMED"
    UNKNOWN = "UNCERTAIN"

    @classmethod
    def from_str(cls, s: str) -> "ResponseSource":
        mapping = {
            "web_search": cls.WEB_SEARCH,
            "search": cls.WEB_SEARCH,
            "memory": cls.MEMORY,
            "tool_result": cls.TOOL_RESULT,
            "tool": cls.TOOL_RESULT,
            "inference": cls.INFERENCE,
            "low_conf_memory": cls.LOW_CONF_MEMORY,
        }
        return mapping.get(s.lower(), cls.UNKNOWN)


# Cache compiled pattern
_TAG_PATTERN = re.compile(r"\[(VERIFIED|RETRIEVED|DERIVED|ASSUMED|UNCERTAIN)\]\(?[^)\s]*\)?\s*")


class EpistemicTagger:
    """Strips and re-applies epistemic tags based on provenance."""

    def strip_tags(self, text: str) -> str:
        """Remove all epistemic tags from text."""
        return _TAG_PATTERN.sub("", text).strip()

    def tag_response(self, text: str, provenance: dict | None = None) -> str:
        """
        Strip existing tags, then re-tag based on provenance.

        Provenance dict:
            source: str  — one of 'web_search', 'memory', 'tool_result', 'inference', 'low_conf_memory'
            confidence: float (0-1)
            url: str | None  — for web_search sources
            claim_map: dict[str, str] | None  — optional per-claim {fragment: source} overrides
        """
        clean = self.strip_tags(text)

        if not provenance:
            return clean

        source = provenance.get("source", "unknown")
        url = provenance.get("url")
        confidence = provenance.get("confidence", 0.5)
        claim_map = provenance.get("claim_map")

        # Determine base tag
        base = ResponseSource.from_str(source)

        # Apply per-claim overrides if provided
        if claim_map:
            sentences = re.split(r"(?<=[.!?])\s+", clean)
            tagged = []
            for sentence in sentences:
                sentence_tag = base
                for fragment, frag_source in claim_map.items():
                    if fragment.lower() in sentence.lower():
                        sentence_tag = ResponseSource.from_str(frag_source)
                        break
                tag_str = sentence_tag.value
                if sentence_tag == ResponseSource.WEB_SEARCH and url:
                    tag_str = f"[RETRIEVED]({url})"
                else:
                    tag_str = f"[{tag_str}]"
                tagged.append(f"{tag_str} {sentence}")
            return " ".join(tagged)

        # Single tag for the whole response
        tag_str = base.value
        if base in (ResponseSource.INFERENCE, ResponseSource.UNKNOWN, ResponseSource.LOW_CONF_MEMORY):
            return clean

        if base == ResponseSource.WEB_SEARCH and url:
            tag_str = f"[RETRIEVED]({url})"
        else:
            tag_str = f"[{tag_str}]"

        return f"{tag_str} {clean}"


epistemic_tagger = EpistemicTagger()
