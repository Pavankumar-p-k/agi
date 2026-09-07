"""Validate the minimum safe environment for a production deployment."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

PLACEHOLDER_SECRETS = {
    "",
    "generate-a-random-string-here",
    "change-me",
    "changeme",
}


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def validate_environment(values: dict[str, str] | None = None) -> list[str]:
    env = dict(os.environ if values is None else values)
    errors: list[str] = []
    if env.get("JARVIS_ENV", "").lower() != "production":
        errors.append("JARVIS_ENV must be set to production")
    secret = env.get("JARVIS_SECRET_KEY") or env.get("SECRET_KEY", "")
    if (
        secret.lower() in PLACEHOLDER_SECRETS
        or secret.lower().startswith(("replace-with", "your-", "example-"))
        or len(secret) < 32
    ):
        errors.append("JARVIS_SECRET_KEY must be a non-placeholder value of at least 32 characters")
    if env.get("HOST", "0.0.0.0") not in {"0.0.0.0", "::"}:
        errors.append("HOST must bind to 0.0.0.0 or :: in production")
    if "*" in env.get("ALLOWED_ORIGINS", ""):
        errors.append("ALLOWED_ORIGINS must not contain '*' in production")
    if not (env.get("JARVIS_DB__URL") or env.get("DATABASE_URL")):
        errors.append("JARVIS_DB__URL (or DATABASE_URL) must be configured")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="dotenv file to validate")
    args = parser.parse_args()
    values = load_env_file(args.env_file) if args.env_file else None
    errors = validate_environment(values)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Production environment validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
