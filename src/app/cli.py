"""Command-line entry point for the app package."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="app",
        description="Minimal project skeleton — does only what it claims.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("hello", help="print 'hello' and exit 0")

    version_parser = sub.add_parser("version", help="print the package version")
    version_parser.add_argument("-v", "--verbose", action="store_true")

    # argparse exits the process on usage errors; convert that into a return
    # code so main() behaves like a library function too.
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    if args.command == "hello":
        print("hello")
        return 0

    if args.command == "version":
        print(__version__ if not args.verbose else f"app {__version__}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
