"""tests/test_snapshot.py — Tests for pc_agent/snapshot.py SystemSnapshot."""
import pytest
import os
import time
import tempfile
from unittest.mock import patch, MagicMock


class TestSystemSnapshot:
    @pytest.fixture
    def snapshot(self):
        from pc_agent.snapshot import SystemSnapshot
        with patch("pc_agent.snapshot.os.makedirs"):
            with patch("pc_agent.snapshot.sqlite3.connect") as mock_conn:
                mock_conn.return_value.execute.return_value = MagicMock()
                yield SystemSnapshot(db_path="/tmp/test_snap.db")

    def test_init(self, snapshot):
        assert snapshot.db_path == "/tmp/test_snap.db"

    def test_create(self, snapshot):
        with patch("pc_agent.snapshot.tempfile.mkdtemp", return_value=tempfile.mkdtemp()):
            with patch("pc_agent.snapshot.os.path.exists", return_value=True):
                with patch("pc_agent.snapshot.shutil.copy2"):
                    with patch("pc_agent.snapshot.shutil.copytree"):
                        sid = snapshot.create("test instruction")
                        assert sid.startswith("snap_")

    def test_rollback_with_snapshot_id(self, snapshot):
        snapshot._snapshot_dir = "/tmp/snap_test"
        with patch("pc_agent.snapshot.sqlite3.connect") as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.execute.return_value.fetchall.return_value = [
                ("/tmp/test.txt", "/tmp/snap_test/test.txt")
            ]
            with patch("pc_agent.snapshot.os.path.exists", return_value=True):
                with patch("pc_agent.snapshot.shutil.copy2"):
                    with patch("pc_agent.snapshot.shutil.rmtree"):
                        result = snapshot.rollback("snap_123")
                        assert result == 1

    def test_clean_old(self, snapshot):
        with patch("pc_agent.snapshot.sqlite3.connect") as mock_conn:
            mock_conn.return_value.execute.return_value.fetchall.return_value = [("old_snap",)]
            snapshot.clean_old(max_age_hours=0)
            assert mock_conn.called

    def test_create_db_init(self):
        with patch("pc_agent.snapshot.os.makedirs"):
            with patch("pc_agent.snapshot.sqlite3.connect") as mock_conn:
                from pc_agent.snapshot import SystemSnapshot
                s = SystemSnapshot(db_path="/tmp/test2.db")
                assert mock_conn.called
