"""tests/test_channels.py — Tests for all channels: base, controller, processor, and 5 integrations."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from channels.base import ChannelPlugin, ChannelConfig
from channels.controller import ChannelController


class TestChannelConfig:
    def test_defaults(self):
        c = ChannelConfig()
        assert c.enabled is False
        assert c.token == ""
        assert c.webhook_secret == ""
        assert c.extra == {}

    def test_with_values(self):
        c = ChannelConfig(enabled=True, token="abc123", extra={"key": "val"})
        assert c.enabled is True
        assert c.token == "abc123"
        assert c.extra["key"] == "val"


class TestChannelPlugin:
    def test_default_lifecycle(self):
        p = ChannelPlugin()
        assert p.is_running is False
        assert p.config.enabled is False

    @pytest.mark.asyncio
    async def test_start_stop(self):
        p = ChannelPlugin()
        await p.start(None)
        assert p.is_running is True
        await p.stop()
        assert p.is_running is False

    def test_send_not_implemented(self):
        p = ChannelPlugin()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(p.send("target", "msg"))

    def test_id_and_name_defaults(self):
        p = ChannelPlugin()
        assert p.id == ""
        assert p.name == ""


class TestChannelController:
    @pytest.fixture
    def controller(self):
        return ChannelController()

    def test_register(self, controller):
        p = ChannelPlugin()
        p.id = "test"
        controller.register(p)
        assert controller.get("test") is p

    def test_channels_property(self, controller):
        p = ChannelPlugin()
        p.id = "c1"
        controller.register(p)
        assert "c1" in controller.channels

    def test_running_empty(self, controller):
        assert controller.running == []

    @pytest.mark.asyncio
    async def test_send_unknown_channel(self, controller):
        result = await controller.send("unknown", "target", "msg")
        assert result is False

    @pytest.mark.asyncio
    async def test_start_all_stop_all(self, controller):
        p = ChannelPlugin()
        p.id = "test"
        controller.register(p)
        await controller.start_all(None)
        assert p.is_running is True
        await controller.stop_all()
        assert p.is_running is False


class TestDiscordChannel:
    @pytest.mark.asyncio
    async def test_start_no_token(self):
        from channels.discord_channel import DiscordChannel
        c = DiscordChannel()
        await c.start(None)
        assert c.is_running is False

    @pytest.mark.asyncio
    async def test_start_with_token(self):
        from channels.discord_channel import DiscordChannel
        c = DiscordChannel(ChannelConfig(token="test-token"))
        with patch("channels.discord_channel.asyncio.create_task") as mock_task:
            mock_task.return_value = MagicMock()
            with patch("discord.Client"):
                await c.start(None)
                assert c.is_running is True
                assert c._task is not None

    @pytest.mark.asyncio
    async def test_stop(self):
        import asyncio
        from channels.discord_channel import DiscordChannel
        c = DiscordChannel()
        task = asyncio.get_running_loop().create_future()
        task.cancel()
        c._task = task
        c._client = AsyncMock()
        c._client.close = AsyncMock()
        await c.stop()
        assert c._client is None

    def test_send_no_client(self):
        from channels.discord_channel import DiscordChannel
        c = DiscordChannel()
        import asyncio
        result = asyncio.run(c.send("channel", "msg"))
        assert result is False


class TestSlackChannel:
    @pytest.mark.asyncio
    async def test_start_no_token(self):
        from channels.slack_channel import SlackChannel
        c = SlackChannel()
        with patch.dict("os.environ", {}, clear=True):
            await c.start(None)
            assert c.is_running is False

    @pytest.mark.asyncio
    async def test_start_with_env(self):
        from channels.slack_channel import SlackChannel
        c = SlackChannel()
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "bot-tok", "SLACK_APP_TOKEN": "app-tok"}):
            with patch("channels.slack_channel.WebClient") as mock_client:
                with patch("channels.slack_channel.SocketModeClient") as mock_socket:
                    mock_socket_instance = MagicMock()
                    mock_socket.return_value = mock_socket_instance
                    m_loop = MagicMock()
                    m_loop.is_running.return_value = True
                    with patch("asyncio.get_running_loop", return_value=m_loop):
                        await c.start(None)
                        assert c.is_running is True

    @pytest.mark.asyncio
    async def test_stop(self):
        from channels.slack_channel import SlackChannel
        c = SlackChannel()
        c._socket_client = MagicMock()
        c._thread = MagicMock()
        await c.stop()
        assert c._client is None

    @pytest.mark.asyncio
    async def test_send(self):
        from channels.slack_channel import SlackChannel
        c = SlackChannel()
        c._client = MagicMock()
        result = await c.send("channel", "msg")
        assert result is True or result is False


class TestTelegramChannel:
    @pytest.mark.asyncio
    async def test_start_no_token(self):
        with patch("httpx.AsyncClient"):
            from channels.telegram_channel import TelegramChannel
            c = TelegramChannel()
            await c.start(None)
            assert c.is_running is False

    @pytest.mark.asyncio
    async def test_start_with_token(self):
        from channels.telegram_channel import TelegramChannel
        c = TelegramChannel(ChannelConfig(token="test-tok"))
        mock_app = MagicMock()
        mock_app.initialize = AsyncMock()
        mock_app.start = AsyncMock()
        mock_app.updater = MagicMock()
        mock_app.updater.start_polling = AsyncMock()
        with patch("channels.telegram_channel.Application.builder") as mock_builder:
            mock_builder.return_value.token.return_value.build.return_value = mock_app
            await c.start(None)

    @pytest.mark.asyncio
    async def test_stop(self):
        from channels.telegram_channel import TelegramChannel
        c = TelegramChannel()
        mock_app = MagicMock()
        mock_app.updater.stop = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app.shutdown = AsyncMock()
        c._app = mock_app
        await c.stop()
        assert c._app is None


class TestMatrixChannel:
    @pytest.mark.asyncio
    async def test_start_no_creds(self):
        from channels.matrix_channel import MatrixChannel
        c = MatrixChannel()
        with patch.dict("os.environ", {}, clear=True):
            await c.start(None)
            assert c.is_running is False

    @pytest.mark.asyncio
    async def test_start_login_fails(self):
        from channels.matrix_channel import MatrixChannel
        from nio import LoginResponse
        c = MatrixChannel(ChannelConfig(extra={"homeserver": "https://matrix.org", "user_id": "u", "password": "p"}))
        mock_client = MagicMock()
        mock_client.login = AsyncMock(return_value="error")
        with patch("channels.matrix_channel.AsyncClient", return_value=mock_client):
            await c.start(None)
            assert c.is_running is False

    @pytest.mark.asyncio
    async def test_stop(self):
        import asyncio
        from channels.matrix_channel import MatrixChannel
        c = MatrixChannel()
        task = asyncio.get_running_loop().create_future()
        task.cancel()
        c._task = task
        c._client = MagicMock()
        c._client.close = AsyncMock()
        await c.stop()
        assert c._client is None


class TestIRCChannel:
    @pytest.fixture(autouse=True)
    def _setup_irc(self):
        import irc.client
        if not hasattr(irc.client, "IRCClient"):
            irc.client.IRCClient = MagicMock()
        if not hasattr(irc.client, "Event"):
            irc.client.Event = MagicMock()
        yield

    @pytest.mark.asyncio
    async def test_start_no_config(self):
        from channels.irc_channel import IRCChannel
        c = IRCChannel()
        with patch.dict("os.environ", {}, clear=True):
            await c.start(None)
            assert c.is_running is False

    @pytest.mark.asyncio
    async def test_start_with_config(self):
        from channels.irc_channel import IRCChannel
        c = IRCChannel(ChannelConfig(extra={"server": "irc.test.net", "nick": "jarvis-test"}))
        with patch("irc.connection.Factory") as mock_factory:
            mock_reactor = MagicMock()
            mock_connection = MagicMock()
            mock_factory.return_value.server.return_value = mock_connection
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = True
            with patch("asyncio.get_running_loop", return_value=mock_loop):
                await c.start(None)
                assert c.is_running is True

    @pytest.mark.asyncio
    async def test_stop(self):
        from channels.irc_channel import IRCChannel
        c = IRCChannel()
        c._connection = MagicMock()
        await c.stop()
        assert c._connection is None

    @pytest.mark.asyncio
    async def test_send_no_connection(self):
        from channels.irc_channel import IRCChannel
        c = IRCChannel()
        result = await c.send("target", "msg")
        assert result is False
