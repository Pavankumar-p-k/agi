import pytest
from unittest.mock import patch


@pytest.fixture
def mock_auth_client(api_client):
    """Configure the app with a mock auth_manager so auth middleware is active."""
    from unittest.mock import MagicMock
    auth_mgr = MagicMock()
    auth_mgr.is_configured = True
    auth_mgr.validate_token.return_value = True
    auth_mgr.get_username_for_token.return_value = "test_user"
    api_client.app.state.auth_manager = auth_mgr
    yield api_client
    api_client.app.state.auth_manager = None


@pytest.fixture
def real_auth_client(api_client):
    """Configure the app with a real AuthManager backed by a temp file."""
    from core import auth as auth_module
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        auth_path = os.path.join(tmpdir, "auth.json")
        old_default = auth_module.DEFAULT_AUTH_PATH
        auth_module.DEFAULT_AUTH_PATH = auth_path

        am = auth_module.AuthManager(auth_path=auth_path)
        am.setup("admin", "Passw0rd!")
        token = am.create_session("admin", "Passw0rd!")
        api_client.app.state.auth_manager = am

        yield api_client, token

        api_client.app.state.auth_manager = None
        auth_module.DEFAULT_AUTH_PATH = old_default


class TestHealthEndpoint:
    def test_health_returns_200(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200


class TestAuthMiddleware:
    def test_blocked_when_no_token(self, mock_auth_client):
        mock_auth_client.app.state.auth_manager.validate_token.return_value = False
        resp = mock_auth_client.get("/api/settings/llm.default_model")
        assert resp.status_code == 401

    def test_blocked_when_invalid_cookie(self, mock_auth_client):
        mock_auth_client.app.state.auth_manager.validate_token.return_value = False
        resp = mock_auth_client.get(
            "/api/settings/llm.default_model",
            cookies={"session_token": "garbage"},
        )
        assert resp.status_code == 401

    def test_passes_with_valid_cookie(self, mock_auth_client):
        mock_auth_client.app.state.auth_manager.validate_token.return_value = True
        resp = mock_auth_client.get(
            "/api/settings/llm.default_model",
            cookies={"session_token": "valid_token"},
        )
        assert resp.status_code != 401

    def test_passes_with_valid_bearer(self, mock_auth_client):
        mock_auth_client.app.state.auth_manager.validate_token.return_value = True
        resp = mock_auth_client.get(
            "/api/settings/llm.default_model",
            headers={"Authorization": "Bearer valid_token"},
        )
        assert resp.status_code != 401

    def test_exempt_path_skips_auth(self, mock_auth_client):
        mock_auth_client.app.state.auth_manager.validate_token.return_value = False
        resp = mock_auth_client.get("/health")
        assert resp.status_code == 200

    def test_auth_with_real_manager_valid_token(self, real_auth_client):
        client, token = real_auth_client
        resp = client.get(
            "/api/settings/llm.default_model",
            cookies={"session_token": token},
        )
        assert resp.status_code == 200

    def test_auth_with_real_manager_no_token(self, real_auth_client):
        client, _token = real_auth_client
        resp = client.get("/api/settings/llm.default_model")
        assert resp.status_code == 401

    def test_auth_with_real_manager_bad_token(self, real_auth_client):
        client, _token = real_auth_client
        resp = client.get(
            "/api/settings/llm.default_model",
            cookies={"session_token": "definitely-not-a-real-token"},
        )
        assert resp.status_code == 401


class TestRateLimiter:
    @patch("core.rate_limiter.api_rate_limiter.check", return_value=False)
    def test_rate_limit_exceeded(self, mock_check, api_client):
        resp = api_client.get("/api/settings")
        assert resp.status_code == 429
