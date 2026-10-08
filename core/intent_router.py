"""core/intent_router — deterministic intent extraction (deprecated module).

STATUS: deprecated for NEW production code — use
``core.routing.request_classifier.classify_request()`` instead
(tests/architecture/test_enforce_canonical.py forbids new imports). The module
is kept alive for its grandfathered callers (network/websocket_server.py) and
the committed e2e contract tests (tests/e2e/test_e2e_intents.py, which patch
``core.intent_router.extract_intent``).

Rebuilt from the committed contracts:

- tests/e2e/test_e2e_intents.py — 16 pinned input -> intent mappings plus a
  fallback guarantee (unknown text must land on chat/web_search/message).
- network/websocket_server.py — ``await extract_intent(text)`` returning a
  dict with an ``intent`` key.

Design: pure keyword/rule engine, no network and no LLM dependency. The
original LLM-assisted path (``instructor``) is optional-by-design here — the
rule engine IS the deterministic fallback the tests pin, so classification is
identical offline and in CI.
"""
from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------- #
# Rule table — evaluated in order; first match wins.                          #
# Order resolves the pinned ambiguities:                                      #
#   "search latest AI news"   -> web_search  (before news)                    #
#   "open youtube"            -> open_url    (site list, before pc_control)   #
#   "open notepad"            -> pc_control  (not a site)                     #
#   "what is python"          -> chat        (no bare-language code trigger)  #
# --------------------------------------------------------------------------- #
_RULES: list[tuple[str, "re.Pattern[str]"]] = [
    ("reminder", re.compile(
        r"\bremind(er| me)?\b|\bset (a|an) reminder\b|\balarm\b", re.I)),
    ("weather", re.compile(
        r"\bweather\b|\bforecast\b|\btemperature (in|at|outside)\b|\bhow (hot|cold)\b", re.I)),
    ("time", re.compile(
        r"\bwhat time\b|\btime is it\b|\bcurrent time\b|\btime in\b|\bdate today\b", re.I)),
    ("web_search", re.compile(
        r"^\s*(search|google|look up|find out|research)\b", re.I)),
    ("news", re.compile(
        r"\b(news|headlines?)\b|\blatest (tech|technology|science|world|updates?)\b", re.I)),
    ("stocks", re.compile(
        r"\bstocks?\b|\bshares?\b|\bshare price\b|\bticker\b|\bmarket price\b|\bnasdaq\b|\bnyse\b", re.I)),
    ("sports", re.compile(
        r"\bnba\b|\bnfl\b|\bmlb\b|\bpremier league\b|\bchampions league\b|"
        r"\bscores?\b|\bmatch (result|score|tonight)\b|\bgame (tonight|last night)\b", re.I)),
    ("message", re.compile(
        r"\bsend\b.*\b(email|e-?mail|text|sms|whatsapp|message|dm)\b|"
        r"\b(email|text|whatsapp) .*\b(saying|with subject|subject:)\b", re.I)),
    ("play_media", re.compile(
        r"^\s*play\b|\bplay (the )?(song|music|video|podcast|playlist|movie)\b", re.I)),
    ("browser_task", re.compile(
        r"\bsign ?up\b|\bregister (for|an|a)\b|\bcreate an? (account|profile)\b|"
        r"\blog ?in to\b|\bcheck ?out\b|\bfill (in )?(the )?form\b|\bsubscribe to\b|"
        r"\bapply for\b|\bbook (a|the) (ticket|flight|table|appointment)\b|\border (a|the)\b", re.I)),
    ("build", re.compile(
        r"\bbuild\b|\bscaffold\b|"
        r"\b(create|make) (a |an )?(website|web ?app|webpage|landing page|site|project|dashboard)\b", re.I)),
    ("code_task", re.compile(
        r"\brefactor\b|\bdebug\b|\boptimi[sz]e\b|\bfix (the )?(bug|error|tests?|build)\b|"
        r"\bwrite (a )?(script|function|class|unit tests?|code)\b|\bpython function\b|"
        r"\bcompile\b|\blint(er)?\b|\bunit test", re.I)),
]

# Sites that make "open X" a browser action rather than a desktop action.
_OPEN_URL_SITES = (
    "youtube", "google", "github", "gitlab", "netflix", "spotify", "twitter",
    "instagram", "facebook", "reddit", "amazon", "gmail", "linkedin", "maps",
    "discord", "twitch", "chatgpt", "stackoverflow", "wikipedia", "medium",
    "whatsapp web", "telegram web", "notion", "figma", "canva",
)

_OPEN_PC = re.compile(
    r"^\s*(open|close|launch|start|quit|kill|shutdown|shut down|restart|switch to)\b", re.I)

_URLISH = re.compile(r"\bwww\.|https?://|\.(com|org|net|io|gov|edu|co)\b", re.I)


def _matches_open_url(text: str) -> bool:
    """True for 'open <known site>' / 'open <url>' (browser action)."""
    if not re.match(r"^\s*(open|go to|visit)\b", text, re.I):
        return False
    if _URLISH.search(text):
        return True
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(site)}\b", lowered) for site in _OPEN_URL_SITES)


def classify(text: str) -> dict[str, Any]:
    """Rule-engine classification (sync). Returns a result dict."""
    text = text or ""
    for intent, pattern in _RULES:
        if pattern.search(text):
            return {
                "intent": intent,
                "text": text,
                "confidence": 0.9,
                "source": "rule",
            }
    # "open X" disambiguation: site/url -> browser, anything else -> desktop.
    if _matches_open_url(text):
        return {"intent": "open_url", "text": text, "confidence": 0.9, "source": "rule"}
    if _OPEN_PC.match(text):
        return {"intent": "pc_control", "text": text, "confidence": 0.85, "source": "rule"}
    # Fallback: contract allows chat / web_search / message; chat is the
    # honest default for plain conversation.
    return {"intent": "chat", "text": text, "confidence": 0.3, "source": "fallback"}


async def extract_intent(text: str) -> dict[str, Any]:
    """Async entry point used by websocket_server and the e2e contract tests."""
    return classify(text)


__all__ = ["extract_intent", "classify"]
