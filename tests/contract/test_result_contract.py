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

"""Contract tests for core.result — Ok/Err type behavior."""
import pytest
from core.result import Ok, Err, ResultError
from core.errors import (
    NotFound, Timeout, ProviderError, NotConfigured,
    ValidationFailed, StorageError, AuthFailed, RateLimited,
    DomainError, domain_to_http, AppError,
)


class TestOk:
    def test_is_ok(self):
        assert Ok(42).is_ok() is True

    def test_is_err(self):
        assert Ok(42).is_err() is False

    def test_unwrap(self):
        assert Ok(42).unwrap() == 42

    def test_unwrap_or_ignores_default(self):
        assert Ok(42).unwrap_or(0) == 42

    def test_map(self):
        assert Ok(42).map(lambda x: x * 2) == Ok(84)

    def test_map_err_noop(self):
        assert Ok(42).map_err(lambda e: str(e)) == Ok(42)

    def test_repr(self):
        assert repr(Ok([1, 2])) == "Ok([1, 2])"

    def test_and_then_chains(self):
        assert Ok(42).and_then(lambda v: Ok(v * 2)) == Ok(84)

    def test_and_then_can_return_err(self):
        assert Ok(42).and_then(lambda _: Err("fail")) == Err("fail")

    def test_and_then_type_change(self):
        assert Ok(42).and_then(lambda _: Ok("hello")) == Ok("hello")

    def test_or_else_noop_on_ok(self):
        assert Ok(42).or_else(lambda e: Ok(0)) == Ok(42)


class TestErr:
    def test_is_ok(self):
        assert Err("fail").is_ok() is False

    def test_is_err(self):
        assert Err("fail").is_err() is True

    def test_unwrap_raises(self):
        with pytest.raises(ResultError):
            Err("fail").unwrap()

    def test_unwrap_or_returns_default(self):
        assert Err("fail").unwrap_or(42) == 42

    def test_map_noop(self):
        assert Err("fail").map(str.upper) == Err("fail")

    def test_map_err(self):
        assert Err("fail").map_err(str.upper) == Err("FAIL")

    def test_repr(self):
        assert repr(Err("oops")) == "Err('oops')"

    def test_and_then_noop_on_err(self):
        assert Err("fail").and_then(lambda v: Ok(v)) == Err("fail")

    def test_or_else_recovers(self):
        assert Err("fail").or_else(lambda e: Ok(f"recovered from {e}")) == Ok("recovered from fail")

    def test_or_else_type_change(self):
        assert Err(42).or_else(lambda e: Ok(str(e))) == Ok("42")

    def test_or_else_can_stay_err(self):
        assert Err("fail").or_else(lambda e: Err(f"wrapped: {e}")) == Err("wrapped: fail")


class TestResultPattern:
    def test_ok_pattern_match_ok(self):
        match Ok("success"):
            case Ok(v):
                assert v == "success"
            case _:
                pytest.fail("should match Ok")

    def test_err_pattern_match_err(self):
        match Err("failure"):
            case Err(e):
                assert e == "failure"
            case _:
                pytest.fail("should match Err")

    def test_unwrap_or_chain(self):
        results = [Ok(1), Err("x"), Ok(3)]
        total = sum(r.unwrap_or(0) for r in results)
        assert total == 4


class TestDomainToHttp:
    @pytest.mark.parametrize("domain_cls,expected_status,expected_code", [
        (NotFound, 404, "NOTFOUND"),
        (Timeout, 504, "TIMEOUT"),
        (ProviderError, 502, "PROVIDERERROR"),
        (NotConfigured, 503, "NOTCONFIGURED"),
        (ValidationFailed, 400, "VALIDATIONFAILED"),
        (StorageError, 500, "STORAGEERROR"),
        (AuthFailed, 401, "AUTHFAILED"),
        (RateLimited, 429, "RATELIMITED"),
    ])
    def test_conversion(self, domain_cls, expected_status, expected_code):
        err = domain_cls("test message")
        http = domain_to_http(err)
        assert isinstance(http, AppError)
        assert http.status_code == expected_status
        assert http.detail["code"] == expected_code
        assert "test message" in http.detail["message"]

    def test_unknown_domain_falls_to_500(self):
        class CustomError(DomainError):
            pass
        http = domain_to_http(CustomError("weird"))
        assert http.status_code == 500
        assert http.detail["code"] == "CUSTOMERROR"


class TestErrorWrapper:
    def test_err_from_exception(self):
        from core.result import err_from
        result = err_from(ValueError("bad value"), "BAD")
        assert result.is_err()
        wrapper = result._error
        assert wrapper.code == "BAD"
        assert "bad value" in wrapper.message
