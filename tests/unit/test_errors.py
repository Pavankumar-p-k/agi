import pytest
from core.errors import (
    AppError, NotFoundError, ValidationError,
    AuthError, ForbiddenError, ServerError, RateLimitError,
)


class TestAppError:
    def test_default_creation(self):
        err = AppError(400, "TEST_CODE", "test message")
        assert err.status_code == 400
        assert err.detail["code"] == "TEST_CODE"
        assert err.detail["message"] == "test message"
        assert err.detail["data"] is None

    def test_with_data(self):
        err = AppError(400, "TEST_CODE", "msg", {"key": "val"})
        assert err.detail["data"] == {"key": "val"}

    def test_is_http_exception(self):
        from fastapi import HTTPException
        err = AppError(400, "TEST")
        assert isinstance(err, HTTPException)


class TestNotFoundError:
    def test_default_message(self):
        err = NotFoundError()
        assert err.status_code == 404
        assert err.detail["code"] == "NOT_FOUND"

    def test_custom_message(self):
        err = NotFoundError("User not found")
        assert err.detail["message"] == "User not found"


class TestValidationError:
    def test_default(self):
        err = ValidationError()
        assert err.status_code == 400
        assert err.detail["code"] == "VALIDATION_ERROR"

    def test_custom(self):
        err = ValidationError("Invalid email")
        assert err.detail["message"] == "Invalid email"


class TestAuthError:
    def test_default(self):
        err = AuthError()
        assert err.status_code == 401
        assert err.detail["code"] == "AUTH_ERROR"


class TestForbiddenError:
    def test_default(self):
        err = ForbiddenError()
        assert err.status_code == 403
        assert err.detail["code"] == "FORBIDDEN"


class TestServerError:
    def test_default(self):
        err = ServerError()
        assert err.status_code == 500
        assert err.detail["code"] == "SERVER_ERROR"


class TestRateLimitError:
    def test_default(self):
        err = RateLimitError()
        assert err.status_code == 429
        assert err.detail["code"] == "RATE_LIMIT"
