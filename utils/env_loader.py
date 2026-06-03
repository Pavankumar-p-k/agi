"""Load environment variables from .env, then .env.local for overrides."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_env_files():
    for env_file in [ROOT / ".env", ROOT / ".env.local"]:
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if value and not os.environ.get(key):
                        os.environ.setdefault(key, value)

load_env_files()
