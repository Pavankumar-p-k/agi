from pathlib import Path


def test_no_placeholder_theater_tokens_in_autonomy_routes():
    text = Path("autonomy/api/autonomous_routes.py").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "todo" not in lowered
    assert "notimplemented" not in lowered
    assert "placeholder" not in lowered
