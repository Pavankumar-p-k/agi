"""Acceptance test configuration.

This conftest overrides the root-level ``mock_external_calls`` autouse fixture
so that acceptance tests run against **real** subprocess, git, and network calls.

The global fixture (tests/conftest.py) stubs out subprocess.run which is
correct for unit tests, but prevents the real-repo harness from doing real
git operations and real test execution.  By re-declaring the same fixture name
at this directory level with autouse=True, pytest picks the most-local fixture
and the root version is not applied to tests in this package.
"""
import pytest


@pytest.fixture(autouse=True)
def mock_external_calls():
    """No-op override: acceptance tests use real subprocess and git."""
    yield
