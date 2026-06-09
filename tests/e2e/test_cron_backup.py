# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""tests/test_cron_backup.py — Tests for core/cron.py CronScheduler + core/backup.py BackupManager."""
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime


class TestCronScheduler:
    @pytest.fixture
    def cron(self):
        with patch("core.cron.STORE_PATH", MagicMock()) as mock_path:
            mock_path.exists.return_value = False
            from core.cron import CronScheduler
            yield CronScheduler()

    def test_init(self, cron):
        assert cron._jobs == {}

    def test_add_job(self, cron):
        job = cron.add_job("test1", "30m", "health_check", {"enabled": True})
        assert job["id"] == "test1"
        assert job["schedule"] == "30m"
        assert job["action"] == "health_check"
        assert cron.get_job("test1") is job

    def test_remove_job(self, cron):
        cron.add_job("test1", "10m", "health_check")
        assert cron.remove_job("test1") is True
        assert cron.remove_job("nonexistent") is False

    def test_list_jobs(self, cron):
        cron.add_job("a", "10m", "health_check")
        cron.add_job("b", "20m", "backup")
        assert len(cron.list_jobs()) == 2

    def test_get_job_not_found(self, cron):
        assert cron.get_job("nonexistent") is None

    def test_parse_interval(self, cron):
        assert cron._parse_interval("30s") == 30
        assert cron._parse_interval("5m") == 300
        assert cron._parse_interval("2h") == 7200
        assert cron._parse_interval("1d") == 86400
        assert cron._parse_interval("60") == 60

    @pytest.mark.asyncio
    async def test_execute_job_health_check(self, cron):
        cron.add_job("hc", "1m", "health_check")
        job = cron.get_job("hc")
        with patch("core.health_monitor.HealthMonitor") as mock_hm:
            mock_hm_instance = MagicMock()
            mock_hm_instance.check_all = AsyncMock()
            mock_hm.return_value = mock_hm_instance
            await cron._execute_job(job)
            assert job["last_run"] is not None

    @pytest.mark.asyncio
    async def test_execute_job_custom(self, cron):
        cron.add_job("cust", "1m", "custom", {"msg": "hello"})
        job = cron.get_job("cust")
        await cron._execute_job(job)
        assert job["last_run"] is not None

    @pytest.mark.asyncio
    async def test_start_stop(self, cron):
        import asyncio
        task = asyncio.get_running_loop().create_future()
        task.cancel()
        with patch("asyncio.create_task", return_value=task):
            await cron.start()
            assert cron._running is True
            await cron.stop()
            assert cron._running is False


class TestBackupManager:
    @pytest.fixture
    def backup(self):
        with patch("core.backup.BACKUP_DIR", MagicMock()):
            from core.backup import BackupManager
            yield BackupManager()

    @pytest.mark.asyncio
    async def test_create_backup_success(self, backup):
        with patch("core.backup.tarfile.open") as mock_tar:
            mock_tar.return_value.__enter__.return_value = MagicMock()
            with patch("pathlib.Path.exists", return_value=False):
                with patch("pathlib.Path.mkdir"):
                    result = await backup.create_backup()
                    assert result.get("success") is True

    @pytest.mark.asyncio
    async def test_create_backup_failure(self, backup):
        with patch("core.backup.tarfile.open", side_effect=Exception("Disk full")):
            result = await backup.create_backup()
            assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_restore_backup_not_found(self, backup):
        with patch("pathlib.Path.exists", return_value=False):
            result = await backup.restore_backup("/nonexistent.tar.gz")
            assert result.get("success") is False
            assert "Not found" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_restore_backup_success(self, backup):
        import tempfile as tf
        restore_dir = tf.mkdtemp()
        os.makedirs(os.path.join(restore_dir, "sessions"), exist_ok=True)
        try:
            with patch("pathlib.Path.exists", return_value=True):
                with patch("tempfile.TemporaryDirectory") as mock_tmp:
                    mock_tmp.return_value.__enter__.return_value = restore_dir
                    with patch("tarfile.open") as mock_tar:
                        mock_tar.return_value.__enter__.return_value = MagicMock()
                        with patch("pathlib.Path.iterdir", return_value=[]):
                            result = await backup.restore_backup("/tmp/test.tar.gz")
                            assert result.get("success") is True
        finally:
            import shutil
            shutil.rmtree(restore_dir, ignore_errors=True)

    def test_list_backups_empty(self, backup):
        backup.BACKUP_DIR = MagicMock()
        backup.BACKUP_DIR.glob.return_value = []
        assert backup.list_backups() == []

    @pytest.mark.asyncio
    async def test_verify_backup_not_found(self, backup):
        with patch("pathlib.Path.exists", return_value=False):
            result = await backup.verify_backup("/nonexistent.tar.gz")
            assert result.get("valid") is False

    @pytest.mark.asyncio
    async def test_verify_backup_valid(self, backup):
        import tempfile as tf
        tf_path = tf.mktemp(suffix=".tar.gz")
        try:
            open(tf_path, "w").close()
            with patch("pathlib.Path.exists", return_value=True):
                with patch("tarfile.open") as mock_tar:
                    mock_tar.return_value.__enter__.return_value.getmembers.return_value = ["f1", "f2"]
                    result = await backup.verify_backup(tf_path)
                    assert result.get("valid") is True
                    assert result.get("file_count") == 2
        finally:
            import os
            os.unlink(tf_path)
