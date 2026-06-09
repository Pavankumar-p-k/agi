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
from collections.abc import Callable
from typing import Generic, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")
F = TypeVar("F")


class Ok(Generic[T]):
    __slots__ = ("_value",)
    __match_args__ = ("_value",)

    def __init__(self, value: T) -> None:
        self._value = value

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self._value

    def unwrap_or(self, _default: object) -> T:
        return self._value

    def map(self, fn: Callable[[T], U]) -> "Ok[U] | Err[E]":
        return Ok(fn(self._value))

    def map_err(self, _fn: Callable[[E], F]) -> "Ok[T] | Err[E]":
        return self

    def and_then(self, fn: Callable[[T], "Ok[U] | Err[E]"]) -> "Ok[U] | Err[E]":
        return fn(self._value)

    def or_else(self, _fn: Callable[[E], "Ok[T] | Err[F]"]) -> "Ok[T] | Err[E]":
        return self

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Ok) and self._value == other._value

    def __hash__(self) -> int:
        return hash(("Ok", self._value))

    def __repr__(self) -> str:
        return f"Ok({self._value!r})"


class Err(Generic[E]):
    __slots__ = ("_error",)
    __match_args__ = ("_error",)

    def __init__(self, error: E) -> None:
        self._error = error

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> object:
        raise ResultError(self._error)

    def unwrap_or(self, default: T) -> T:
        return default

    def map(self, _fn: Callable[[T], U]) -> "Ok[T] | Err[E]":
        return self

    def map_err(self, fn: Callable[[E], F]) -> "Ok[T] | Err[F]":
        return Err(fn(self._error))

    def and_then(self, _fn: Callable[[T], "Ok[U] | Err[E]"]) -> "Ok[U] | Err[E]":
        return self

    def or_else(self, fn: Callable[[E], "Ok[T] | Err[F]"]) -> "Ok[T] | Err[F]":
        return fn(self._error)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Err) and self._error == other._error

    def __hash__(self) -> int:
        return hash(("Err", self._error))

    def __repr__(self) -> str:
        return f"Err({self._error!r})"


class ResultError(Exception):
    def __init__(self, error: object) -> None:
        self.inner = error
        super().__init__(str(error))


def err_from(e: Exception, code: str = "UNKNOWN") -> Err:
    return Err(ErrorWrapper(str(e), code, e))


class ErrorWrapper:
    __slots__ = ("message", "code", "cause")

    def __init__(self, message: str, code: str = "UNKNOWN", cause: Exception | None = None) -> None:
        self.message = message
        self.code = code
        self.cause = cause

    def __repr__(self) -> str:
        return f"ErrorWrapper({self.code}: {self.message})"


# Type alias: Result[T, E] = Ok[T] | Err[E]
Result = Union[Ok[T], Err[E]]
