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

"""Core unit tests for Result type, domain errors, and error pattern."""
from core.result import Ok, Err, ResultError, err_from
from core.errors import (
    NotFound, Timeout, ProviderError, NotConfigured,
    ValidationFailed, StorageError, AuthFailed, RateLimited,
    DomainError, domain_to_http, AppError,
)


class TestOk:
    def test_create_and_unwrap(self):
        assert Ok(42).unwrap() == 42

    def test_unwrap_or_ignores_default(self):
        assert Ok(42).unwrap_or(0) == 42

    def test_map(self):
        assert Ok(2).map(lambda x: x * 3) == Ok(6)

    def test_map_err_noop(self):
        assert Ok(2).map_err(str) == Ok(2)

    def test_is_ok(self):
        assert Ok(1).is_ok() is True

    def test_is_err(self):
        assert Ok(1).is_err() is False


class TestErr:
    def test_create_and_unwrap_raises(self):
        import pytest
        with pytest.raises(ResultError):
            Err("fail").unwrap()

    def test_unwrap_or(self):
        assert Err("fail").unwrap_or(42) == 42

    def test_map_noop(self):
        assert Err("fail").map(str.upper) == Err("fail")

    def test_map_err(self):
        assert Err("fail").map_err(str.upper) == Err("FAIL")

    def test_is_ok(self):
        assert Err("x").is_ok() is False

    def test_is_err(self):
        assert Err("x").is_err() is True


class TestErrFrom:
    def test_wraps_exception(self):
        result = err_from(ValueError("bad"), "BAD")
        assert result.is_err()
        assert result._error.code == "BAD"

    def test_default_code(self):
        result = err_from(RuntimeError("oops"))
        assert result._error.code == "UNKNOWN"


class TestDomainToHttp:
    def test_not_found(self):
        http = domain_to_http(NotFound("missing"))
        assert http.status_code == 404

    def test_timeout(self):
        http = domain_to_http(Timeout("slow"))
        assert http.status_code == 504

    def test_provider_error(self):
        http = domain_to_http(ProviderError("down"))
        assert http.status_code == 502

    def test_not_configured(self):
        http = domain_to_http(NotConfigured("no key"))
        assert http.status_code == 503

    def test_validation_failed(self):
        http = domain_to_http(ValidationFailed("bad input"))
        assert http.status_code == 400

    def test_storage_error(self):
        http = domain_to_http(StorageError("disk full"))
        assert http.status_code == 500

    def test_auth_failed(self):
        http = domain_to_http(AuthFailed("bad token"))
        assert http.status_code == 401

    def test_rate_limited(self):
        http = domain_to_http(RateLimited("too fast"))
        assert http.status_code == 429

    def test_unknown_domain_falls_to_500(self):
        class Custom(DomainError):
            pass
        http = domain_to_http(Custom("weird"))
        assert http.status_code == 500

    def test_all_app_error_subtypes(self):
        err = domain_to_http(NotFound("test"))
        assert isinstance(err, AppError)
        assert "NOTFOUND" in err.detail["code"]
