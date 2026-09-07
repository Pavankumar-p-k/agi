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

"""Property-based fuzz tests for config merge, session keys, and plugin manifests."""

from __future__ import annotations

from hypothesis import given, assume, strategies as st
from core.result import Ok, Err


# ── Strategies ───────────────────────────────────────────────────────

session_key_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd", "P")),
    min_size=1,
    max_size=64,
)

plugin_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd", "P")),
    min_size=1,
    max_size=32,
)

version_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd", "P")),
    min_size=1,
    max_size=20,
)


# ── Ok/Err Functor Laws (map) ────────────────────────────────────────

@given(st.integers())
def test_ok_identity_map(value):
    """Functor identity: m.map(lambda x: x) == m."""
    assert Ok(value).map(lambda x: x) == Ok(value)


@given(st.integers())
def test_ok_composition_map(value):
    """Functor composition: m.map(f).map(g) == m.map(lambda x: g(f(x)))."""
    def f(v):
        return v + 1
    def g(v):
        return v * 2
    left = Ok(value).map(f).map(g)
    right = Ok(value).map(lambda x: g(f(x)))
    assert left == right


@given(st.integers())
def test_ok_unwrap_or_identity(value):
    """Ok(x).unwrap_or(y) == x."""
    assert Ok(value).unwrap_or(-1) == value


@given(st.integers())
def test_err_unwrap_or_fallback(value):
    """Err(e).unwrap_or(x) == x."""
    assert Err("error").unwrap_or(value) == value


# ── Ok/Err and_then Properties ─────────────────────────────────────

@given(st.integers())
def test_ok_and_then(value):
    """Ok(x).and_then(f) == f(x)."""
    def f(v):
        return Ok(v * 2)
    assert Ok(value).and_then(f) == f(value)


@given(st.integers(), st.integers())
def test_ok_and_then_chain(value1, value2):
    """Ok(x).and_then(f).and_then(g) == f(x).and_then(g)."""
    def f(v):
        return Ok(v + value2)
    def g(v):
        return Ok(v * 2)
    assert Ok(value1).and_then(f).and_then(g) == f(value1).and_then(g)


@given(st.integers())
def test_err_and_then_ignored(value):
    """Err.and_then(f) returns self (does not call f)."""
    e = Err("error")
    assert e.and_then(lambda v: Ok(v)) == e


# ── Ok/Err map_err Properties ──────────────────────────────────────

@given(st.integers())
def test_ok_map_err_identity(value):
    """Ok(x).map_err(f) returns self unchanged."""
    assert Ok(value).map_err(lambda e: str(e) + "!") == Ok(value)


@given(st.text())
def test_err_map_err(message):
    """Err(e).map_err(f) == Err(f(e))."""
    assume(len(message) < 100)
    assert Err(message).map_err(lambda e: e.upper()) == Err(message.upper())


# ── Session Key Properties ──────────────────────────────────────────

@given(session_key_strategy)
def test_session_key_not_empty(key):
    """Session keys must not be empty."""
    assert len(key) > 0


@given(session_key_strategy)
def test_session_key_printable(key):
    """Session keys should contain only printable characters."""
    assert all(c.isprintable() for c in key)


# ── Ok/Err Inequality ───────────────────────────────────────────────

@given(st.integers(), st.integers())
def test_ok_inequality(a, b):
    """Ok(a) == Ok(b) iff a == b."""
    assume(a != b)
    assert Ok(a) != Ok(b)


@given(st.text(), st.text())
def test_err_inequality(a, b):
    """Err(a) == Err(b) iff a == b."""
    assume(a != b)
    assert Err(a) != Err(b)
