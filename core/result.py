"""Result type pattern (Ok/Err) for robust functional error handling."""
from __future__ import annotations
from typing import TypeVar, Generic, Callable, Any, Union
from dataclasses import dataclass

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")


class ResultError(Exception):
    """Raised when unwrapping an Err result."""
    pass


@dataclass(frozen=True)
class ErrorWrapper:
    exception: Exception | None = None
    code: str = "UNKNOWN"
    message: str = ""


@dataclass(frozen=True)
class Ok(Generic[T]):
    _value: T
    __match_args__ = ("_value",)

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self._value

    def unwrap_or(self, default: Any) -> T:
        return self._value

    def map(self, fn: Callable[[T], U]) -> Ok[U]:
        return Ok(fn(self._value))

    def map_err(self, fn: Callable[[Any], Any]) -> Ok[T]:
        return self

    def and_then(self, fn: Callable[[T], Ok[U] | Err[Any]]) -> Ok[U] | Err[Any]:
        return fn(self._value)

    def or_else(self, fn: Callable[[Any], Any]) -> Ok[T]:
        return self

    def __repr__(self) -> str:
        return f"Ok({self._value!r})"


@dataclass(frozen=True)
class Err(Generic[E]):
    _error: E
    __match_args__ = ("_error",)

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> Any:
        raise ResultError(self._error)

    def unwrap_or(self, default: U) -> U:
        return default

    def map(self, fn: Callable[[Any], Any]) -> Err[E]:
        return self

    def map_err(self, fn: Callable[[E], U]) -> Err[U]:
        return Err(fn(self._error))

    def and_then(self, fn: Callable[[Any], Any]) -> Err[E]:
        return self

    def or_else(self, fn: Callable[[E], Ok[U] | Err[U]]) -> Ok[U] | Err[U]:
        return fn(self._error)

    def __repr__(self) -> str:
        return f"Err({self._error!r})"


Result = Union[Ok[T], Err[E]]


def err_from(exc: Exception, code: str = "UNKNOWN") -> Err[ErrorWrapper]:
    return Err(ErrorWrapper(exception=exc, code=code, message=str(exc)))
