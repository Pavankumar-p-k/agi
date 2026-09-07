"""Domain errors and HTTP error mapping."""
from __future__ import annotations
from typing import Any
from fastapi import HTTPException


class DomainError(Exception):
    def __init__(self, message: str = "", code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__.upper()


class NotFound(DomainError): pass
class Timeout(DomainError): pass
class ProviderError(DomainError): pass
class NotConfigured(DomainError): pass
class ValidationFailed(DomainError): pass
class StorageError(DomainError): pass
class AuthFailed(DomainError): pass
class RateLimited(DomainError): pass


class AppError(HTTPException):
    def __init__(self, status_code: int, code_or_detail: str | dict[str, Any], message: str | None = None, data: Any = None):
        if isinstance(code_or_detail, dict):
            detail = code_or_detail
        else:
            detail = {"code": code_or_detail, "message": message or "", "data": data}
        super().__init__(status_code=status_code, detail=detail)
        self.status_code = status_code
        self.detail = detail


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found", data: Any = None):
        super().__init__(404, "NOT_FOUND", message, data)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation failed", data: Any = None):
        super().__init__(400, "VALIDATION_ERROR", message, data)


class AuthError(AppError):
    def __init__(self, message: str = "Authentication failed", data: Any = None):
        super().__init__(401, "AUTH_ERROR", message, data)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden", data: Any = None):
        super().__init__(403, "FORBIDDEN", message, data)


class ServerError(AppError):
    def __init__(self, message: str = "Internal server error", data: Any = None):
        super().__init__(500, "SERVER_ERROR", message, data)


class RateLimitError(AppError):
    def __init__(self, message: str = "Rate limit exceeded", data: Any = None):
        super().__init__(429, "RATE_LIMIT", message, data)


_STATUS_MAP = {
    NotFound: 404,
    Timeout: 504,
    ProviderError: 502,
    NotConfigured: 503,
    ValidationFailed: 400,
    StorageError: 500,
    AuthFailed: 401,
    RateLimited: 429,
}


def domain_to_http(err: DomainError) -> AppError:
    status_code = _STATUS_MAP.get(type(err), 500)
    code = getattr(err, "code", type(err).__name__.upper())
    message = str(err.message if hasattr(err, "message") and err.message else err)
    return AppError(status_code=status_code, detail={"code": code, "message": message})
