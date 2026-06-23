from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RequestMode(Enum):
    CHAT = "chat"
    DIRECT = "direct"
    ACTION = "action"
    CODEBASE = "codebase"
    AGENT = "agent"


ACTION_SUB_TYPE = {
    "file": "ACTION_FILE",
    "shell": "ACTION_SHELL",
    "browser": "ACTION_BROWSER",
    "system": "ACTION_SYSTEM",
}


@dataclass
class Classification:
    mode: RequestMode
    confidence: float
    sub_type: str | None = None


# ── Keyword patterns ──────────────────────────────────────────────
# Each entry: (mode, confidence, sub_type, triggers)

# Pre-check: single-step file actions that would otherwise match AGENT patterns
_AGENT_OVERRIDE_PATTERNS = [
    (RequestMode.ACTION, 0.95, "ACTION_FILE", [
        "create a file", "create file", "create directory",
        "make directory", "delete file", "delete directory",
        "remove file", "remove directory", "rename file",
        "move file", "copy file",
    ]),
]

_AGENT_PATTERNS = [
    (RequestMode.AGENT, 0.90, None, [
        "build a project", "create a project",
        "build an app", "build a app", "build an application",
        "create an app", "create a application",
        "implement a ", "generate a ", "set up a ", "scaffold a ",
    ]),
    (RequestMode.AGENT, 0.88, None, [
        "build a calculator", "build a game", "build a website",
        "build a web app", "build a mobile app",
    ]),
    (RequestMode.AGENT, 0.85, None, [
        "fix this ", "repair this ", "debug this ",
        "fix the repository", "repair the project",
        "fix ", "repair ", "debug ",
    ]),
    (RequestMode.AGENT, 0.80, None, [
        "research ", "investigate ", "explore the ",
        "build an ", "create an ",
    ]),
]

_CODEBASE_PATTERNS = [
    (RequestMode.CODEBASE, 0.93, None, [
        "explain architecture", "explain this code", "explain the architecture",
        "understand this project", "understand this code",
    ]),
    (RequestMode.CODEBASE, 0.90, None, [
        "find where ", "search for ", "search codebase",
        "find auth", "find api", "find websocket",
        "where is login", "where is auth",
    ]),
    (RequestMode.CODEBASE, 0.85, None, [
        "review this code", "analyze this ", "what does this code",
        "show architecture", "show structure", "how does this work",
        "show api routes", "show database", "find all ",
        "display project structure", "show project structure",
        "project structure", "repository structure",
    ]),
]

_DIRECT_PATTERNS = [
    (RequestMode.DIRECT, 0.98, None, [
        "weather ", "what's the weather", "what is the weather",
        "news ", "stock ", "stocks ", "time ",
    ]),
]

_ACTION_PATTERNS = [
    # FILE
    (RequestMode.ACTION, 0.97, "ACTION_FILE", [
        "list files", "list directory", "ls ", "dir ",
        "show files", "show directory", "display files",
        "show me files", "show me the files", "show the files",
        "list all files", "list everything",
    ]),
    (RequestMode.ACTION, 0.95, "ACTION_FILE", [
        "read ", "open file", "edit file",
        "rename file", "move file", "copy file",
        "create file", "create directory", "mkdir ",
        "delete directory", "remove file",
        "delete ", "remove ", "rename ", "copy ", "move ",
    ]),
    # SHELL
    (RequestMode.ACTION, 0.90, "ACTION_SHELL", [
        "run ", "execute ", "build ", "test ", "install ",
    ]),
    (RequestMode.ACTION, 0.85, "ACTION_SHELL", [
        "commit ", "push ", "pull ", "git ",
        "npm ", "poetry ", "pip ", "yarn ",
    ]),
    # BROWSER
    (RequestMode.ACTION, 0.90, "ACTION_BROWSER", [
        "search amazon", "search google", "open website",
        "browse to ",
    ]),
    # SYSTEM
    (RequestMode.ACTION, 0.90, "ACTION_SYSTEM", [
        "open chrome", "open browser", "launch ",
        "start ", "open folder", "open project",
    ]),
    (RequestMode.ACTION, 0.90, "ACTION_SYSTEM", [
        "go to web folder", "go to project", "go to folder",
    ]),
    (RequestMode.ACTION, 0.85, "ACTION_SYSTEM", [
        "change directory", "cd ",
        "open settings", "change settings",
    ]),
]

