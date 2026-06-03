from __future__ import annotations

from fastapi import HTTPException
from typing import Any, Optional


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str = "", data: Any = None, cause: Optional[Exception] = None):
        body = {"code": code, "message": detail, "data": data}
        if cause:
            body["cause_chain"] = self._chain(cause)
        super().__init__(status_code=status_code, detail=body)

    @staticmethod
    def _chain(err: Exception) -> list[str]:
        msgs = []
        while err:
            msgs.append(f"{type(err).__name__}: {err}")
            err = err.__cause__
        return msgs

class NotFoundError(AppError):
    def __init__(self, detail: str = "Resource not found", data: Any = None):
        super().__init__(404, "NOT_FOUND", detail, data)

class ValidationError(AppError):
    def __init__(self, detail: str = "Invalid request", data: Any = None):
        super().__init__(400, "VALIDATION_ERROR", detail, data)

class AuthError(AppError):
    def __init__(self, detail: str = "Unauthorized", data: Any = None):
        super().__init__(401, "AUTH_ERROR", detail, data)

class ForbiddenError(AppError):
    def __init__(self, detail: str = "Forbidden", data: Any = None):
        super().__init__(403, "FORBIDDEN", detail, data)

class ServerError(AppError):
    def __init__(self, detail: str = "Internal server error", data: Any = None):
        super().__init__(500, "SERVER_ERROR", detail, data)

class RateLimitError(AppError):
    def __init__(self, detail: str = "Rate limit exceeded", data: Any = None):
        super().__init__(429, "RATE_LIMIT", detail, data)


# ── Domain-level errors (not HTTP — for Result type) ──────────────

class DomainError(Exception):
    """Base for all domain-level errors used with Result types."""

class NotFound(DomainError): ...
class Timeout(DomainError): ...
class ProviderError(DomainError): ...
class NotConfigured(DomainError): ...
class ValidationFailed(DomainError): ...
class StorageError(DomainError): ...
class AuthFailed(DomainError): ...
class RateLimited(DomainError): ...
class LLMError(DomainError): ...


# ── Converter: DomainError → AppError (for HTTP boundary) ────────

_CODE_MAP: dict[type[DomainError], int] = {
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
    status = _CODE_MAP.get(type(err), 500)
    return AppError(status, type(err).__name__.upper(), str(err))
