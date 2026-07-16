#!/usr/bin/env python3
"""
Migrate secrets from .env to encrypted ~/.jarvis/api_keys.json
Usage: python scripts/migrate_secrets.py [--dry-run] [--execute]
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.secret_storage import encrypt

ENV_PATH = ROOT / ".env"
TARGET_DIR = Path.home() / ".jarvis"
TARGET_FILE = TARGET_DIR / "api_keys.json"
OAUTH_FILE = TARGET_DIR / "oauth_tokens.json"

SECRET_KEYS = {
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEY",
    "DEEPSEEK_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "TOGETHER_API_KEY",
    "PERPLEXITY_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "META_WHATSAPP_TOKEN",
    "META_WHATSAPP_PHONE_ID",
    "META_VERIFY_TOKEN",
    "NEWS_API_KEY",
    "OPENWEATHER_API_KEY",
    "ALPHA_VANTAGE_KEY",
    "PEXELS_API_KEY",
    "NVIDIA_API_KEY",
    "GITHUB_TOKEN",
    "COMPOSIO_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "EMAIL_PASS",
    "SMTP_HOST",
    "SMTP_PORT",
    "TAVILY_API_KEY",
    "SECRET_KEY",
    "PUSHOVER_USER",
    "PUSHOVER_TOKEN",
    "NTFY_TOPIC",
    "IMAP_PASSWORD",
    "MATRIX_PASSWORD",
    "IRC_PASSWORD",
}


def parse_env(path: Path) -> dict:
    """Parse .env file, preserving comments and formatting."""
    result = {}
    if not path.exists():
        return result
    content = path.read_text(encoding="utf-8")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            result[key] = value
    return result


def load_existing_keys(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="Migrate secrets from .env to encrypted storage")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Print what would be done (default)")
    parser.add_argument("--execute", action="store_true", help="Actually perform the migration")
    parser.add_argument("--decrypt-test", action="store_true", help="Test decryption after migration")
    args = parser.parse_args()

    if args.execute:
        args.dry_run = False

    env_data = parse_env(ENV_PATH)
    existing = load_existing_keys(TARGET_FILE)
    existing_oauth = load_existing_keys(OAUTH_FILE)

    to_migrate = {}
    for key in SECRET_KEYS:
        if key in env_data and env_data[key] and not env_data[key].startswith("#"):
            if key not in existing:
                to_migrate[key] = env_data[key]
            else:
                print(f"  SKIP {key}: already in encrypted store")

    if not to_migrate:
        print("No new secrets to migrate.")
        return 0

    print(f"\n{'DRY RUN' if args.dry_run else 'EXECUTING'}: Would migrate {len(to_migrate)} secrets:")
    for key in sorted(to_migrate.keys()):
        val = to_migrate[key]
        masked = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
        print(f"  {key}={masked}")

    if args.dry_run:
        print("\nRun with --execute to perform migration.")
        return 0

    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    for key, value in to_migrate.items():
        try:
            encrypted = encrypt(value)
            existing[key] = encrypted
            print(f"  Encrypted: {key}")
        except Exception as e:
            print(f"  ERROR encrypting {key}: {e}")
            return 1

    TARGET_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"\nWritten to {TARGET_FILE}")

    if args.decrypt_test:
        print("\nTesting decryption...")
        from core.secret_storage import decrypt
        for key in to_migrate.keys():
            try:
                decrypted = decrypt(existing[key])
                assert decrypted == to_migrate[key], f"Mismatch for {key}"
                print(f"  OK: {key}")
            except Exception as e:
                print(f"  FAIL: {key} - {e}")
                return 1
        print("All decryption tests passed.")

    print("\nNext steps:")
    print("  1. Verify app starts with encrypted keys")
    print("  2. Remove migrated keys from .env")
    print("  3. Add .app_key to .gitignore if not present")

    return 0


if __name__ == "__main__":
    sys.exit(main())