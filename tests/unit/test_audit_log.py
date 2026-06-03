import json
import os
import tempfile

from core.audit_log import AuditLog, _strip_pii


class TestStripPii:
    def test_strips_email(self):
        result = _strip_pii("Contact me at test@example.com")
        assert "[REDACTED]" in result
        assert "test@example.com" not in result

    def test_strips_phone(self):
        result = _strip_pii("Call 555-123-4567 now")
        assert "[REDACTED]" in result

    def test_strips_credit_card(self):
        result = _strip_pii("Card: 4111111111111111")
        assert "[REDACTED]" in result

    def test_strips_api_key(self):
        result = _strip_pii("api_key=sk-1234567890abcdef")
        assert "[REDACTED]" in result

    def test_strips_password(self):
        result = _strip_pii("password: mysecret123")
        assert "[REDACTED]" in result

    def test_plain_text_unchanged(self):
        text = "Hello world, how are you?"
        assert _strip_pii(text) == text

    def test_multiple_patterns(self):
        text = "Email: user@test.com, Phone: 555-000-1111"
        result = _strip_pii(text)
        assert result.count("[REDACTED]") == 2


class TestAuditLog:
    def test_log_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditLog(log_dir=tmp)
            audit.log(event="test_event", user_id="u1", path="/test", method="GET")
            audit.force_flush()
            files = list(audit.log_dir.glob("*.jsonl"))
            assert len(files) == 1

    def test_log_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditLog(log_dir=tmp)
            audit.log(event="test_event", user_id="u1", path="/test", method="GET", status=200)
            audit.force_flush()
            data = json.loads(next(audit.log_dir.glob("*.jsonl")).read_text())
            assert data["event"] == "test_event"
            assert data["user_id"] == "u1"
            assert data["path"] == "/test"
            assert data["status"] == 200

    def test_log_strips_pii_from_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditLog(log_dir=tmp)
            audit.log(event="login", request_body={"email": "secret@example.com"})
            audit.force_flush()
            data = json.loads(next(audit.log_dir.glob("*.jsonl")).read_text())
            assert "secret@example.com" not in data["request_body"]

    def test_buffer_flushes_after_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditLog(log_dir=tmp, buffer_size=5)
            for i in range(5):
                audit.log(event=f"e{i}")
            files_before = len(list(audit.log_dir.glob("*.jsonl")))
            audit.log(event="trigger_flush")
            files_after = len(list(audit.log_dir.glob("*.jsonl")))
            assert files_after > files_before or files_after > 0

    def test_force_flush_writes_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditLog(log_dir=tmp)
            audit.log(event="e1")
            audit.log(event="e2")
            audit.force_flush()
            lines = next(audit.log_dir.glob("*.jsonl")).read_text().strip().split("\n")
            assert len(lines) >= 2
