"""Safe provider configuration diagnostic; never prints credential values."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis_provider import get_model, _env


def diagnostic() -> dict[str, object]:
    model = get_model("reasoning")
    provider = model.split("/", 1)[0]
    key_name = {
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }.get(provider)
    return {
        "reasoning_model": model,
        "provider": provider,
        "credential_variable": key_name,
        "credential_present": bool(_env(key_name)) if key_name else None,
        "configuration_file_order": [".env", ".env.local"],
    }


if __name__ == "__main__":
    print(diagnostic())
