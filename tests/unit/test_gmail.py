"""tests/unit/test_gmail.py — Comprehensive tests for Gmail API integration.

All tests mock the Google API client to avoid real API calls.
"""
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch, call

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_creds():
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "fake_refresh_token"
    creds.token = "fake_access_token"
    creds.to_json.return_value = json.dumps({
        "token": "fake_access_token",
        "refresh_token": "fake_refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake.apps.googleusercontent.com",
        "scopes": [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.labels",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.readonly",
        ],
    })
    return creds


def _make_get_executor(result):
    """Create a mock for the `get(kwargs).execute()` chain that returns `result`."""
    get_mock = MagicMock()
    get_mock.execute.return_value = result
    return get_mock


def _make_list_result(msg_ids):
    """Create a mock for `list(kwargs).execute()` returning message IDs."""
    return {"messages": [{"id": m} for m in msg_ids]}


def _msg_dict(msg_id, thread_id, subject, sender, recipients="me@b.com",
              labels=None, snippet=""):
    import base64
    from datetime import datetime
    return {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": labels or [],
        "snippet": snippet,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "To", "value": recipients},
                {"name": "Date", "value": "Mon, 01 Jan 2024 12:00:00 +0000"},
            ],
            "body": {"data": base64.urlsafe_b64encode(b"Body text").decode()},
        },
    }


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "test@gmail.com",
        "messagesTotal": 500,
        "threadsTotal": 50,
        "historyId": "h100",
    }
    return service


def _make_client(mock_creds, mock_service, client_cls=None):
    """Create a GmailClient with mocks ready for chained API calls."""
    if client_cls is None:
        from integrations.gmail import GmailClient
        client_cls = GmailClient
    auth = MagicMock()
    auth.is_authenticated = True
    auth._creds = mock_creds
    auth.service = mock_service  # <-- use .service not ._service
    auth.health_check.return_value = {
        "healthy": True,
        "email": "test@gmail.com",
        "messages_total": 100,
        "latency_ms": 42.0,
    }
    client = client_cls(auth=auth)
    client._authenticated_once = True
    return client, auth, mock_service


def _setup_get_side_effect(service, msg_dicts):
    """Configure service.users().messages().get() to return msg_dicts in sequence."""
    executors = [_make_get_executor(m) for m in msg_dicts]
    service.users.return_value.messages.return_value.get.side_effect = executors


@pytest.fixture
def mock_gmail_client(mock_creds, mock_service):
    return _make_client(mock_creds, mock_service)


# ── Auth Tests ───────────────────────────────────────────────────────────────

