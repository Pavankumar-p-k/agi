import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestAuthExemptPaths:
    def test_exempt_paths_defined(self):
        from core.main import AUTH_EXEMPT_PREFIXES, AUTH_EXEMPT_PATHS
        assert "/health" in AUTH_EXEMPT_PREFIXES
        assert "/docs" in AUTH_EXEMPT_PREFIXES
        assert "/api/auth" in AUTH_EXEMPT_PREFIXES
        assert "/" in AUTH_EXEMPT_PATHS

    def test_api_routes_not_exempt(self):
        from core.main import AUTH_EXEMPT_PREFIXES, AUTH_EXEMPT_PATHS
        assert "/api/admin" not in AUTH_EXEMPT_PREFIXES
        assert "/api/admin" not in AUTH_EXEMPT_PATHS
        assert "/api/chat" not in AUTH_EXEMPT_PREFIXES
        assert "/api/chat" not in AUTH_EXEMPT_PATHS


class TestAuthMiddleware:
    @pytest.fixture
    def auth_mgr(self):
        mgr = MagicMock()
        mgr.is_configured = True
        mgr.validate_token.return_value = False
        mgr.get_username_for_token.return_value = "test_user"
        return mgr

    def _make_request(self, path="/api/admin", auth_mgr=None):
        mock_request = MagicMock()
        mock_request.url.path = path
        mock_request.state = MagicMock()
        if auth_mgr is not None:
            mock_app = MagicMock()
            mock_app.state.auth_manager = auth_mgr
            mock_request.app = mock_app
        return mock_request

    @pytest.mark.asyncio
    async def test_blocked_when_no_token(self):
        from core.main import session_auth_middleware
        from fastapi.responses import JSONResponse

        auth_mgr = MagicMock()
        auth_mgr.is_configured = True
        auth_mgr.validate_token.return_value = False

        mock_request = self._make_request("/api/settings", auth_mgr)

        def header_get(key, default=None):
            return "" if key == "Authorization" else default

        mock_request.headers.get = header_get

        async def call_next(req):
            return JSONResponse(content={"ok": True})

        response = await session_auth_middleware(mock_request, call_next)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_passes_when_valid_cookie(self, auth_mgr):
        auth_mgr.validate_token.return_value = True
        from core.main import session_auth_middleware
        from fastapi.responses import JSONResponse

        mock_request = self._make_request("/api/settings", auth_mgr)
        mock_request.cookies.get = lambda key, default=None: "valid_token" if key == "session_token" else default

        async def call_next(req):
            return JSONResponse(content={"ok": True})

        response = await session_auth_middleware(mock_request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_passes_when_valid_bearer_token(self, auth_mgr):
        auth_mgr.validate_token.return_value = True
        from core.main import session_auth_middleware
        from fastapi.responses import JSONResponse

        mock_request = self._make_request("/api/settings", auth_mgr)

        def header_get(key, default=None):
            return "Bearer valid_token" if key == "Authorization" else default

        mock_request.headers.get = header_get

        async def call_next(req):
            return JSONResponse(content={"ok": True})

        response = await session_auth_middleware(mock_request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_skips_auth_when_not_configured(self):
        from core.main import session_auth_middleware
        from fastapi.responses import JSONResponse

        auth_mgr = MagicMock()
        auth_mgr.is_configured = False

        mock_request = self._make_request("/api/settings", auth_mgr)

        async def call_next(req):
            return JSONResponse(content={"ok": True})

        response = await session_auth_middleware(mock_request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_exempt_path_skips_auth_check(self, auth_mgr):
        from core.main import session_auth_middleware
        from fastapi.responses import JSONResponse

        mock_request = self._make_request("/health", auth_mgr)

        async def call_next(req):
            return JSONResponse(content={"ok": True})

        response = await session_auth_middleware(mock_request, call_next)
        assert response.status_code == 200


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_exempt_paths_skip_rate_limit(self):
        from core.main import rate_limit_middleware
        from fastapi.responses import JSONResponse

        for path in ["/health", "/docs", "/openapi.json"]:
            mock_request = MagicMock()
            mock_request.url.path = path
            called = False

            async def call_next(req):
                nonlocal called
                called = True
                return JSONResponse(content={"ok": True})

            response = await rate_limit_middleware(mock_request, call_next)
            assert called is True
            assert response.status_code == 200
