from core.routing.request_classifier import RequestMode, classify_request
from core.pipeline.adapters.rest_adapter import _desktop_action, _reminder_action, _needs_reminder_time, _inline_reminder_action


def test_normalizes_polite_browser_commands():
    result = classify_request("Please open yt!")
    assert result.mode is RequestMode.ACTION
    assert result.sub_type == "ACTION_BROWSER"


def test_normalizes_conversational_agent_request():
    result = classify_request("Could you build an app?")
    assert result.mode is RequestMode.AGENT


def test_understands_desktop_state_and_input_commands():
    assert _desktop_action("what apps are open", "session")["action"] == "desktop_state"
    assert _desktop_action("click at 100, 200", "session")["params"] == {"x": 100, "y": 200}
    assert _desktop_action("type hello", "session")["params"]["text"] == "hello"
    assert _desktop_action("press enter", "session")["params"]["key"] == "enter"


def test_splits_mixed_desktop_command_chain():
    import re

    message = "what apps are open click at 100, 200 type hello press enter"
    starts = list(re.finditer(
        r"\b(?:what\s+(?:apps?|applications?|windows?|tabs?)(?:\s+(?:are\s+)?open)?|"
        r"open|launch|start|play|click|type|write|press|hit)\b",
        message,
        flags=re.IGNORECASE,
    ))
    actions = [
        _desktop_action(message[m.start():starts[i + 1].start() if i + 1 < len(starts) else len(message)].strip(), "session")
        for i, m in enumerate(starts)
    ]
    assert [action["action"] for action in actions] == [
        "desktop_state", "click", "type_text", "press_key"
    ]


def test_parses_relative_reminder():
    action = _reminder_action("remind me in 10 minutes to check the oven", "peter")
    assert action["action"] == "create_reminder"
    assert action["params"]["title"] == "check the oven"
    assert action["params"]["user_id"] == "peter"


def test_detects_reminder_missing_time():
    assert _needs_reminder_time("reminder check the refrigerator")
    assert _needs_reminder_time("reaminder me to tmr next day")
    assert not _needs_reminder_time("remind me in 10 minutes to check the oven")


def test_parses_absolute_reminder_time():
    action = _reminder_action("remind me at 03:30 to check the refrigerator", "peter")
    assert action["params"]["title"] == "check the refrigerator"


def test_accepts_shorthand_minutes_in_inline_reminder():
    action = _inline_reminder_action("reminder check refrigerator at 3:3", "peter")
    assert action["params"]["title"] == "check refrigerator"
    assert _inline_reminder_action("reminder check refrigerator at 3 30", "peter")["params"]["title"] == "check refrigerator"
