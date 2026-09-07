"""Tests for integrations/whatsapp/ — provider abstraction, webhooks, media, retry."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime


class TestWhatsAppModels:
    def test_message_type_enum(self):
        from integrations.whatsapp.models import MessageType
        assert MessageType.TEXT.value == "text"
        assert MessageType.IMAGE.value == "image"

    def test_send_result_defaults(self):
        from integrations.whatsapp.models import SendResult
        r = SendResult(success=True, message_id="wamid.123")
        assert r.success is True
        assert r.message_id == "wamid.123"
        assert r.error is None
        assert r.retry_attempts == 0

    def test_whatsapp_media_from_api(self):
        from integrations.whatsapp.models import WhatsAppMedia
        data = {"id": "media1", "mime_type": "image/jpeg", "sha256": "abc", "file_size": 1024, "caption": "Photo"}
        media = WhatsAppMedia.from_api(data, "image")
        assert media.id == "media1"
        assert media.mime_type == "image/jpeg"
        assert media.caption == "Photo"

    def test_message_from_webhook_text(self):
        from integrations.whatsapp.models import WhatsAppMessage
        payload = {
            "message": {
                "id": "msg1",
                "type": "text",
                "from": "+1234567890",
                "timestamp": "1718400000",
                "text": {"body": "Hello World"},
            }
        }
        msg = WhatsAppMessage.from_webhook_payload(payload, "+1987654321")
        assert msg.id == "msg1"
        assert msg.type.value == "text"
        assert msg.from_number == "+1234567890"
        assert msg.text == "Hello World"
        assert msg.to_number == "+1987654321"
        assert msg.timestamp is not None

    def test_message_from_webhook_image(self):
        from integrations.whatsapp.models import WhatsAppMessage, MessageType
        payload = {
            "message": {
                "id": "img1",
                "type": "image",
                "from": "+1234567890",
                "timestamp": "1718400000",
                "image": {"id": "media1", "mime_type": "image/jpeg", "sha256": "abc", "file_size": 2048},
            }
        }
        msg = WhatsAppMessage.from_webhook_payload(payload, "+1987654321")
        assert msg.type == MessageType.IMAGE
        assert msg.media is not None
        assert msg.media.id == "media1"
        assert msg.media.mime_type == "image/jpeg"

    def test_message_from_webhook_location(self):
        from integrations.whatsapp.models import WhatsAppMessage, MessageType
        payload = {
            "message": {
                "id": "loc1",
                "type": "location",
                "from": "+1234567890",
                "timestamp": "1718400000",
                "location": {"latitude": 37.77, "longitude": -122.42, "name": "San Francisco"},
            }
        }
        msg = WhatsAppMessage.from_webhook_payload(payload, "+1987654321")
        assert msg.type == MessageType.LOCATION
        assert msg.location is not None
        assert msg.location.latitude == 37.77
        assert msg.location.name == "San Francisco"

    def test_message_from_webhook_contacts(self):
        from integrations.whatsapp.models import WhatsAppMessage, MessageType
        payload = {
            "message": {
                "id": "con1",
                "type": "contacts",
                "from": "+1234567890",
                "timestamp": "1718400000",
                "contacts": [{
                    "name": {"formatted_name": "John Doe"},
                    "phones": [{"phone": "+1111111111"}],
                    "emails": [{"email": "john@example.com"}],
                }],
            }
        }
        msg = WhatsAppMessage.from_webhook_payload(payload, "+1987654321")
        assert msg.type == MessageType.CONTACTS
        assert len(msg.contacts) == 1
        assert msg.contacts[0].name == "John Doe"
        assert msg.contacts[0].phones == ["+1111111111"]

    def test_message_from_webhook_interactive_button(self):
        from integrations.whatsapp.models import WhatsAppMessage, MessageType
        payload = {
            "message": {
                "id": "int1",
                "type": "interactive",
                "from": "+1234567890",
                "timestamp": "1718400000",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": "btn1", "title": "Yes"},
                },
            }
        }
        msg = WhatsAppMessage.from_webhook_payload(payload, "+1987654321")
        assert msg.type == MessageType.INTERACTIVE
        assert msg.text == "Yes"

    def test_message_from_status_payload(self):
        from integrations.whatsapp.models import WhatsAppMessage, MessageStatus
        payload = {
            "status": {
                "statuses": [{"id": "msg1", "recipient_id": "+123", "status": "delivered"}]
            }
        }
        msg = WhatsAppMessage.from_status_payload(payload)
        assert msg.status == MessageStatus.DELIVERED
        assert msg.from_number == "+123"


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_retry_success_first_attempt(self):
        from integrations.whatsapp.retry import AsyncRetry
        retry = AsyncRetry(max_attempts=3)
        fn = AsyncMock(return_value="ok")
        result, attempts = await retry.execute(fn)
        assert result == "ok"
        assert attempts == 1
        fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_success_after_retries(self):
        from integrations.whatsapp.retry import AsyncRetry
        retry = AsyncRetry(max_attempts=3, base_delay=0.01)
        fn = AsyncMock(side_effect=[ValueError("fail"), ValueError("fail"), "ok"])
        result, attempts = await retry.execute(fn)
        assert result == "ok"
        assert attempts == 3

    @pytest.mark.asyncio
    async def test_retry_all_fail(self):
        from integrations.whatsapp.retry import AsyncRetry
        retry = AsyncRetry(max_attempts=2, base_delay=0.01)
        fn = AsyncMock(side_effect=ValueError("always fails"))
        with pytest.raises(ValueError):
            await retry.execute(fn)
        assert fn.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_retry_callback(self):
        from integrations.whatsapp.retry import AsyncRetry
        retry = AsyncRetry(max_attempts=2, base_delay=0.01)
        err = ValueError("fail")
        fn = AsyncMock(side_effect=[err, "ok"])
        cb = MagicMock()
        result, attempts = await retry.execute(fn, on_retry=cb)
        cb.assert_called_once_with(1, err)

    def test_backoff_increases(self):
        from integrations.whatsapp.retry import AsyncRetry
        retry = AsyncRetry(base_delay=1.0, backoff_factor=2.0, jitter=False)
        d1 = retry._backoff(1)
        d2 = retry._backoff(2)
        d3 = retry._backoff(3)
        assert d1 == 1.0
        assert d2 == 2.0
        assert d3 == 4.0

    def test_backoff_capped(self):
        from integrations.whatsapp.retry import AsyncRetry
        retry = AsyncRetry(base_delay=1.0, max_delay=5.0, backoff_factor=10.0, jitter=False)
        d = retry._backoff(5)
        assert d == 5.0

    def test_backoff_with_jitter(self):
        from integrations.whatsapp.retry import AsyncRetry
        retry = AsyncRetry(base_delay=1.0, jitter=True)
        delays = [retry._backoff(1) for _ in range(10)]
        assert all(0.5 <= d <= 1.0 for d in delays)


class TestWhatsAppWebhookHandler:
    def test_init_defaults(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler(app_secret="secret", verify_token="mytoken")
        assert handler._app_secret == "secret"
        assert handler._verify_token == "mytoken"

    def test_verify_signature_valid(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        import hmac, hashlib
        app_secret = "test_secret"
        handler = WhatsAppWebhookHandler(app_secret=app_secret)
        body = b'{"test": "payload"}'
        expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
        assert handler.verify_signature(body, f"sha256={expected}") is True

    def test_verify_signature_invalid(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler(app_secret="secret")
        assert handler.verify_signature(b"body", "sha256=wrong") is False

    def test_verify_signature_missing_header(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler(app_secret="secret")
        assert handler.verify_signature(b"body", None) is False

    def test_verify_signature_no_secret_skips(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler(app_secret="")
        assert handler.verify_signature(b"body", "any") is True

    def test_verify_webhook_token_valid(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler(verify_token="abc")
        result = handler.verify_webhook_token("subscribe", "abc", "challenge123")
        assert result == "challenge123"

    def test_verify_webhook_token_invalid(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler(verify_token="abc")
        result = handler.verify_webhook_token("subscribe", "wrong", "challenge")
        assert result is None

    def test_process_incoming_text_message(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler()
        body = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "+1987654321"},
                        "messages": [{"id": "m1", "type": "text", "from": "+123", "timestamp": "1718400000", "text": {"body": "Hi"}}],
                    }
                }]
            }]
        }
        msgs = handler.process_incoming(body)
        assert len(msgs) == 1
        assert msgs[0].text == "Hi"
        assert msgs[0].from_number == "+123"

    def test_process_incoming_buffers_messages(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler()
        body = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "+1"},
                        "messages": [
                            {"id": "m1", "type": "text", "from": "+2", "timestamp": "1718400000", "text": {"body": "A"}},
                            {"id": "m2", "type": "text", "from": "+3", "timestamp": "1718400001", "text": {"body": "B"}},
                        ],
                    }
                }]
            }]
        }
        msgs = handler.process_incoming(body)
        assert len(msgs) == 2
        buffered = handler.get_buffered_messages(clear=False)
        assert len(buffered) == 2

    def test_get_buffered_messages_clears(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler()
        handler._message_buffer.append(MagicMock())
        result = handler.get_buffered_messages(clear=True)
        assert len(result) == 1
        assert len(handler._message_buffer) == 0

    def test_get_buffered_messages_limit(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler()
        for _ in range(10):
            handler._message_buffer.append(MagicMock())
        result = handler.get_buffered_messages(clear=False, limit=3)
        assert len(result) == 3

    def test_get_message_status(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        from integrations.whatsapp.models import MessageStatus
        handler = WhatsAppWebhookHandler()
        handler._last_status["msg1"] = MessageStatus.DELIVERED
        assert handler.get_message_status("msg1") == MessageStatus.DELIVERED
        assert handler.get_message_status("unknown") is None

    def test_process_incoming_statuses(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler()
        on_status = MagicMock()
        handler.set_on_status(on_status)
        body = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "+1"},
                        "statuses": [{"id": "msg1", "recipient_id": "+2", "status": "read"}],
                    }
                }]
            }]
        }
        handler.process_incoming(body)
        assert handler.get_message_status("msg1").value == "read"

    def test_requires_media_download(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        from integrations.whatsapp.models import WhatsAppMessage, MessageType, WhatsAppMedia, MessageDirection
        handler = WhatsAppWebhookHandler()
        msg = WhatsAppMessage(id="m1", type=MessageType.IMAGE, direction=MessageDirection.INBOUND,
                              from_number="+1", to_number="+2",
                              media=WhatsAppMedia(id="media1", mime_type="image/jpeg", sha256="a", file_size=100))
        assert handler.requires_media_download(msg) is True
        text_msg = WhatsAppMessage(id="m2", type=MessageType.TEXT, direction=MessageDirection.INBOUND,
                                   from_number="+1", to_number="+2", text="hi")
        assert handler.requires_media_download(text_msg) is False

    def test_on_message_callback(self):
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        handler = WhatsAppWebhookHandler()
        cb = MagicMock()
        handler.set_on_message(cb)
        body = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "+1"},
                        "messages": [{"id": "m1", "type": "text", "from": "+2", "timestamp": "1718400000", "text": {"body": "Hi"}}],
                    }
                }]
            }]
        }
        handler.process_incoming(body)
        cb.assert_called_once()


class TestWhatsAppCloudAPIProvider:
    @pytest.mark.asyncio
    async def test_connect_no_creds(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        with patch.dict("os.environ", {}, clear=True):
            p = WhatsAppCloudAPIProvider()
            ok = await p.connect()
            assert ok is False

    @pytest.mark.asyncio
    async def test_connect_success(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p.health_check = AsyncMock(return_value=True)
        p.get_business_profile = AsyncMock(return_value={"display_phone_number": "+123"})
        with patch("httpx.AsyncClient"):
            ok = await p.connect(token="tok", phone_id="pid")
            assert ok is True
            assert p.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_health_check_fails(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p.health_check = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient"):
            ok = await p.connect(token="tok", phone_id="pid")
            assert ok is False

    @pytest.mark.asyncio
    async def test_send_text_success(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p._http = MagicMock()
        p._token = "tok"
        p._phone_id = "pid"
        p._do_post = AsyncMock(return_value=MagicMock(success=True, message_id="wamid.1"))
        result = await p.send_text("+123", "Hello")
        assert result.success is True
        assert result.message_id == "wamid.1"

    @pytest.mark.asyncio
    async def test_send_text_not_connected(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        result = await p.send_text("+123", "Hello")
        assert result.success is False
        assert "Not connected" in result.error

    @pytest.mark.asyncio
    async def test_health_check_not_configured(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        ok = await p.health_check()
        assert ok is False

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p._token = "tok"
        p._phone_id = "pid"
        import httpx
        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            ok = await p.health_check()
            assert ok is True

    @pytest.mark.asyncio
    async def test_send_image(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p._http = MagicMock()
        p._token = "tok"
        p._phone_id = "pid"
        p._do_post = AsyncMock(return_value=MagicMock(success=True, message_id="wamid.2"))
        result = await p.send_image("+123", "https://example.com/img.jpg", caption="Photo")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_document(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p._http = MagicMock()
        p._token = "tok"
        p._phone_id = "pid"
        p._do_post = AsyncMock(return_value=MagicMock(success=True, message_id="wamid.3"))
        result = await p.send_document("+123", "https://example.com/doc.pdf", "report.pdf")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_location(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p._http = MagicMock()
        p._token = "tok"
        p._phone_id = "pid"
        p._do_post = AsyncMock(return_value=MagicMock(success=True, message_id="wamid.4"))
        result = await p.send_location("+123", 37.77, -122.42, name="SF")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_audio(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p._http = MagicMock()
        p._token = "tok"
        p._phone_id = "pid"
        p._do_post = AsyncMock(return_value=MagicMock(success=True, message_id="wamid.5"))
        result = await p.send_audio("+123", "https://example.com/audio.ogg")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_download_media(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p._http = MagicMock()
        p._token = "tok"
        p._get_media_url = AsyncMock(return_value={"url": "https://download.url"})
        p._download_url = AsyncMock(return_value=b"imagedata")
        data = await p.download_media("media1", "image/jpeg")
        assert data == b"imagedata"

    @pytest.mark.asyncio
    async def test_mark_as_read(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p._http = MagicMock()
        p._token = "tok"
        p._phone_id = "pid"
        p._http.post = AsyncMock(return_value=MagicMock(status_code=200))
        ok = await p.mark_as_read("msg1")
        assert ok is True

    @pytest.mark.asyncio
    async def test_get_business_profile(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        p = WhatsAppCloudAPIProvider()
        p._http = MagicMock()
        p._token = "tok"
        p._phone_id = "pid"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"display_phone_number": "+123"}]}
        p._http.get = AsyncMock(return_value=mock_resp)
        profile = await p.get_business_profile()
        assert profile.get("display_phone_number") == "+123"


class TestTwilioWhatsAppProvider:
    @pytest.mark.asyncio
    async def test_connect_no_creds(self):
        from integrations.whatsapp.twilio_provider import TwilioWhatsAppProvider
        with patch.dict("os.environ", {}, clear=True):
            p = TwilioWhatsAppProvider()
            ok = await p.connect()
            assert ok is False

    @pytest.mark.asyncio
    async def test_connect_success(self):
        from integrations.whatsapp.twilio_provider import TwilioWhatsAppProvider
        p = TwilioWhatsAppProvider()
        p.health_check = AsyncMock(return_value=True)
        with patch("httpx.AsyncClient"):
            ok = await p.connect(account_sid="sid", auth_token="tok", from_number="whatsapp:+123")
            assert ok is True
            assert p.is_connected is True

    @pytest.mark.asyncio
    async def test_send_text_success(self):
        from integrations.whatsapp.twilio_provider import TwilioWhatsAppProvider
        p = TwilioWhatsAppProvider()
        p._http = MagicMock()
        p._account_sid = "sid"
        p._auth_token = "tok"
        p._from_number = "whatsapp:+123"
        p._do_post = AsyncMock(return_value=MagicMock(success=True, message_id="SM123"))
        result = await p.send_text("+456", "Hello")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_image(self):
        from integrations.whatsapp.twilio_provider import TwilioWhatsAppProvider
        p = TwilioWhatsAppProvider()
        p._http = MagicMock()
        p._account_sid = "sid"
        p._auth_token = "tok"
        p._from_number = "whatsapp:+123"
        p._do_post = AsyncMock(return_value=MagicMock(success=True, message_id="SM456"))
        result = await p.send_image("+456", "https://example.com/img.jpg", caption="Photo")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        from integrations.whatsapp.twilio_provider import TwilioWhatsAppProvider
        p = TwilioWhatsAppProvider()
        p._account_sid = "sid"
        p._auth_token = "tok"
        import httpx
        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            ok = await p.health_check()
            assert ok is True

    @pytest.mark.asyncio
    async def test_format_number(self):
        from integrations.whatsapp.twilio_provider import TwilioWhatsAppProvider
        p = TwilioWhatsAppProvider()
        assert p._format_number("+123") == "whatsapp:+123"
        assert p._format_number("whatsapp:+123") == "whatsapp:+123"

    @pytest.mark.asyncio
    async def test_send_text_not_connected(self):
        from integrations.whatsapp.twilio_provider import TwilioWhatsAppProvider
        p = TwilioWhatsAppProvider()
        result = await p.send_text("+123", "Hello")
        assert result.success is False


class TestMediaManager:
    def test_get_extension_known(self):
        from integrations.whatsapp.media import MediaManager
        mgr = MediaManager()
        assert mgr.get_extension("image/jpeg") == ".jpg"
        assert mgr.get_extension("application/pdf") == ".pdf"
        assert mgr.get_extension("audio/ogg") == ".ogg"

    def test_get_extension_unknown(self):
        from integrations.whatsapp.media import MediaManager
        mgr = MediaManager()
        ext = mgr.get_extension("application/x-unknown")
        assert ext == ".bin" or ext.startswith(".")

    def test_is_image(self):
        from integrations.whatsapp.media import MediaManager
        mgr = MediaManager()
        assert mgr.is_image("image/jpeg") is True
        assert mgr.is_image("audio/mp3") is False

    def test_is_audio(self):
        from integrations.whatsapp.media import MediaManager
        mgr = MediaManager()
        assert mgr.is_audio("audio/mpeg") is True
        assert mgr.is_audio("video/mp4") is False

    def test_is_document(self):
        from integrations.whatsapp.media import MediaManager
        mgr = MediaManager()
        assert mgr.is_document("application/pdf") is True
        assert mgr.is_document("image/jpeg") is False

    def test_get_cache_path(self):
        from integrations.whatsapp.media import MediaManager
        import tempfile
        import os
        mgr = MediaManager(cache_dir=os.path.join(tempfile.gettempdir(), "jarvis_test_media"))
        path = mgr.get_cache_path("media123", "image/png")
        assert path.name == "media123.png"

    @pytest.mark.asyncio
    async def test_download_and_cache(self):
        from integrations.whatsapp.media import MediaManager
        from integrations.whatsapp.models import WhatsAppMedia
        import tempfile
        import os
        cache_dir = os.path.join(tempfile.gettempdir(), "jarvis_test_cache")
        mgr = MediaManager(cache_dir=cache_dir)
        media = WhatsAppMedia(id="test1", mime_type="text/plain", sha256="abc", file_size=10)
        provider = MagicMock()
        provider.download_media = AsyncMock(return_value=b"test data")
        path = await mgr.download_and_cache(provider, media)
        assert path is not None
        assert path.exists()
        assert path.read_bytes() == b"test data"
        assert media.local_path == str(path)
        path.unlink(missing_ok=True)


class TestWhatsAppIntegration:
    @pytest.mark.asyncio
    async def test_connect_success_cloud_api(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        with patch.object(w, "_get_provider_class") as mock_cls:
            mock_provider = MagicMock()
            mock_provider.connect = AsyncMock(return_value=True)
            mock_cls.return_value.return_value = mock_provider
            ok = await w.connect(token="tok", phone_id="pid")
            assert ok is True
            assert w._connected is True

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        with patch.object(w, "_get_provider_class") as mock_cls:
            mock_provider = MagicMock()
            mock_provider.connect = AsyncMock(return_value=False)
            mock_cls.return_value.return_value = mock_provider
            ok = await w.connect(token="tok", phone_id="pid")
            assert ok is False

    @pytest.mark.asyncio
    async def test_disconnect(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        mock_provider = MagicMock()
        mock_provider.disconnect = AsyncMock(return_value=True)
        w._provider = mock_provider
        w._connected = True
        ok = await w.disconnect()
        assert ok is True
        assert w._connected is False
        assert w._provider is None

    @pytest.mark.asyncio
    async def test_health_check_not_connected(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        s = await w.health_check()
        assert s.healthy is False
        assert "Not connected" in s.error

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        w._connected = True
        w._provider = MagicMock()
        w._provider.health_check = AsyncMock(return_value=True)
        s = await w.health_check()
        assert s.healthy is True

    @pytest.mark.asyncio
    async def test_send_text(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        w._connected = True
        w._provider = MagicMock()
        w._provider.send_text = AsyncMock(return_value=MagicMock(success=True))
        ok = await w.send("+123", "Hello")
        assert ok is True
        w._provider.send_text.assert_called_once_with("+123", "Hello")

    @pytest.mark.asyncio
    async def test_send_image(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        w._connected = True
        w._provider = MagicMock()
        w._provider.send_image = AsyncMock(return_value=MagicMock(success=True))
        ok = await w.send("+123", "", media_url="https://img.jpg", media_type="image", caption="Photo")
        assert ok is True
        w._provider.send_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_not_connected(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        ok = await w.send("+123", "msg")
        assert ok is False

    @pytest.mark.asyncio
    async def test_receive_empty(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        result = await w.receive()
        assert result == []

    @pytest.mark.asyncio
    async def test_receive_with_messages(self):
        from core.integration_manager import WhatsAppIntegration
        from integrations.whatsapp.models import WhatsAppMessage, MessageType, MessageDirection
        w = WhatsAppIntegration()
        w._webhook_handler = MagicMock()
        mock_msg = WhatsAppMessage(id="m1", type=MessageType.TEXT, direction=MessageDirection.INBOUND,
                                   from_number="+123", to_number="+456", text="hello")
        w._webhook_handler.get_buffered_messages.return_value = [mock_msg]
        result = await w.receive()
        assert len(result) == 1
        assert result[0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_get_provider_class_cloud_api(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        cls = w._get_provider_class("cloud_api")
        assert cls is not None
        assert cls.__name__ == "WhatsAppCloudAPIProvider"

    @pytest.mark.asyncio
    async def test_get_provider_class_twilio(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        cls = w._get_provider_class("twilio")
        assert cls is not None
        assert cls.__name__ == "TwilioWhatsAppProvider"

    @pytest.mark.asyncio
    async def test_get_provider_class_unknown(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        cls = w._get_provider_class("nonexistent")
        assert cls is None


class TestWhatsAppHistory:
    @pytest.mark.asyncio
    async def test_save_and_retrieve_message(self):
        from integrations.whatsapp.history import WhatsAppHistory
        from integrations.whatsapp.models import WhatsAppMessage, MessageType, MessageDirection, MessageStatus
        h = WhatsAppHistory(db_path=":memory:")
        msg = WhatsAppMessage(
            id="hist1", type=MessageType.TEXT, direction=MessageDirection.INBOUND,
            from_number="+111", to_number="+222", text="hello history",
            status=MessageStatus.PENDING,
        )
        await h.save_message(msg)
        conv = await h.get_conversation("+111", "+222")
        assert len(conv) == 1
        assert conv[0].text == "hello history"
        assert conv[0].from_number == "+111"
        h.close()

    @pytest.mark.asyncio
    async def test_get_conversation_limit_offset(self):
        from integrations.whatsapp.history import WhatsAppHistory
        from integrations.whatsapp.models import WhatsAppMessage, MessageType, MessageDirection, MessageStatus
        from datetime import datetime
        h = WhatsAppHistory(db_path=":memory:")
        for i in range(5):
            msg = WhatsAppMessage(
                id=f"lim_{i}", type=MessageType.TEXT, direction=MessageDirection.INBOUND,
                from_number="+a", to_number="+b", text=f"msg {i}",
                timestamp=datetime(2024, 1, 1, 0, 0, i),
                status=MessageStatus.PENDING,
            )
            await h.save_message(msg)
        conv = await h.get_conversation("+a", "+b", limit=3)
        assert len(conv) == 3
        assert conv[0].text == "msg 2"
        assert conv[-1].text == "msg 4"
        h.close()

    @pytest.mark.asyncio
    async def test_search_messages(self):
        from integrations.whatsapp.history import WhatsAppHistory
        from integrations.whatsapp.models import WhatsAppMessage, MessageType, MessageDirection, MessageStatus
        h = WhatsAppHistory(db_path=":memory:")
        for i, txt in enumerate(["apple", "banana", "apple pie", "cherry"]):
            msg = WhatsAppMessage(
                id=f"srch_{i}", type=MessageType.TEXT, direction=MessageDirection.INBOUND,
                from_number="+1", to_number="+2", text=txt,
                status=MessageStatus.PENDING,
            )
            await h.save_message(msg)
        results = await h.search_messages("apple")
        assert len(results) == 2
        assert all("apple" in r.text for r in results)
        h.close()

    @pytest.mark.asyncio
    async def test_update_message_status(self):
        from integrations.whatsapp.history import WhatsAppHistory
        from integrations.whatsapp.models import WhatsAppMessage, MessageType, MessageDirection, MessageStatus
        h = WhatsAppHistory(db_path=":memory:")
        msg = WhatsAppMessage(
            id="stat1", type=MessageType.TEXT, direction=MessageDirection.OUTBOUND,
            from_number="+a", to_number="+b", text="status test",
            status=MessageStatus.SENT,
        )
        await h.save_message(msg)
        await h.update_message_status("stat1", MessageStatus.DELIVERED)
        conv = await h.get_conversation("+a", "+b")
        assert conv[0].status == MessageStatus.DELIVERED
        h.close()

    @pytest.mark.asyncio
    async def test_delete_conversation(self):
        from integrations.whatsapp.history import WhatsAppHistory
        from integrations.whatsapp.models import WhatsAppMessage, MessageType, MessageDirection, MessageStatus
        h = WhatsAppHistory(db_path=":memory:")
        msg = WhatsAppMessage(
            id="del1", type=MessageType.TEXT, direction=MessageDirection.INBOUND,
            from_number="+x", to_number="+y", text="delete me",
            status=MessageStatus.PENDING,
        )
        await h.save_message(msg)
        await h.delete_conversation("+x", "+y")
        conv = await h.get_conversation("+x", "+y")
        assert len(conv) == 0
        h.close()

    @pytest.mark.asyncio
    async def test_message_count(self):
        from integrations.whatsapp.history import WhatsAppHistory
        from integrations.whatsapp.models import WhatsAppMessage, MessageType, MessageDirection, MessageStatus
        h = WhatsAppHistory(db_path=":memory:")
        for i in range(3):
            msg = WhatsAppMessage(
                id=f"cnt_{i}", type=MessageType.TEXT, direction=MessageDirection.INBOUND,
                from_number="+m", to_number="+n", text=f"count {i}",
                status=MessageStatus.PENDING,
            )
            await h.save_message(msg)
        count = await h.message_count("+m", "+n")
        assert count == 3
        h.close()

    @pytest.mark.asyncio
    async def test_get_recent_conversations(self):
        from integrations.whatsapp.history import WhatsAppHistory
        from integrations.whatsapp.models import WhatsAppMessage, MessageType, MessageDirection, MessageStatus
        h = WhatsAppHistory(db_path=":memory:")
        msg = WhatsAppMessage(
            id="rec1", type=MessageType.TEXT, direction=MessageDirection.INBOUND,
            from_number="+a", to_number="+b", text="recent",
            status=MessageStatus.PENDING,
        )
        await h.save_message(msg)
        convs = await h.get_recent_conversations()
        assert len(convs) >= 1
        assert any(c["phone_number"] == "+a" for c in convs)
        h.close()


class TestInteractiveModels:
    def test_interactive_button(self):
        from integrations.whatsapp.models import InteractiveButton
        btn = InteractiveButton(id="btn_yes", title="Yes")
        assert btn.id == "btn_yes"
        assert btn.title == "Yes"

    def test_interactive_list_row(self):
        from integrations.whatsapp.models import InteractiveListRow
        row = InteractiveListRow(id="row1", title="Option 1", description="Desc 1")
        assert row.id == "row1"
        assert row.description == "Desc 1"

    def test_interactive_body_minimal(self):
        from integrations.whatsapp.models import InteractiveBody
        body = InteractiveBody(text="Hello")
        assert body.text == "Hello"
        assert body.title is None

    def test_interactive_body_with_action(self):
        from integrations.whatsapp.models import InteractiveBody, InteractiveAction, InteractiveButton
        action = InteractiveAction(button="Select", buttons=[InteractiveButton(id="1", title="A")])
        body = InteractiveBody(text="Pick one", title="Menu", footer="Thanks", action=action)
        assert body.title == "Menu"
        assert len(body.action.buttons) == 1

    def test_interactive_list_section(self):
        from integrations.whatsapp.models import InteractiveListSection, InteractiveListRow
        rows = [InteractiveListRow(id="r1", title="Row 1")]
        sec = InteractiveListSection(title="Section", rows=rows)
        assert sec.title == "Section"
        assert len(sec.rows) == 1

    @pytest.mark.asyncio
    async def test_send_interactive_buttons(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        from integrations.whatsapp.models import InteractiveBody, InteractiveAction, InteractiveButton
        p = WhatsAppCloudAPIProvider()
        p._http = MagicMock()
        p._token = "tok"
        p._phone_id = "pid"
        p._do_post = AsyncMock(return_value=MagicMock(success=True, message_id="wamid.int"))
        body = InteractiveBody(
            text="Confirm?",
            title="Question",
            action=InteractiveAction(button="", buttons=[InteractiveButton(id="yes", title="Yes")]),
        )
        result = await p.send_interactive_buttons("+123", body)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_interactive_list(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        from integrations.whatsapp.models import InteractiveBody, InteractiveAction, InteractiveListSection, InteractiveListRow
        p = WhatsAppCloudAPIProvider()
        p._http = MagicMock()
        p._token = "tok"
        p._phone_id = "pid"
        p._do_post = AsyncMock(return_value=MagicMock(success=True, message_id="wamid.list"))
        body = InteractiveBody(
            text="Choose:",
            action=InteractiveAction(
                button="Options",
                sections=[InteractiveListSection(title="S1", rows=[InteractiveListRow(id="r1", title="Row 1")])],
            ),
        )
        result = await p.send_interactive_list("+123", body)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_interactive_buttons_no_buttons(self):
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        from integrations.whatsapp.models import InteractiveBody
        p = WhatsAppCloudAPIProvider()
        body = InteractiveBody(text="No buttons")
        result = await p.send_interactive_buttons("+123", body)
        assert result.success is False
        assert "No buttons" in result.error

    @pytest.mark.asyncio
    async def test_base_raises_not_implemented(self):
        from integrations.whatsapp.base import BaseWhatsAppProvider
        from integrations.whatsapp.models import InteractiveBody
        class MinimalProvider(BaseWhatsAppProvider):
            name = "test"
            async def connect(self, **kw): return True
            async def disconnect(self): return True
            async def send_text(self, to, text, **kw): return MagicMock(success=True)
            async def send_image(self, to, url, caption=None, **kw): return MagicMock(success=True)
            async def send_document(self, to, url, filename, caption=None, **kw): return MagicMock(success=True)
            async def send_audio(self, to, url, **kw): return MagicMock(success=True)
            async def send_location(self, to, lat, lon, name=None, address=None, **kw): return MagicMock(success=True)
            async def download_media(self, media_id, mime_type): return b""
            async def health_check(self): return True
            async def get_business_profile(self): return {}
        p = MinimalProvider()
        with pytest.raises(NotImplementedError):
            await p.send_interactive_buttons("+123", InteractiveBody(text="test"))
        with pytest.raises(NotImplementedError):
            await p.send_interactive_list("+123", InteractiveBody(text="test"))

    @pytest.mark.asyncio
    async def test_integration_send_interactive_buttons(self):
        from core.integration_manager import WhatsAppIntegration
        from integrations.whatsapp.models import InteractiveBody, InteractiveAction, InteractiveButton
        w = WhatsAppIntegration()
        w._connected = True
        w._provider = MagicMock()
        w._provider.send_interactive_buttons = AsyncMock(return_value=MagicMock(success=True))
        body = InteractiveBody(text="Test", action=InteractiveAction(button="", buttons=[InteractiveButton(id="b1", title="B1")]))
        ok = await w.send("+123", "", media_type="interactive_buttons", interactive_body=body)
        assert ok is True
        w._provider.send_interactive_buttons.assert_called_once()

    @pytest.mark.asyncio
    async def test_integration_send_interactive_list(self):
        from core.integration_manager import WhatsAppIntegration
        from integrations.whatsapp.models import InteractiveBody, InteractiveAction, InteractiveListSection, InteractiveListRow
        w = WhatsAppIntegration()
        w._connected = True
        w._provider = MagicMock()
        w._provider.send_interactive_list = AsyncMock(return_value=MagicMock(success=True))
        body = InteractiveBody(
            text="List", action=InteractiveAction(button="Go", sections=[InteractiveListSection(title="S", rows=[InteractiveListRow(id="r", title="R")])])
        )
        ok = await w.send("+123", "", media_type="interactive_list", interactive_body=body)
        assert ok is True
        w._provider.send_interactive_list.assert_called_once()


class TestWhatsAppPhoneManager:
    @pytest.mark.asyncio
    async def test_register_phone(self):
        from integrations.whatsapp.phone_manager import WhatsAppPhoneManager
        mgr = WhatsAppPhoneManager()
        provider = MagicMock()
        mgr.register_phone("+1555", provider)
        assert "+1555" in mgr.phone_numbers
        assert mgr.default_phone == "+1555"

    @pytest.mark.asyncio
    async def test_register_multiple_phones(self):
        from integrations.whatsapp.phone_manager import WhatsAppPhoneManager
        mgr = WhatsAppPhoneManager()
        mgr.register_phone("+1111", MagicMock(), make_default=True)
        mgr.register_phone("+2222", MagicMock())
        assert mgr.default_phone == "+1111"
        assert len(mgr.phone_numbers) == 2

    @pytest.mark.asyncio
    async def test_unregister_phone(self):
        from integrations.whatsapp.phone_manager import WhatsAppPhoneManager
        mgr = WhatsAppPhoneManager()
        mgr.register_phone("+3333", MagicMock())
        mgr.unregister_phone("+3333")
        assert "+3333" not in mgr.phone_numbers
        assert mgr.default_phone is None

    @pytest.mark.asyncio
    async def test_get_provider_by_phone(self):
        from integrations.whatsapp.phone_manager import WhatsAppPhoneManager
        mgr = WhatsAppPhoneManager()
        p1 = MagicMock()
        p2 = MagicMock()
        mgr.register_phone("+aaa", p1)
        mgr.register_phone("+bbb", p2)
        assert mgr.get_provider("+aaa") is p1
        assert mgr.get_provider("+bbb") is p2

    @pytest.mark.asyncio
    async def test_get_provider_default(self):
        from integrations.whatsapp.phone_manager import WhatsAppPhoneManager
        mgr = WhatsAppPhoneManager()
        p1 = MagicMock()
        mgr.register_phone("+default", p1, make_default=True)
        assert mgr.get_provider() is p1
        assert mgr.get_provider("+default") is p1

    @pytest.mark.asyncio
    async def test_get_provider_none_when_empty(self):
        from integrations.whatsapp.phone_manager import WhatsAppPhoneManager
        mgr = WhatsAppPhoneManager()
        assert mgr.get_provider() is None
        assert mgr.get_provider("+any") is None

    @pytest.mark.asyncio
    async def test_health_check_all(self):
        from integrations.whatsapp.phone_manager import WhatsAppPhoneManager
        mgr = WhatsAppPhoneManager()
        p1 = MagicMock()
        p1.health_check = AsyncMock(return_value=True)
        p2 = MagicMock()
        p2.health_check = AsyncMock(return_value=False)
        mgr.register_phone("+ok", p1)
        mgr.register_phone("+fail", p2)
        results = await mgr.health_check_all()
        assert results["+ok"] is True
        assert results["+fail"] is False

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        from integrations.whatsapp.phone_manager import WhatsAppPhoneManager
        mgr = WhatsAppPhoneManager()
        p1 = MagicMock()
        p1.disconnect = AsyncMock(return_value=True)
        mgr.register_phone("+d1", p1)
        ok = await mgr.disconnect_all()
        assert ok is True
        assert mgr.phone_numbers == []

    @pytest.mark.asyncio
    async def test_set_default_phone_validates(self):
        from integrations.whatsapp.phone_manager import WhatsAppPhoneManager
        mgr = WhatsAppPhoneManager()
        with pytest.raises(ValueError):
            mgr.default_phone = "+nonexistent"


class TestIntegrationHistoryMethods:
    @pytest.mark.asyncio
    async def test_get_conversation(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        w._history = MagicMock()
        w._history.get_conversation = AsyncMock(return_value=[])
        result = await w.get_conversation("+a", "+b")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_conversation_no_history(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        result = await w.get_conversation("+a", "+b")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_conversations(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        w._history = MagicMock()
        w._history.search_messages = AsyncMock(return_value=[])
        result = await w.search_conversations("test")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_recent_conversations(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        w._history = MagicMock()
        w._history.get_recent_conversations = AsyncMock(return_value=[])
        result = await w.get_recent_conversations()
        assert result == []

    @pytest.mark.asyncio
    async def test_register_phone(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        w._phone_manager = MagicMock()
        with patch.object(w, "_get_provider_class") as mock_cls:
            mock_provider = MagicMock()
            mock_provider.connect = AsyncMock(return_value=True)
            mock_cls.return_value.return_value = mock_provider
            ok = await w.register_phone("+5555", "tok", "pid")
            assert ok is True

    @pytest.mark.asyncio
    async def test_register_phone_failure(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        with patch.object(w, "_get_provider_class") as mock_cls:
            mock_provider = MagicMock()
            mock_provider.connect = AsyncMock(return_value=False)
            mock_cls.return_value.return_value = mock_provider
            ok = await w.register_phone("+6666", "tok", "pid")
            assert ok is False

    @pytest.mark.asyncio
    async def test_unregister_phone(self):
        from core.integration_manager import WhatsAppIntegration
        w = WhatsAppIntegration()
        w._phone_manager = MagicMock()
        w._phone_manager.unregister_phone.return_value = True
        ok = await w.unregister_phone("+7777")
        assert ok is True
