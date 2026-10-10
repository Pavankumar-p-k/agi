"""core.routing.request_classifier — canonical intent classifier.

Single canonical module for intent classification (arch test
``test_single_intent_classifier``): any other module that defines
``classify_request`` is an architecture violation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


class RequestMode:
    """Classification outcome modes (kept simple: comparable by identity)."""

    ACTION = "action"
    AGENT = "agent"
    CHAT = "chat"

    _values = {ACTION, AGENT, CHAT}

    @classmethod
    def all(cls) -> tuple[str, ...]:
        return cls.ACTION, cls.AGENT, cls.CHAT


@dataclass
class ClassifiedRequest:
    mode: str = RequestMode.CHAT
    sub_type: str = ""
    confidence: float = 1.0
    params: dict[str, Any] = field(default_factory=dict)

    def __eq__(self, other):
        return isinstance(other, ClassifiedRequest) and self.mode == other.mode and self.sub_type == other.sub_type

    def __repr__(self):
        return f"ClassifiedRequest(mode={self.mode!r}, sub_type={self.sub_type!r}, confidence={self.confidence!r})"


# ═══════════════════════════════════════════════════════════════════════════
#  Pattern tables — verb-led commands are ACTION*, agent-markers are AGENT
# ═════════════════════════ classification tables ══════════════════════════
_BROWSER_TRIGGERS = ("yt", "youtube", "google", "search", "open", "launch", "browse",
                    "visit", "go to", "navigate", "click", "type", "press", "hit",
                    "what apps", "what windows", "what tabs", "screenshot", "run")

_AGENT_TRIGGERS = ("build", "create", "develop", "make me", "design", "generate",
                  "write a", "write an", "code a", "code an", "fix", "refactor",
                  "deploy", "automate", "implement", "develop an app",
                  "could you", "can you", "please build", "please create")

_REMINDER_TRIGGERS = ("remind", "reminder", "remind me", "set a reminder", "unremind")

# Action sub-types matched tightly so hyphen/space variants land together.
_BROWSER_MAP = [
    (re.compile(r"\bwhat\s+(?:apps?|applications?|windows?|tabs?)(?:\s+(?:are\s+)?open)?\b", re.I), "ACTION_BROWSER"),
    (re.compile(r"\b(?:click|type|press|hit)\b", re.I), "ACTION_BROWSER"),
    (re.compile(r"\b(?:open|launch|start|play|browse|visit|go to|navigate)\b", re.I), "ACTION_BROWSER"),
    (re.compile(r"\b(?:yt|youtube|google|search for|search)\b", re.I), "ACTION_BROWSER"),
    (re.compile(r"\bscreenshot\b", re.I), "ACTION_BROWSER"),
]

_AGENT_MAP = [
    (re.compile(r"\b(?:build|create|develop|implement|automate|deploy|design|generate|refactou?r|fix)\b", re.I), "AGENT"),
]

_REMINDER_MAP = [
    (re.compile(r"\b(?:remind(?:er)?|reminder)\b", re.I), "ACTION_REMINDER"),
]


def _detect(mode_table, message: str) -> Optional[str]:
    for pattern, sub_type in mode_table:
        if pattern.search(message):
            return sub_type
    return None


def classify_request(message: str, **_kwargs: Any) -> ClassifiedRequest:
    """Classify a user request into ACTION / AGENT / CHAT.

    Order of precedence: reminder > agent > browser-action > chat.
    The arch test pins this module as the sole owner of classify_request.
    """
    text = (message or "").strip()
    if not text:
        return ClassifiedRequest(mode=RequestMode.CHAT, sub_type="", confidence=0.5)

    sub_type = _detect(_REMINDER_MAP, text)
    if sub_type:
        return ClassifiedRequest(mode=RequestMode.ACTION, sub_type=sub_type, confidence=0.95)
    sub_type = _detect(_AGENT_MAP, text)
    if sub_type:
        return ClassifiedRequest(mode=RequestMode.AGENT, sub_type="AGENT", confidence=0.9)
    sub_type = _detect(_BROWSER_MAP, text)
    if sub_type:
        return ClassifiedRequest(mode=RequestMode.ACTION, sub_type=sub_type, confidence=0.9)

    return ClassifiedRequest(mode=RequestMode.CHAT, sub_type="", confidence=0.8)


__all__ = ["RequestMode", "ClassifiedRequest", "classify_request"]
