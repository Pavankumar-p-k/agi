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

"""tests/test_commitments.py — Tests for core/commitments.py CommitmentTracker."""
import time
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


class TestCommitmentTracker:
    @pytest.fixture
    def tracker(self):
        with patch("core.commitments.STORE_PATH", MagicMock()) as mock_path:
            mock_path.exists.return_value = False
            from core.commitments import CommitmentTracker
            yield CommitmentTracker()

    def test_init_empty(self, tracker):
        assert tracker._commitments == {}

    def test_add_commitment(self, tracker):
        cmt = tracker.add("Review the report", source="conversation", priority="high")
        assert cmt["description"] == "Review the report"
        assert cmt["status"] == "pending"
        assert cmt["priority"] == "high"
        assert cmt["source"] == "conversation"
        assert cmt["id"].startswith("cmt_")

    def test_complete_commitment(self, tracker):
        cmt = tracker.add("Test task")
        assert tracker.complete(cmt["id"]) is True
        assert tracker._commitments[cmt["id"]]["status"] == "completed"

    def test_complete_not_found(self, tracker):
        assert tracker.complete("nonexistent") is False

    def test_dismiss_commitment(self, tracker):
        cmt = tracker.add("Dismiss me")
        assert tracker.dismiss(cmt["id"]) is True
        assert tracker._commitments[cmt["id"]]["status"] == "dismissed"

    def test_list_all(self, tracker):
        tracker.add("Task 1")
        time.sleep(0.01)
        tracker.add("Task 2")
        assert len(tracker.list()) == 2

    def test_list_by_status(self, tracker):
        t1 = tracker.add("Pending task")
        t2 = tracker.add("Complete me")
        tracker.complete(t2["id"])
        pending = tracker.list(status="pending")
        completed = tracker.list(status="completed")
        assert len(pending) == 1, f"got {len(pending)} pending: {[c['description'] for c in pending]}"
        assert len(completed) == 1

    def test_stats(self, tracker):
        t1 = tracker.add("Task A")
        time.sleep(0.01)
        t2 = tracker.add("Task B")
        tracker.complete(t1["id"])
        stats = tracker.stats()
        assert stats["total"] == 2
        assert stats["pending"] == 1
        assert stats["completed"] == 1
        assert stats["dismissed"] == 0

    def test_get_overdue(self, tracker):
        future = (datetime.now() + timedelta(days=30)).isoformat()
        past = (datetime.now() - timedelta(days=1)).isoformat()
        tracker.add("Future task", due=future)
        tracker.add("Past task", due=past)
        overdue = tracker.get_overdue()
        assert len(overdue) == 1
        assert overdue[0]["description"] == "Past task"

    def test_infer_from_text(self, tracker):
        text = "I will send the email tomorrow. Don't forget to check the logs."
        found = tracker.infer_from_text(text)
        assert len(found) >= 1
        assert any("send the email" in c["description"] for c in found)
        assert any("check the logs" in c["description"] for c in found)

    def test_infer_short_ignored(self, tracker):
        text = "I'll go."
        found = tracker.infer_from_text(text)
        assert len(found) == 0