class TestGmailAuth:
    def test_initial_state(self):
        from integrations.gmail.auth import GmailAuth
        auth = GmailAuth(creds_path="/nonexistent/creds.json", token_path="/nonexistent/token.json")
        assert not auth.is_authenticated
        assert auth.email is None
        assert not auth.has_credentials_file()
        assert not auth.has_token()

    def test_has_credentials_file(self, tmp_path):
        from integrations.gmail.auth import GmailAuth
        creds_file = tmp_path / "creds.json"
        creds_file.write_text("{}")
        auth = GmailAuth(creds_path=str(creds_file), token_path=str(tmp_path / "token.json"))
        assert auth.has_credentials_file()
        assert not auth.has_token()

    def test_has_token(self, tmp_path):
        from integrations.gmail.auth import GmailAuth
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")
        auth = GmailAuth(creds_path=str(tmp_path / "creds.json"), token_path=str(token_file))
        assert not auth.has_credentials_file()
        assert auth.has_token()

    def test_authenticate_with_existing_token(self, tmp_path, mock_creds):
        from integrations.gmail.auth import GmailAuth
        token_file = tmp_path / "token.json"
        token_file.write_text(mock_creds.to_json())
        auth = GmailAuth(creds_path=str(tmp_path / "creds.json"), token_path=str(token_file))
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_file") as mock_from:
            mock_from.return_value = mock_creds
            with patch("google.auth.transport.requests.Request"):
                result = auth.authenticate()
                assert result
                assert auth.is_authenticated

    def test_health_check_authenticated(self, mock_creds):
        from integrations.gmail.auth import GmailAuth
        auth = GmailAuth(creds_path="/dev/null", token_path="/dev/null")
        auth._creds = mock_creds
        mock_service = MagicMock()
        mock_service.users().getProfile().execute.return_value = {
            "emailAddress": "test@gmail.com",
            "messagesTotal": 100,
        }
        auth._service = mock_service
        result = auth.health_check()
        assert result["healthy"]
        assert result["email"] == "test@gmail.com"
        assert "latency_ms" in result

    def test_health_check_unauthenticated(self):
        from integrations.gmail.auth import GmailAuth
        auth = GmailAuth(creds_path="/dev/null", token_path="/dev/null")
        result = auth.health_check()
        assert not result["healthy"]
        assert "Not authenticated" in result["error"]

    def test_health_check_api_failure(self, mock_creds):
        from integrations.gmail.auth import GmailAuth
        auth = GmailAuth(creds_path="/dev/null", token_path="/dev/null")
        auth._creds = mock_creds
        mock_service = MagicMock()
        mock_service.users().getProfile().execute.side_effect = Exception("API error")
        auth._service = mock_service
        result = auth.health_check()
        assert not result["healthy"]

    def test_get_auth_url_generates_url(self, tmp_path):
        from integrations.gmail.auth import GmailAuth
        creds_file = tmp_path / "creds.json"
        creds_file.write_text(json.dumps({
            "installed": {
                "client_id": "test.apps.googleusercontent.com",
                "project_id": "test",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_secret": "test_secret",
                "redirect_uris": ["http://localhost"]
            }
        }))
        auth = GmailAuth(creds_path=str(creds_file), token_path=str(tmp_path / "token.json"))
        with patch("google_auth_oauthlib.flow.InstalledAppFlow") as MockFlow:
            flow_instance = MagicMock()
            flow_instance.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?test=1", "")
            MockFlow.from_client_secrets_file.return_value = flow_instance
            url = auth.get_auth_url()
            assert url.startswith("https://accounts.google.com/")

    def test_revoke_deletes_token(self, tmp_path, mock_creds):
        from integrations.gmail.auth import GmailAuth
        token_file = tmp_path / "token.json"
        token_file.write_text(mock_creds.to_json())
        auth = GmailAuth(creds_path=str(tmp_path / "creds.json"), token_path=str(token_file))
        auth._creds = mock_creds
        with patch("requests.post"):
            auth.revoke()
        assert not token_file.exists()
        assert not auth.is_authenticated

    def test_save_token_persists(self, tmp_path, mock_creds):
        from integrations.gmail.auth import GmailAuth
        token_file = tmp_path / "token.json"
        auth = GmailAuth(creds_path=str(tmp_path / "creds.json"), token_path=str(token_file))
        auth._creds = mock_creds
        auth._save_token()
        assert token_file.exists()
        data = json.loads(token_file.read_text())
        assert data["token"] == "fake_access_token"

    def test_get_auth_singleton(self):
        from integrations.gmail.auth import get_auth, _auth_instance, _auth_lock
        _auth_instance = None
        with patch("integrations.gmail.auth.GmailAuth") as MockAuth:
            a1 = get_auth()
            a2 = get_auth()
            assert a1 is a2


# ── Types Tests ──────────────────────────────────────────────────────────────

