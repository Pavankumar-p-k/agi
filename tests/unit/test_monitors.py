from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from monitors.resource import ResourceMonitor, ResourceSnapshot, resource_monitor
from monitors.services import ServiceHealthChecker, ServiceHealth, ServicesSnapshot
from monitors.alerts import AlertRouter, Alert, AlertPriority


class TestResourceMonitor:
    def test_snapshot_without_psutil(self):
        """Should return zeros when psutil is not available."""
        snap = resource_monitor.snapshot()
        assert isinstance(snap, ResourceSnapshot)
        assert snap.timestamp > 0
        assert snap.cpu_percent >= 0
        assert snap.disk_free_gb >= 0

    def test_agent_tracking(self):
        rm = ResourceMonitor()
        rm.register_agent("agent-1")
        rm.register_agent("agent-2")
        snap = rm.snapshot()
        assert snap.active_agents == 2
        rm.unregister_agent("agent-1")
        snap = rm.snapshot()
        assert snap.active_agents == 1

    def test_skill_tracking(self):
        rm = ResourceMonitor()
        rm.start_skill("weather")
        rm.start_skill("search")
        snap = rm.snapshot()
        assert "weather" in snap.active_skills
        assert "search" in snap.active_skills
        rm.finish_skill("weather")
        snap = rm.snapshot()
        assert "weather" not in snap.active_skills

    def test_is_healthy(self):
        snap = ResourceSnapshot(cpu_percent=50, ram_percent=60)
        assert snap.is_healthy is True

    def test_is_critical(self):
        snap = ResourceSnapshot(cpu_percent=96, ram_percent=50)
        assert snap.is_critical is True

    def test_should_throttle(self):
        snap = ResourceSnapshot(cpu_percent=85, ram_percent=50)
        assert snap.should_throttle is True

    def test_should_reject(self):
        snap = ResourceSnapshot(cpu_percent=96, ram_percent=50)
        assert snap.should_reject is True

    def test_recommend_concurrency(self):
        assert ResourceSnapshot(cpu_percent=10, ram_percent=10).recommend_concurrency() == 8
        assert ResourceSnapshot(cpu_percent=40, ram_percent=30).recommend_concurrency() == 8
        assert ResourceSnapshot(cpu_percent=70, ram_percent=50).recommend_concurrency() == 4
        assert ResourceSnapshot(cpu_percent=85, ram_percent=50).recommend_concurrency() == 2
        assert ResourceSnapshot(cpu_percent=96, ram_percent=96).recommend_concurrency() == 1

    def test_to_dict(self):
        snap = ResourceSnapshot(cpu_percent=42.5, ram_percent=63.1)
        d = snap.to_dict()
        assert d["cpu_percent"] == 42.5
        assert d["ram_percent"] == 63.1
        assert "is_healthy" in d
        assert "is_critical" in d
        assert "timestamp" in d

    @patch("monitors.resource._psutil_available", True)
    @patch("monitors.resource.psutil")
    def test_snapshot_with_psutil(self, mock_psutil):
        mock_psutil.cpu_percent.return_value = 45.0
        mock_psutil.virtual_memory.return_value = MagicMock(percent=62.0, available=4 * 1024**3)
        mock_psutil.disk_usage.return_value = MagicMock(percent=55.0, free=100 * 1024**3)

        rm = ResourceMonitor()
        snap = rm.snapshot()
        assert snap.cpu_percent == 45.0
        assert snap.ram_percent == 62.0
        assert snap.ram_available_gb == pytest.approx(4.0, rel=0.1)
        assert snap.disk_percent == 55.0

    @patch("monitors.resource.ResourceMonitor._check_gpu", return_value=6.0)
    def test_gpu_check(self, mock_gpu):
        rm = ResourceMonitor()
        snap = rm.snapshot()
        assert snap.gpu_free_gb == pytest.approx(6.0)


class TestServiceHealthChecker:
    @pytest.mark.asyncio
    async def test_check_ollama_healthy(self):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = MagicMock(status_code=200)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await ServiceHealthChecker._check_ollama()

        assert result.status == "healthy"
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_check_ollama_down(self):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.side_effect = ConnectionError("refused")

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await ServiceHealthChecker._check_ollama()

        assert result.status == "down"
        assert "refused" in result.error

    @pytest.mark.asyncio
    async def test_check_search_healthy(self):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = MagicMock(status_code=200)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await ServiceHealthChecker._check_search()

        assert result.status == "healthy"

    @pytest.mark.asyncio
    async def test_check_search_down(self):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.side_effect = ConnectionError("no server")

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await ServiceHealthChecker._check_search()

        assert result.status == "down"

    @pytest.mark.asyncio
    async def test_check_network_healthy(self):
        mock_sock = MagicMock()
        with patch("socket.socket", return_value=mock_sock):
            result = await ServiceHealthChecker._check_network()

        assert result.status == "healthy"

    def test_latest_returns_snapshot(self):
        shc = ServiceHealthChecker()
        snap = shc.latest()
        assert isinstance(snap, ServicesSnapshot)

    def test_snapshot_to_dict(self):
        snap = ServicesSnapshot(
            ollama=ServiceHealth(name="ollama", status="healthy", latency_ms=12.5),
            search=ServiceHealth(name="search", status="degraded", latency_ms=500),
            warnings=["test warning"],
        )
        d = snap.to_dict()
        assert d["ollama"]["status"] == "healthy"
        assert d["search"]["status"] == "degraded"
        assert "test warning" in d["warnings"]

    @pytest.mark.asyncio
    async def test_check_voice_modules_healthy(self):
        import sys
        fake_stt = MagicMock()
        fake_tts = MagicMock()
        fake_wake = MagicMock()
        fake_mods = {
            "assistant": MagicMock(),
            "assistant.stt": MagicMock(stt_processor=fake_stt),
            "assistant.tts": MagicMock(tts_engine=fake_tts),
            "assistant.wake_word": MagicMock(wake_word_detector=fake_wake),
        }
        with patch.dict("sys.modules", fake_mods, clear=False):
            result = await ServiceHealthChecker._check_voice_modules()
        assert result.status == "healthy"


class TestAlertRouter:
    def test_alert_broadcast(self):
        mock_broadcast = AsyncMock()
        router = AlertRouter(broadcast_fn=mock_broadcast)
        router.send(Alert(priority=AlertPriority.INFO, module="test", message="hello"))
        assert len(router.get_history()) == 1

    def test_alert_history_bounded(self):
        router = AlertRouter()
        router._max_history = 3
        for i in range(5):
            router.send(Alert(priority=AlertPriority.INFO, module="test", message=str(i)))
        assert len(router.get_history()) == 3
        assert router.get_history(1)[0].message == "4"

    def test_info_alert_no_whatsapp(self):
        mock_wa = MagicMock()
        router = AlertRouter(whatsapp_fn=mock_wa)
        router.send(Alert(priority=AlertPriority.INFO, module="test", message="info only"))
        mock_wa.assert_not_called()

    def test_warning_alert_sends_whatsapp(self):
        mock_wa = MagicMock()
        router = AlertRouter(whatsapp_fn=mock_wa)
        router.send(Alert(priority=AlertPriority.WARNING, module="test", message="warning"))
        mock_wa.assert_called_once()

    def test_alert_priority_str_enum(self):
        assert AlertPriority.INFO == "info"
        assert AlertPriority.WARNING == "warning"
        assert AlertPriority.CRITICAL == "critical"
