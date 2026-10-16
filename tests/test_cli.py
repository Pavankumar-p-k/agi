"""Smoke tests for the app CLI — real output assertions, nothing stubbed."""

from __future__ import annotations

import subprocess
import sys

import pytest

from app import __version__
from app.cli import main


def test_hello_command():
    assert main(["hello"]) == 0


def test_version_command(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_hello_via_subprocess():
    result = subprocess.run(
        [sys.executable, "-m", "app", "hello"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "hello"


def test_unknown_command_fails():
    assert main(["nonsense"]) == 2


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["hello", "extra-arg"],
    ],
)
def test_usage_errors_exit_nonzero(argv):
    # main() converts argparse usage errors into a nonzero return code.
    assert main(argv) == 2