class TestGmailTypes:
    def test_message_from_api_basic(self):
        from integrations.gmail.types import message_from_api
        api_msg = {
            "id": "msg123",
            "threadId": "thread456",
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": "Hello world",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@gmail.com"},
                    {"name": "To", "value": "recipient@gmail.com"},
                    {"name": "Date", "value": "Mon, 01 Jan 2024 12:00:00 +0000"},
                ],
                "body": {"data": "SGVsbG8gV29ybGQ="},  # "Hello World"
            },
        }
        msg = message_from_api(api_msg)
        assert msg.id == "msg123"
        assert msg.thread_id == "thread456"
        assert msg.subject == "Test Subject"
        assert msg.sender == "sender@gmail.com"
        assert "recipient@gmail.com" in msg.recipients
        assert msg.unread
        assert msg.body_text == "Hello World"

    def test_message_from_api_html_alternative(self):
        from integrations.gmail.types import message_from_api
        api_msg = {
            "id": "msg1",
            "threadId": "t1",
            "labelIds": [],
            "snippet": "HTML email",
            "payload": {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": "UGxhaW4gYm9keQ=="},  # "Plain body"
                    },
                    {
                        "mimeType": "text/html",
                        "body": {"data": "PGgxPkhUTUwgYm9keTwvaDE+"},  # "<h1>HTML body</h1>"
                    },
                ],
            },
        }
        msg = message_from_api(api_msg)
        assert msg.body_text == "Plain body"
        assert msg.body_html == "<h1>HTML body</h1>"

    def test_extract_attachments_no_attachments(self):
        from integrations.gmail.types import _extract_attachments
        payload = {"mimeType": "text/plain", "body": {}}
        atts = _extract_attachments(payload, "msg1")
        assert atts == []

    def test_label_from_api(self):
        from integrations.gmail.types import label_from_api
        api_label = {
            "id": "LABEL_1",
            "name": "My Label",
            "type": "user",
            "messageListVisibility": "show",
            "labelListVisibility": "labelShow",
            "messagesTotal": 10,
            "messagesUnread": 2,
            "threadsTotal": 8,
            "threadsUnread": 1,
        }
        label = label_from_api(api_label)
        assert label.id == "LABEL_1"
        assert label.name == "My Label"
        assert label.messages_total == 10
        assert label.messages_unread == 2

    def test_thread_from_api(self):
        from integrations.gmail.types import thread_from_api
        api_thread = {
            "id": "thread1",
            "snippet": "Thread snippet",
            "historyId": "h1",
            "messages": [
                {
                    "id": "msg1",
                    "threadId": "thread1",
                    "labelIds": [],
                    "snippet": "First",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "Subject", "value": "Re: Hello"},
                            {"name": "From", "value": "a@b.com"},
                            {"name": "To", "value": "c@d.com"},
                            {"name": "Date", "value": "Mon, 01 Jan 2024 12:00:00 +0000"},
                        ],
                        "body": {},
                    },
                },
                {
                    "id": "msg2",
                    "threadId": "thread1",
                    "labelIds": [],
                    "snippet": "Second",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "Subject", "value": "Re: Hello"},
                            {"name": "From", "value": "c@d.com"},
                            {"name": "To", "value": "a@b.com"},
                            {"name": "Date", "value": "Mon, 01 Jan 2024 12:01:00 +0000"},
                        ],
                        "body": {},
                    },
                },
            ],
        }
        thread = thread_from_api(api_thread)
        assert thread.id == "thread1"
        assert len(thread.messages) == 2
        assert thread.messages[0].id == "msg1"
        assert thread.messages[1].id == "msg2"

    def test_decode_data(self):
        from integrations.gmail.types import _decode_data
        import base64
        original = "Hello World!"
        encoded = base64.urlsafe_b64encode(original.encode()).decode()
        assert _decode_data(encoded) == "Hello World!"

    def test_decode_data_invalid(self):
        from integrations.gmail.types import _decode_data
        assert _decode_data("!!!invalid base64!!!") == ""


# ── Client Tests ─────────────────────────────────────────────────────────────

