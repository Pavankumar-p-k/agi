# Self-Hosting JARVIS

## Requirements

- Python 3.11+
- Ollama (for local LLMs) or API keys for cloud providers
- 8GB+ RAM (16GB recommended for local models)

## Quick Start (Docker)

```bash
git clone https://github.com/your-username/jarvis
cd jarvis
cp .env.example .env
# Edit .env with your API keys
docker compose up -d
```

## Manual Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python core/main.py
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CHAT_MODEL` | No | Chat model (default: ollama/llama3.1:8b) |
| `CODE_MODEL` | No | Code model (default: ollama/qwen2.5-coder:3b) |
| `META_VERIFY_TOKEN` | Yes (for WhatsApp) | WhatsApp webhook verification token |
| `OPENAI_API_KEY` | No | OpenAI API key for cloud fallback |
| `ANTHROPIC_API_KEY` | No | Anthropic API key for cloud fallback |

## Flutter Mobile App

```bash
cd apps/jarvis_app
flutter pub get
flutter run
```

## Production Deployment

- Use `docker compose -f docker-compose.yml up -d` for production.
- Set `JARVIS_DEV_MODE=false` in .env.
- Configure a reverse proxy (nginx/caddy) for SSL termination.
- Use the provided `docker-compose.yml` which includes ChromaDB and Ollama services.
