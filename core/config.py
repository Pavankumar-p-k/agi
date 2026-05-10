# core/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8000") or 8000)

ALLOWED_ORIGINS_RAW = _env("ALLOWED_ORIGINS", "*") or "*"
if ALLOWED_ORIGINS_RAW.strip() == "*":
    ALLOWED_ORIGINS = ["*"]
else:
    ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",") if o.strip()]

SECRET_KEY = _env("SECRET_KEY", "dev-secret-change-me")
DEV_MODE = (_env("DEV_MODE", "true") or "true").lower() in {"1", "true", "yes", "on"}

DATABASE_URL = _env(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{(BASE_DIR / 'data' / 'jarvis.db').as_posix()}",
)

FIREBASE_CREDENTIALS = _env(
    "FIREBASE_CREDENTIALS",
    str(BASE_DIR / "firebase-credentials.json"),
)

OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "llama3")
VOSK_MODEL_PATH = _env(
    "VOSK_MODEL_PATH",
    str(BASE_DIR / "models" / "vosk-model-small-en-us-0.15"),
)

# ── HYBRID MODEL CONFIGURATION ──
CLAUDE_API_KEY = _env("CLAUDE_API_KEY")
COPILOT_API_KEY = _env("COPILOT_API_KEY")
GITHUB_TOKEN = _env("GITHUB_TOKEN")  # For Copilot API access
CODEX_CLI_PATH = _env("CODEX_CLI_PATH", str(BASE_DIR / "tools" / "codex-cli"))

# Model fallback settings
HYBRID_MAX_RETRIES = int(_env("HYBRID_MAX_RETRIES", "3") or 3)
HYBRID_TIMEOUT_SECONDS = int(_env("HYBRID_TIMEOUT_SECONDS", "30") or 30)

# Multi-instance Ollama ports (for different models)
OLLAMA_PORTS = {
    "tinyllama": 11434,
    "deepseek-r1:1.5b": 11435,
    "qwen2.5-coder:3b": 11436,
    "qwen3:4b": 11437,
    "qwen2.5:7b": 11438,
    "mistral:7b": 11439,
    "llama3.1:8b": 11440,
    "phi3:mini": 11441,
    "moondream": 11442,
}

FACES_DIR = Path(_env("FACES_DIR", str(BASE_DIR / "data" / "faces")) or str(BASE_DIR / "data" / "faces"))
FACE_RECOGNITION_MODEL = _env("FACE_RECOGNITION_MODEL", "VGG-Face")
FACE_DETECTION_BACKEND = _env("FACE_DETECTION_BACKEND", "opencv")
FACE_DISTANCE_THRESHOLD = float(_env("FACE_DISTANCE_THRESHOLD", "0.38") or 0.38)

MUSIC_DIR = _env("MUSIC_DIR", str(Path.home() / "Music"))
