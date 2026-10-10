"""Transport adapters — thin bridges from each channel into the pipeline.

Every adapter builds a canonical ``PipelineContext``, runs it through the
default pipeline, and returns the transport's native response shape.

Pinned contracts
----------------
* ``tests/integration/test_pipeline_transport_consistency.py``
  - ``rest_adapter(message=..., user_id=..., session_id=...)`` -> dict with
    ``response`` == pipeline text, ``model`` == "pipeline"; context captures
    ``transport="rest"``.
  - ``ws_adapter(text=..., user_id=..., session_id=...)`` -> dict with
    ``response``; ``transport="websocket"``.
  - ``voice_adapter(text=..., user_id=..., session_id=...)`` -> string;
    ``transport="voice"``.
  - ``channel_adapter(text=..., source=..., channel_id=..., user_id=...,
    user_name=...)`` -> string; ``transport=<source>``.
* ``tests/unit/test_nlp_intent.py``
  - ``_desktop_action(slot, session_id)`` parses desktop verbs
    (what apps are open / click / type / press) into action dicts.
  - ``_reminder_action`` / ``_needs_reminder_time`` /
    ``_inline_reminder_action`` parse reminder phrasing.

``rest_adapter`` lives in its own submodule with the parsers so
``from core.pipeline.adapters.rest_adapter import _reminder_action`` works;
this package re-exports everything and (on submodule exec) Python rebinds
the parent attribute to the *module*, so we bind the function back under the
module-attribute hook below.
"""
from __future__ import annotations

import core.pipeline.adapters.rest_adapter as _rest_mod

_ws_adapter = _rest_mod.ws_adapter
_voice_adapter = _rest_mod.voice_adapter
_channel_adapter = _rest_mod.channel_adapter
rest_adapter = _rest_mod.rest_adapter
ws_adapter = _ws_adapter
voice_adapter = _voice_adapter
channel_adapter = _channel_adapter
_desktop_action = _rest_mod._desktop_action
_reminder_action = _rest_mod._reminder_action
_needs_reminder_time = _rest_mod._needs_reminder_time
_inline_reminder_action = _rest_mod._inline_reminder_action
parse_desktop_actions = _rest_mod.parse_desktop_actions


# Python's import machinery (``_handle_fromlist``/``_load``) rebinds
# ``core.pipeline.adapters.rest_adapter`` to the *module* object whenever the
# submodule is imported after the package attribute was set to the function.
# Restore the function attribute after the machinery's bind runs
# (``__getattr__`` is only consulted when the attribute lookup fails).
def __getattr__(name: str):
    if name in ("rest_adapter", "ws_adapter", "voice_adapter",
                "channel_adapter", "_desktop_action", "_reminder_action",
                "_needs_reminder_time", "_inline_reminder_action",
                "parse_desktop_actions"):
        return getattr(_rest_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _fixup() -> None:
    """Module-attribute hook: keep the function callable in the parent."""
    import sys

    parent = sys.modules.get(__name__)
    if parent is not None:
        for _name in ("rest_adapter", "ws_adapter", "voice_adapter",
                      "channel_adapter"):
            setattr(parent, _name, getattr(_rest_mod, _name))


_fixup()
del _fixup

__all__ = [
    "rest_adapter", "ws_adapter", "voice_adapter", "channel_adapter",
    "_desktop_action", "_reminder_action", "_needs_reminder_time",
    "_inline_reminder_action", "parse_desktop_actions",
]