_CHAT_PATTERNS = [
    (RequestMode.CHAT, 0.99, None, [
        "hello", "hi ", "hey", "thanks", "thank you",
        "goodbye", "bye", "good morning", "good evening",
    ]),
    (RequestMode.CHAT, 0.95, None, [
        "what is ", "what's ", "who is ", "how do ", "how to ",
    ]),
    (RequestMode.CHAT, 0.90, None, [
        "explain ", "tell me about ", "meaning of ", "definition of ",
        "what can you do", "help", "how does ",
    ]),
    (RequestMode.CHAT, 0.85, None, [
        "why is ", "why does ", "can you explain",
    ]),
]

_ALL_PATTERNS = (
    ("agent", _AGENT_PATTERNS),
    ("codebase", _CODEBASE_PATTERNS),
    ("direct", _DIRECT_PATTERNS),
    ("chat", _CHAT_PATTERNS),
    ("action", _ACTION_PATTERNS),
)


def _keyword_classify(text: str) -> Classification | None:
    lowered = text.lower().strip()

    # Agent override patterns (checked before AGENT, same priority)
    for mode, conf, sub_type, triggers in _AGENT_OVERRIDE_PATTERNS:
        for trigger in triggers:
            if trigger in lowered:
                return Classification(mode=mode, confidence=conf, sub_type=sub_type)

    for group_name, patterns in _ALL_PATTERNS:
        for mode, conf, sub_type, triggers in patterns:
            for trigger in triggers:
                if lowered.startswith(trigger) or trigger in lowered:
                    if group_name == "action":
                        return Classification(mode=mode, confidence=conf, sub_type=sub_type)
                    return Classification(mode=mode, confidence=conf)

    # Catch "can you X", "please X", "could you X"
    for prefix in ("can you ", "could you ", "please ", "i need you to "):
        if lowered.startswith(prefix):
            rest = lowered[len(prefix):]
            for mode, conf, sub_type, triggers in _ACTION_PATTERNS:
                for trigger in triggers:
                    if rest.startswith(trigger) or trigger in rest:
                        return Classification(mode=mode, confidence=conf - 0.10, sub_type=sub_type)
            for mode, conf, _, triggers in _CODEBASE_PATTERNS:
                for trigger in triggers:
                    if rest.startswith(trigger) or trigger in rest:
                        return Classification(mode=mode, confidence=conf - 0.10)

    return None


def _llm_router_classify(text: str, fallback: Classification) -> Classification:
    """Use a small, fast LLM to classify ambiguous requests."""
    try:
        from core.llm_router import complete
        import asyncio

        prompt = (
            "Classify this user request into exactly one mode.\n\n"
            "Modes:\n"
            "- CHAT: greetings, questions, explanations, discussion\n"
            "- DIRECT: weather, news, stocks, time\n"
            "- ACTION: file ops, shell commands, browser ops, system control\n"
            "- CODEBASE: find code, explain architecture, search project\n"
            "- AGENT: multi-step tasks, project generation, repair, build\n\n"
            "Reply with only the mode name.\n\n"
            f"Request: {text}\n\nMode:"
        )

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(complete(prompt, model="qwen2.5:0.5b"))
            loop.close()
            mode_str = result.unwrap_or("").strip().upper() if hasattr(result, "unwrap_or") else str(result).strip().upper()
        except Exception:
            return fallback

        mode_map = {
            "CHAT": RequestMode.CHAT,
            "DIRECT": RequestMode.DIRECT,
            "ACTION": RequestMode.ACTION,
            "CODEBASE": RequestMode.CODEBASE,
            "AGENT": RequestMode.AGENT,
        }

        for key, mode in mode_map.items():
            if key in mode_str or mode_str == key:
                return Classification(mode=mode, confidence=0.82)
        return fallback
    except Exception as e:
        logger.debug("[classify] LLM router failed: %s", e)
        return fallback


def classify_request(text: str) -> Classification:
    """
    Hybrid classifier: fast keyword match (<1ms), then LLM router if uncertain.
    Returns a Classification with mode, confidence, and optional sub_type.
    """
    # Step 1: Fast keyword
    result = _keyword_classify(text)

    if result is not None and result.confidence >= 0.85:
        return result

    # Step 2: Low confidence or no match → use router LLM
    fallback = result or Classification(mode=RequestMode.AGENT, confidence=0.50)
    result = _llm_router_classify(text, fallback)

    # Step 3: Uncertainty floor → upgrade to AGENT
    if result.confidence < 0.70:
        result.mode = RequestMode.AGENT
        result.confidence = 0.50

    return result
