"""Run a dependency-light HTTP smoke test against a running JARVIS instance."""
from __future__ import annotations

import argparse
import json
import urllib.request


def check(url: str, timeout: float) -> None:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read())
        if response.status != 200 or payload.get("status") not in {"ok", "healthy"}:
            raise RuntimeError(f"unexpected health response: HTTP {response.status} {payload!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    check(args.base_url.rstrip("/") + "/health", args.timeout)
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
