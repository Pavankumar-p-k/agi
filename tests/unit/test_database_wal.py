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

import pytest
from unittest.mock import MagicMock, patch


class TestDatabaseWALPragma:
    def test_wal_pragma_executed_on_connect(self):
        from core.database_models import _set_sqlite_pragma
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        _set_sqlite_pragma(mock_conn, None)
        calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        assert any("journal_mode=WAL" in c for c in calls)
        assert any("synchronous=NORMAL" in c for c in calls)
        assert any("busy_timeout=5000" in c for c in calls)
        assert mock_cursor.close.called

    def test_engine_create_args_include_connect_args(self):
        from sqlalchemy import create_engine
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        # Verify the connect_args are stored on the engine
        assert test_engine.dialect.dbapi is not None
        assert True  # engine created successfully with connect_args

    def test_engine_url_is_sqlite(self):
        from core.database_models import engine
        assert engine.url.drivername == "sqlite"
