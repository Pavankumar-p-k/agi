"""Tests for core/integration_manager.py — all 6 integration classes."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from core.integration_manager import (
    IntegrationManager,
    IntegrationStatus,
    TelegramIntegration,
    DiscordIntegration,
    SlackIntegration,
    WhatsAppIntegration,
    GitHubIntegration,
    GoogleDriveIntegration,
    get_integration_manager,
)


class TestIntegrationStatus:
    def test_defaults(self):
        s = IntegrationStatus(name="test")
        assert s.name == "test"
        assert s.connected is False
        assert s.healthy is False
        assert s.error == ""

    def test_to_dict(self):
        s = IntegrationStatus(name="t", connected=True, healthy=True, latency_ms=12.34)
        d = s.to_dict()
        assert d["name"] == "t"
        assert d["connected"] is True
        assert d["healthy"] is True
        assert d["latency_ms"] == 12.3


class TestIntegrationManager:
    def test_register_and_get(self):
        m = IntegrationManager()
        t = TelegramIntegration()
        m.register(t)
        assert m.get("telegram") is t

    def test_list_empty(self):
        m = IntegrationManager()
        assert m.list_integrations() == []

    def test_list_after_register(self):
        m = IntegrationManager()
        m.register(TelegramIntegration())
        assert m.list_integrations() == [{"name": "telegram", "connected": False}]

    async def test_connect_unknown(self):
        m = IntegrationManager()
        result = await m.connect("nonexistent")
        assert result is False

    async def test_disconnect_unknown(self):
        m = IntegrationManager()
        result = await m.disconnect("nonexistent")
        assert result is False

    async def test_health_check_unknown(self):
        m = IntegrationManager()
        s = await m.health_check("nonexistent")
        assert s.error == "Unknown integration"

    async def test_send_unknown(self):
        m = IntegrationManager()
        result = await m.send("nonexistent", "target", "msg")
        assert result is False

    async def test_receive_unknown(self):
        m = IntegrationManager()
        result = await m.receive("nonexistent")
        assert result == []

    async def test_health_check_all(self):
        m = IntegrationManager()
        m.register(TelegramIntegration())
        s = TelegramIntegration()
        s._connected = True
        m.register(s)
        results = await m.health_check_all()
        assert "telegram" in results

    def test_get_integration_manager_singleton(self):
        m1 = get_integration_manager()
        m2 = get_integration_manager()
        assert m1 is m2


class TestTelegramIntegration:
    async def test_connect_success(self):
        t = TelegramIntegration()
        with patch.object(t, "_get_credential", return_value="bot123"):
            result = await t.connect(bot_token="bot123")
            assert result is True
            assert t._connected is True

    async def test_connect_no_token(self):
        t = TelegramIntegration()
        with patch.object(t, "_get_credential", return_value=None):
            result = await t.connect()
            assert result is False

    async def test_disconnect(self):
        t = TelegramIntegration()
        t._connected = True
        result = await t.disconnect()
        assert result is True
        assert t._connected is False

    async def test_health_check_not_connected(self):
        t = TelegramIntegration()
        s = await t.health_check()
        assert s.healthy is False
        assert s.error == "Not connected"

    async def test_health_check_success(self):
        t = TelegramIntegration()
        t._connected = True
        with patch.object(t, "_get_credential", return_value="bot123"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.elapsed.total_seconds.return_value = 0.15
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
                s = await t.health_check()
                assert s.healthy is True
                assert s.latency_ms > 0

    async def test_health_check_failure(self):
        t = TelegramIntegration()
        t._connected = True
        with patch.object(t, "_get_credential", return_value="bot123"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("API down"))
                s = await t.health_check()
                assert s.healthy is False
                assert "API down" in s.error

    async def test_send_not_connected(self):
        t = TelegramIntegration()
        result = await t.send("target", "msg")
        assert result is False

    async def test_send_success(self):
        t = TelegramIntegration()
        t._connected = True
        with patch("channels.channel_controller.send", new_callable=AsyncMock, return_value=True):
            result = await t.send("12345", "hello")
            assert result is True

    async def test_receive_not_connected(self):
        t = TelegramIntegration()
        result = await t.receive()
        assert result == []

    async def test_receive_success(self):
        t = TelegramIntegration()
        t._connected = True
        with patch.object(t, "_get_credential", return_value="bot123"):
            with patch("telegram.Bot") as mock_bot:
                mock_update = MagicMock()
                mock_update.update_id = 100
                mock_update.effective_chat.id = 123
                mock_update.effective_user.id = 456
                mock_update.effective_user.full_name = "TestUser"
                mock_update.message.text = "hello"
                mock_update.message.date.isoformat.return_value = "2025-01-01T00:00:00"
                mock_bot.return_value.get_updates = AsyncMock(return_value=[mock_update])
                result = await t.receive()
                assert len(result) == 1
                assert result[0]["text"] == "hello"
                assert t._update_offset == 101


class TestDiscordIntegration:
    async def test_connect_success(self):
        d = DiscordIntegration()
        with patch.object(d, "_get_credential", return_value="token123"):
            result = await d.connect(token="token123")
            assert result is True

    async def test_connect_no_token(self):
        d = DiscordIntegration()
        with patch.object(d, "_get_credential", return_value=None):
            result = await d.connect()
            assert result is False

    async def test_health_check_not_connected(self):
        d = DiscordIntegration()
        s = await d.health_check()
        assert s.error == "Not connected"

    async def test_health_check_success(self):
        d = DiscordIntegration()
        d._connected = True
        with patch.object(d, "_get_credential", return_value="token"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.elapsed.total_seconds.return_value = 0.1
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
                s = await d.health_check()
                assert s.healthy is True

    async def test_send_not_connected(self):
        d = DiscordIntegration()
        result = await d.send("ch", "msg")
        assert result is False

    async def test_receive_not_connected(self):
        d = DiscordIntegration()
        result = await d.receive()
        assert result == []

    async def test_receive_no_target(self):
        d = DiscordIntegration()
        d._connected = True
        result = await d.receive()
        assert result == []

    async def test_receive_success(self):
        d = DiscordIntegration()
        d._connected = True
        with patch.object(d, "_get_credential", return_value="token"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = [{
                    "id": "123",
                    "author": {"id": "456", "username": "User"},
                    "content": "hello",
                    "timestamp": "2025-01-01T00:00:00",
                    "attachments": [],
                }]
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
                result = await d.receive(target="789")
                assert len(result) == 1
                assert result[0]["content"] == "hello"
                assert result[0]["has_attachments"] is False


class TestSlackIntegration:
    async def test_connect_success(self):
        s = SlackIntegration()
        with patch.object(s, "_get_credential", return_value="xoxb-token"):
            with patch("slack_sdk.WebClient") as mock_wc:
                result = await s.connect(bot_token="xoxb-token")
                assert result is True
                assert s._web_client is not None

    async def test_connect_no_token(self):
        s = SlackIntegration()
        with patch.object(s, "_get_credential", return_value=None):
            result = await s.connect()
            assert result is False

    async def test_health_check_not_connected(self):
        s = SlackIntegration()
        stat = await s.health_check()
        assert stat.error == "Not connected"

    async def test_health_check_success(self):
        s = SlackIntegration()
        s._connected = True
        s._web_client = MagicMock()
        s._web_client.auth_test.return_value = {"ok": True}
        stat = await s.health_check()
        assert stat.healthy is True

    async def test_health_check_failure(self):
        s = SlackIntegration()
        s._connected = True
        s._web_client = MagicMock()
        s._web_client.auth_test.side_effect = Exception("Slack error")
        stat = await s.health_check()
        assert stat.healthy is False

    async def test_send_not_connected(self):
        s = SlackIntegration()
        result = await s.send("ch", "msg")
        assert result is False

    async def test_send_success(self):
        s = SlackIntegration()
        s._connected = True
        s._web_client = MagicMock()
        result = await s.send("C123", "hello")
        assert result is True
        s._web_client.chat_postMessage.assert_called_once_with(channel="C123", text="hello")

    async def test_receive_not_connected(self):
        s = SlackIntegration()
        result = await s.receive()
        assert result == []

    async def test_receive_no_channel(self):
        s = SlackIntegration()
        s._connected = True
        s._web_client = MagicMock()
        result = await s.receive()
        assert result == []

    async def test_receive_success(self):
        s = SlackIntegration()
        s._connected = True
        s._web_client = MagicMock()
        s._web_client.conversations_history.return_value = {
            "ok": True,
            "messages": [{"ts": "123.456", "user": "U789", "text": "hello", "type": "message"}],
        }
        result = await s.receive(target="C123")
        assert len(result) == 1
        assert result[0]["text"] == "hello"


class TestWhatsAppIntegration:
    async def test_connect_success(self):
        w = WhatsAppIntegration()
        with patch.object(w, "_get_credential", side_effect=lambda k: {"token": "tok", "phone_id": "pid"}.get(k)):
            result = await w.connect(token="tok", phone_id="pid")
            assert result is True

    async def test_connect_no_creds(self):
        w = WhatsAppIntegration()
        with patch.object(w, "_get_credential", return_value=None):
            result = await w.connect()
            assert result is False

    async def test_health_check_not_connected(self):
        w = WhatsAppIntegration()
        s = await w.health_check()
        assert s.error == "Not connected"

    async def test_health_check_success(self):
        w = WhatsAppIntegration()
        w._connected = True
        mock_provider = AsyncMock()
        mock_provider.health_check = AsyncMock(return_value=True)
        w._provider = mock_provider
        s = await w.health_check()
        assert s.healthy is True

    async def test_health_check_failure(self):
        w = WhatsAppIntegration()
        w._connected = True
        mock_provider = AsyncMock()
        mock_provider.health_check = AsyncMock(return_value=False)
        w._provider = mock_provider
        s = await w.health_check()
        assert s.healthy is False
        assert "failed" in s.error

    async def test_send_not_connected(self):
        w = WhatsAppIntegration()
        result = await w.send("+123", "msg")
        assert result is False

    async def test_send_success(self):
        w = WhatsAppIntegration()
        w._connected = True
        from integrations.whatsapp.models import SendResult
        mock_provider = AsyncMock()
        mock_provider.send_text = AsyncMock(return_value=SendResult(success=True))
        w._provider = mock_provider
        result = await w.send("+123", "hello")
        assert result is True

    async def test_receive_empty(self):
        w = WhatsAppIntegration()
        result = await w.receive()
        assert result == []


class TestGitHubIntegration:
    async def test_connect_success(self):
        g = GitHubIntegration()
        with patch.object(g, "_get_credential", return_value="ghp_token"):
            result = await g.connect(token="ghp_token")
            assert result is True

    async def test_connect_no_token(self):
        g = GitHubIntegration()
        with patch.object(g, "_get_credential", return_value=None):
            result = await g.connect()
            assert result is False

    async def test_health_check_not_connected(self):
        g = GitHubIntegration()
        s = await g.health_check()
        assert s.error == "Not connected"

    async def test_health_check_success(self):
        g = GitHubIntegration()
        g._connected = True
        with patch.object(g, "_get_credential", return_value="tok"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.elapsed.total_seconds.return_value = 0.2
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
                s = await g.health_check()
                assert s.healthy is True
                assert s.latency_ms > 0

    async def test_send_not_connected(self):
        g = GitHubIntegration()
        result = await g.send("user/repo", "msg")
        assert result is False

    async def test_send_creates_issue(self):
        g = GitHubIntegration()
        g._connected = True
        with patch.object(g, "_get_credential", return_value="tok"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_resp = MagicMock()
                mock_resp.status_code = 201
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
                result = await g.send("user/repo", "Issue body", title="Test Issue")
                assert result is True

    async def test_receive_not_connected(self):
        g = GitHubIntegration()
        result = await g.receive()
        assert result == []

    async def test_receive_success(self):
        g = GitHubIntegration()
        g._connected = True
        with patch.object(g, "_get_credential", return_value="tok"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = [{
                    "id": 1,
                    "number": 42,
                    "title": "Test Issue",
                    "state": "open",
                    "body": "Description",
                    "html_url": "https://github.com/user/repo/issues/42",
                    "user": {"login": "author"},
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-02T00:00:00Z",
                    "labels": [{"name": "bug"}],
                }]
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
                result = await g.receive(repo="user/repo")
                assert len(result) == 1
                assert result[0]["title"] == "Test Issue"
                assert result[0]["number"] == 42
                assert result[0]["labels"] == ["bug"]
                assert result[0]["type"] == "issue"


class TestGoogleDriveIntegration:
    async def test_connect_sets_connected(self):
        g = GoogleDriveIntegration()
        result = await g.connect()
        assert result is True
        assert g._connected is True

    async def test_disconnect(self):
        g = GoogleDriveIntegration()
        g._connected = True
        result = await g.disconnect()
        assert result is True
        assert g._connected is False

    async def test_health_check_not_connected(self):
        g = GoogleDriveIntegration()
        g._connected = False
        s = await g.health_check()
        assert s.error == "Not connected"

    async def test_health_check_no_api_key(self):
        g = GoogleDriveIntegration()
        g._connected = True
        with patch.object(g, "_get_credential", return_value=None):
            s = await g.health_check()
            assert s.healthy is False
            assert "No API key" in s.error

    async def test_send_returns_false(self):
        g = GoogleDriveIntegration()
        result = await g.send("target", "msg")
        assert result is False

    async def test_receive_returns_empty(self):
        g = GoogleDriveIntegration()
        result = await g.receive()
        assert result == []
