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

"""tests/test_oauth.py — Tests for core/oauth.py OAuthManager."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path


class TestOAuthManager:
    @pytest.fixture
    def oauth(self):
        with patch("core.oauth.STORE_PATH", MagicMock()):
            om = __import__("core.oauth", fromlist=["OAuthManager"]).OAuthManager()
            om._tokens = {}
            yield om

    def test_init_no_tokens(self, oauth):
        assert oauth._tokens == {}

    def test_load_tokens(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = '{"test": {"id": "test"}}'
        with patch("core.oauth.STORE_PATH", mock_path):
            from core.oauth import OAuthManager
            om = OAuthManager()
            assert "test" in om._tokens

    def test_get_providers_no_env(self, oauth):
        with patch.dict("os.environ", {}, clear=True):
            providers = oauth.get_providers()
            assert providers == []

    @patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "g-id", "GOOGLE_CLIENT_SECRET": "g-secret"})
    def test_get_providers_google(self, oauth):
        providers = oauth.get_providers()
        assert "google" in providers

    def test_list_tokens_empty(self, oauth):
        assert oauth.list_tokens() == []

    def test_remove_token_not_found(self, oauth):
        assert oauth.remove_token("google", "nonexistent") is False

    @pytest.mark.asyncio
    async def test_authorize_redirect_no_oauth(self, oauth):
        import starlette.responses
        oauth._oauth = None
        oauth._init_providers = MagicMock()
        result = await oauth.authorize_redirect("google", None, "http://localhost/callback")
        assert isinstance(result, starlette.responses.JSONResponse)
        assert result.status_code == 503

    @pytest.mark.asyncio
    async def test_authorize_access_token_no_oauth(self, oauth):
        oauth._oauth = None
        result = await oauth.authorize_access_token("google", None)
        assert result is None

    @patch("core.oauth.oauth_manager._get_userinfo")
    def test_store_and_list_tokens(self, mock_userinfo):
        om = __import__("core.oauth", fromlist=["OAuthManager"]).OAuthManager()
        om._store_token("google", {"access_token": "tok1"}, {"sub": "u1", "name": "User1", "email": "u1@test.com"})
        tokens = om.list_tokens()
        assert len(tokens) == 1
        assert tokens[0]["user"] == "User1"
        assert tokens[0]["email"] == "u1@test.com"

    def test_store_and_remove_token(self, oauth):
        oauth._store_token("github", {"access_token": "tok2"}, {"sub": "u2", "name": "User2"})
        assert oauth.remove_token("github", "u2") is True
        assert oauth.list_tokens() == []

    @pytest.mark.asyncio
    async def test_authorize_redirect_unknown_provider(self, oauth):
        oauth._init_providers = MagicMock()
        oauth._oauth = MagicMock()
        oauth._oauth.create_client.return_value = None
        import starlette.responses
        result = await oauth.authorize_redirect("nonexistent", MagicMock(), "http://localhost/callback")
        assert isinstance(result, starlette.responses.JSONResponse)
        assert result.status_code == 400