class TestGmailClient:
    def test_authenticate(self, mock_creds, mock_service):
        from integrations.gmail.client import GmailClient
        auth = MagicMock()
        auth.is_authenticated = False
        def _authenticate(headless=False):
            auth.is_authenticated = True
            return True
        auth.authenticate.side_effect = _authenticate
        auth.service = mock_service
        client = GmailClient(auth=auth)
        assert client.authenticate()
        assert client.is_authenticated()

    def test_is_authenticated(self, mock_gmail_client):
        client, auth, _ = mock_gmail_client
        assert client.is_authenticated()

    def test_health_check(self, mock_gmail_client):
        client, auth, _ = mock_gmail_client
        result = client.health_check()
        assert result["healthy"]
        assert result["email"] == "test@gmail.com"

    def test_get_profile(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        service.users.return_value.getProfile.return_value.execute.return_value = {
            "emailAddress": "test@gmail.com",
            "messagesTotal": 500,
            "threadsTotal": 50,
            "historyId": "h100",
        }
        profile = client.get_profile()
        assert profile is not None
        assert profile.email == "test@gmail.com"
        assert profile.messages_total == 500
        assert profile.threads_total == 50

    def test_get_profile_failure(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        service.users.return_value.getProfile.return_value.execute.side_effect = Exception("API error")
        assert client.get_profile() is None

    def test_list_messages(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.list.return_value.execute.return_value = _make_list_result(["msg1", "msg2"])
        _setup_get_side_effect(service, [
            _msg_dict("msg1", "t1", "First", "a@b.com", labels=["INBOX"], snippet="First"),
            _msg_dict("msg2", "t2", "Second", "c@b.com", labels=["INBOX", "UNREAD"], snippet="Second"),
        ])
        msgs = client.list_messages(max_results=2)
        assert len(msgs) == 2
        assert msgs[0].id == "msg1"
        assert msgs[0].subject == "First"
        assert msgs[1].id == "msg2"
        assert msgs[1].unread

    def test_list_messages_empty(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        service.users.return_value.messages.return_value.list.return_value.execute.return_value = {}
        msgs = client.list_messages()
        assert msgs == []

    def test_list_messages_api_error(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        service.users.return_value.messages.return_value.list.return_value.execute.side_effect = Exception("API error")
        msgs = client.list_messages()
        assert msgs == []

    def test_get_message(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        _setup_get_side_effect(service, [
            _msg_dict("msg1", "t1", "Single", "x@y.com", recipients="me@y.com", snippet="Single"),
        ])
        msg = client.get_message("msg1")
        assert msg is not None
        assert msg.id == "msg1"
        assert msg.subject == "Single"

    def test_get_message_not_found(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.get.return_value.execute.side_effect = Exception("Not found")
        msg = client.get_message("nonexistent")
        assert msg is None

    def test_send_message(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.send.return_value.execute.return_value = {
            "id": "sent1", "threadId": "thread1",
        }
        result = client.send_message(
            to="recipient@example.com",
            subject="Hello",
            body="Test message"
        )
        assert result is not None
        assert result["id"] == "sent1"

    def test_send_message_with_thread(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.send.return_value.execute.return_value = {
            "id": "sent2", "threadId": "thread1",
        }
        result = client.send_message(
            to="r@example.com",
            subject="Re: Hello",
            body="Reply",
            thread_id="thread1",
        )
        assert result is not None
        body_arg = msgs_service.send.call_args[1]["body"]
        assert body_arg["threadId"] == "thread1"

    def test_send_message_html(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.send.return_value.execute.return_value = {"id": "s1", "threadId": "t1"}
        result = client.send_message(
            to="r@example.com",
            subject="HTML",
            body="<h1>Hello</h1>",
            body_type="html",
        )
        assert result is not None

    def test_send_message_multiple_recipients(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.send.return_value.execute.return_value = {"id": "s1", "threadId": "t1"}
        result = client.send_message(
            to=["a@b.com", "c@d.com"],
            subject="Multiple",
            body="Hi all",
        )
        assert result is not None

    def test_send_message_failure(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.send.return_value.execute.side_effect = Exception("Send failed")
        result = client.send_message(
            to="r@example.com",
            subject="Fail",
            body="Test",
        )
        assert result is None

    def test_search_messages(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.list.return_value.execute.return_value = _make_list_result(["msg1"])
        _setup_get_side_effect(service, [
            _msg_dict("msg1", "t1", "Found", "a@b.com", snippet="Found"),
        ])
        results = client.search_messages(query="from:someone", max_results=5)
        assert len(results) == 1
        assert results[0].subject == "Found"

    def test_get_attachment(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        import base64
        file_data = base64.urlsafe_b64encode(b"fake file content").decode()
        att_service = service.users.return_value.messages.return_value.attachments.return_value
        att_service.get.return_value.execute.return_value = {
            "data": file_data,
            "size": 17,
            "mimeType": "text/plain",
        }
        att = client.get_attachment("msg1", "att1")
        assert att is not None
        assert att.attachment_id == "att1"
        assert att.message_id == "msg1"
        assert att.data == b"fake file content"

    def test_get_attachment_not_found(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        att_service = service.users.return_value.messages.return_value.attachments.return_value
        att_service.get.return_value.execute.side_effect = Exception("Not found")
        att = client.get_attachment("msg1", "nonexistent")
        assert att is None

    def test_download_attachment(self, mock_gmail_client, tmp_path):
        client, auth, service = mock_gmail_client
        import base64
        file_data = base64.urlsafe_b64encode(b"download test").decode()
        att_service = service.users.return_value.messages.return_value.attachments.return_value
        att_service.get.return_value.execute.return_value = {
            "data": file_data,
            "size": 13,
            "mimeType": "application/pdf",
        }
        save_path = client.download_attachment("msg1", "att1", str(tmp_path), filename="test.pdf")
        assert save_path is not None
        assert save_path.exists()
        assert save_path.read_bytes() == b"download test"

    def test_list_labels(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        labels_service = service.users.return_value.labels.return_value
        labels_service.list.return_value.execute.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "LABEL_1", "name": "My Label", "type": "user",
                 "messageListVisibility": "show", "labelListVisibility": "labelShow",
                 "messagesTotal": 5, "messagesUnread": 1,
                 "threadsTotal": 4, "threadsUnread": 1},
            ],
        }
        labels = client.list_labels()
        assert len(labels) == 2
        assert labels[0].name == "INBOX"
        assert labels[1].name == "My Label"
        assert labels[1].messages_total == 5

    def test_list_labels_empty(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        service.users.return_value.labels.return_value.list.return_value.execute.return_value = {}
        assert client.list_labels() == []

    def test_list_labels_error(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        service.users.return_value.labels.return_value.list.return_value.execute.side_effect = Exception("API error")
        assert client.list_labels() == []

    def test_create_label(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        labels_service = service.users.return_value.labels.return_value
        labels_service.create.return_value.execute.return_value = {
            "id": "NEW_LABEL",
            "name": "New Label",
            "type": "user",
            "messageListVisibility": "show",
            "labelListVisibility": "labelShow",
        }
        label = client.create_label("New Label")
        assert label is not None
        assert label.id == "NEW_LABEL"
        assert label.name == "New Label"

    def test_create_label_failure(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        service.users.return_value.labels.return_value.create.return_value.execute.side_effect = Exception("Create failed")
        label = client.create_label("Fail")
        assert label is None

    def test_get_label(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        labels_service = service.users.return_value.labels.return_value
        labels_service.get.return_value.execute.return_value = {
            "id": "LABEL_1", "name": "My Label", "type": "user",
            "messageListVisibility": "hide", "labelListVisibility": "labelHide",
            "messagesTotal": 3, "messagesUnread": 0,
            "threadsTotal": 3, "threadsUnread": 0,
        }
        label = client.get_label("LABEL_1")
        assert label is not None
        assert label.name == "My Label"

    def test_update_label(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        labels_service = service.users.return_value.labels.return_value
        labels_service.get.return_value.execute.return_value = {
            "id": "LABEL_1", "name": "Old Name", "type": "user",
            "messageListVisibility": "show", "labelListVisibility": "labelShow",
            "messagesTotal": 0, "messagesUnread": 0,
            "threadsTotal": 0, "threadsUnread": 0,
        }
        labels_service.update.return_value.execute.return_value = {
            "id": "LABEL_1", "name": "New Name", "type": "user",
            "messageListVisibility": "show", "labelListVisibility": "labelShow",
            "messagesTotal": 0, "messagesUnread": 0,
            "threadsTotal": 0, "threadsUnread": 0,
        }
        label = client.update_label("LABEL_1", name="New Name")
        assert label is not None
        assert label.name == "New Name"

    def test_delete_label(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        labels_service = service.users.return_value.labels.return_value
        labels_service.delete.return_value.execute.return_value = {}
        assert client.delete_label("LABEL_1")

    def test_delete_label_failure(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        labels_service = service.users.return_value.labels.return_value
        labels_service.delete.return_value.execute.side_effect = Exception("Delete failed")
        assert not client.delete_label("LABEL_1")

    def test_modify_message_labels(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.modify.return_value.execute.return_value = {}
        assert client.modify_message_labels("msg1", add_label_ids=["STARRED"])

    def test_modify_message_labels_remove(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.modify.return_value.execute.return_value = {}
        assert client.modify_message_labels("msg1", remove_label_ids=["UNREAD"])

    def test_modify_message_labels_noop(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        assert not client.modify_message_labels("msg1")

    def test_mark_as_read(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.modify.return_value.execute.return_value = {}
        assert client.mark_as_read("msg1")

    def test_mark_as_unread(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.modify.return_value.execute.return_value = {}
        assert client.mark_as_unread("msg1")

    def test_move_to_trash(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.trash.return_value.execute.return_value = {}
        assert client.move_to_trash("msg1")

    def test_untrash(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.untrash.return_value.execute.return_value = {}
        assert client.untrash("msg1")

    def test_batch_modify_labels(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        msgs_service = service.users.return_value.messages.return_value
        msgs_service.batchModify.return_value.execute.return_value = {}
        assert client.batch_modify_labels(
            ["msg1", "msg2"],
            add_label_ids=["STARRED"],
            remove_label_ids=["UNREAD"],
        )

    def test_list_threads(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        threads_service = service.users.return_value.threads.return_value
        threads_service.list.return_value.execute.return_value = {
            "threads": [{"id": "thread1"}],
        }
        threads_service.get.return_value.execute.return_value = {
            "id": "thread1", "snippet": "A thread",
            "historyId": "h1",
            "messages": [
                {
                    "id": "msg1", "threadId": "thread1", "labelIds": [],
                    "snippet": "First",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": "Subject", "value": "Re: Hello"},
                                    {"name": "From", "value": "a@b.com"},
                                    {"name": "To", "value": "me@b.com"},
                                    {"name": "Date", "value": "Mon, 01 Jan 2024 12:00:00 +0000"}],
                        "body": {},
                    },
                },
            ],
        }
        threads = client.list_threads(max_results=1)
        assert len(threads) == 1
        assert threads[0].id == "thread1"
        assert len(threads[0].messages) == 1

    def test_get_thread(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        threads_service = service.users.return_value.threads.return_value
        threads_service.get.return_value.execute.return_value = {
            "id": "thread1",
            "snippet": "Full thread",
            "historyId": "h1",
            "messages": [
                {
                    "id": "msg1", "threadId": "thread1", "labelIds": [],
                    "snippet": "Msg 1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": "Subject", "value": "Re: Hello"},
                                    {"name": "From", "value": "a@b.com"},
                                    {"name": "To", "value": "me@b.com"},
                                    {"name": "Date", "value": "Mon, 01 Jan 2024 12:00:00 +0000"}],
                        "body": {},
                    },
                },
            ],
        }
        thread = client.get_thread("thread1")
        assert thread is not None
        assert thread.id == "thread1"

    def test_modify_thread_labels(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        threads_service = service.users.return_value.threads.return_value
        threads_service.modify.return_value.execute.return_value = {}
        assert client.modify_thread_labels("thread1", add_label_ids=["STARRED"])

    def test_list_drafts(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        drafts_service = service.users.return_value.drafts.return_value
        drafts_service.list.return_value.execute.return_value = {
            "drafts": [{"id": "d1", "message": {"id": "m1"}}],
        }
        drafts = client.list_drafts()
        assert len(drafts) == 1
        assert drafts[0]["id"] == "d1"

    def test_get_draft(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        drafts_service = service.users.return_value.drafts.return_value
        drafts_service.get.return_value.execute.return_value = {
            "id": "d1", "message": {"id": "m1"},
        }
        draft = client.get_draft("d1")
        assert draft is not None
        assert draft["id"] == "d1"

    def test_create_draft(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        drafts_service = service.users.return_value.drafts.return_value
        drafts_service.create.return_value.execute.return_value = {
            "id": "d1", "message": {"id": "m1"},
        }
        draft = client.create_draft(to="r@example.com", subject="Draft", body="Test")
        assert draft is not None
        assert draft["id"] == "d1"

    def test_send_draft(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        drafts_service = service.users.return_value.drafts.return_value
        drafts_service.send.return_value.execute.return_value = {
            "id": "sent_d1", "threadId": "t1",
        }
        result = client.send_draft("d1")
        assert result is not None
        assert result["id"] == "sent_d1"

    def test_delete_draft(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        drafts_service = service.users.return_value.drafts.return_value
        drafts_service.delete.return_value.execute.return_value = {}
        assert client.delete_draft("d1")

    def test_batch_get_messages(self, mock_gmail_client):
        client, auth, service = mock_gmail_client
        _setup_get_side_effect(service, [
            _msg_dict("m1", "t1", "M1", "a@b.com", snippet="M1"),
            _msg_dict("m2", "t2", "M2", "c@b.com", snippet="M2"),
        ])
        msgs = client.batch_get_messages(["m1", "m2"])
        assert len(msgs) == 2


# ── Integration Manager Tests ────────────────────────────────────────────────

class TestGmailIntegration:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        from core.integration_manager import GmailIntegration
        integ = GmailIntegration()
        with patch("integrations.gmail.GmailClient") as MockClient:
            client_instance = MagicMock()
            MockClient.return_value = client_instance
            client_instance.authenticate.return_value = True
            ok = await integ.connect()
            assert ok
            assert integ._connected

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        from core.integration_manager import GmailIntegration
        integ = GmailIntegration()
        with patch("integrations.gmail.GmailClient") as MockClient:
            client_instance = MagicMock()
            MockClient.return_value = client_instance
            client_instance.authenticate.return_value = False
            ok = await integ.connect()
            assert not ok
            assert not integ._connected

    @pytest.mark.asyncio
    async def test_health_check_not_connected(self):
        from core.integration_manager import GmailIntegration
        integ = GmailIntegration()
        status = await integ.health_check()
        assert not status.healthy
        assert "Not connected" in status.error

    @pytest.mark.asyncio
    async def test_health_check_connected(self):
        from core.integration_manager import GmailIntegration
        integ = GmailIntegration()
        integ._connected = True
        integ._gmail_client = MagicMock()
        integ._gmail_client.health_check.return_value = {
            "healthy": True, "email": "t@t.com", "latency_ms": 50.0,
        }
        status = await integ.health_check()
        assert status.healthy

    @pytest.mark.asyncio
    async def test_send_not_connected(self):
        from core.integration_manager import GmailIntegration
        integ = GmailIntegration()
        result = await integ.send("t@t.com", "hello")
        assert not result

    @pytest.mark.asyncio
    async def test_send_success(self):
        from core.integration_manager import GmailIntegration
        integ = GmailIntegration()
        integ._connected = True
        integ._gmail_client = MagicMock()
        integ._gmail_client.send_message.return_value = {"id": "sent1"}
        result = await integ.send("t@t.com", "hello", subject="Test")
        assert result

    @pytest.mark.asyncio
    async def test_receive_not_connected(self):
        from core.integration_manager import GmailIntegration
        integ = GmailIntegration()
        result = await integ.receive()
        assert result == []

    @pytest.mark.asyncio
    async def test_receive_success(self):
        from core.integration_manager import GmailIntegration
        from integrations.gmail.types import GmailMessage
        from datetime import datetime, timezone
        integ = GmailIntegration()
        integ._connected = True
        integ._gmail_client = MagicMock()
        integ._gmail_client.list_messages.return_value = [
            GmailMessage(
                id="m1", thread_id="t1", subject="Hi", sender="a@b.com",
                recipients=["me@b.com"], date=datetime.now(timezone.utc),
                snippet="Hello", unread=True, labels=["INBOX"],
            ),
        ]
        result = await integ.receive()
        assert len(result) == 1
        assert result[0]["id"] == "m1"
        assert result[0]["subject"] == "Hi"
