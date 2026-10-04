"""Special-token filter - strips forbidden model control tokens from text.

Honest scope: this is a tokenizer-artifact filter. It removes well-known
control tokens that must never survive into prompts or model output.
It does NOT detect or stop prompt injection, does NOT isolate untrusted
content, and is unrelated to the AuthContext authorization
work.

API:
- ``FORBIDDEN_TOKENS`` - control tokens that must never appear.
- ``special_token_free(text)`` - text with every forbidden token
  replaced by ``<REDACTED>`` (formerly misnamed
  ``untrusted_context_message``).
- ``is_token_clean(text)`` - True when text contains no forbidden token
  (formerly misnamed ``is_prompt_safe``).

Untrusted-content isolation and injection-pattern detection exist only
for browser page content: ``core/browser/page_security.py`` (tested by
tests/unit/test_browser_page_security.py, 20 passed). A system-wide
prompt-injection / untrusted-content layer does NOT exist - that is an
open gap, not a completed task.

The earlier status claim of a spec in
``tests/contract/test_prompt_security.py`` was false: that file does
not exist.
"""
from __future__ import annotations

import re
from typing import Any, List

FORBIDDEN_TOKENS: List[str] = [
    "<|endoftext|>",
    "<|endofprompt|>",
    "<|padding|>",
    "<|startoftext|>",
]

_FORBIDDEN_RE: Any = re.compile(
    "|".join(re.escape(t) for t in FORBIDDEN_TOKENS),
    re.IGNORECASE,
)


def special_token_free(message: str) -> str:
    """Return *message* with every forbidden control token redacted."""
    return _FORBIDDEN_RE.sub("<REDACTED>", message)


def is_token_clean(text: str) -> bool:
    """Return True when *text* contains no forbidden control token."""
    return not bool(_FORBIDDEN_RE.search(text))


__all__ = ["FORBIDDEN_TOKENS", "special_token_free", "is_token_clean"]
