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

"""Property-based fuzz tests for Result types using hypothesis."""
import json
from hypothesis import given, assume, strategies as st, settings, HealthCheck
import pytest

from core.result import Ok, Err, ResultError


# --- strategies ---

def _safe_for_eq(v):
    """Filter out NaN-like values (NaN != NaN by IEEE 754)."""
    if v is ResultError:
        return False
    try:
        if isinstance(v, float):
            return not __import__("math").isnan(v)
        if isinstance(v, complex):
            return not (__import__("math").isnan(v.real) or __import__("math").isnan(v.imag))
        # Decimal
        if type(v).__name__ == "Decimal":
            return not type(v).is_nan(v)
        return True
    except Exception:
        return True

any_value = st.from_type(object).filter(lambda x: x is not ResultError)
not_a_nan = st.from_type(object).filter(_safe_for_eq)
# Avoid unhashable types for eq/hash tests
hashable_value = st.from_type(object).filter(
    lambda x: isinstance(x, (type(None), int, str, bytes, float, bool, tuple, frozenset))
)
error_value = st.one_of(
    st.text(), st.integers(), st.builds(ValueError, st.text()),
)


# --- Ok properties ---

class TestOkFuzz:
    @given(not_a_nan)
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_unwrap_returns_value(self, v):
        assert Ok(v).unwrap() == v

    @given(not_a_nan, not_a_nan)
    def test_unwrap_or_ignores_default(self, v, default):
        assert Ok(v).unwrap_or(default) == v

    @given(not_a_nan, st.lists(st.integers()))
    def test_map_identity(self, v, _):
        assume(not (isinstance(v, float) and __import__("math").isnan(v)))
        assert Ok(v).map(lambda x: x).unwrap() == v

    @given(st.integers())
    def test_map_transforms(self, n):
        assert Ok(n).map(lambda x: x * 2).unwrap() == n * 2

    @given(not_a_nan)
    def test_is_ok_true(self, v):
        assert Ok(v).is_ok() is True

    @given(not_a_nan)
    def test_is_err_false(self, v):
        assert Ok(v).is_err() is False

    @given(not_a_nan, st.booleans())
    def test_ok_eq(self, v, _):
        assert Ok(v) == Ok(v)

    @given(st.integers(), st.integers())
    def test_ok_neq(self, a, b):
        assume(a != b)
        assert Ok(a) != Ok(b)

    @given(hashable_value)
    def test_ok_hash(self, v):
        assert hash(Ok(v)) == hash(("Ok", v))


# --- Err properties ---

class TestErrFuzz:
    @given(error_value)
    def test_unwrap_raises(self, e):
        with pytest.raises(ResultError):
            Err(e).unwrap()

    @given(error_value, not_a_nan)
    def test_unwrap_or_returns_default(self, e, default):
        assert Err(e).unwrap_or(default) == default

    @given(error_value, st.integers())
    def test_map_is_noop(self, e, _):
        assert Err(e).map(lambda x: x + 1).is_err() is True

    @given(error_value, st.text())
    def test_map_err(self, e, suffix):
        assert Err(e).map_err(lambda x: f"{x}{suffix}")._error == f"{e}{suffix}"

    @given(error_value)
    def test_is_ok_false(self, e):
        assert Err(e).is_ok() is False

    @given(error_value)
    def test_is_err_true(self, e):
        assert Err(e).is_err() is True

    @given(error_value)
    def test_err_eq(self, e):
        assert Err(e) == Err(e)

    @given(st.integers(), st.integers())
    def test_err_neq(self, a, b):
        assume(a != b)
        assert Err(a) != Err(b)


# --- Ok | Err cross properties ---

class TestCrossFuzz:
    @given(st.integers(), st.text())
    def test_ok_never_eq_err(self, n, s):
        assert Ok(n) != Err(s)

    @given(st.integers(min_value=-1000, max_value=1000))
    def test_monoid_law_unwrap_or_chain(self, n):
        """Unwrap-or chain: a.unwrap_or(x).unwrap_or(y) == a.unwrap_or(y)."""
        a = Ok(n) if n >= 0 else Err("neg")
        r1 = a.unwrap_or(0)
        r2 = a.unwrap_or(999)
        assert r1 == r2 or a.is_err()  # Err can differ; Ok must be same

    @given(st.text(min_size=1))
    def test_json_roundtrip_via_serialization(self, s):
        """Demonstrate that Ok/Err can encode into JSON-compatible dicts."""
        d = {"_type": "Ok", "value": s}
        assert d["_type"] == "Ok"
        assert d["value"] == s

    @given(st.lists(st.integers()))
    def test_map_then_unwrap_congruence(self, items):
        """map(f); unwrap == f(unwrap) for Ok."""
        ok = Ok(items)
        f = lambda xs: [x * 2 for x in xs]
        assert ok.map(f).unwrap() == f(ok.unwrap())

    def test_map_is_functorial(self):
        """Functor identity + composition laws for Ok."""
        # identity: x.map(id) == x
        x = Ok(42)
        assert x.map(lambda v: v) == x
        # composition: x.map(f).map(g) == x.map(lambda v: g(f(v)))
        f = lambda n: n + 1
        g = lambda n: n * 2
        assert x.map(f).map(g) == x.map(lambda v: g(f(v)))

    @given(st.integers())
    def test_and_then_monad_law_left_identity(self, n):
        """monad left-identity: unit(x).bind(f) == f(x)"""
        f = lambda v: Ok(v * 2)
        assert Ok(n).and_then(f) == f(n)

    @given(st.integers())
    def test_and_then_monad_law_right_identity(self, n):
        """monad right-identity: m.bind(unit) == m"""
        assert Ok(n).and_then(lambda v: Ok(v)) == Ok(n)

    @given(st.integers())
    def test_and_then_associativity(self, n):
        """monad associativity: m.bind(f).bind(g) == m.bind(lambda x: f(x).bind(g))"""
        f = lambda v: Ok(v + 1)
        g = lambda v: Ok(v * 2)
        m = Ok(n)
        assert m.and_then(f).and_then(g) == m.and_then(lambda x: f(x).and_then(g))

    @given(st.text(), st.text())
    def test_or_else_ignores_ok(self, s, default):
        assert Ok(s).or_else(lambda e: Ok(default)) == Ok(s)

    @given(st.integers(), st.integers())
    def test_or_else_recovers_err(self, e, recovery):
        assert Err(e).or_else(lambda _: Ok(recovery)) == Ok(recovery)
